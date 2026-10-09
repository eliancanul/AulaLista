"""Source interpreter integration with a stable, provisional JSON contract.

The default path is local and deterministic. An explicitly supplied candidate
provider may propose additions, with at most three attempts. There is no model
selection, publication, persistence, or mutation of existing teacher drafts.
"""
from __future__ import annotations

import copy
import math
import re
import time
from typing import Any, Callable

from curriculum.document_extraction import (
    DocumentExtractionError, ExtractedDocument, extract_document,
)

from curriculum.interpretation_schema import (
    FIELD_QUESTIONS, INSUFFICIENT_SOURCE, SCHEMA_VERSION,
    InterpretationSchemaError, evidence_texts, initial_title, literal_supported,
    OVERVIEW_ROLES, overview_supported, validate_interpretation,
)
from curriculum.source_interpreter import (
    CurriculumSourceInterpreter, ImportDossier, InterpretedField, SourceReference,
    InterpretationCancelledError, InterpretationTimeoutError, SourcePdfReadError,
)
from curriculum.verification import normalize_text_for_evidence_check as normalize

SESSION_KEYS = ("inicio", "desarrollo", "cierre", "materiales", "evaluacion")


def _unknown(key: str, reason: str = "No se encontró evidencia suficiente en la fuente.") -> dict:
    return {"key": key, "value": None, "status": "unknown", "evidence_ids": [], "reason": reason}


def _locate_excerpt(excerpt: str, page: int, segments: list[dict]) -> list[str]:
    """Locate one contiguous quotation in S02 text, without translating offsets."""
    parts = [segment for segment in segments if segment["page"] == page]
    normalized = [normalize(segment["text"]) for segment in parts]
    text = " ".join(normalized)
    needle = normalize(excerpt)
    start = text.find(needle) if needle else -1
    if start < 0 or text.find(needle, start + 1) >= 0:
        return []
    end = start + len(needle)
    offset = 0
    refs = []
    for segment, value in zip(parts, normalized):
        if offset < end and offset + len(value) > start:
            refs.append(segment["id"])
        offset += len(value) + 1
    return refs


def _school_metadata(pages: list[str], sha: str, segments: list[dict] | None = None) -> dict[str, dict]:
    """Only complete, explicitly labelled header lines can resolve school level.

    Multiple grade/level values stay unknown. These source facts never set the
    installation's institutional modality or a classroom assignment.
    """
    patterns = {
        "grado": r"Grado\s*:?\s+(.+)",
        "nivel_educativo": r"Nivel(?:\s+educativo)?\s*:\s*(.+)",
    }
    result = {}
    for key, pattern in patterns.items():
        matches = [(page, m.group(1).strip(), line.strip()) for page, text in enumerate(pages[:3], 1)
                   for line in text.splitlines() if (m := re.fullmatch(pattern, line.strip(), re.I))]
        if not matches:
            continue
        values = []
        for _, raw, _ in matches:
            value = normalize(raw)
            if key == "grado":
                ordinal = re.fullmatch(r"([1-6])(?:ro|do|to|er|o|a|º|°)?(?:\s+grado)?", value)
                names = {"primero": "1", "primer": "1", "segundo": "2", "tercero": "3",
                         "tercer": "3", "cuarto": "4", "quinto": "5", "sexto": "6"}
                value = ordinal.group(1) if ordinal else names.get(value.removesuffix(" grado"))
            elif not re.fullmatch(r"primaria|secundaria(?: general| tecnica)?|telesecundaria", value):
                value = None
            values.append(value)
        refs = []
        for page, _, line in matches:
            located = _locate_excerpt(line, page, segments) if segments is not None else [f"{sha}:p{page}"]
            if not located:
                values.append(None)
            refs.extend(located)
        if None in values or len(set(values)) != 1:
            result[key] = _unknown(key, "Hay datos escolares ambiguos o distintos; confirma cuál corresponde.")
        else:
            result[key] = {
                "key": key, "value": values[0] if key == "grado" else matches[0][1],
                "status": "extracted", "evidence_ids": list(dict.fromkeys(refs)),
                "reason": "Dato escolar explícito en el encabezado; pendiente de revisión docente.",
            }
    return result


