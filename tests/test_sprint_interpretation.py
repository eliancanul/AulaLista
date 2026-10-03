"""S06 contract checks with authored PDFs and provider doubles, not provider results."""
import copy
import hashlib
import io
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from curriculum.interpretation_schema import (
    FIELD_QUESTIONS, INSUFFICIENT_SOURCE, InterpretationSchemaError, validate_interpretation,
    interpretation_json_schema, interpretation_validation_errors,
)
from curriculum.interpretation_service import dossier_to_interpretation, interpret_source
from curriculum.source_interpreter import (
    ImportDossier, InterpretedField, SourceReference, SourcePdfReadError,
    InterpretationCancelledError, InterpretationTimeoutError,
)
from test_t15_curriculum_import import make_minimal_pdf


@pytest.fixture
def pdf():
    return make_minimal_pdf([
        'Proyecto: "Guardianes"\nPropósito: Reconocer plantas locales.\n'
        'Campo: Lenguajes\nGrado: 3ro\nSesión 1\n'
        'Inicio: Observar una planta.\nDesarrollo: Dibujar la planta.\n'
        'Cierre: Compartir dibujos.\nMateriales: Papel y lápiz.\nEvaluación: Revisar dibujos.'
    ])


def fields(payload):
    return {item["key"]: item for item in payload["fields"]}


def test_real_pdf_to_json_keeps_sources_and_human_review(pdf):
    result = interpret_source(io.BytesIO(pdf), document_id="doc-1")
    assert json.loads(json.dumps(result)) == result
    assert result["document_id"] == "doc-1"
    assert result["source_segments"][0]["page"] == 1
    assert fields(result)["proposito"]["value"] == "Reconocer plantas locales."
    assert fields(result)["proposito"]["status"] == "extracted"
    assert fields(result)["proposito"]["evidence_ids"] == [result["source_segments"][1]["id"]]
    assert fields(result)["nivel_educativo"]["status"] == "unknown"
    assert fields(result)["nivel_educativo"]["value"] is None
    assert FIELD_QUESTIONS["nivel_educativo"] in result["missing_questions"]
    assert result["draft"]["objective"] == "Reconocer plantas locales."
    assert result["draft"]["steps"]
    assert result["draft"]["approval_status"] == "pending"
    assert result["draft"]["revision"] == 1
    assert result["diagnostics"]["model_winner"] is None
    assert result["diagnostics"]["attempts"] == 0


def test_synthetic_five_page_pdf_has_pending_traceable_draft_without_invented_steps():
    content = make_minimal_pdf([
        'Proyecto: El jardín\nPropósito: Observar las plantas.\nGrado: 3ro',
        'Materiales: Papel', 'Nota informativa: Las hojas tienen formas diferentes.',
        'Texto sintético para contrastar las fuentes.', 'Recordatorio: Revisar con una persona.',
    ])
    result = interpret_source(content)
    assert result["document_id"] == hashlib.sha256(content).hexdigest()
    assert sorted({s["page"] for s in result["source_segments"]}) == [1, 2, 3, 4, 5]
    assert fields(result)["proyecto"]["value"] == "El jardín"
    assert fields(result)["nivel_educativo"]["value"] is None
    assert result["draft"]["steps"] == []
    assert result["draft"]["status"] == INSUFFICIENT_SOURCE
    assert fields(result)["inicio"]["status"] == "unknown"
    assert result["draft"]["approval_status"] == "pending"


@pytest.mark.parametrize("grade", ["1ro", "3ro", "1", "3", "Primero", "Tercero"])
def test_grade_never_implies_school_level(grade):
    result = interpret_source(make_minimal_pdf([f"Grado: {grade}\nProyecto: Semillas"]))
    assert fields(result)["nivel_educativo"]["value"] is None
    assert fields(result)["nivel_educativo"]["status"] == "unknown"
    assert fields(result)["grado"]["value"] == ("1" if grade.lower().startswith(("1", "prim")) else "3")


def test_explicit_school_level_is_extracted_but_a_prose_mention_is_not():
    result = interpret_source(make_minimal_pdf(["Nivel educativo: Primaria\nGrado: 1ro"]))
    assert fields(result)["nivel_educativo"]["value"] == "Primaria"
    assert fields(result)["nivel_educativo"]["status"] == "extracted"
    result = interpret_source(make_minimal_pdf(["Una escuela primaria aparece en el cuento.\nGrado: 1ro"]))
    assert fields(result)["nivel_educativo"]["status"] == "unknown"


@pytest.mark.parametrize("lines,key", [
    ("Grado: 1ro\nGrado: 3ro", "grado"),
    ("Grado: 1ro y 3ro", "grado"),
    ("Nivel educativo: Primaria\nNivel educativo: Secundaria", "nivel_educativo"),
])
def test_conflicting_school_metadata_never_selects_first_value(lines, key):
    result = interpret_source(make_minimal_pdf([lines]))
    assert fields(result)[key]["value"] is None
    assert fields(result)[key]["status"] == "unknown"


