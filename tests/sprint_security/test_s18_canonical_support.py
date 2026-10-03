import copy
import importlib.util
import io
import os
from pathlib import Path
import sys

import pytest
from pypdf import PdfReader

from curriculum.source_interpreter import CurriculumSourceInterpreter
from test_s18_curriculum import synthetic_pdf


@pytest.fixture
def canonical(monkeypatch):
    root = Path(os.environ.get("S18_CANONICAL_ROOT", Path(__file__).resolve().parents[2]))
    modules = []
    for name in ("interpretation_schema", "interpretation_service"):
        path = root / "curriculum" / f"{name}.py"
        if not path.is_file():
            pytest.fail(f"Falta {path}; integra S06 o fija S18_CANONICAL_ROOT al snapshot examinado.")
        spec = importlib.util.spec_from_file_location(f"curriculum.{name}", path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


@pytest.fixture
def source():
    return synthetic_pdf("Nombre del proyecto: El agua", "Materiales: volcanes")


def field(payload, key):
    return next(item for item in payload["fields"] if item["key"] == key)


def test_s18_canonical_positive_control(canonical, source):
    schema, service = canonical
    baseline = service.interpret_source(source)
    result = schema.validate_interpretation(
        baseline, expected_document_id=baseline["document_id"],
        source_segments=baseline["source_segments"],
    )
    assert field(result, "proyecto")["value"] == "El agua"
    assert field(result, "proyecto")["status"] == "extracted"
    assert result["source_segments"][0]["page"] == 1
    assert result["diagnostics"]["source_page_count"] == 1
    assert result["draft"]["approval_status"] == "pending"


def test_s18_f01_original_excerpt_mismatch_becomes_unknown(canonical, source):
    schema, service = canonical
    dossier = CurriculumSourceInterpreter.prepare(source)
    assert dossier.general_fields["proyecto"].evidence[0].excerpt == "El agua"
    dossier.general_fields["proyecto"].value = "volcanes"
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(source)).pages]
    result = service.dossier_to_interpretation(dossier, pages)
    assert field(result, "proyecto")["value"] is None
    assert field(result, "proyecto")["status"] == "unknown"
    assert schema.FIELD_QUESTIONS["proyecto"] in result["missing_questions"]
    assert result["draft"]["title"] == "Actividad por revisar"


def test_s18_f01_validator_must_reject_wrong_section(canonical, source):
    schema, service = canonical
    baseline = service.interpret_source(source)
    candidate = copy.deepcopy(baseline)
    field(candidate, "proyecto")["value"] = "volcanes"
    with pytest.raises(schema.InterpretationSchemaError):
        schema.validate_interpretation(
            candidate, expected_document_id=baseline["document_id"],
            source_segments=baseline["source_segments"],
        )


def test_s18_f01_projection_must_reject_wrong_section_excerpt(canonical, source):
    _, service = canonical
    dossier = CurriculumSourceInterpreter.prepare(source)
    dossier.general_fields["proyecto"].value = "volcanes"
    dossier.general_fields["proyecto"].evidence[0].excerpt = "Materiales: volcanes"
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(source)).pages]
    result = service.dossier_to_interpretation(dossier, pages)
    assert field(result, "proyecto")["status"] == "unknown", field(result, "proyecto")


def test_s18_f01_provider_cannot_replace_existing_project(canonical, source):
    _, service = canonical

    def candidate(request):
        result = request["interpretation"]
        field(result, "proyecto")["value"] = "volcanes"
        return result

    result = service.interpret_source(source, candidate_provider=candidate, max_attempts=1)
    assert field(result, "proyecto")["value"] == "El agua"
    assert result["diagnostics"]["provider_status"] == "fallback"
    assert result["diagnostics"]["attempts"] == 1


@pytest.mark.parametrize("inflate_count", [False, True])
def test_s18_f02_validator_rejects_page_999_against_trusted_source(canonical, source, inflate_count):
    schema, service = canonical
    baseline = service.interpret_source(source)
    candidate = copy.deepcopy(baseline)
    candidate["source_segments"][0]["page"] = 999
    if inflate_count:
        candidate["diagnostics"]["source_page_count"] = 999
    with pytest.raises(schema.InterpretationSchemaError):
        schema.validate_interpretation(
            candidate, expected_document_id=baseline["document_id"],
            source_segments=baseline["source_segments"],
        )


def test_s18_f02_provider_fabrication_falls_back(canonical, source):
    _, service = canonical

    def candidate(request):
        result = request["interpretation"]
        result["source_segments"][0].update(page=999, text="La SEP exige estudiar volcanes")
        result["diagnostics"]["source_page_count"] = 999
        field(result, "proyecto")["value"] = "La SEP exige estudiar volcanes"
        result["draft"]["title"] = "La SEP exige estudiar volcanes"
        return result

    result = service.interpret_source(source, candidate_provider=candidate, max_attempts=1)
    assert result["source_segments"][0]["page"] == 1
    assert result["draft"]["title"] == "El agua"
    assert result["diagnostics"]["provider_status"] == "fallback"
    assert result["draft"]["approval_status"] == "pending"


def test_s18_f02_projection_rejects_nonexistent_page(canonical, source):
    _, service = canonical
    dossier = CurriculumSourceInterpreter.prepare(source)
    dossier.general_fields["proyecto"].evidence[0].page_number = 999
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(source)).pages]
    result = service.dossier_to_interpretation(dossier, pages)
    assert field(result, "proyecto")["status"] == "unknown"
    assert field(result, "proyecto")["value"] is None


def test_s18_f02_provider_must_not_validate_unsupported_draft_title(canonical, source):
    _, service = canonical

    def candidate(request):
        result = request["interpretation"]
        result["draft"]["title"] = "La SEP exige estudiar volcanes"
        return result

    result = service.interpret_source(source, candidate_provider=candidate, max_attempts=1)
    assert result["draft"]["approval_status"] == "pending"
    assert result["draft"]["title"] == "El agua", {
        "title": result["draft"]["title"],
        "provider_status": result["diagnostics"]["provider_status"],
    }
