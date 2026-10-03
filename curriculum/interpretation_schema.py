"""Versioned boundary for provisional, source-linked interpretations.

Mechanical evidence coverage is not pedagogical validation or human approval.
Only this initial-response contract is validated here; saved draft lifecycle and
teacher-authored revisions belong to the draft service.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Literal, NotRequired, TypedDict

from curriculum.verification import normalize_text_for_evidence_check as normalize

SCHEMA_VERSION = 2
INSUFFICIENT_SOURCE = "No hay suficiente fuente local"
FIELD_QUESTIONS = {
    "proyecto": "¿Cuál es el nombre del proyecto?",
    "campos_formativos": "¿Qué campos formativos corresponden?",
    "proposito": "¿Cuál es el propósito de la actividad?",
    "finalidad": "¿Cuál es la finalidad del proyecto?",
    "metodologia": "¿Qué metodología se utilizará?",
    "escenario_proyecto": "¿En qué escenario se realizará?",
    "grado": "¿A qué grado corresponde el material?",
    "nivel_educativo": "¿A qué nivel educativo corresponde el material?",
    "duracion_proyecto": "¿Cuánto tiempo se dedicará al proyecto?",
    "contenidos": "¿Qué contenidos curriculares se trabajarán?",
    "pda": "¿Qué procesos de desarrollo de aprendizaje se trabajarán?",
    "ejes_articuladores": "¿Qué ejes articuladores corresponden?",
    "inicio": "¿Cómo comenzará la actividad?",
    "desarrollo": "¿Qué harán durante la actividad?",
    "cierre": "¿Cómo cerrarán la actividad?",
    "materiales": "¿Qué materiales se necesitan?",
    "evaluacion": "¿Cómo se revisará el trabajo realizado?",
}


class SourceSegment(TypedDict):
    id: str
    text: str
    page: int
    kind: NotRequired[str]
    text_start: NotRequired[int]
    text_end: NotRequired[int]


class InterpretationField(TypedDict):
    key: str
    value: str | list[str] | None
    status: Literal["extracted", "suggested", "unknown"]
    evidence_ids: list[str]
    reason: str


class InitialDraft(TypedDict):
    title: str
    objective: str
    materials: list[str]
    steps: list[str]
    assessment: str
    source_ids: list[str]
    revision: int
    approval_status: Literal["pending"]
    status: str


def _object_schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def interpretation_json_schema() -> dict:
    """A fresh JSON Schema for provider adapters; runtime validation is required.

    JSON Schema cannot establish document identity, citation coverage, unique
    field keys, or human authority. Use validate_interpretation after generation.
    """
    text = {"type": "string", "minLength": 1}
    strings = {"type": "array", "items": text}
    references = {**strings, "uniqueItems": True}
    field = _object_schema({
        "key": {"type": "string", "enum": list(FIELD_QUESTIONS)},
        "value": {"anyOf": [text, {**strings, "minItems": 1}, {"type": "null"}]},
        "status": {"type": "string", "enum": ["extracted", "suggested", "unknown"]},
        "evidence_ids": references, "reason": {"type": "string"},
    })
    field["allOf"] = [{
        "if": {"properties": {"status": {"const": "unknown"}}},
        "then": {"properties": {"value": {"type": "null"}}},
        "else": {"properties": {"value": {"anyOf": [text, {**strings, "minItems": 1}]},
                                 "evidence_ids": {"minItems": 1}}},
    }]
    schema = _object_schema({
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "document_id": text,
        "source_segments": {"type": "array", "items": _object_schema({
            "id": text, "text": text, "page": {"type": "integer", "minimum": 1},
            "kind": {"enum": ["text", "heading_candidate", "table_row_candidate"]},
            "text_start": {"type": "integer", "minimum": 0},
            "text_end": {"type": "integer", "minimum": 1}})},
        "fields": {"type": "array", "minItems": len(FIELD_QUESTIONS), "maxItems": len(FIELD_QUESTIONS), "items": field},
        "missing_questions": strings,
        "draft": _object_schema({
            "title": {"type": "string"}, "objective": {"type": "string"},
            "materials": strings, "steps": strings, "assessment": {"type": "string"},
            "source_ids": references, "revision": {"type": "integer", "const": 1},
            "approval_status": {"type": "string", "const": "pending"},
            "status": {"type": "string", "enum": ["needs_review", INSUFFICIENT_SOURCE]},
        }),
        "diagnostics": _object_schema({
            "method": {"type": "string", "const": "local_source_interpreter"},
            "provider_status": {"type": "string", "enum": ["not_requested", "proposal_validated", "fallback"]},
            "attempts": {"type": "integer", "minimum": 0, "maximum": 3},
            "errors": strings, "model_winner": {"type": "null"},
            "source_page_count": {"type": "integer", "minimum": 1},
            "source_warnings": {"type": "array", "items": _object_schema({
                "page": {"type": "integer", "minimum": 1}, "message": text})},
        }),
    })
    extraction = _object_schema({
        "document_id": text, "status": {"enum": ["complete", "partial", "unreadable"]},
        "page_count": {"type": "integer", "minimum": 1},
        "requires_review": {"const": True}, "warnings": strings,
        "pages": {"type": "array", "minItems": 1, "items": _object_schema({
            "page": {"type": "integer", "minimum": 1},
            "text": {"type": "string"}, "raw_text": {"type": "string"},
            "status": {"enum": ["extracted", "empty", "failed"]},
            "method": {"enum": ["pypdf-layout", "pypdf-plain", "none"]}, "warnings": strings,
        })},
    })
    diagnostics = schema["properties"]["diagnostics"]
    diagnostics["properties"]["source_extraction"] = extraction
    diagnostics["required"].append("source_extraction")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return copy.deepcopy(schema)


class InterpretationSchemaError(ValueError):
    """A provisional response violates the source or review contract."""


def literal_supported(value: str | list[str], texts: list[str], key: str = "") -> bool:
    """Each value must occur wholly on a cited page, never across page seams."""
    values = value if isinstance(value, list) else [value]
    normalized = [normalize(text) for text in texts]
    for item in values:
        needle = normalize(item)
        if not needle:
            return False
        if key == "grado" and needle in "123456" and len(needle) == 1:
            words = {
                "1": "primer|primero|primera", "2": "segundo|segunda",
                "3": "tercer|tercero|tercera", "4": "cuarto|cuarta",
                "5": "quinto|quinta", "6": "sexto|sexta",
            }
            pattern = rf"(?<!\w)(?:{needle}(?:ro|do|to|er|o|a|º|°)?|{words[needle]})(?!\w)"
        else:
            pattern = rf"(?<!\w){re.escape(needle)}(?!\w)"
        if not any(re.search(pattern, text) for text in normalized):
            return False
    return bool(values)


def evidence_texts(segments: list[dict], refs: list[str]) -> list[str]:
    """Only consecutive cited lines on the same physical page may be joined."""
    texts = []
    previous = None
    for segment in segments:
        if segment["id"] not in refs:
            previous = None
            continue
        if previous is not None and "text_start" in segment and previous["page"] == segment["page"]:
            texts[-1] += "\n" + segment["text"]
        else:
            texts.append(segment["text"])
        previous = segment
    return texts


OVERVIEW_ROLES = frozenset({"proyecto", "proposito", "finalidad"})


def overview_supported(value: str | list[str], texts: list[str], key: str) -> bool:
    """Match the complete value within its explicit, unambiguous labelled role.

    This checks source structure, not semantic entailment. A literal occurrence
    in materials (or another overview role) cannot establish an objective.
    """
    from curriculum.overview_fields import iter_overview_spans

    values = value if isinstance(value, list) else [value]
    supported = {
        normalize(span.excerpt).strip('"«»“”')
        for text in texts for span in iter_overview_spans([text])
        if span.name == key and not span.ambiguous
    }
    return bool(values) and all(normalize(item).strip('"«»“”') in supported for item in values)


def project_supported(value: str | list[str], texts: list[str]) -> bool:
    return overview_supported(value, texts, "proyecto")


def initial_title(project: dict) -> str:
    """Initial titles inherit field provenance; teacher revisions live elsewhere."""
    if project["status"] == "unknown":
        return "Actividad por revisar"
    value = project["value"]
    title = "\n".join(value) if isinstance(value, list) else value
    return f"Propuesta de actividad: {title}" if project["status"] == "suggested" else title


def _validate_extraction(details: Any, segments: list[dict], count: int) -> None:
    from curriculum.source_segments import extracted_page_segments

    _require(isinstance(details, dict) and set(details) == {
        "document_id", "status", "page_count", "pages", "requires_review", "warnings",
    }, "Diagnóstico de extracción no válido.")
    _require(_text(details["document_id"]), "Falta la identidad de extracción.")
    _require(type(details["page_count"]) is int and details["page_count"] == count,
             "La cobertura de extracción no coincide.")
    _require(details["requires_review"] is True, "La extracción requiere revisión humana.")
    _require(isinstance(details["warnings"], list) and all(_text(w) for w in details["warnings"]),
             "Advertencias de extracción no válidas.")
    pages = details["pages"]
    _require(isinstance(pages, list) and len(pages) == count, "Faltan páginas físicas.")
    expected = []
    readable = 0
    for number, page in enumerate(pages, 1):
        _require(isinstance(page, dict) and set(page) == {
            "page", "text", "raw_text", "status", "method", "warnings",
        }, "Página extraída no válida.")
        _require(type(page["page"]) is int and page["page"] == number, "Orden de páginas no válido.")
        _require(isinstance(page["text"], str) and isinstance(page["raw_text"], str), "Texto de página no válido.")
        _require(page["status"] in ("extracted", "empty", "failed"), "Estado de página no válido.")
        _require(page["method"] in ("pypdf-layout", "pypdf-plain", "none"), "Método de página no válido.")
        _require(isinstance(page["warnings"], list) and all(_text(w) for w in page["warnings"]),
                 "Advertencias de página no válidas.")
        readable += page["status"] == "extracted"
        _require(bool(page["text"].strip()) == (page["status"] == "extracted"), "Estado y texto no coinciden.")
        if page["status"] != "extracted":
            _require(bool(page["warnings"]), "Una página sin texto requiere advertencia.")
        expected.extend(extracted_page_segments(page["text"], details["document_id"], number))
    status = "complete" if readable == count else "partial" if readable else "unreadable"
    _require(details["status"] == status, "Cobertura de extracción no válida.")
    _require(segments == expected, "Los segmentos no conservan IDs, offsets o texto de las páginas.")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InterpretationSchemaError(message)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _references(value: Any, segments: dict, label: str) -> None:
    _require(isinstance(value, list), f"{label}: se requiere una lista de fuentes.")
    _require(all(_text(item) for item in value), f"{label}: referencia no válida.")
    _require(len(value) == len(set(value)), f"{label}: referencias duplicadas.")
    _require(all(item in segments for item in value), f"{label}: la fuente no existe.")


def validate_interpretation(
    payload: Any, *, expected_document_id: str | None = None,
    source_segments: list[SourceSegment] | None = None,
) -> dict:
    """Validate and detach JSON-like data; supplied segments are trusted input.

    External provider responses must always pass the original document identity
    and source segments. Without them this function checks internal consistency,
    not whether a document or quotation is authentic.
    """
    _require(isinstance(payload, dict), "La interpretación debe ser un objeto.")
    _require(set(payload) == {"schema_version", "document_id", "source_segments", "fields",
                              "missing_questions", "draft", "diagnostics"},
             "La interpretación contiene propiedades faltantes o desconocidas.")
    _require(type(payload.get("schema_version")) is int and payload["schema_version"] in (1, SCHEMA_VERSION),
             "Versión del esquema no compatible.")
    _require(_text(payload.get("document_id")), "Falta el identificador del documento.")
    if expected_document_id is not None:
        _require(payload["document_id"] == expected_document_id, "El documento no coincide.")
    version = payload["schema_version"]
    raw_segments = payload.get("source_segments")
    _require(isinstance(raw_segments, list), "Faltan los segmentos de la fuente.")
    segments = {}
    for segment in raw_segments:
        _require(isinstance(segment, dict), "Segmento no válido.")
        shape = {"id", "text", "page"} if version == 1 else {"id", "text", "page", "kind", "text_start", "text_end"}
        _require(set(segment) == shape, "Propiedades de fuente no válidas.")
        _require(_text(segment.get("id")) and _text(segment.get("text")), "Segmento vacío.")
        _require(type(segment.get("page")) is int and segment["page"] > 0, "Página física no válida.")
        if version == SCHEMA_VERSION:
            _require(type(segment["text_start"]) is int and type(segment["text_end"]) is int
                     and 0 <= segment["text_start"] < segment["text_end"], "Offsets de fuente no válidos.")
            _require(segment["kind"] in ("text", "heading_candidate", "table_row_candidate"),
                     "Tipo de segmento no válido.")
        _require(segment["id"] not in segments, "Identificador de fuente duplicado.")
        segments[segment["id"]] = segment
    if source_segments is not None:
        _require(raw_segments == source_segments, "La respuesta modificó la fuente original.")
    fields = payload.get("fields")
    _require(isinstance(fields, list), "Faltan los campos curriculares.")
    seen = set()
    for item in fields:
        _require(isinstance(item, dict), "Campo curricular no válido.")
        _require(set(item) == {"key", "value", "status", "evidence_ids", "reason"},
                 "Propiedades de campo no válidas.")
        key = item.get("key")
        _require(isinstance(key, str) and key in FIELD_QUESTIONS and key not in seen,
                 "Campo curricular desconocido o duplicado.")
        seen.add(key)
        status, value = item.get("status"), item.get("value")
        _require(status in ("extracted", "suggested", "unknown"), "Estado de campo no válido.")
        _require(isinstance(item.get("reason"), str), "Falta la explicación del campo.")
        _references(item.get("evidence_ids"), segments, key)
        if status == "unknown":
            _require(value is None, "Un campo desconocido debe tener valor nulo.")
        else:
            _require(_text(value) or (isinstance(value, list) and bool(value) and all(_text(v) for v in value)),
                     "Un campo afirmado debe tener contenido.")
            _require(bool(item["evidence_ids"]), "Un campo afirmado requiere fuentes.")
            if status == "extracted" or key == "nivel_educativo":
                _require(literal_supported(value, evidence_texts(raw_segments, item["evidence_ids"]), key),
                         "El valor extraído no aparece en la evidencia citada.")
            if status == "extracted" and key in OVERVIEW_ROLES:
                _require(overview_supported(value, evidence_texts(raw_segments, item["evidence_ids"]), key),
                         "La cita no respalda el valor en su sección curricular (nombre del proyecto, propósito o finalidad).")
    _require(seen == set(FIELD_QUESTIONS), "Faltan campos; declare los desconocidos explícitamente.")
    questions = payload.get("missing_questions")
    _require(isinstance(questions, list) and all(_text(q) for q in questions), "Preguntas no válidas.")
    _require(all(FIELD_QUESTIONS[f["key"]] in questions for f in fields if f["status"] == "unknown"),
             "Faltan preguntas para los campos desconocidos.")
    draft = payload.get("draft")
    _require(isinstance(draft, dict), "Falta el borrador.")
    _require(set(draft) == set(InitialDraft.__annotations__), "Propiedades de borrador no válidas.")
    for key in ("title", "objective", "assessment"):
        _require(isinstance(draft.get(key), str), f"Borrador: {key} debe ser texto.")
    project = next(item for item in fields if item["key"] == "proyecto")
    _require(draft["title"] == initial_title(project),
             "El título inicial debe conservar el proyecto y su estado de propuesta.")
    for key in ("materials", "steps"):
        _require(isinstance(draft.get(key), list) and all(_text(v) for v in draft[key]),
                 f"Borrador: {key} debe ser una lista de textos.")
    _require(type(draft.get("revision")) is int and draft["revision"] == 1,
             "Una interpretación nueva debe comenzar en revisión 1.")
    _require(draft.get("approval_status") == "pending", "La interpretación no puede aprobar un borrador.")
    _references(draft.get("source_ids"), segments, "Borrador")
    enough = bool(draft["source_ids"] and draft["objective"].strip() and draft["steps"])
    _require(draft.get("status") == ("needs_review" if enough else INSUFFICIENT_SOURCE),
             "El borrador debe declarar la falta de fuente suficiente.")
    _require(not any((draft["objective"], draft["materials"], draft["steps"], draft["assessment"]))
             or bool(draft["source_ids"]), "El contenido del borrador requiere fuentes.")
    diagnostics = payload["diagnostics"]
    diagnostic_keys = {"method", "provider_status", "attempts", "errors", "model_winner", "source_page_count", "source_warnings"}
    if version == SCHEMA_VERSION:
        diagnostic_keys.add("source_extraction")
    _require(isinstance(diagnostics, dict) and set(diagnostics) == diagnostic_keys,
        "Diagnóstico no válido.")
    _require(diagnostics["method"] == "local_source_interpreter" and diagnostics["model_winner"] is None,
             "El diagnóstico no puede declarar un modelo ganador.")
    _require(diagnostics["provider_status"] in ("not_requested", "proposal_validated", "fallback"),
             "Estado del proveedor no válido.")
    _require(type(diagnostics["attempts"]) is int and 0 <= diagnostics["attempts"] <= 3,
             "Número de intentos no válido.")
    _require(isinstance(diagnostics["errors"], list) and all(_text(v) for v in diagnostics["errors"]),
             "Mensajes de diagnóstico no válidos.")
    count = diagnostics["source_page_count"]
    _require(type(count) is int and count > 0 and all(s["page"] <= count for s in raw_segments),
             "Total de páginas no válido.")
    _require(isinstance(diagnostics["source_warnings"], list), "Advertencias de fuente no válidas.")
    for warning in diagnostics["source_warnings"]:
        _require(isinstance(warning, dict) and set(warning) == {"page", "message"}, "Advertencia no válida.")
        _require(type(warning["page"]) is int and 1 <= warning["page"] <= count and _text(warning["message"]),
                 "Página o mensaje de advertencia no válido.")
    if version == SCHEMA_VERSION:
        _validate_extraction(diagnostics["source_extraction"], raw_segments, count)
    return copy.deepcopy(payload)


def interpretation_validation_errors(payload: Any, *, expected_document_id: str,
                                     source_segments: list[SourceSegment]) -> list[str]:
    """Safe callback bridge for evaluators requiring error codes, including S05."""
    try:
        validate_interpretation(payload, expected_document_id=expected_document_id, source_segments=source_segments)
    except InterpretationSchemaError:
        return ["interpretation_contract_invalid"]
    return []
