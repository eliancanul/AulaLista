"""Page-local text anchors and shared structural boundaries for extraction/audit.

Offsets address Python character positions in pypdf's extracted page text, not
PDF coordinates. Every verification recomputes these slices from the source.
Project proximity is a reviewable interpretation, never a membership claim.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

from curriculum.overview_fields import iter_overview_spans, _quote_stack

ANCHOR_SCHEMA_VERSION = 1
PROJECT_CONTEXT_SCHEMA_VERSION = 1
_DAYS = r"Lunes|Martes|Miércoles|Miercoles|Jueves|Viernes"
_SESSION_RE = re.compile(
    rf"^[ \t]*((?:({_DAYS})[ \t]*[-–—]?[ \t]*)?SESI[OÓ]N[ \t]*([1-9]\d*)"
    r"(?=[ \t]*(?::|\r?$))[ \t]*(?::[ \t]*([^\n\r]+))?)", re.IGNORECASE | re.MULTILINE,
)
_DAY_RE = re.compile(
    rf"^[ \t]*(({_DAYS})(?:[ \t]*:[ \t]*[^\n\r]+|[ \t]*\r?$)"
    r"(?:\n[ \t]*\d+[ \t]+de[ \t]+[^\n\r]+)?)", re.IGNORECASE | re.MULTILINE,
)


def text_anchor(page: str, sha: str, page_number: int, occurrence: int, start: int, end: int, kind: str) -> dict[str, Any]:
    return {
        "schema_version": ANCHOR_SCHEMA_VERSION,
        "kind": kind,
        "document_sha256": sha,
        "page_number": page_number,
        "occurrence": occurrence,
        "text_start": start,
        "text_end": end,
        "excerpt": page[start:end],
    }


def anchor_matches(value: Any, expected: dict[str, Any]) -> bool:
    """Strict, fail-closed comparison; bool and numeric strings are not ints."""
    if not isinstance(value, dict) or value.keys() != expected.keys():
        return False
    for key in ("schema_version", "page_number", "occurrence", "text_start", "text_end"):
        if type(value.get(key)) is not int:
            return False
    return value == expected


def missing_project_context() -> dict[str, Any]:
    return {
        "schema_version": PROJECT_CONTEXT_SCHEMA_VERSION,
        "project_id": None, "title": "", "title_status": "missing",
        "origin": "proposed", "status": "missing", "review": "pending",
        "reason": "No hay un encabezado de proyecto anterior a esta unidad en la fuente; no se hereda el título general.",
        "anchor": None,
    }


def _session_headers(pages: list[str]):
    numbered = [[m for m in _SESSION_RE.finditer(page) if not _quote_stack(page[:m.start()])] for page in pages]
    if any(numbered):
        return True, numbered
    return False, [[m for m in _DAY_RE.finditer(page) if not _quote_stack(page[:m.start()])] for page in pages]


def project_occurrences(pages: list[str], sha: str) -> list[dict[str, Any]]:
    result = []
    _, headers = _session_headers(pages)
    extra = {number: [m.start(1) for m in matches] for number, matches in enumerate(headers, 1)}
    for span in iter_overview_spans(pages, extra_boundaries=extra):
        if span.name != "proyecto":
            continue
        title = re.sub(r"\s+", " ", span.excerpt).strip()
        uncertain = span.ambiguous or (span.termination != "quoted_title" and bool(
            re.match(r"^[sS]\b|^[eE]je\b|^\W", title) or len(title) < 3
            or title.lower().startswith("eje seleccionado")
        ))
        title_status = "missing" if not title else "ambiguous" if uncertain else "supported"
        anchor = text_anchor(pages[span.page_number - 1], sha, span.page_number, span.occurrence,
                             span.text_start, span.text_end, "project")
        reason = "Contexto propuesto por el último encabezado de proyecto anterior en orden físico; no confirma pertenencia curricular."
        if title_status == "missing":
            reason += " El encabezado está vacío; no se reutiliza el proyecto anterior."
        elif title_status == "ambiguous":
            reason += " El título tiene un límite incierto y requiere revisión del fragmento."
        result.append({
            "schema_version": PROJECT_CONTEXT_SCHEMA_VERSION,
            "project_id": f"{sha}:p{span.page_number}:project{span.occurrence}",
            "title": title, "title_status": title_status,
            "origin": "proposed", "status": "missing" if not title else "ambiguous", "review": "pending",
            "reason": reason, "anchor": anchor,
        })
    return result


def context_before(projects: list[dict[str, Any]], page_number: int, text_start: int) -> dict[str, Any]:
    preceding = [p for p in projects if (p["anchor"]["page_number"], p["anchor"]["text_start"]) < (page_number, text_start)]
    return copy.deepcopy(preceding[-1] if preceding else missing_project_context())


@dataclass
class SessionSegment:
    session_id: str
    session_number: int
    title: str
    day_of_week: str
    header_anchor: dict[str, Any]
    project_context: dict[str, Any]
    page_segments: list[tuple[int, str]] = field(default_factory=list)


def clean_page_prefix(text: str) -> str:
    """Legacy continuation cleaning, shared so audit sees the same slices."""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or re.match(r"^Planeación Didáctica|^Semana \d+|^Página \d+|^Vo\.\s*Bo\.", s, re.IGNORECASE):
            continue
        if re.search(r"https?://\S+", s) and len(s) < 140 and "elaborar" not in s.lower() and "material" not in s.lower():
            continue
        if re.match(r"^(?:Nivel:|Zona Escolar:|Sector:|Ciclo Escolar:|Nombre del Docente:|Grado:)", s, re.IGNORECASE):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def is_structural_barrier(text: str) -> bool:
    if not text.strip():
        return True
    norm = re.sub(r"\s+", " ", text).strip().lower()
    return bool(
        re.search(r"\b(?:r[uú]brica(?: de evaluaci[oó]n)?|escala estimativa|lista de cotejo|matriz de valoraci[oó]n|criterios de evaluaci[oó]n)\b", norm)
        or re.search(r"\b(?:desarrollo de actividades|proyecto(?: de diagn[oó]stico)?:|prop[oó]sito:|metodolog[ií]a:|campos formativos:)\b", norm)
        or re.search(r"(?:^|\n)\s*anexos?(?:\s*\d+|:|\s*$)", norm)
        or re.search(r"\b(?:vo\.\s*bo\.|directora? escolar|docente frente a grupo|firma del docente)\b", norm)
    )


def scan_session_segments(pages: list[str], sha: str) -> list[SessionSegment]:
    projects = project_occurrences(pages, sha)
    # A quoted session label is prose, even when its line begins with SESIÓN.
    use_numbered, headers = _session_headers(pages)
    segments = []
    counts: dict[str, int] = {}
    boundaries: dict[int, list[int]] = {}
    for project in projects:
        anchor = project["anchor"]
        boundaries.setdefault(anchor["page_number"], []).append(anchor["text_start"])
    for page_number, page in enumerate(pages, 1):
        matches = headers[page_number - 1]
        for occurrence, m in enumerate(matches, 1):
            start, end = m.span(1)
            day = (m.group(2) or "").capitalize()
            number = int(m.group(3)) if use_numbered else occurrence
            title = (m.group(4) or "") if use_numbered else day
            title = re.sub(r"\s*Recursos:?.*$", "", title, flags=re.IGNORECASE).strip()
            base = f"p{page_number}_s{number}"
            counts[base] = counts.get(base, 0) + 1
            sid = base if counts[base] == 1 else f"{base}_{counts[base]}"
            segments.append(SessionSegment(
                sid, number, title or f"Sesión {number}", day,
                text_anchor(page, sha, page_number, occurrence, start, end, "session" if use_numbered else "day"),
                context_before(projects, page_number, start),
            ))
            boundaries.setdefault(page_number, []).append(start)
    for segment in segments:
        anchor = segment.header_anchor
        page_number, start = anchor["page_number"], anchor["text_start"]
        page = pages[page_number - 1]
        following = sorted(b for b in boundaries.get(page_number, []) if b > start)
        end = following[0] if following else len(page)
        segment.page_segments = [(page_number, page[start:end])]
        if following or page_number >= len(pages):
            continue
        # Preserve the existing immediate-next-page-only continuation contract.
        # A project boundary cuts the candidate prefix just like a session.
        next_boundaries = boundaries.get(page_number + 1, [])
        next_page = pages[page_number]
        prefix = next_page[:min(next_boundaries)] if next_boundaries else next_page
        cleaned = clean_page_prefix(prefix)
        cleaned = re.split(r"(?:\n|\s{2,})(?:Producto\s+del\s+proyecto|Evidencias\s+de\s+aprendizaje|Aspectos\s+a\s+evaluar|Adecuaciones\s+curriculares|Vo\.\s*Bo\.)", cleaned, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        if cleaned and not is_structural_barrier(cleaned) and re.search(r"(?:^|\n|\b)(?:Inicio|Desarrollo|Cierre)\b", cleaned, re.IGNORECASE):
            segment.page_segments.append((page_number + 1, cleaned))
    return segments


def match_session_segment(session: dict[str, Any], segments: list[SessionSegment]) -> SessionSegment | None:
    """Resolve by physical ID, or a unique legacy number/page, never by title/order."""
    sid = session.get("session_id")
    number = session.get("session_number")
    pages = session.get("pages")
    if type(number) is not int or not isinstance(pages, list) or not pages or any(type(p) is not int for p in pages):
        return None
    exact = [s for s in segments if s.session_id == sid]
    if exact:
        match = exact[0]
        return match if match.session_number == number and match.header_anchor["page_number"] == pages[0] else None
    # A missing canonical ID is not a licence to silently relabel another unit.
    if isinstance(sid, str) and re.fullmatch(r"p\d+_s\d+(?:_\d+)?", sid):
        return None
    candidates = [s for s in segments if s.session_number == number and s.header_anchor["page_number"] == pages[0]]
    return candidates[0] if len(candidates) == 1 else None


def phase_project_context(pages: list[str], sha: str, first_page: int) -> dict[str, Any]:
    page = pages[first_page - 1]
    start = re.search(r"(?im)^[ \t]*DESARROLLO\s+DEL\s+PROYECTO\b", page)
    return context_before(project_occurrences(pages, sha), first_page, start.start() if start else 0)


def project_context_matches(value: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value != expected:
        return False
    anchor = expected["anchor"]
    return anchor_matches(value.get("anchor"), anchor) if anchor is not None else value.get("anchor") is None


def phase_review_segments(pages: list[str], sha: str, first_page: int) -> list[tuple[int, str]]:
    """Bound the existing synthetic phase-review unit at the next project."""
    first = re.search(r"(?im)^[ \t]*DESARROLLO\s+DEL\s+PROYECTO\b", pages[first_page - 1])
    if not first:
        return []
    begin = (first_page, first.start())
    projects = project_occurrences(pages, sha)
    later = [(p["anchor"]["page_number"], p["anchor"]["text_start"]) for p in projects if (p["anchor"]["page_number"], p["anchor"]["text_start"]) > begin]
    limit = min(later) if later else (len(pages) + 1, 0)
    result = []
    for number in range(first_page, len(pages) + 1):
        text = pages[number - 1]
        if number > limit[0] or (number == limit[0] and limit[1] == 0):
            break
        if number > first_page and re.search(r"(?im)^[ \t]*ANEXOS?\b", text):
            break
        start = begin[1] if number == first_page else 0
        end = limit[1] if number == limit[0] else len(text)
        result.append((number, text[start:end]))
        if number == limit[0] or re.search(r"(?im)^[ \t]*Productos\s+y\s+evidencias\s+de\s+aprendizaje\b", text):
            break
    return result
