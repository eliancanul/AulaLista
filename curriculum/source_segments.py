"""Page-local text anchors and shared structural boundaries for extraction/audit.

Offsets address Python character positions in pypdf's extracted page text, not
PDF coordinates. Every verification recomputes these slices from the source.
Project proximity is a reviewable interpretation, never a membership claim.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from curriculum.overview_fields import (
    iter_overview_spans, is_curriculum_columns_header, _headers, _quote_stack, _advance_quotes,
)
from curriculum.vocabulary import CANONICAL_CAMPOS

ANCHOR_SCHEMA_VERSION = 1
PROJECT_CONTEXT_SCHEMA_VERSION = 1
_DAYS = r"Lunes|Martes|Miércoles|Miercoles|Jueves|Viernes"
# Preserve the legacy spacing class for existing entities and safety cuts.
# Only the newly admitted wrapped form uses the stricter physical-line class.
_H = r"[^\S\r\n\v\f\x85\u2028\u2029]"
_WRAPPED_H = r"[^\S\r\n\v\f\x85\x1c-\x1e\u2028\u2029]"
_SESSION_WORD = r"SESI[OÓ]\u0301?N"
# Only a standalone positive number followed immediately by a labelled moment
# corroborates this wrapped form. Keep unknown titles, lists, dates and other
# line separators as safety cuts, without creating a session from them.
_WRAPPED_SESSION_SEPARATOR = (
    rf"{_WRAPPED_H}*\r?\n(?={_WRAPPED_H}*0*[1-9][0-9]*{_WRAPPED_H}*\r?\n"
    rf"{_WRAPPED_H}*(?:Inicio|Desarrollo|Cierre)(?={_WRAPPED_H}*(?::|\r?$))){_WRAPPED_H}*"
)
_SESSION_RE = re.compile(
    rf"^{_H}*((?:({_DAYS}){_H}*[-–—]?{_H}*)?{_SESSION_WORD}"
    rf"(?:{_H}*|{_WRAPPED_SESSION_SEPARATOR})(0*[1-9][0-9]*)"
    rf"(?={_H}*(?:[:.]|\r?$)){_H}*(?:[:.]{_H}*([^\n\r\u2028\u2029]*))?)",
    re.IGNORECASE | re.MULTILINE,
)
# Additional format admission is intentionally independent of the legacy regex.
# A same-line labelled date plus a following labelled moment corroborates a
# planning unit; a prose mention/date/number alone never creates one. Date text
# is kept literal; this does not infer a calendar date, duration or curriculum.
_DATED_SESSION_RE = re.compile(
    rf"^{_H}*((?:({_DAYS}){_H}*[-–—]?{_H}*)?{_SESSION_WORD}"
    rf"{_WRAPPED_H}+(0*[1-9][0-9]*){_WRAPPED_H}+Fecha{_WRAPPED_H}*:{_WRAPPED_H}*"
    rf"(?:(?:{_DAYS}){_WRAPPED_H}+)?(?:0?[1-9]|[12][0-9]|3[01])"
    rf"(?={_WRAPPED_H}|[/.-]|\r?$)[^\n\r\u2028\u2029]*())",
    re.IGNORECASE | re.MULTILINE,
)
_PARTIAL_DATED_SESSION_RE = re.compile(
    rf"^{_H}*((?:({_DAYS}){_H}*[-–—]?{_H}*)?{_SESSION_WORD}"
    rf"{_WRAPPED_H}+(0*[1-9][0-9]*){_WRAPPED_H}+Fecha{_WRAPPED_H}*:{_WRAPPED_H}*"
    rf"(?:{_DAYS})(?={_WRAPPED_H}*(?:Tema\b|Tiempo\b|Organizaci[oó]n\b|\r?$))[^\n\r\u2028\u2029]*())",
    re.IGNORECASE | re.MULTILINE,
)
_MOMENT_LABEL_RE = re.compile(
    rf"^{_H}*(?:Inicio|Desarrollo|Cierre){_H}*(?::|\r?$)",
    re.IGNORECASE | re.MULTILINE,
)
_DAY_RE = re.compile(
    rf"^{_H}*(({_DAYS})(?:{_H}*:{_H}*[^\n\r]+|{_H}*\r?$)"
    rf"(?:\n{_H}*\d+{_H}+de{_H}+[^\n\r]+)?)", re.IGNORECASE | re.MULTILINE,
)
_UNRESOLVED_SESSION_RE = re.compile(
    rf"^{_H}*((?:({_DAYS}){_H}*[-–—]?{_H}*)?{_SESSION_WORD}\s*[0-9]+\b)",
    re.IGNORECASE | re.MULTILINE,
)

_WEAK_DAY_RE = re.compile(rf"^{_H}*((?:{_DAYS})\b)", re.IGNORECASE | re.MULTILINE)
_WEAK_PROJECT_RE = re.compile(
    rf"^{_H}*((?:Nombre{_H}+del{_H}+)?Proyecto(?:{_H}+de{_H}+diagn[oó]stico)?)"
    rf"(?={_H}*(?::|\r?$))", re.IGNORECASE | re.MULTILINE,
)
_GENERAL_DATA_RE = re.compile(
    rf"^{_H}*(DATOS{_H}+GENERALES){_H}*:?[ \t\r]*$", re.IGNORECASE | re.MULTILINE,
)
_CAMPO_LABEL_RE = re.compile(r"Campos?\s+formativos?\s*:?[ \t\r]*$", re.IGNORECASE)
_INTENTION_LABEL_RE = re.compile(
    r"(?:Finalidad\s+e\s+)?Intenci[oó]n\s+did[aá]ctica(?:\s+docente)?\s*:?[ \t\r]*$", re.IGNORECASE,
)
_BODY_LABEL_RE = re.compile(
    rf"^{_H}*(?:{_SESSION_WORD}\b|(?:{_DAYS})(?={_H}*(?::|\r?$))|"
    rf"(?:Inicio|Desarrollo|Cierre|Actividad|Fase)(?={_H}*(?::|\d|\r?$))|DESARROLLO{_H}+DEL{_H}+PROYECTO\b)",
    re.IGNORECASE | re.MULTILINE,
)
_PHASE_ANNEX_RE = re.compile(r"(?im)^[ \t]*ANEXOS?\b")
_PHASE_END_RE = re.compile(r"(?im)^[ \t]*Productos\s+y\s+evidencias\s+de\s+aprendizaje\b")


def _normalized_campo_names(text: str) -> tuple[str, ...]:
    """Accept only complete known labels, never a prose mention of a campo."""
    def normalize(value):
        return re.sub(r"\s+", " ", "".join(
            c for c in unicodedata.normalize("NFD", value.casefold()) if unicodedata.category(c) != "Mn"
        )).strip()

    remaining = normalize(text)
    names = []
    for name in CANONICAL_CAMPOS:
        normalized = normalize(name)
        if normalized in remaining:
            names.append(normalized)
            remaining = remaining.replace(normalized, "")
    return tuple(sorted(names)) if names and not remaining.strip(" ,;/.\t") else ()


def _closed_quote_ranges(page: str) -> list[tuple[int, int]]:
    """Balanced prose quotes may suppress cues; an open quote cannot hide scope."""
    ranges = []
    stack: list[str] = []
    begin = 0
    for position, char in enumerate(page):
        was_open = bool(stack)
        _advance_quotes(stack, char)
        if not was_open and stack:
            begin = position
        elif was_open and not stack:
            ranges.append((begin, position + 1))
    return ranges


def planning_boundary_positions(pages: list[str]) -> dict[int, list[int]]:
    """Safety cuts for a changed, untitled planning block; never new entities.

    Require prior activity plus three page-local structural cues in order:
    DATOS GENERALES, an explicit changed campo, and INTENCIÓN DIDÁCTICA.
    A repeated table header with the same campo, isolated words, balanced quotes,
    unknown campo values, or cues separated by an activity are not enough.
    This narrow development rule is not a general PDF/table reconstruction.
    """
    result = {number: [] for number in range(1, len(pages) + 1)}
    previous_campo: tuple[str, ...] = ()
    had_body = False
    for number, page in enumerate(pages, 1):
        closed_quotes = _closed_quote_ranges(page)

        def is_quoted(position):
            return any(begin <= position < end for begin, end in closed_quotes)

        # Ordinary overview/entity extraction still filters all quoted headers.
        # A safety cut must also see through an incomplete quote, but preserves
        # the balanced-quotation negative control instead of treating it as data.
        headers, _ = _headers(page, include_quoted=True)
        headers = [h for h in headers if not is_quoted(h[1])]
        data_starts = [m.start(1) for m in _GENERAL_DATA_RE.finditer(page) if not is_quoted(m.start(1))]
        body_starts = [m.start() for m in _BODY_LABEL_RE.finditer(page) if not is_quoted(m.start())]
        events = [(p, "data", ()) for p in data_starts] + [(p, "body", ()) for p in body_starts]
        for index, (kind, start, value_start) in enumerate(headers):
            label = page[start:value_start].strip()
            if kind == "proyecto":
                events.append((start, "project", ()))
            # Only line-start metadata qualifies; a tabular/prose mention is
            # insufficient to reset the sequence's inherited context.
            if page[page.rfind("\n", 0, start) + 1:start].strip():
                continue
            if _CAMPO_LABEL_RE.fullmatch(label):
                if is_curriculum_columns_header(page, start, value_start):
                    # A table's column names do not replace the last actual
                    # campo value or disable a later planning-reset safety cut.
                    continue
                stops = [headers[index + 1][1]] if index + 1 < len(headers) else []
                stops.extend(p for p in data_starts + body_starts if p > start)
                end = min(stops) if stops else len(page)
                events.append((start, "campo", _normalized_campo_names(page[value_start:end])))
            elif kind == "finalidad" and _INTENTION_LABEL_RE.fullmatch(label):
                events.append((start, "intention", ()))
        events.sort()
        for index, (start, kind, campo) in enumerate(events):
            if kind == "body":
                had_body = True
            elif kind == "project":
                # Metadata belonging to a new explicit project must not erase
                # its title using activity state inherited from an older one.
                had_body = False
            elif kind == "campo":
                previous_campo = campo
            elif kind == "data" and had_body and previous_campo:
                candidate_campo = ()
                for _, next_kind, next_campo in events[index + 1:]:
                    if next_kind in ("data", "body", "project"):
                        break
                    if next_kind == "campo":
                        candidate_campo = next_campo
                    elif next_kind == "intention":
                        if candidate_campo and candidate_campo != previous_campo:
                            result[number].append(start)
                        break
    return result


def session_boundary_positions(pages: list[str], *, include_quoted: bool = False) -> dict[int, list[int]]:
    """Possible numbered headers cut scope, but unknown formats create no unit.

    The deliberately broader safety detector can see wrapped/unknown headings
    or prose such as 'SESIÓN 2 del cuento'. It only abstains/cuts; it never
    infers a session from them or certifies whole-page membership.
    """
    return {
        number: [m.start(1) for m in _UNRESOLVED_SESSION_RE.finditer(page) if include_quoted or not _quote_stack(page[:m.start()])]
        for number, page in enumerate(pages, 1)
    }


def has_possible_session_structure(pages: list[str]) -> bool:
    """Safety only: quotes/unknown layouts cannot license whole-page scope."""
    return any(session_boundary_positions(pages, include_quoted=True).values()) or any(
        _WEAK_DAY_RE.search(page) for page in pages
    )


def safety_boundary_positions(pages: list[str]) -> dict[int, list[int]]:
    """Unfiltered conservative scope barriers, distinct from entity extraction.

    A source quote can suppress a candidate entity, but cannot enlarge another
    entity's verified scope. Unknown day formats are only relevant when there
    are no possible numbered headers, matching the existing day-only mode.
    """
    result = session_boundary_positions(pages, include_quoted=True)
    planning = planning_boundary_positions(pages)
    day_only = not any(result.values())
    for number, page in enumerate(pages, 1):
        result[number].extend(planning[number])
        result[number].extend(m.start(1) for m in _WEAK_PROJECT_RE.finditer(page))
        if day_only:
            result[number].extend(m.start(1) for m in _WEAK_DAY_RE.finditer(page))
        result[number] = sorted(set(result[number]))
    return result


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
    numbered = []
    for page_index, page in enumerate(pages):
        matches = list(_SESSION_RE.finditer(page))
        cuts = sorted({m.start(1) for pattern in (_UNRESOLVED_SESSION_RE, _WEAK_PROJECT_RE, _GENERAL_DATA_RE)
                       for m in pattern.finditer(page)})
        for candidate in [*_DATED_SESSION_RE.finditer(page), *_PARTIAL_DATED_SESSION_RE.finditer(page)]:
            end = next((pos for pos in cuts if pos > candidate.start(1)), len(page))
            # Require corroboration in this physical block, never borrow a
            # moment from the following session/project or a quoted example.
            corroborated = any(not _quote_stack(page[:moment.start()])
                               for moment in _MOMENT_LABEL_RE.finditer(page, candidate.end(1), end))
            if candidate.re is _PARTIAL_DATED_SESSION_RE:
                # A weekday without a day number stays a partial date, never
                # filled in. Its header needs richer planning corroboration.
                block = page[candidate.end(1):end]
                metadata = {label.casefold().replace("ó", "o") for label in re.findall(
                    r"(?im)^[ \t]*(Campo|Contenidos/PDA|Tiempo|Organizaci[oó]n)[ \t]*:", block)}
                corroborated = corroborated and len(metadata) >= 2 and bool(re.search(
                    r"(?im)^[ \t]*Descripci[oó]n de actividades[ \t]*:", block))
            if not corroborated and candidate.re is _DATED_SESSION_RE and end == len(page) and page_index + 1 < len(pages):
                # Narrow footer continuation: at least two distinct labelled
                # planning metadata fields and an explicit activity-section
                # label followed by a moment on the immediate next-page prefix.
                # Date/index mentions cannot borrow arbitrary following prose.
                metadata = {label.casefold().replace("ó", "o") for label in re.findall(
                    r"(?im)^[ \t]*(Campo|Contenidos/PDA|Tiempo|Organizaci[oó]n)[ \t]*:",
                    page[candidate.end(1):end],
                )}
                following = pages[page_index + 1]
                next_cuts = [m.start(1) for pattern in (_UNRESOLVED_SESSION_RE, _WEAK_PROJECT_RE, _GENERAL_DATA_RE)
                             for m in pattern.finditer(following)]
                prefix = following[:min(next_cuts)] if next_cuts else following
                section = re.search(r"(?im)^[ \t]*Descripci[oó]n de actividades[ \t]*:[ \t]*$", prefix)
                if len(metadata) >= 2 and section:
                    corroborated = any(not _quote_stack(page + "\n" + prefix[:moment.start()])
                                       for moment in _MOMENT_LABEL_RE.finditer(prefix, section.end()))
                elif re.search(r"\bTiempo[ \t]*:", candidate.group(1), re.I):
                    # Some planning tables split immediately after the dated
                    # header. Require both phase and purpose labels before the
                    # first next-page moment, never just an unrelated Inicio.
                    for moment in _MOMENT_LABEL_RE.finditer(prefix):
                        before = prefix[:moment.start()]
                        if (re.search(r"(?im)^[ \t]*Fase[ \t]*:", before)
                                and re.search(r"(?im)^[ \t]*Prop[oó]sito[ \t]*:", before)
                                and not _quote_stack(page + "\n" + before)):
                            corroborated = True
                            break
            if corroborated:
                matches.append(candidate)
        numbered.append(sorted((m for m in matches if not _quote_stack(page[:m.start()])), key=lambda m: m.start(1)))
    if any(numbered) or any(session_boundary_positions(pages).values()):
        return True, numbered
    return False, [[m for m in _DAY_RE.finditer(page) if not _quote_stack(page[:m.start()])] for page in pages]


def project_occurrences(pages: list[str], sha: str) -> list[dict[str, Any]]:
    result = []
    _, headers = _session_headers(pages)
    extra = session_boundary_positions(pages)
    for number, matches in enumerate(headers, 1):
        extra[number] = sorted(set(extra[number] + [m.start(1) for m in matches]))
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


def context_before(
    projects: list[dict[str, Any]], page_number: int, text_start: int,
    planning_boundaries: dict[int, list[int]] | None = None,
) -> dict[str, Any]:
    preceding = [p for p in projects if (p["anchor"]["page_number"], p["anchor"]["text_start"]) < (page_number, text_start)]
    resets = [(number, pos) for number, positions in (planning_boundaries or {}).items()
              for pos in positions if (number, pos) < (page_number, text_start)]
    if resets and (not preceding or max(resets) > (preceding[-1]["anchor"]["page_number"], preceding[-1]["anchor"]["text_start"])):
        context = missing_project_context()
        context["reason"] = (
            "Un reinicio de datos generales con cambio de campo formativo e intención didáctica "
            "interrumpe el contexto anterior; no hay un encabezado de proyecto posterior al corte. "
            "El límite propuesto requiere revisión; no se infiere otro proyecto."
        )
        return context
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
    unassigned_segments: list[tuple[int, str]] = field(default_factory=list)


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
    planning = planning_boundary_positions(pages)
    # A quoted session label is prose, even when its line begins with SESIÓN.
    use_numbered, headers = _session_headers(pages)
    segments = []
    counts: dict[str, int] = {}
    boundaries = safety_boundary_positions(pages)
    strong_boundaries: dict[int, set[int]] = {}
    for project in projects:
        anchor = project["anchor"]
        boundaries.setdefault(anchor["page_number"], []).append(anchor["text_start"])
        strong_boundaries.setdefault(anchor["page_number"], set()).add(anchor["text_start"])
    for page_number, page in enumerate(pages, 1):
        matches = headers[page_number - 1]
        for occurrence, m in enumerate(matches, 1):
            start, end = m.span(1)
            day = (m.group(2) or "").capitalize()
            try:
                # Keep arbitrarily padded source labels literal in the anchor,
                # while avoiding Python's string-to-int limit for their zeros.
                number = int(m.group(3).lstrip("0")) if use_numbered else occurrence
            except ValueError:
                # An unconvertible number remains a weak boundary with its
                # original text; malformed input must not abort extraction.
                continue
            title = (m.group(4) or "") if use_numbered else day
            title = re.sub(r"\s*Recursos:?.*$", "", title, flags=re.IGNORECASE).strip()
            base = f"p{page_number}_s{number}"
            counts[base] = counts.get(base, 0) + 1
            sid = base if counts[base] == 1 else f"{base}_{counts[base]}"
            segments.append(SessionSegment(
                sid, number, title or f"Sesión {number}", day,
                text_anchor(page, sha, page_number, occurrence, start, end, "session" if use_numbered else "day"),
                context_before(projects, page_number, start, planning),
            ))
            boundaries.setdefault(page_number, []).append(start)
            strong_boundaries.setdefault(page_number, set()).add(start)

    def retain_unassigned(segment: SessionSegment, page_number: int, start: int) -> None:
        next_strong = [p for p in strong_boundaries.get(page_number, set()) if p > start]
        end = min(next_strong) if next_strong else len(pages[page_number - 1])
        segment.unassigned_segments.append((page_number, pages[page_number - 1][start:end]))

    for segment in segments:
        anchor = segment.header_anchor
        page_number, start = anchor["page_number"], anchor["text_start"]
        page = pages[page_number - 1]
        following = sorted(b for b in boundaries.get(page_number, []) if b > start)
        end = following[0] if following else len(page)
        segment.page_segments = [(page_number, page[start:end])]
        if following and end not in strong_boundaries.get(page_number, set()):
            retain_unassigned(segment, page_number, end)
        if following or page_number >= len(pages):
            continue
        # Preserve the existing immediate-next-page-only continuation contract.
        # A project boundary cuts the candidate prefix just like a session.
        next_boundaries = boundaries.get(page_number + 1, [])
        next_page = pages[page_number]
        prefix = next_page[:min(next_boundaries)] if next_boundaries else next_page
        if next_boundaries and min(next_boundaries) not in strong_boundaries.get(page_number + 1, set()):
            retain_unassigned(segment, page_number + 1, min(next_boundaries))
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


def first_phase_review_page(pages: list[str]) -> int | None:
    """The single phase-review unit admitted by the existing source detector."""
    return next(
        (number for number, text in enumerate(pages, 1)
         if re.search(r"(?:^|\n)\s*DESARROLLO\s+DEL\s+PROYECTO\b", text, re.IGNORECASE)
         and re.search(r"(?:^|\n)\s*Fase\s*#?\s*1\b", text, re.IGNORECASE)),
        None,
    )


def phase_project_context(pages: list[str], sha: str, first_page: int) -> dict[str, Any]:
    page = pages[first_page - 1]
    start = re.search(rf"(?im)^{_H}*DESARROLLO\s+DEL\s+PROYECTO\b", page)
    return context_before(project_occurrences(pages, sha), first_page, start.start() if start else 0, planning_boundary_positions(pages))


def project_context_matches(value: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value != expected:
        return False
    anchor = expected["anchor"]
    return anchor_matches(value.get("anchor"), anchor) if anchor is not None else value.get("anchor") is None


def phase_review_segments(pages: list[str], sha: str, first_page: int) -> list[tuple[int, str]]:
    """Bound the existing phase-review unit at the next project/planning reset."""
    return phase_review_scope(pages, sha, first_page)[0]


def phase_review_scope(
    pages: list[str], sha: str, first_page: int,
) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return phase text and a literal unassigned planning reset for review."""
    first = re.search(rf"(?im)^{_H}*DESARROLLO\s+DEL\s+PROYECTO\b", pages[first_page - 1])
    if not first:
        return [], []
    begin = (first_page, first.start())
    projects = project_occurrences(pages, sha)
    later = [(p["anchor"]["page_number"], p["anchor"]["text_start"]) for p in projects if (p["anchor"]["page_number"], p["anchor"]["text_start"]) > begin]
    planning = [(number, pos) for number, positions in planning_boundary_positions(pages).items()
                for pos in positions if (number, pos) > begin]
    later.extend(planning)
    limit = min(later) if later else (len(pages) + 1, 0)
    result = []
    reached_limit = False
    for number in range(first_page, len(pages) + 1):
        text = pages[number - 1]
        if number > limit[0] or (number == limit[0] and limit[1] == 0):
            reached_limit = True
            break
        if number > first_page and _PHASE_ANNEX_RE.search(text):
            break
        start = begin[1] if number == first_page else 0
        end = limit[1] if number == limit[0] else len(text)
        result.append((number, text[start:end]))
        if number == limit[0]:
            reached_limit = True
            break
        if _PHASE_END_RE.search(text):
            break
    unassigned = []
    if reached_limit and limit in planning:
        next_projects = [(p["anchor"]["page_number"], p["anchor"]["text_start"]) for p in projects
                         if (p["anchor"]["page_number"], p["anchor"]["text_start"]) > limit]
        unassigned_end = min(next_projects) if next_projects else (len(pages) + 1, 0)
        for number in range(limit[0], len(pages) + 1):
            text = pages[number - 1]
            # Preserve only text removed by this reset, respecting the phase
            # unit's pre-existing annex/product stops on these source pages.
            if number > first_page and _PHASE_ANNEX_RE.search(text):
                break
            start = limit[1] if number == limit[0] else 0
            if (number, start) >= unassigned_end:
                break
            end = unassigned_end[1] if number == unassigned_end[0] else len(text)
            unassigned.append((number, text[start:end]))
            if _PHASE_END_RE.search(text):
                break
    return result, unassigned
