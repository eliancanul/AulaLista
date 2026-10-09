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
DEFAULT_MODEL = "qwen2.5:14b"
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

CONSOLIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "temas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "indices": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["titulo", "indices"],
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
    current_pages = []
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
                    "page_texts": current_pages,
                }
            )
            current_lines, current_size = [], 0
            current_pages = []
            current_first = None
        if current_first is None:
            current_first = page_number
        current_last = page_number
        current_lines.append(page_text)
        current_pages.append(text)
        current_size += page_size
    if current_lines:
        chunks.append(
            {
                "first_page": current_first,
                "last_page": current_last,
                "text": "\n".join(current_lines),
                "page_texts": current_pages,
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


def _is_planning_container(title):
    """Reject labels that organize a plan but are not teachable themes.

    The model may call these a theme, so this is deliberately deterministic.
    Their source text remains available in the draft for a teacher to use; they
    simply cannot start automatic subtopic/activity generation.
    """

    normalized = _normalize_title(title)
    return normalized.startswith((
        "planeaciondidactica",
        "identificaciongeneral",
        "semana",
        "proyecto",
    ))


def _topic_source_pages(chunk):
    """Recover physical pages, never a model-supplied range or PDF marker hint.

    New chunks retain their extraction boundaries separately from PDF text.
    The legacy text-only shape is accepted only with an unambiguous, complete
    sequence of line-start page markers matching the declared chunk bounds.
    """
    if not isinstance(chunk, dict):
        return None
    first, last, text = (chunk.get(key) for key in ("first_page", "last_page", "text"))
    if (type(first) is not int or type(last) is not int or first < 1
            or last < first or not isinstance(text, str)):
        return None
    if "page_texts" in chunk:
        pages = chunk["page_texts"]
        if (not isinstance(pages, list) or len(pages) != last - first + 1
                or any(not isinstance(page, str) for page in pages)):
            return None
        rendered = "\n".join(f"[página {first + offset}]\n{page}"
                             for offset, page in enumerate(pages))
        return pages if rendered == text else None
    markers = list(re.finditer(r"^\[página ([0-9]+)\]", text, re.MULTILINE))
    if (len(markers) != last - first + 1 or not markers
            or text[:markers[0].start()].strip()):
        return None
    pages = []
    for offset, marker in enumerate(markers):
        # String comparison avoids unbounded integer conversion of source text.
        if marker.group(1) != str(first + offset):
            return None
        end = markers[offset + 1].start() if offset + 1 < len(markers) else len(text)
        pages.append(text[marker.end():end])
    return pages


def _topic_title_in_page(title, page):
    def normalize(value):
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    # Keep punctuation and accents; do not use the fuzzy deduplication key as
    # evidence, or accept a short title embedded inside an unrelated word.
    return re.search(r"(?<!\w)" + re.escape(normalize(title)) + r"(?!\w)",
                     normalize(page)) is not None


def identify_topics(chunk, *, transport=None):
    """Stage B: propose topics for one chunk, with page citations.

    Candidates are classified so that central curriculum topics survive and
    mere activity titles or secondary headings are dropped (#33).
    """

    pages = _topic_source_pages(chunk)
    if pages is None:
        return []
    prompt = render_prompt("identify_topics", chunk_text=chunk["text"])
    result = chat_json(
        prompt, TOPIC_SCHEMA, stage="identify_topics", transport=transport
    )
    topics = []
    for topic in result["temas"][:20]:
        if not isinstance(topic, dict) or not isinstance(topic.get("titulo"), str):
            continue
        title = topic["titulo"].strip()
        if not title or len(title) > 200:
            continue
        # Missing tipo keeps the candidate: only explicit non-topics drop.
        tipo = str(topic.get("tipo") or "tema").strip().lower()
        if tipo != "tema" or _is_planning_container(title):
            continue
        first = topic.get("pagina_inicio", chunk["first_page"])
        last = topic.get("pagina_fin", chunk["last_page"])
        if (type(first) is not int or type(last) is not int
                or not chunk["first_page"] <= first <= last <= chunk["last_page"]):
            continue
        cited_pages = pages[first - chunk["first_page"]:last - chunk["first_page"] + 1]
        if not any(_topic_title_in_page(title, page) for page in cited_pages):
            continue
        topics.append(
            {
                "titulo": title,
                "pagina_inicio": first,
                "pagina_fin": last,
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


def consolidate_topics_semantic(candidates, *, transport=None):
    """Final semantic grouping pass over candidate topics (#47).

    One cheap LLM call receives the numbered candidates and returns groups
    of real curriculum themes; citations are computed in code as the union
    of the members' page ranges (the model never invents pages). Candidates
    the model does not claim survive untouched for human review. Any LLM
    failure degrades gracefully to the heuristic consolidation result.
    """

    if len(candidates) <= 1:
        return [dict(topic) for topic in candidates]
    numbered = "\n".join(
        f"{index}. {topic['titulo']} ([página {topic['pagina_inicio']}-"
        f"página {topic['pagina_fin']}])"
        for index, topic in enumerate(candidates)
    )
    prompt = render_prompt("consolidate_topics", candidates=numbered)
    try:
        result = chat_json(
            prompt,
            CONSOLIDATE_SCHEMA,
            stage="consolidate_topics",
            transport=transport,
        )
    except ImportPipelineError:
        # Degradación elegante: sin pasada semántica se conservan los
        # candidatos heurísticos; la maestra decide en la revisión.
        return [dict(topic) for topic in candidates]

    grouped = []
    claimed = set()
    for group in result.get("temas", []):
        title = str(group.get("titulo", "")).strip()[:200]
        members = []
        for raw_index in group.get("indices", []):
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(candidates) and index not in claimed:
                claimed.add(index)
                members.append(candidates[index])
        if not title or not members:
            continue
        grouped.append(
            {
                "titulo": title,
                "pagina_inicio": min(member["pagina_inicio"] for member in members),
                "pagina_fin": max(member["pagina_fin"] for member in members),
            }
        )
    grouped.extend(
        dict(topic)
        for index, topic in enumerate(candidates)
        if index not in claimed
    )
    return grouped


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


# ---------------------------------------------------------------------------
# Deterministic annex fast path
# ---------------------------------------------------------------------------

# This path deliberately recognises structure and explicit instructions rather
# than filenames, provider URLs, or a particular publisher.  It is a staging
# adapter only: every generated companion keeps the exact source page text and
# page number so a teacher can review the printable annex beside it.
_SOURCE_PAGE_MARKER_RE = re.compile(r"\[página\s+(\d+)\]", re.IGNORECASE)
_ANNEX_HEADER_RE = re.compile(
    r"^\s*ANEXO\s*(?:#\s*)?(\d+)\s*$",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_VOWELS = ("a", "e", "i", "o", "u")
_COLOR_LINE_RE = re.compile(
    # PDF text extraction often drops decorative arrows and leaves
    # ``Vocal A      verde``; accept both that layout and explicit arrows.
    r"\bVocal\s+([aeiou])\s*(?:(?:->|→|:|-)\s*)?([A-Za-zÁÉÍÓÚáéíóúÜüÑñ]+)",
    re.IGNORECASE,
)


def _source_pages(source_text):
    """Return extracted source text grouped by its immutable page markers."""

    matches = list(_SOURCE_PAGE_MARKER_RE.finditer(source_text or ""))
    if not matches:
        return {}
    pages = {}
    for index, marker in enumerate(matches):
        page = int(marker.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
        pages[page] = source_text[marker.end() : end].strip()
    return pages


def extract_annex_manifest(source_text):
    """Extract a source manifest for structured ``ANEXO`` pages.

    The returned text is copied from ``source_text`` and is never rewritten by
    the model.  A missing page marker or header produces an empty manifest so
    callers can safely use the normal LLM path.
    """

    pages = _source_pages(source_text)
    manifest = []
    for page, text in sorted(pages.items()):
        first_line = next((line for line in text.splitlines() if line.strip()), "")
        # References such as "anexo 3" in a session paragraph are not source
        # pages.  A high-confidence annex starts its page with the heading.
        header = _ANNEX_HEADER_RE.fullmatch(first_line)
        if not header:
            continue
        number = int(header.group(1))
        urls = [match.rstrip(".,;:)") for match in _URL_RE.findall(text)]
        manifest.append(
            {
                "number": number,
                "page": page,
                "source_anchor": header.group(0).strip(),
                "source_text": text,
                "source_url": urls[0] if urls else "",
                "source_urls": urls,
            }
        )
    return manifest


def _deterministic_question(prompt, options, expected_index, hint):
    """Build one option question with the package's existing strict contract."""

    return {
        "block_type": "reactivo",
        "value": {
            "prompt": prompt,
            "options": [
                {
                    "position": position,
                    "text": str(option).strip(),
                    "expected": position - 1 == expected_index,
                    "feedback": (
                        "Correcto."
                        if position - 1 == expected_index
                        else "Revisa la instrucción del anexo."
                    ),
                }
                for position, option in enumerate(options, start=1)
            ],
            "hints": [hint],
        },
    }


def _proposal_from_annex(title, objective, micro_lesson, explanation, questions):
    return {
        "title": title[:160],
        "objective": objective,
        "micro_lesson": micro_lesson,
        "final_explanation": explanation,
        "questions": questions,
    }


def _build_fill_blank_annex(manifest_item):
    text = manifest_item["source_text"]
    if not re.search(r"cinco\s+vocales", text, re.IGNORECASE):
        return None
    blank_lines = [line.strip() for line in text.splitlines() if re.search(r"_{2,}", line)]
    blank_count = sum(len(re.findall(r"_{2,}", line)) for line in blank_lines)
    # The educational template is safe only when its five blanks correspond to
    # the explicit five-vowel instruction.  Otherwise an unknown answer key
    # must remain on the regular LLM/review path.
    if blank_count != len(_VOWELS) or not blank_lines:
        return None
    proposal = _proposal_from_annex(
        f"ANEXO # {manifest_item['number']:02d}",
        "Completar huecos con las cinco vocales.",
        "La hoja conserva cinco espacios para que la maestra autorice la clave.",
        "La clave de respuestas no aparece en la fuente; requiere revisión humana antes de evaluar.",
        [],
    )
    return "fill_blank", proposal, {
        "blank_count": blank_count,
        "blanks": blank_lines,
        "vowels_instruction": "Escribe en los círculos las cinco vocales mostradas en el vídeo.",
        "requires_human_answer_key": True,
        "non_evaluable": True,
    }


def _build_color_mapping_annex(manifest_item):
    text = manifest_item["source_text"]
    mapping = {}
    for raw_vowel, raw_color in _COLOR_LINE_RE.findall(text):
        vowel = raw_vowel.lower()
        color = raw_color.strip()
        if vowel in _VOWELS and color:
            mapping[vowel] = color
    if set(mapping) != set(_VOWELS) or len(set(mapping.values())) != len(_VOWELS):
        return None
    colors = list(mapping.values())
    questions = [
        _deterministic_question(
            f"¿De qué color se colorea la vocal {vowel.upper()}?",
            colors,
            colors.index(mapping[vowel]),
            "Busca la leyenda de colores del anexo.",
        )
        for vowel in _VOWELS
    ]
    proposal = _proposal_from_annex(
        f"ANEXO # {manifest_item['number']:02d}",
        "Relacionar cada vocal con el color indicado.",
        "La leyenda del anexo asigna un color distinto a cada vocal.",
        "Colorea únicamente según la leyenda; la imagen original permanece disponible para revisión.",
        questions,
    )
    return "color_mapping", proposal, {"mapping": mapping}


def _build_matching_annex(manifest_item):
    text = manifest_item["source_text"]
    compact = re.sub(r"\s+", " ", text)
    has_lower = bool(re.search(r"\ba\s*,\s*e\s*,\s*i\s*,\s*o\s*,\s*u\b", compact))
    has_upper = bool(re.search(r"\bA\s*,\s*E\s*,\s*I\s*,\s*O\s*,\s*U\b", compact))
    if not (has_lower and has_upper):
        return None
    if not all(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in (r"vocales\s+mayúsculas", r"vocales\s+minúsculas", r"significa\s+menor", r"significa\s+mayor")
    ):
        return None
    questions = [
        _deterministic_question(
            "Relaciona el grupo a, e, i, o, u con su descripción.",
            ["Vocales minúsculas", "Vocales mayúsculas"],
            0,
            "Las letras minúsculas se escriben con menor tamaño.",
        ),
        _deterministic_question(
            "Relaciona el grupo A, E, I, O, U con su descripción.",
            ["Vocales minúsculas", "Vocales mayúsculas"],
            1,
            "Las letras mayúsculas se escriben con mayor tamaño.",
        ),
        _deterministic_question(
            "¿Qué significa minúscula?",
            ["Significa menor", "Significa mayor"],
            0,
            "Observa la relación mostrada en el anexo.",
        ),
        _deterministic_question(
            "¿Qué significa mayúscula?",
            ["Significa menor", "Significa mayor"],
            1,
            "Observa la relación mostrada en el anexo.",
        ),
    ]
    proposal = _proposal_from_annex(
        f"ANEXO # {manifest_item['number']:02d}",
        "Relacionar vocales mayúsculas y minúsculas con su significado.",
        "Las vocales aparecen en grupos mayúscula y minúscula.",
        "Relaciona cada grupo con la etiqueta correspondiente y conserva el anexo original para revisión.",
        questions,
    )
    return "matching", proposal, {
        "pairs": [
            ["a, e, i, o, u", "Vocales minúsculas"],
            ["A, E, I, O, U", "Vocales mayúsculas"],
            ["Vocales minúsculas", "Significa menor"],
            ["Vocales mayúsculas", "Significa mayor"],
        ]
    }


def _build_annex_companion(manifest_item):
    """Return a high-confidence deterministic companion or ``None``."""

    builders = (_build_fill_blank_annex, _build_color_mapping_annex, _build_matching_annex)
    matches = [built for builder in builders if (built := builder(manifest_item))]
    if len(matches) != 1:
        return None
    return matches[0]


def build_annex_fast_path(source_text):
    """Build reviewable annex activities without calling the local model.

    ``None`` means the document is not a high-confidence structured planning
    document; callers must use the unchanged topic/subtopic/activity pipeline.
    """

    pages = _source_pages(source_text)
    if not pages or not re.search(r"planeación\s+didáctica", source_text or "", re.IGNORECASE):
        return None
    manifest = extract_annex_manifest(source_text)
    if not manifest:
        return None
    activities = []
    for item in manifest:
        built = _build_annex_companion(item)
        if built is None:
            return None
        kind, proposal, details = built
        is_evaluable = not details.get("requires_human_answer_key", False)
        activities.append(
            {
                "id": f"annex-{item['number']:02d}",
                "topic_title": "",
                "subtopic_title": f"ANEXO # {item['number']:02d}",
                "is_valid": is_evaluable,
                "issues": (
                    []
                    if is_evaluable
                    else [
                        "requires_human_answer_key",
                        "El anexo conserva huecos sin clave; no es evaluable todavía.",
                    ]
                ),
                "proposal": proposal,
                "selected": True,
                "annex": {
                    "number": item["number"],
                    "kind": kind,
                    "source_pages": [item["page"]],
                    "source_anchor": item["source_anchor"],
                    "source_text": item["source_text"],
                    "source_url": item["source_url"],
                    "source_urls": item["source_urls"],
                    "details": details,
                },
            }
        )
    project_match = re.search(r"(?:^|\n)\s*Proyecto\s*:\s*([^\n]+)", source_text, re.IGNORECASE)
    content_match = re.search(r"(?:^|\n)\s*Contenido\s*:\s*([^\n]+)", source_text, re.IGNORECASE)
    topic_title = (project_match or content_match).group(1).strip() if (project_match or content_match) else "Anexos de la planeación"
    for activity in activities:
        activity["topic_title"] = topic_title[:200]
    pages_for_topic = [item["page"] for item in manifest]
    topic = {
        "titulo": topic_title[:200],
        "pagina_inicio": min(pages_for_topic),
        "pagina_fin": max(pages_for_topic),
        "subtemas": [
            {"titulo": activity["subtopic_title"], "actividades_sugeridas": 1}
            for activity in activities
        ],
    }
    return {"manifest": manifest, "topics": [topic], "activities": activities}


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
