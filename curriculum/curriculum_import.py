"""Local-Ollama curriculum import pipeline: PDF text → topics → subtopics.

Everything runs against a local Ollama server using structured outputs
(JSON Schema via ``format``). The LLM only proposes staging data for human
review; it never touches CurriculumPackage, revisions or snapshots.
"""

import json
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from string import Template

from django.conf import settings

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"
CHAT_TIMEOUT_SECONDS = 180
MAX_ATTEMPTS = 3
CHUNK_MAX_CHARS = 4000


PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt_template(name):
    """Read a versioned prompt template (editable without touching code)."""

    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render_prompt(name, **values):
    """Fill a versioned prompt template with the stage's dynamic values."""

    return Template(load_prompt_template(name)).substitute(**values)


SYSTEM_PROMPT_NAME = "system"

# Per-thread recorder: stage workers bracket their LLM calls with
# start_llm_trace()/stop_llm_trace() and every chat_json call appends an
# entry with prompt, raw answer, duration and retry count (#34).
_trace = threading.local()


def start_llm_trace():
    _trace.entries = []


def stop_llm_trace():
    entries = getattr(_trace, "entries", None)
    _trace.entries = None
    return entries or []


def _record_trace(entry):
    entries = getattr(_trace, "entries", None)
    if entries is not None:
        entries.append(entry)


class ImportPipelineError(ValueError):
    """Raised when the local LLM cannot produce a schema-valid proposal."""


def ollama_url():
    return getattr(settings, "AULALISTA_OLLAMA_URL", "") or DEFAULT_OLLAMA_URL


def llm_model():
    return getattr(settings, "AULALISTA_LLM_MODEL", "") or DEFAULT_MODEL


TOPIC_SCHEMA = {
    "type": "object",
    "properties": {
        "temas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "pagina_inicio": {"type": "integer"},
                    "pagina_fin": {"type": "integer"},
                    "tipo": {
                        "type": "string",
                        "enum": ["tema", "actividad", "otro"],
                    },
                },
                "required": ["titulo"],
            },
        }
    },
    "required": ["temas"],
}

SUBTOPIC_SCHEMA = {
    "type": "object",
    "properties": {
        "subtemas": {"type": "array", "items": {"type": "string"}},
        "actividades_sugeridas": {"type": "integer"},
    },
    "required": ["subtemas"],
}

ACTIVITY_SCHEMA = {
    "type": "object",
    "properties": {
        "objetivo": {"type": "string"},
        "microleccion": {"type": "string"},
        "explicacion_final": {"type": "string"},
        "reactivos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "enunciado": {"type": "string"},
                    "opciones": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "posicion": {"type": "integer"},
                                "texto": {"type": "string"},
                                "correcta": {"type": "boolean"},
                                "retroalimentacion": {"type": "string"},
                            },
                            "required": ["posicion", "texto", "correcta", "retroalimentacion"],
                        },
                    },
                    "pistas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["enunciado", "opciones", "pistas"],
            },
        },
    },
    "required": ["objetivo", "microleccion", "explicacion_final", "reactivos"],
}


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_pdf_pages(pdf_file):
    """Return one text string per page using pypdf. Raises ValueError on failure."""

    from pypdf import PdfReader

    try:
        reader = PdfReader(pdf_file)
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as error:  # pypdf raises several unrelated exception types
        raise ValueError(f"No se pudo leer el PDF: {error}") from error
    if not any(pages):
        raise ValueError(
            "El PDF no contiene texto extraíble; los documentos escaneados no "
            "están soportados en esta etapa."
        )
    return pages


