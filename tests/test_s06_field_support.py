"""S06 structural support regressions; provider callbacks are local test doubles."""
import copy
import io

import pytest
from pypdf import PdfReader

from curriculum.document_extraction import extract_document
from curriculum.interpretation_schema import (
    FIELD_QUESTIONS, InterpretationSchemaError, validate_interpretation,
)
from curriculum.interpretation_service import dossier_to_interpretation, interpret_source
from curriculum.source_interpreter import CurriculumSourceInterpreter
from test_t15_curriculum_import import make_minimal_pdf


def field(payload, key="proyecto"):
    return next(item for item in payload["fields"] if item["key"] == key)


def project_pdf():
    return make_minimal_pdf(["Nombre del proyecto: El agua\nMateriales: volcanes"])


def projection(content, version):
    dossier = CurriculumSourceInterpreter.prepare(content)
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(content)).pages]
    kwargs = {"extraction": extract_document(content)} if version == 2 else {}
    return dossier, pages, kwargs


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("refs", ["original", "all", "materials"])
def test_value_from_materials_never_becomes_extracted_project(version, refs):
    dossier, pages, kwargs = projection(project_pdf(), version)
    baseline = dossier_to_interpretation(dossier, pages, **kwargs)
    candidate = copy.deepcopy(baseline)
    field(candidate)["value"] = "volcanes"
    candidate["draft"]["title"] = "volcanes"
    if refs != "original":
        field(candidate)["evidence_ids"] = [
            s["id"] for s in candidate["source_segments"]
            if refs == "all" or "Materiales" in s["text"]
        ]
    with pytest.raises(InterpretationSchemaError, match="evidencia|nombre del proyecto"):
        validate_interpretation(candidate, expected_document_id=baseline["document_id"],
                                source_segments=baseline["source_segments"])


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("excerpt", ["El agua", "Materiales: volcanes"])
def test_changed_dossier_value_and_quote_abstain_without_mutating_dossier(version, excerpt):
    dossier, pages, kwargs = projection(project_pdf(), version)
    dossier.general_fields["proyecto"].value = "volcanes"
    dossier.general_fields["proyecto"].evidence[0].excerpt = excerpt
    before = copy.deepcopy(dossier)
    result = dossier_to_interpretation(dossier, pages, **kwargs)
    assert dossier == before
    assert field(result)["status"] == "unknown"
    assert field(result)["value"] is None
    assert field(result)["evidence_ids"] == []
    assert FIELD_QUESTIONS["proyecto"] in result["missing_questions"]
    assert result["draft"]["title"] == "Actividad por revisar"
    assert result["draft"]["approval_status"] == "pending"


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("title", ['El agua', '"El agua"'])
def test_supported_project_keeps_full_value_title_and_pending_review(version, title):
    content = make_minimal_pdf([f"Nombre del proyecto: {title}\nMateriales: volcanes"])
    dossier, pages, kwargs = projection(content, version)
    result = dossier_to_interpretation(dossier, pages, **kwargs)
    assert field(result)["status"] == "extracted"
    assert field(result)["value"] == title
    assert result["draft"]["title"] == title
    assert result["draft"]["approval_status"] == "pending"
    assert validate_interpretation(result, source_segments=result["source_segments"]) == result


@pytest.mark.parametrize("source", [project_pdf(), make_minimal_pdf(["Materiales: Papel"])])
def test_title_only_provider_claim_exhausts_bound_and_returns_original_draft(source):
    baseline = interpret_source(source)
    calls = []

    def provider(request):
        calls.append(request["attempt"])
        candidate = request["interpretation"]
        candidate["draft"]["title"] = "La SEP exige estudiar volcanes"
        return candidate

    result = interpret_source(source, candidate_provider=provider, max_attempts=2)
    assert calls == [1, 2]
    assert result["fields"] == baseline["fields"]
    assert result["draft"] == baseline["draft"]
    assert result["diagnostics"]["provider_status"] == "fallback"
    assert result["draft"]["approval_status"] == "pending"


def test_creative_title_is_explicit_suggestion_with_evidence_and_pending_review():
    source = make_minimal_pdf(["Materiales: Papel"])

    def provider(request):
        candidate = request["interpretation"]
        field(candidate).update(value="Exploramos el papel", status="suggested",
                                evidence_ids=[candidate["source_segments"][0]["id"]],
                                reason="Nombre propuesto para revisión docente.")
        candidate["missing_questions"].remove(FIELD_QUESTIONS["proyecto"])
        candidate["draft"]["title"] = "Propuesta de actividad: Exploramos el papel"
        candidate["draft"]["source_ids"] = field(candidate)["evidence_ids"]
        return candidate

    result = interpret_source(source, candidate_provider=provider)
    assert result["diagnostics"]["provider_status"] == "proposal_validated"
    assert field(result)["status"] == "suggested"
    assert result["draft"]["title"] == "Propuesta de actividad: Exploramos el papel"
    assert result["draft"]["approval_status"] == "pending"


def test_project_substring_is_not_the_complete_extracted_name():
    result = interpret_source(make_minimal_pdf(["Proyecto: El agua y las plantas\nMateriales: Papel"]))
    field(result)["value"] = "plantas"
    result["draft"]["title"] = "plantas"
    with pytest.raises(InterpretationSchemaError, match="nombre del proyecto"):
        validate_interpretation(result)