def _project_field(key: str, field: InterpretedField | None, dossier: ImportDossier, pages: list[str], segments: list[dict] | None = None) -> dict:
    if field is None or not field.value or field.status in ("missing", "conflicting"):
        return _unknown(key, field.reason if field and field.reason else "No se encontró evidencia suficiente en la fuente.")
    if not isinstance(field.value, str) and not (
        isinstance(field.value, list) and all(isinstance(v, str) and v.strip() for v in field.value)
    ):
        return _unknown(key, "El valor requiere revisión de su estructura.")
    refs = []
    excerpts = []
    for evidence in field.evidence:
        if not isinstance(evidence, SourceReference) or evidence.document_sha256 != dossier.source_sha256:
            return _unknown(key, "La evidencia no corresponde al documento.")
        page = evidence.page_number
        if type(page) is not int or not 1 <= page <= len(pages):
            return _unknown(key, "La página de la evidencia no existe.")
        excerpt = normalize(evidence.excerpt)
        if not excerpt or excerpt not in normalize(pages[page - 1]):
            return _unknown(key, "No se pudo localizar la cita en la página indicada.")
        located = _locate_excerpt(evidence.excerpt, page, segments) if segments is not None else [f"{dossier.source_sha256}:p{page}"]
        if not located:
            return _unknown(key, "La cita no tiene una correspondencia continua y única en el texto por páginas; revisa el PDF original.")
        refs.extend(located)
        excerpts.append(evidence.excerpt)
    if not refs:
        return _unknown(key)
    status = "suggested"
    if field.origin == "extracted" and field.status == "supported":
        if not literal_supported(field.value, excerpts, key):
            return _unknown(key, "El valor no está respaldado por la cita; requiere revisión.")
        if key in OVERVIEW_ROLES:
            texts = evidence_texts(segments, refs) if segments is not None else [
                pages[e.page_number - 1] for e in field.evidence
            ]
            if not overview_supported(field.value, texts, key):
                return _unknown(key, "La fuente citada no respalda el valor en su sección curricular.")
        status = "extracted"
    if segments is not None and (status == "extracted" or key == "nivel_educativo"):
        if not literal_supported(field.value, evidence_texts(segments, refs), key):
            return _unknown(key, "El valor no está respaldado por los segmentos de la fuente.")
    return {"key": key, "value": copy.deepcopy(field.value), "status": status,
            "evidence_ids": list(dict.fromkeys(refs)), "reason": field.reason}


def _draft(fields: list[dict]) -> dict:
    by_key = {f["key"]: f for f in fields}
    used = []

    def take(key):
        field = by_key[key]
        if field["status"] == "unknown":
            return ""
        used.extend(field["evidence_ids"])
        return field["value"]

    take("proyecto")
    objective = take("proposito")
    steps = [take(key) for key in ("inicio", "desarrollo", "cierre")]
    steps = [v for value in steps for v in (value if isinstance(value, list) else [value]) if v]
    materials = take("materiales")
    assessment = take("evaluacion")
    return {
        "title": initial_title(by_key["proyecto"]),
        "objective": "\n".join(objective) if isinstance(objective, list) else objective,
        "materials": materials if isinstance(materials, list) else ([materials] if materials else []),
        "steps": steps,
        "assessment": "\n".join(assessment) if isinstance(assessment, list) else assessment,
        "source_ids": list(dict.fromkeys(used)), "revision": 1, "approval_status": "pending",
        "status": "needs_review" if objective and steps and used else INSUFFICIENT_SOURCE,
    }


