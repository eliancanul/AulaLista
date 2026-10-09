"""Literal physical-page candidates for methodology and global project time.

These candidates are source observations, never class scheduling decisions.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class GeneralDetail:
    value: str
    fragments: list[tuple[int, str]]
    ambiguous: bool = False


_METHOD_LABEL = re.compile(r"\bMetodolog[ií]a(?:[ \t]+sugerida)?[ \t]*:?[ \t]*", re.IGNORECASE)
_BOUNDARY = re.compile(
    r"(?:^|\n|[ \t]{2,})[ \t]*(?:Tiempo\s+de\b|Campos?\b|Contenidos?\b|Escenario\b|"
    r"Ejes?\b|Prop[oó]sito\b|Finalidad\b|Temporalidad\b|Metodolog[ií]a\b|"
    r"Fase\b|DESARROLLO\b|Recursos(?:[ \t]+(?:e[ \t]+implicaciones|did[aá]cticos))?[ \t]*(?=:|\r?\n|$)|"
    r"Materiales(?:[ \t]+(?:educativos|did[aá]cticos))?[ \t]*(?=:|\r?\n|$)|"
    r"Evaluaci[oó]n(?:[ \t]+(?:formativa|final|del[ \t]+proyecto|de[ \t]+la[ \t]+fase))?[ \t]*(?=:|\r?\n|$)|Productos?\b|"
    r"Anexos?\b|Inicio\b|Cierre\b|Duraci[oó]n(?:\s+sugerida)?\s+del\s+proyecto\b|Sesi[oó]n\b|[-•–])|"
    r"[ \t]+Tiempo\s+de\b|[ \t]+(?:Metodolog[ií]a(?:[ \t]+sugerida)?|"
    r"Temporalidad|Recursos|Materiales|Evaluaci[oó]n|Escenario|Fase|Inicio|Desarrollo|Cierre)[ \t]*:", re.IGNORECASE,
)


def extract_methodology(pages: list[str]) -> GeneralDetail | None:
    for index, page in enumerate(pages):
        body = _BODY.search(page)
        label = next((
            match for match in _METHOD_LABEL.finditer(page, 0, body.start() if body else len(page))
            if _at_metadata_start(page, match.start()) or _same_duration_row(page, match.start())
        ), None)
        if not label:
            if body:
                return None
            continue
        boundary = _BOUNDARY.search(page, label.end())
        raw = page[label.end():boundary.start() if boundary else len(page)].strip()
        partial = bool(re.search(r"\b(?:de|en|para|con|por|a)$", raw, re.IGNORECASE))
        fragments = [(index + 1, raw)] if raw else []
        time_label = _DURATION_LABEL.search(page, label.end())
        adjacent_time_label = bool(
            time_label and boundary and not page[boundary.start():time_label.start()].strip()
        )
        continuation = _split_table_tail(pages, index, time_label) if adjacent_time_label else None
        if continuation and continuation[0]:
            fragments.append((index + 2, continuation[0]))
        elif not boundary and index + 1 < len(pages) and partial:
            next_page = pages[index + 1]
            next_boundary = _BOUNDARY.search(next_page)
            prefix = next_page[:next_boundary.start() if next_boundary else len(next_page)].strip()
            if prefix:
                fragments.append((index + 2, prefix))
        value = " ".join(re.sub(r"\s+", " ", text) for _, text in fragments)
        suggested = bool(re.search(r"sugerid[oa]", label.group(), re.IGNORECASE))
        if suggested and fragments:
            fragments[0] = (index + 1, page[label.start():boundary.start() if boundary else len(page)].strip())
        suggested_value = bool(re.search(
            r"\b(?:sugiere|sugerid[oa]|propone|propuest[oa])\b", raw, re.IGNORECASE,
        ))
        uncertain_heading = bool(re.search(
            r"(?:^|\n)[ \t]*(?:recursos|materiales|evaluaci[oó]n)\b", raw, re.IGNORECASE,
        ))
        return GeneralDetail(
            value=value,
            fragments=fragments,
            ambiguous=bool(
                (not boundary and index + 1 < len(pages)) or suggested or suggested_value
                or uncertain_heading or len(fragments) > 1 or len(raw) > 150 or partial
            ),
        )
    return None


_DURATION_LABEL = re.compile(
    r"\b(?:Tiempo\s+de(?:\s+aplicaci[oó]n)?|Duraci[oó]n(?:\s+sugerida)?\s+del\s+proyecto|Temporalidad)(?:[ \t]+sugerid[oa])?[ \t]*:?[ \t]*",
    re.IGNORECASE,
)


def extract_project_duration(pages: list[str]) -> GeneralDetail | None:
    for index, page in enumerate(pages):
        body = _BODY.search(page)
        label = next((
            match for match in _DURATION_LABEL.finditer(page, 0, body.start() if body else len(page))
            if _at_metadata_start(page, match.start()) or _same_method_row(page, match.start())
        ), None)
        if not label:
            if body:
                return None
            continue
        boundary = _BOUNDARY.search(page, label.end())
        raw = page[label.end():boundary.start() if boundary else len(page)].strip()
        fragments = [(index + 1, raw)] if raw else []
        continuation = _split_table_tail(pages, index, label) if not boundary else None
        if continuation and continuation[1]:
            fragments.append((index + 2, continuation[1]))
        elif not boundary and index + 1 < len(pages):
            next_page = pages[index + 1]
            next_boundary = _BOUNDARY.search(next_page)
            prefix = next_page[:next_boundary.start() if next_boundary else len(next_page)].strip()
            if (
                not _TIME_UNIT.search(raw) and _DURATION_START.match(prefix)
                or re.match(r"(?:o|y|seg[uú]n|hasta|aproximadamente)\b", prefix, re.IGNORECASE)
            ):
                fragments.append((index + 2, prefix))
        value = " ".join(re.sub(r"\s+", " ", text) for _, text in fragments)
        if not raw and fragments:
            fragments.insert(0, (index + 1, label.group().strip()))
        suggested = bool(re.search(r"sugerid[oa]", label.group(), re.IGNORECASE))
        if suggested and fragments:
            fragments[0] = (index + 1, page[label.start():boundary.start() if boundary else len(page)].strip())
        return GeneralDetail(
            value=value,
            fragments=fragments,
            ambiguous=bool(suggested or len(fragments) > 1 or continuation or not _FIXED_TIME.fullmatch(raw)),
        )
    return None


def _split_table_tail(pages: list[str], index: int, label: re.Match) -> tuple[str, str] | None:
    """An unfinished time label may resume in the next physical header.

    Preserve the two column fragments as candidates, never as one PDF quote.
    """
    if index + 1 >= len(pages) or not re.fullmatch(r"Tiempo\s+de\s*:?[ \t]*", label.group(), re.IGNORECASE):
        return None
    next_page = pages[index + 1]
    continuation = re.search(r"\baplicaci[oó]n\s*:?[ \t]*", next_page, re.IGNORECASE)
    if not continuation or continuation.start() > 256:
        return None
    prefix = next_page[:continuation.start()]
    if prefix.count("\n") > 2 or _BOUNDARY.search(prefix):
        return None
    boundary = _BOUNDARY.search(next_page, continuation.end())
    suffix = next_page[continuation.end():boundary.start() if boundary else len(next_page)].strip()
    if not _DURATION_START.match(suffix):
        return None
    return prefix.strip(), suffix


_TIME_UNIT = re.compile(
    r"\b(?:minutos?|horas?|d[ií]as?|semanas?|mes(?:es)?|bimestres?|trimestres?|"
    r"cuatrimestres?|semestres?|a[nñ]os?|ciclos?)\b", re.IGNORECASE,
)


_QUANTITY = r"(?:\d{1,3}|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte)"
_FIXED_TIME = re.compile(
    rf"{_QUANTITY}(?:\s*(?:a|-|y)\s*{_QUANTITY})?\s+{_TIME_UNIT.pattern}"
    r"(?:\s+(?:lectiv[oa]s?|h[aá]biles?|naturales?))?\.?", re.IGNORECASE,
)


_BODY = re.compile(
    r"^[ \t]*(?:DESARROLLO(?:[ \t]+DEL[ \t]+PROYECTO)?\b|"
    r"Fase[ \t]*(?:#[ \t]*\d+|\d+[ \t]*[.:])|Sesi[oó]n[ \t]+\d+\b|Anexos?\b)",
    re.IGNORECASE | re.MULTILINE,
)


def _at_metadata_start(page: str, position: int) -> bool:
    prefix = page[page.rfind("\n", 0, position) + 1:position]
    return not prefix.strip() or prefix.endswith(("  ", "\t"))


def _same_method_row(page: str, position: int) -> bool:
    prefix = page[page.rfind("\n", 0, position) + 1:position]
    return bool(_METHOD_LABEL.match(prefix.lstrip()))


def _same_duration_row(page: str, position: int) -> bool:
    prefix = page[page.rfind("\n", 0, position) + 1:position]
    return bool(_DURATION_LABEL.match(prefix.lstrip()))


_DURATION_START = re.compile(
    rf"(?:(?:se\s+sugiere|aproximadamente|de|a)\s+)?(?:{_QUANTITY}\s+)?{_TIME_UNIT.pattern}",
    re.IGNORECASE,
)