def test_blank_pdf_has_explicit_unknowns_and_no_invented_activity():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    stream = io.BytesIO()
    writer.write(stream)
    result = interpret_source(stream.getvalue())
    assert result["source_segments"] == []
    assert all(f["value"] is None and f["status"] == "unknown" for f in result["fields"])
    assert len(result["missing_questions"]) == len(FIELD_QUESTIONS)
    assert result["draft"]["status"] == INSUFFICIENT_SOURCE
    assert result["draft"]["steps"] == []
    assert result["draft"]["source_ids"] == []
    assert result["diagnostics"]["source_page_count"] == 1
    assert result["diagnostics"]["source_warnings"][0]["page"] == 1


def test_corrupt_pdf_fails_before_candidate_is_called():
    calls = []
    with pytest.raises(SourcePdfReadError):
        interpret_source(b"not a PDF", candidate_provider=lambda request: calls.append(request))
    assert calls == []


@pytest.mark.parametrize("change", [
    lambda p: p.update(document_id="other-document"),
    lambda p: p["source_segments"][0].update(text="Fuente falsa"),
    lambda p: p["source_segments"][0].update(page=True),
    lambda p: p["source_segments"].append(copy.deepcopy(p["source_segments"][0])),
    lambda p: p["fields"].append(copy.deepcopy(p["fields"][0])),
    lambda p: p["fields"].pop(),
    lambda p: fields(p)["proposito"].update(evidence_ids=["absent"]),
    lambda p: fields(p)["proposito"].update(evidence_ids=[]),
    lambda p: fields(p)["proposito"].update(value="Astronomía inventada"),
    lambda p: fields(p)["nivel_educativo"].update(value="Primaria"),
    lambda p: p.update(missing_questions=[]),
    lambda p: p["draft"].update(approval_status="approved"),
    lambda p: p["draft"].update(revision=True),
    lambda p: p["draft"].update(source_ids=["absent"]),
    lambda p: p["draft"].update(materials="papel"),
    lambda p: p["draft"].update(approved=True),
    lambda p: fields(p)["nivel_educativo"].pop("value"),
    lambda p: p.update(published=True),
    lambda p: p["diagnostics"].update(model_winner="fixture-provider"),
    lambda p: p["diagnostics"].update(source_page_count=True),
])
def test_rejects_invalid_or_fabricated_contract(pdf, change):
    baseline = interpret_source(pdf)
    candidate = copy.deepcopy(baseline)
    change(candidate)
    with pytest.raises(InterpretationSchemaError):
        validate_interpretation(candidate, expected_document_id=baseline["document_id"],
                                source_segments=baseline["source_segments"])


@pytest.mark.parametrize("evidence", [
    SourceReference("another-source", 1, excerpt="Semillas"),
    SourceReference("sha", 2, excerpt="Semillas"),
    SourceReference("sha", 1, excerpt="Inventado"),
    SourceReference("sha", True, excerpt="Semillas"),
    "malformed",
])
def test_projection_rejects_wrong_source_page_quote_or_malformed_evidence(evidence):
    dossier = ImportDossier(source_sha256="sha", source_name="test.pdf", page_count=1,
                           general_fields={"proyecto": InterpretedField("proyecto", "Semillas", evidence=[evidence])})
    before = copy.deepcopy(dossier)
    result = dossier_to_interpretation(dossier, ["Proyecto: Semillas"])
    assert fields(result)["proyecto"]["status"] == "unknown"
    assert fields(result)["proyecto"]["value"] is None
    assert dossier == before


def test_suggestion_is_not_promoted_and_conflict_has_no_winner():
    reference = SourceReference("sha", 1, excerpt="Semillas")
    dossier = ImportDossier(source_sha256="sha", source_name="test.pdf", page_count=1, general_fields={
        "proyecto": InterpretedField("proyecto", "Estudiar semillas", origin="proposed", status="ambiguous", evidence=[reference]),
        "proposito": InterpretedField("proposito", "Semillas", status="conflicting", evidence=[reference]),
    })
    result = dossier_to_interpretation(dossier, ["Semillas"])
    assert fields(result)["proyecto"]["status"] == "suggested"
    assert fields(result)["proposito"]["status"] == "unknown"
    assert result["draft"]["status"] == INSUFFICIENT_SOURCE


def test_scalar_value_cannot_be_stitched_across_pages():
    dossier = ImportDossier(source_sha256="sha", source_name="test.pdf", page_count=2, general_fields={
        "proposito": InterpretedField("proposito", "Observar plantas", evidence=[
            SourceReference("sha", 1, excerpt="Observar"), SourceReference("sha", 2, excerpt="plantas")])})
    result = dossier_to_interpretation(dossier, ["Observar", "plantas"])
    assert fields(result)["proposito"]["status"] == "unknown"


def test_existing_mechanical_block_is_not_laundered_into_a_fact():
    dossier = ImportDossier(source_sha256="sha", source_name="test.pdf", page_count=1,
                           general_fields={"proyecto": InterpretedField("proyecto", "Semillas", evidence=[
                               SourceReference("sha", 1, excerpt="Semillas")])},
                           verification_report={"items": [{"status": "blocked", "path": "general_fields/proyecto/evidence/0"}]})
    result = dossier_to_interpretation(dossier, ["Semillas"])
    assert fields(result)["proyecto"]["status"] == "unknown"