def dossier_to_interpretation(dossier: ImportDossier, pages: list[str], *, document_id: str | None = None,
                              extraction: ExtractedDocument | None = None) -> dict:
    """Project a freshly extracted dossier; pages must belong to its source PDF.

    This is not a saved-dossier migration. Human review history stays in the
    existing dossier; it must not be replaced by this provisional projection.
    """
    if dossier.status != "active" or dossier.page_count != len(pages):
        raise InterpretationSchemaError("El documento cambió o sus páginas no coinciden.")
    segments = [{"id": f"{dossier.source_sha256}:p{i}", "text": text, "page": i}
                for i, text in enumerate(pages, 1) if text.strip()]
    if extraction is not None:
        if extraction.document_id != dossier.source_sha256 or [p.raw_text for p in extraction.pages] != pages:
            raise InterpretationSchemaError("La extracción no corresponde a la fuente del dossier.")
        segments = extraction.source_segments
    selected_id = dossier.selection.get("session_id")
    session = dossier.get_session(selected_id) if selected_id else None
    fields = []
    school_metadata = _school_metadata(pages, dossier.source_sha256, segments if extraction is not None else None)
    blocked_paths = [item.get("path", "") for item in (dossier.verification_report or {}).get("items", [])
                     if item.get("status") == "blocked"]
    for key in FIELD_QUESTIONS:
        source_fields = session.fields if key in SESSION_KEYS and session else dossier.general_fields
        path = f"sessions/{session.session_id}/fields/{key}" if key in SESSION_KEYS and session else f"general_fields/{key}"
        if any(p == path or p.startswith(path + "/") for p in blocked_paths):
            fields.append(_unknown(key, "La verificación de la fuente detectó un problema; revisa este campo."))
        else:
            item = school_metadata.get(key) or _project_field(key, source_fields.get(key), dossier, pages, segments if extraction is not None else None)
            if key in school_metadata and item["status"] == "extracted" and any(
                s["page"] in dossier.page_warnings and s["id"] in item["evidence_ids"] for s in segments
            ):
                item["status"] = "suggested"
            fields.append(item)
    warning_pages = set(dossier.page_warnings) | {i for i, text in enumerate(pages, 1) if not text.strip()}
    payload = {
        "schema_version": SCHEMA_VERSION if extraction is not None else 1, "document_id": document_id or dossier.source_sha256,
        "source_segments": segments, "fields": fields,
        "missing_questions": [FIELD_QUESTIONS[f["key"]] for f in fields if f["status"] == "unknown"],
        "draft": _draft(fields),
        "diagnostics": {"method": "local_source_interpreter", "provider_status": "not_requested",
                        "attempts": 0, "errors": [], "model_winner": None,
                        "source_page_count": len(pages),
                        "source_warnings": [{"page": p, "message": "Esta página tiene texto ausente o incierto; revisa el PDF original."}
                                            for p in sorted(warning_pages)]},
    }
    if extraction is not None:
        details = extraction.to_dict()
        details.pop("source_segments")
        # JSON round trips must preserve the canonical response exactly.
        for page in details["pages"]:
            page["warnings"] = list(page["warnings"])
        payload["diagnostics"]["source_extraction"] = details
        for page in extraction.pages:
            for message in page.warnings:
                payload["diagnostics"]["source_warnings"].append({"page": page.page, "message": message})
        warned = {p.page for p in extraction.pages if p.warnings}
        for field in fields:
            if field["status"] == "extracted" and any(
                s["page"] in warned and s["id"] in field["evidence_ids"] for s in segments
            ):
                field["status"] = "suggested"
        payload["draft"] = _draft(fields)
    return validate_interpretation(payload)


