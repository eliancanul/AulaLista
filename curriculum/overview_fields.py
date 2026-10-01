"""Conservative page-local boundaries for explicitly labelled overview fields.

The parser preserves original slices. A bounded block is not automatically an
unambiguous title, and physical page breaks are never treated as soft wrapping.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from collections.abc import Iterator

from curriculum.vocabulary import CANONICAL_CAMPOS


_LABELS = {
    "proyecto": r"(?:Nombre\s+del\s+)?Proyecto(?:\s+de\s+diagn[oó]stico)?",
    "proposito": r"Prop[oó]sito(?:\s+para\s+el\s+alumno)?",
    "finalidad": r"Finalidad(?:\s+e\s+intenci[oó]n\s+did[aá]ctica\s+docente)?|Intenci[oó]n\s+did[aá]ctica(?:\s+docente)?",
    "barrier": (
        r"Productos?(?:\s+(?:final(?:es)?|esperados?|del\s+proyecto))?|"
        r"Evaluaci[oó]n(?:\s+(?:formativa|final|del\s+proyecto))?|"
        r"Campos?(?:\s+formativos?)?|Contenidos?|Ejes?(?:\s+articuladores)?|"
        r"Metodolog[ií]a|Escenario|Temporalidad|Tiempo\s+de\s+aplicaci[oó]n|"
        r"Duraci[oó]n\s+del\s+proyecto|Fase|Grado|SESI[OÓ]N|"
        r"Materiales(?:\s+(?:educativos|did[aá]cticos))?|Recursos(?:\s+did[aá]cticos)?|"
        r"Instrumentos?(?:\s+de\s+evaluaci[oó]n)?|PDA|"
        r"Procesos?\s+de\s+desarrollo(?:\s+de\s+aprendizajes?)?|"
        r"Ajustes(?:\s+razonables)?|Observaciones|Anexos?|"
        r"DESARROLLO\s+DEL\s+PROYECTO|Inicio|Desarrollo|Cierre"
    ),
}
_LABEL_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(f"(?P<{key}>{pattern})" for key, pattern in _LABELS.items()) + r")(?!\w)",
    re.IGNORECASE,
)
_QUOTE_PAIRS = {'"': '"', '«': '»', '“': '”'}
_COLON_RE = re.compile(r"[ \t\u00a0]*:")
_EMPTY_TAIL_RE = re.compile(r"[ \t\r]*$")
_SCENARIO_RE = re.compile(r"[ \t]+(?:Aula|Escolar|Comunitario)\.?[ \t\r]*", re.IGNORECASE)
_METHOD_RE = re.compile(
    r"[ \t]+Aprendizaje[ \t]+(?:basado[ \t]+en[ \t]+"
    r"(?:problemas|proyectos(?:[ \t]+comunitarios)?|indagaci[oó]n)|servicio)"
    r"(?:[ \t]*\((?:ABP|ABPC|AS|STEAM)\))?\.?[ \t\r]*", re.IGNORECASE,
)
_CAMPO_FORMS = set()
for _name in CANONICAL_CAMPOS:
    _nfd = unicodedata.normalize("NFD", _name)
    _CAMPO_FORMS.update((_name, _nfd, "".join(c for c in _nfd if unicodedata.category(c) != "Mn")))
_CAMPO_NAME_RE = "(?:" + "|".join(re.escape(name).replace(r"\ ", r"[ \t]+") for name in sorted(_CAMPO_FORMS)) + ")"
_CAMPOS_ROW_RE = re.compile(
    rf"[ \t]+{_CAMPO_NAME_RE}(?:[ \t]*[,;/][ \t]*{_CAMPO_NAME_RE})*\.?[ \t\r]*", re.IGNORECASE,
)
_CURRICULUM_COLUMNS_RE = re.compile(
    r"[ \t]+Contenidos?(?:[ \t]+(?:PDA|Procesos?[ \t]+de[ \t]+desarrollo"
    r"(?:[ \t]+de[ \t]+aprendizajes?)?))?[ \t\r]*", re.IGNORECASE,
)
_NUMBERED_HEADER_RE = re.compile(r"[ \t]+#?\s*\d+(?=[ \t]*(?:[:.]|$))")
_LEGACY_SCENARIO_RE = re.compile(
    r"\bEscenario\b(?:[ \t]*:|[ \t]+(?:Aula|Escolar|Comunitario)\.?[ \t]*$|[ \t]*$)", re.IGNORECASE,
)


@dataclass(frozen=True)
class OverviewFieldSpan:
    name: str
    page_number: int
    excerpt: str
    ambiguous: bool
    termination: str
    text_start: int = 0
    value_start: int = 0
    text_end: int = 0
    occurrence: int = 1


def _advance_quotes(stack: list[str], text: str) -> None:
    for char in text:
        if stack and char == stack[-1]:
            stack.pop()
        elif char in _QUOTE_PAIRS:
            stack.append(_QUOTE_PAIRS[char])


def _quote_stack(text: str) -> list[str]:
    stack: list[str] = []
    _advance_quotes(stack, text)
    return stack


def _bare_metadata(label: str, page: str, start: int, end: int) -> bool:
    """Narrow compatibility with existing unpunctuated metadata rows."""
    if re.fullmatch(r"Escenario", label, re.IGNORECASE):
        return bool(_SCENARIO_RE.fullmatch(page, start, end))
    if re.fullmatch(r"Metodolog[ií]a", label, re.IGNORECASE):
        return bool(_METHOD_RE.fullmatch(page, start, end))
    if re.fullmatch(r"Campos?(?:\s+formativos?)?", label, re.IGNORECASE):
        return bool(_CAMPOS_ROW_RE.fullmatch(page, start, end) or _CURRICULUM_COLUMNS_RE.fullmatch(page, start, end))
    if re.fullmatch(r"(?:Fase|Grado|SESI[OÓ]N)", label, re.IGNORECASE):
        return bool(_NUMBERED_HEADER_RE.match(page, start, end))
    return False


def _headers(page: str) -> tuple[list[tuple[str, int, int]], list[int]]:
    headers = []
    candidates = []
    uncertain_positions = []
    quotes: list[str] = []
    quote_position = 0
    line_start = 0
    line_end = page.find("\n")
    if line_end < 0:
        line_end = len(page)
    content_start = line_start + len(page[line_start:line_end]) - len(page[line_start:line_end].lstrip())
    for match in _LABEL_RE.finditer(page):
        while match.start() > line_end:
            line_start = line_end + 1
            line_end = page.find("\n", line_start)
            if line_end < 0:
                line_end = len(page)
            line = page[line_start:line_end]
            content_start = line_start + len(line) - len(line.lstrip())
        _advance_quotes(quotes, page[quote_position:match.start()])
        quote_position = match.start()
        key = match.lastgroup
        label = match.group()
        at_line_start = match.start() == content_start
        tabular = page[max(line_start, match.start() - 1):match.start()] == "\t" or page[max(line_start, match.start() - 2):match.start()] == "  "
        # Preserve the source's established 'Proyecto Título Escenario Aula'.
        inline_scenario = (
            label.lower() == "escenario" and bool(candidates)
            and candidates[-1][0] == "proyecto" and candidates[-1][1] >= line_start
        )
        # Reuse the line boundary for ordinary labels. A label itself may wrap,
        # in which case find the end of its last physical line once.
        tail_end = line_end
        if match.end() > tail_end:
            tail_end = page.find("\n", match.end())
            if tail_end < 0:
                tail_end = len(page)
        if quotes:
            continue
        if not (at_line_start or tabular or inline_scenario):
            # A single space cannot distinguish a column from ordinary prose.
            # Preserve it, but do not silently certify an apparent labelled
            # second field inside an active overview value.
            if candidates and candidates[-1][0] != "barrier" and _COLON_RE.match(page, match.end(), tail_end):
                uncertain_positions.append(match.start())
            continue
        colon = _COLON_RE.match(page, match.end(), tail_end)
        standalone = bool(_EMPTY_TAIL_RE.match(page, match.end(), tail_end))
        legacy_project = (
            not colon and key == "proyecto" and at_line_start
            and _LEGACY_SCENARIO_RE.search(page, match.end(), tail_end)
        )
        bare = _bare_metadata(label, page, match.end(), tail_end)
        if not (colon or standalone or legacy_project or bare):
            if at_line_start or tabular:
                uncertain_positions.append(match.start())
            continue
        value_start = colon.end() if colon else match.end()
        numbered = bool(re.fullmatch(r"(?:Fase|Grado|SESI[OÓ]N)", label, re.IGNORECASE) and bare)
        weak = bool(bare and not (colon or standalone or legacy_project or inline_scenario or numbered))
        candidates.append((key, match.start(), value_start, tail_end, weak))

    # Bare metadata rows are weaker than labelled headers. Keep a consecutive
    # group only when its rows have no free continuation before the next strong
    # header. An objective also needs a sentence-ending cue before that group;
    # otherwise preserve its complete candidate for review rather than cutting.
    index = 0
    while index < len(candidates):
        candidate = candidates[index]
        if not candidate[4]:
            headers.append(candidate[:3])
            index += 1
            continue
        end = index
        while end < len(candidates) and candidates[end][4]:
            end += 1
        next_strong_start = candidates[end][1] if end < len(candidates) else len(page)
        group = candidates[index:end]
        has_continuation = any(
            page[row[3]:(group[position + 1][1] if position + 1 < len(group) else next_strong_start)].strip()
            for position, row in enumerate(group)
        )
        objective_end_is_clear = True
        if headers and headers[-1][0] in ("proposito", "finalidad"):
            preceding_value = page[headers[-1][2]:group[0][1]].rstrip()
            objective_end_is_clear = bool(re.search(r'''[.!?]["»”']?$''', preceding_value))
        if has_continuation or not objective_end_is_clear:
            uncertain_positions.extend(row[1] for row in group)
        else:
            headers.extend(row[:3] for row in group)
        index = end
    return headers, uncertain_positions


def iter_overview_spans(
    pages: list[str], *, has_later_pages: bool = False,
    extra_boundaries: dict[int, list[int]] | None = None,
) -> Iterator[OverviewFieldSpan]:
    """Yield every explicit occurrence in physical order, including empty labels.

    All excerpts are contiguous slices of one physical page. We do not silently
    infer that an unlabeled line on the next page continues a field.
    """
    for page_index, page in enumerate(pages):
        occurrences: dict[str, int] = {}
        headers, uncertain_positions = _headers(page)
        if extra_boundaries:
            positions = {start for _, start, _ in headers}
            headers.extend(("barrier", start, start) for start in extra_boundaries.get(page_index + 1, []) if start not in positions)
            headers.sort(key=lambda h: h[1])
        for index, (name, start, value_start) in enumerate(headers):
            if name == "barrier":
                continue
            next_start = headers[index + 1][1] if index + 1 < len(headers) else len(page)
            source_slice = page[value_start:next_start]
            raw_start = value_start + len(source_slice) - len(source_slice.lstrip())
            raw = source_slice.strip()
            termination = "header" if index + 1 < len(headers) else (
                "page_end" if page_index + 1 < len(pages) or has_later_pages else "document_end"
            )
            quoted_title = False
            if name == "proyecto" and raw:
                blank = re.search(r"\r?\n[ \t]*\r?\n", raw)
                if blank:
                    raw = raw[:blank.start()].rstrip()
                    termination = "blank_line"
                if raw[0] in _QUOTE_PAIRS:
                    title_quotes = [_QUOTE_PAIRS[raw[0]]]
                    for position in range(1, len(raw)):
                        _advance_quotes(title_quotes, raw[position])
                        if not title_quotes:
                            # A quoted phrase may only be part of a larger title.
                            # Never silently discard a suffix after its closing quote.
                            if not raw[position + 1:].strip():
                                if not raw[1:position].strip():
                                    raw = ""
                                quoted_title = True
                                termination = "quoted_title"
                            break
            ambiguous = (
                termination == "page_end" or bool(_quote_stack(raw))
                or any(raw_start <= pos < raw_start + len(raw) for pos in uncertain_positions)
            )
            if name == "proyecto" and not quoted_title:
                ambiguous = ambiguous or "\n" in raw or bool(re.search(
                    r"\b(?:de|del|la|el|los|las|y|e|o|u|para|con|por|en|a|un|una|unos|unas)$", raw, re.IGNORECASE,
                ))
            occurrences[name] = occurrences.get(name, 0) + 1
            yield OverviewFieldSpan(
                name, page_index + 1, raw, ambiguous, termination,
                start, raw_start, raw_start + len(raw), occurrences[name],
            )


def extract_overview_spans(pages: list[str], *, has_later_pages: bool = False) -> dict[str, OverviewFieldSpan]:
    """Compatibility projection: only the first explicit occurrence per field."""
    result = {}
    for span in iter_overview_spans(pages, has_later_pages=has_later_pages):
        result.setdefault(span.name, span)
    return result