def test_evaluator_callback_returns_safe_errors_and_schema_is_detached(pdf):
    result = interpret_source(pdf)
    validate = lambda value: interpretation_validation_errors(
        value, expected_document_id=result["document_id"], source_segments=result["source_segments"])
    assert validate(result) == []
    invalid = copy.deepcopy(result)
    invalid["draft"]["approval_status"] = "approved"
    assert validate(invalid) == ["interpretation_contract_invalid"]
    schema = interpretation_json_schema()
    json.dumps(schema, allow_nan=False)
    schema["properties"]["draft"]["properties"]["approval_status"]["const"] = "approved"
    assert interpretation_json_schema()["properties"]["draft"]["properties"]["approval_status"]["const"] == "pending"


def test_invalid_provider_retries_then_returns_unchanged_source_result(pdf):
    baseline = interpret_source(pdf)
    requests = []

    def provider(request):
        requests.append(request)
        request["interpretation"]["source_segments"][0]["text"] = "alterada"
        return request["interpretation"]

    result = interpret_source(pdf, candidate_provider=provider, max_attempts=2)
    assert [r["attempt"] for r in requests] == [1, 2]
    assert requests[0]["errors"] == []
    assert len(requests[1]["errors"]) == 1
    assert result["fields"] == baseline["fields"]
    assert result["source_segments"] == baseline["source_segments"]
    assert result["draft"] == baseline["draft"]
    assert result["diagnostics"]["provider_status"] == "fallback"
    assert result["diagnostics"]["attempts"] == 2


def test_provider_can_propose_supported_addition_but_never_becomes_model_winner(pdf):
    responses = []

    def provider(request):
        result = request["interpretation"]
        item = fields(result)["contenidos"]
        item.update(value="Reconocer plantas locales.", status="extracted",
                    evidence_ids=fields(result)["proposito"]["evidence_ids"])
        result["missing_questions"].remove(FIELD_QUESTIONS["contenidos"])
        responses.append(copy.deepcopy(result))
        return result

    result = interpret_source(pdf, candidate_provider=provider)
    assert fields(result)["contenidos"]["status"] == "suggested"
    assert result["diagnostics"]["provider_status"] == "proposal_validated"
    assert result["diagnostics"]["attempts"] == 1
    assert result["diagnostics"]["model_winner"] is None
    assert fields(responses[0])["contenidos"]["status"] == "extracted"


def test_provider_does_not_override_known_fact(pdf):
    def provider(request):
        response = request["interpretation"]
        fields(response)["proposito"].update(value="Compartir dibujos.", status="suggested")
        return response
    result = interpret_source(pdf, candidate_provider=provider, max_attempts=1)
    assert fields(result)["proposito"]["value"] == "Reconocer plantas locales."
    assert result["diagnostics"]["provider_status"] == "fallback"


def test_transient_provider_error_recovers_without_exposing_exception(pdf):
    calls = []

    def provider(request):
        calls.append(request)
        if len(calls) == 1:
            raise OSError("private-token-secret")
        return request["interpretation"]

    result = interpret_source(pdf, candidate_provider=provider)
    assert result["diagnostics"]["attempts"] == 2
    assert result["diagnostics"]["provider_status"] == "proposal_validated"
    assert "private-token-secret" not in json.dumps(result)
    assert "private-token-secret" not in json.dumps(calls)


def test_cancellation_during_provider_is_not_retried(pdf):
    cancelled = False
    calls = []

    def provider(request):
        nonlocal cancelled
        calls.append(request)
        cancelled = True
        return request["interpretation"]

    with pytest.raises(InterpretationCancelledError):
        interpret_source(pdf, candidate_provider=provider, is_cancelled=lambda: cancelled)
    assert len(calls) == 1


@pytest.mark.parametrize("fails", [False, True])
def test_expired_provider_result_is_never_accepted(pdf, monkeypatch, fails):
    from curriculum import interpretation_service as service
    clock = [0.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    calls = []

    def provider(request):
        calls.append(request)
        clock[0] = 31.0
        if fails:
            raise OSError("unavailable")
        return request["interpretation"]

    with pytest.raises(InterpretationTimeoutError):
        interpret_source(pdf, candidate_provider=provider, timeout_seconds=30, max_attempts=1)
    assert len(calls) == 1


@pytest.mark.parametrize("kwargs", [
    {"max_attempts": 0}, {"max_attempts": 4}, {"max_attempts": True},
    {"timeout_seconds": 0}, {"timeout_seconds": float("nan")},
    {"timeout_seconds": float("inf")}, {"timeout_seconds": True}, {"document_id": ""},
])
def test_invalid_resource_policy_is_rejected_before_pdf_parse(kwargs):
    with pytest.raises(ValueError):
        interpret_source(b"not PDF", **kwargs)