def _integrate_candidate(candidate: Any, baseline: dict) -> dict:
    candidate = validate_interpretation(candidate, expected_document_id=baseline["document_id"],
                                        source_segments=baseline["source_segments"])
    if candidate["schema_version"] != baseline["schema_version"] or candidate["diagnostics"] != baseline["diagnostics"]:
        raise InterpretationSchemaError("La propuesta modificó el contrato o el diagnóstico de la fuente.")
    proposed = {f["key"]: f for f in candidate["fields"]}
    result = copy.deepcopy(baseline)
    for field in result["fields"]:
        new = proposed[field["key"]]
        # Existing facts and ambiguity are not overwritten by a provider.
        if field["status"] != "unknown" or field["key"] in ("grado", "nivel_educativo"):
            if new != field:
                raise InterpretationSchemaError("La propuesta cambió un dato de la fuente o infirió grado o nivel.")
        elif new["status"] != "unknown":
            field.update(new)
            field["status"] = "suggested"
    result["missing_questions"] = [FIELD_QUESTIONS[f["key"]] for f in result["fields"] if f["status"] == "unknown"]
    result["draft"] = candidate["draft"]
    result["draft"]["title"] = initial_title(next(f for f in result["fields"] if f["key"] == "proyecto"))
    return validate_interpretation(result)


def interpret_source(
    source: Any, *, document_id: str | None = None, selection: dict | None = None,
    candidate_provider: Callable[[dict], dict] | None = None, max_attempts: int = 2,
    timeout_seconds: float = 30, is_cancelled: Callable[[], bool] | None = None,
) -> dict:
    """Interpret an actual PDF and optionally validate an explicit proposal.

    Provider receives a detached `interpretation`, `attempt`, `errors` and the
    remaining `timeout_seconds`. It MUST enforce its own transport timeout.
    Deadline/cancellation checks here are cooperative, not process termination.
    Invalid provider output or transport failure falls back to the source-only
    interpretation. A cancellation never retries and never returns a proposal.
    """
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError("Se permiten entre uno y tres intentos.")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("El tiempo máximo debe ser positivo y finito.")
    if document_id is not None and (not isinstance(document_id, str) or not document_id.strip()):
        raise ValueError("El identificador del documento no puede estar vacío.")
    deadline = time.monotonic() + timeout_seconds

    def check():
        if is_cancelled and is_cancelled():
            raise InterpretationCancelledError("La interpretación fue cancelada.")
        if time.monotonic() >= deadline:
            raise InterpretationTimeoutError("Se agotó el tiempo de interpretación.")

    check()
    try:
        content, _, filename = CurriculumSourceInterpreter.read_pdf_bytes_and_sha(source)
    except OSError as error:
        raise SourcePdfReadError("No se pudo abrir la fuente. Vuelve a cargar el PDF.") from error
    check()

    def extraction_checkpoint():
        check()
        return False

    try:
        extraction = extract_document(content, filename=filename, is_cancelled=extraction_checkpoint)
    except DocumentExtractionError as error:
        raise SourcePdfReadError(str(error)) from error
    check()
    dossier = CurriculumSourceInterpreter.prepare(content, selection=copy.deepcopy(selection),
                                                   timeout_seconds=deadline - time.monotonic(), is_cancelled=is_cancelled)
    check()
    baseline = dossier_to_interpretation(
        dossier, [page.raw_text for page in extraction.pages], document_id=document_id, extraction=extraction,
    )
    check()
    if candidate_provider is None:
        return baseline
    errors = []
    for attempt in range(1, max_attempts + 1):
        check()
        try:
            response = candidate_provider({"interpretation": copy.deepcopy(baseline), "attempt": attempt,
                                           "errors": list(errors), "timeout_seconds": deadline - time.monotonic()})
            check()
            result = _integrate_candidate(response, baseline)
        except (InterpretationCancelledError, InterpretationTimeoutError):
            raise
        except (InterpretationSchemaError, OSError, TimeoutError, ValueError, TypeError):
            check()
            # Provider exception messages may contain credentials or source data.
            errors.append("La propuesta no cumplió el contrato o el proveedor no respondió.")
            continue
        result["diagnostics"].update(provider_status="proposal_validated", attempts=attempt, errors=errors)
        return result
    baseline["diagnostics"].update(provider_status="fallback", attempts=max_attempts, errors=errors)
    return baseline