def chunk_pages(pages, max_chars=CHUNK_MAX_CHARS):
    """Group pages into chunks tagged with [página N] markers within context limits."""

    chunks = []
    current_lines = []
    current_size = 0
    current_first = current_last = None
    for page_number, text in enumerate(pages, start=1):
        page_text = f"[página {page_number}]\n{text}"
        page_size = len(page_text)
        if current_lines and current_size + page_size > max_chars:
            chunks.append(
                {
                    "first_page": current_first,
                    "last_page": current_last,
                    "text": "\n".join(current_lines),
                }
            )
            current_lines, current_size = [], 0
            current_first = None
        if current_first is None:
            current_first = page_number
        current_last = page_number
        current_lines.append(page_text)
        current_size += page_size
    if current_lines:
        chunks.append(
            {
                "first_page": current_first,
                "last_page": current_last,
                "text": "\n".join(current_lines),
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# Local LLM structured-output client
# ---------------------------------------------------------------------------

def _validate_against_schema(payload, schema):
    """Minimal structural check for the two flat schemas used here."""

    if not isinstance(payload, dict):
        raise ImportPipelineError("La respuesta del modelo no es un objeto JSON.")
    for key in schema.get("required", []):
        if key not in payload:
            raise ImportPipelineError(f"Falta '{key}' en la respuesta del modelo.")
    items_key = "temas" if "temas" in payload else "subtemas"
    if items_key in payload and not isinstance(payload[items_key], list):
        raise ImportPipelineError(f"'{items_key}' debe ser una lista.")
    return payload


SYSTEM_PROMPT_CACHE = {}


def system_prompt():
    """The shared system prompt, loaded from its versioned file (#34)."""

    if SYSTEM_PROMPT_NAME not in SYSTEM_PROMPT_CACHE:
        SYSTEM_PROMPT_CACHE[SYSTEM_PROMPT_NAME] = load_prompt_template(
            SYSTEM_PROMPT_NAME
        )
    return SYSTEM_PROMPT_CACHE[SYSTEM_PROMPT_NAME]


def chat_json(prompt, schema, *, stage="", model=None, transport=None):
    """Call the local Ollama chat API constrained to the given JSON Schema.

    Every exchange is recorded into the active thread trace when one is
    running: full system/user prompts, raw answer, duration and retries (#34).
    """

    body = json.dumps(
        {
            "model": model or llm_model(),
            "messages": [
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{ollama_url().rstrip('/')}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    def _post(data=request):
        with urllib.request.urlopen(  # noqa: S310 - local trusted service
            data, timeout=CHAT_TIMEOUT_SECONDS
        ) as response:
            return json.loads(response.read().decode("utf-8"))

    started = time.monotonic()
    attempt_errors = []
    parsed_result = None
    raw_content = ""
    for _attempt in range(MAX_ATTEMPTS):
        try:
            raw = transport(request) if transport else _post()
            content = raw["message"]["content"]
            raw_content = content
            parsed_result = _validate_against_schema(json.loads(content), schema)
            break
        except (ImportPipelineError, KeyError, json.JSONDecodeError,
                urllib.error.URLError, TimeoutError, OSError) as error:
            attempt_errors.append(str(error))
    duration_ms = int((time.monotonic() - started) * 1000)
    _record_trace(
        {
            "stage": stage,
            "model": model or llm_model(),
            "system": system_prompt(),
            "prompt": prompt,
            "response_raw": raw_content,
            "duration_ms": duration_ms,
            "attempts": len(attempt_errors) + (1 if parsed_result is not None else 0),
            "errors": attempt_errors,
            "ok": parsed_result is not None,
        }
    )
    if parsed_result is None:
        raise ImportPipelineError(
            f"El modelo local no produjo una propuesta válida tras {MAX_ATTEMPTS} "
            f"intentos: {attempt_errors[-1] if attempt_errors else 'desconocido'}"
        )
    return parsed_result


# ---------------------------------------------------------------------------
# Stage B/C: topic identification and subtopic proposals
# ---------------------------------------------------------------------------

def _normalize_title(title):
    normalized = unicodedata.normalize("NFKD", str(title or "").strip().lower())
    return re.sub(r"[^a-z0-9]+", "", normalized)


def identify_topics(chunk, *, transport=None):
    """Stage B: propose topics for one chunk, with page citations.

    Candidates are classified so that central curriculum topics survive and
    mere activity titles or secondary headings are dropped (#33).
    """

    prompt = render_prompt("identify_topics", chunk_text=chunk["text"])
    result = chat_json(
        prompt, TOPIC_SCHEMA, stage="identify_topics", transport=transport
    )
    topics = []
    for topic in result["temas"][:20]:
        title = str(topic.get("titulo", "")).strip()[:200]
        if not title:
            continue
        # Missing tipo keeps the candidate: only explicit non-topics drop.
        tipo = str(topic.get("tipo") or "tema").strip().lower()
        if tipo != "tema":
            continue
        topics.append(
            {
                "titulo": title,
                "pagina_inicio": int(topic.get("pagina_inicio") or chunk["first_page"]),
                "pagina_fin": int(topic.get("pagina_fin") or chunk["last_page"]),
            }
        )
    return topics


def _ranges_overlap(a, b):
    return a["pagina_inicio"] <= b["pagina_fin"] and b["pagina_inicio"] <= a["pagina_fin"]


def _titles_equivalent(a, b):
    """Near-duplicate detection: substring or high sequence similarity (#43)."""

    left, right = _normalize_title(a), _normalize_title(b)
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.7


def consolidate_topics(proposals_per_chunk):
    """Merge per-chunk topic lists, deduplicating near-identical titles (#43).

    Exact and fuzzy duplicates merge only when their page ranges overlap, so
    distinct topics that merely share a title fragment survive. The shorter
    (more generic) title wins; citations are widened to the union.
    """

    consolidated = [
        dict(topic) for proposals in proposals_per_chunk for topic in proposals
    ]
    # Absorb equivalent+overlapping pairs until stable: widening a range can
    # enable further merges (transitive near-duplicates, #43).
    changed = True
    while changed:
        changed = False
        for i in range(len(consolidated)):
            for j in range(i + 1, len(consolidated)):
                first, second = consolidated[i], consolidated[j]
                exact_match = _normalize_title(first["titulo"]) == _normalize_title(
                    second["titulo"]
                )
                if exact_match or (
                    _titles_equivalent(first["titulo"], second["titulo"])
                    and _ranges_overlap(first, second)
                ):
                    first["pagina_inicio"] = min(
                        first["pagina_inicio"], second["pagina_inicio"]
                    )
                    first["pagina_fin"] = max(first["pagina_fin"], second["pagina_fin"])
                    if len(str(second["titulo"])) < len(str(first["titulo"])):
                        first["titulo"] = second["titulo"]
                    del consolidated[j]
                    changed = True
                    break
            if changed:
                break
    return consolidated


def context_for_pages(source_text, start, end, *, pad=1, max_chars=CHUNK_MAX_CHARS):
    """Extract the source window covering pages start..end (plus padding).

    Subtopic proposals must reason about the text where the topic actually
    lives (#42); falls back to the head of the document when the markers are
    missing.
    """

    if not source_text:
        return ""
    marker = re.compile(r"\[página (\d+)\]")
    matches = list(marker.finditer(source_text))
    if not matches:
        return source_text[:max_chars]

    pages = {}
    for index, match in enumerate(matches):
        page = int(match.group(1))
        begin = match.end()
        finish = matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
        pages[page] = source_text[begin:finish].strip("\n")

    lo = max(min(pages), int(start) - pad)
    hi = min(max(pages), int(end) + pad)
    window = "\n\n".join(
        f"[página {page}]\n{pages[page]}" for page in sorted(pages) if lo <= page <= hi
    )
    return window or source_text[:max_chars]


def propose_subtopics(topic_title, context_text, *, transport=None):
    """Stage C: propose subtopics (and an activity-count hint) for one topic."""

    prompt = render_prompt(
        "propose_subtopics",
        topic_title=topic_title,
        context=context_text[:CHUNK_MAX_CHARS],
    )
    result = chat_json(
        prompt, SUBTOPIC_SCHEMA, stage="propose_subtopics", transport=transport
    )
    subtopics = []
    for subtopic in result["subtemas"][:15]:
        title = str(subtopic).strip()[:200]
        if title:
            subtopics.append(title)
    activities_hint = result.get("actividades_sugeridas")
    return {
        "subtemas": subtopics,
        "actividades_sugeridas": (
            int(activities_hint) if isinstance(activities_hint, int) else 1
        ),
    }


VALIDATION_FEEDBACK_SUFFIX = (
    "\n\nNota: tu intento anterior fue rechazado por validación "
    "estructural por: {issues}. Corrige exactamente esos puntos."
)


def _with_validation_feedback(prompt, issues):
    if not issues:
        return prompt
    return prompt + VALIDATION_FEEDBACK_SUFFIX.format(issues="; ".join(issues))


def propose_activities(subtopic_title, context_text, count, *, transport=None, feedback_issues=None):
    """Stage D: draft one or more single-choice activities for a subtopic.

    Returns a proposal dict shaped like a CurriculumPackage payload; it is
    staging data only and must pass structural validation plus human review.
    """

    count = max(1, min(int(count), 5))
    prompt = render_prompt(
        "propose_activities",
        subtopic_title=subtopic_title,
        context=context_text[:CHUNK_MAX_CHARS],
        count=count,
    )
    prompt = _with_validation_feedback(prompt, feedback_issues)
    result = chat_json(
        prompt, ACTIVITY_SCHEMA, stage="propose_activities", transport=transport
    )
    return _map_activity_payload(subtopic_title, result)


def _map_activity_payload(subtopic_title, result):
    """Map a raw ACTIVITY_SCHEMA response into the staging proposal shape."""

    questions = []
    for reactivo in result.get("reactivos", [])[:5]:
        options = []
        for position, option in enumerate(reactivo.get("opciones", [])[:6], start=1):
            options.append(
                {
                    "position": position,
                    "text": str(option.get("texto", "")).strip(),
                    "expected": option.get("correcta") is True,
                    "feedback": str(option.get("retroalimentacion", "")).strip(),
                }
            )
        hints = [
            str(hint).strip() for hint in reactivo.get("pistas", []) if str(hint).strip()
        ]
        questions.append(
            {
                "block_type": "reactivo",
                "value": {
                    "prompt": str(reactivo.get("enunciado", "")).strip(),
                    "options": options,
                    "hints": hints,
                },
            }
        )
    return {
        "title": subtopic_title[:160],
        "objective": str(result.get("objetivo", "")).strip(),
        "micro_lesson": str(result.get("microleccion", "")).strip(),
        "final_explanation": str(result.get("explicacion_final", "")).strip(),
        "questions": questions,
    }


def propose_activities_incremental(
    subtopic_title,
    context_text,
    count,
    existing_summaries,
    *,
    transport=None,
    feedback_issues=None,
):
    """Stage D+: append-only top-up for a subtopic (#35).

    Existing proposals are passed as immutable context; the model must not
    modify or repeat them and only draft the missing ones.
    """

    count = max(1, min(int(count), 5))
    existing_block = "\n".join(f"- {summary}" for summary in existing_summaries)
    prompt = render_prompt(
        "propose_activities_incremental",
        subtopic_title=subtopic_title,
        context=context_text[:CHUNK_MAX_CHARS],
        existing_block=existing_block,
        count=count,
    )
    prompt = _with_validation_feedback(prompt, feedback_issues)
    result = chat_json(
        prompt,
        ACTIVITY_SCHEMA,
        stage="add_missing_activities",
        transport=transport,
    )
    return _map_activity_payload(subtopic_title, result)
