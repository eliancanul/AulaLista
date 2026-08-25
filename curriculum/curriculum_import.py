"""Local-Ollama curriculum import pipeline: PDF text → topics → subtopics.

Everything runs against a local Ollama server using structured outputs
(JSON Schema via ``format``). The LLM only proposes staging data for human
review; it never touches CurriculumPackage, revisions or snapshots.
"""

import json
import re
import unicodedata
import urllib.error
import urllib.request

from django.conf import settings

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"
CHAT_TIMEOUT_SECONDS = 180
MAX_ATTEMPTS = 3
CHUNK_MAX_CHARS = 4000


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


def chat_json(prompt, schema, *, model=None, transport=None):
    """Call the local Ollama chat API constrained to the given JSON Schema."""

    body = json.dumps(
        {
            "model": model or llm_model(),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente que analiza currículas escolares y "
                        "responde exclusivamente con JSON válido conforme al "
                        "esquema indicado. No inventes contenido que no esté "
                        "en el texto entregado."
                    ),
                },
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

    last_error = None
    for _attempt in range(MAX_ATTEMPTS):
        try:
            raw = transport(request) if transport else _post()
            content = raw["message"]["content"]
            parsed = json.loads(content)
            return _validate_against_schema(parsed, schema)
        except (ImportPipelineError, KeyError, json.JSONDecodeError,
                urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
    raise ImportPipelineError(
        f"El modelo local no produjo una propuesta válida tras {MAX_ATTEMPTS} "
        f"intentos: {last_error}"
    )


# ---------------------------------------------------------------------------
# Stage B/C: topic identification and subtopic proposals
# ---------------------------------------------------------------------------

def _normalize_title(title):
    normalized = unicodedata.normalize("NFKD", str(title or "").strip().lower())
    return re.sub(r"[^a-z0-9]+", "", normalized)


def identify_topics(chunk, *, transport=None):
    """Stage B: propose topics for one chunk, with page citations."""

    prompt = (
        "El siguiente fragmento de una currícula escolar tiene marcadores de "
        "página como [página 3]. Identifica los temas curriculares presentes. "
        "Responde JSON con la forma {\"temas\": [{\"titulo\": string, "
        "\"pagina_inicio\": int, \"pagina_fin\": int}]}. Usa los números de "
        "página de los marcadores.\n\n" + chunk["text"]
    )
    result = chat_json(prompt, TOPIC_SCHEMA, transport=transport)
    topics = []
    for topic in result["temas"][:20]:
        title = str(topic.get("titulo", "")).strip()[:200]
        if not title:
            continue
        topics.append(
            {
                "titulo": title,
                "pagina_inicio": int(topic.get("pagina_inicio") or chunk["first_page"]),
                "pagina_fin": int(topic.get("pagina_fin") or chunk["last_page"]),
            }
        )
    return topics


def consolidate_topics(proposals_per_chunk):
    """Merge per-chunk topic lists, deduplicating by normalized title."""

    consolidated = []
    seen = {}
    for proposals in proposals_per_chunk:
        for topic in proposals:
            key = _normalize_title(topic["titulo"])
            if key in seen:
                existing = seen[key]
                existing["pagina_inicio"] = min(
                    existing["pagina_inicio"], topic["pagina_inicio"]
                )
                existing["pagina_fin"] = max(
                    existing["pagina_fin"], topic["pagina_fin"]
                )
                continue
            seen[key] = dict(topic)
            consolidated.append(seen[key])
    return consolidated


def propose_subtopics(topic_title, context_text, *, transport=None):
    """Stage C: propose subtopics (and an activity-count hint) for one topic."""

    prompt = (
        "Tema curricular: \"" + topic_title + "\".\n\nContexto de la currícula "
        "(con páginas):\n" + context_text[:CHUNK_MAX_CHARS] + "\n\nPropón los "
        "subtemas que componen este tema, en orden pedagógico. Responde JSON "
        "{\"subtemas\": [string], \"actividades_sugeridas\": int} donde "
        "actividades_sugeridas es cuántas actividades convendría por subtema "
        "según su densidad conceptual."
    )
    result = chat_json(prompt, SUBTOPIC_SCHEMA, transport=transport)
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
