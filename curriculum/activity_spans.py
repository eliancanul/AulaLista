"""Conservative page-local listed activity spans inside explicit lesson moments.

This is layout-based proposal extraction, not pedagogical classification. Lists
outside labelled moments, quoted examples, resources and nested substeps are not
independent activities. It never infers an objective, domain, date or outcome.
"""
from __future__ import annotations

import re

from curriculum.overview_fields import _advance_quotes
from curriculum.vocabulary import CANONICAL_CAMPOS

_HORIZONTAL = r'[^\S\r\n\v\f\x85\x1c-\x1e\u2028\u2029]'
_MOMENT = re.compile(rf'^{_HORIZONTAL}*(Inicio|Desarrollo|Cierre|Tarea){_HORIZONTAL}*(?::|$)', re.I)
_BULLET = re.compile(rf'^({_HORIZONTAL}*)[-•*]{_HORIZONTAL}*(\S.*)$')
_LABELLED_ACTIVITY = re.compile(rf'^{_HORIZONTAL}*Actividad(?:{_HORIZONTAL}+[0-9]+|{_HORIZONTAL}+[A-Za-z](?={_HORIZONTAL}*[:.-])|{_HORIZONTAL}*:)', re.I)
# Both known operational sections and an explicit short colon heading close a
# list. A later moment may reopen it; words inside prose do not close a list.
_SECTION = re.compile(
    rf'^{_HORIZONTAL}*(?:(?:Recursos(?: did[aá]cticos)?|Materiales(?: did[aá]cticos)?|Evaluaci[oó]n|Productos?(?: del proyecto)?|'
    r'Evidencias(?: de aprendizaje)?|Aspectos(?: a evaluar)?|Adecuaciones(?: curriculares)?|'
    r'Anexos?|Contenidos?(?:/PDA)?|Campos?(?: formativos?)?|PDA|Prop[oó]sito|'
    r'Tiempo|Organizaci[oó]n|Tema(?: de la sesi[oó]n)?|Proyecto|Fase|DATOS GENERALES|'
    r'Vo\.\s*Bo\.|Firma(?: del docente)?)[ \t]*(?::|$))', re.I,
)
_GENERIC_HEADING = re.compile(r'^[^\W\d_][^:\n]{0,79}:[ \t]*[«“"]?[ \t]*$')
_STRONG_ACTIVITY_LABEL = re.compile(rf'^{_HORIZONTAL}*Actividad(?:{_HORIZONTAL}+[0-9A-Za-z]+)?{_HORIZONTAL}*[:.-]', re.I)
_SENTENCE_END = re.compile(r'[.!?][»”"\)\]]*$')

# These are source display separators only. Recognizing the label does NOT
# assign its curricular meaning to an activity or create a campo relationship.
_SUBSECTION = re.compile(
    r'^(?:(?:' + '|'.join(re.escape(name) for name in CANONICAL_CAMPOS) + r')[ \t]+[–—-][ \t]+.+|'
    r'Integraci[oó]n para el producto final)[ \t]*$', re.I,
)



def listed_activity_spans(text: str, *, context: dict | None = None, continuation_end: int = 0) -> list[tuple[int, int, str]]:
    """Return (start,end,description) with offsets into the unchanged segment."""
    spans = []
    context = context if context is not None else {}
    active = context.get('active', False)
    labelled = context.get('labelled', False)
    base_indent = context.get('base_indent')
    quotes = list(context.get('quotes', []))
    current_start = current_end = None
    content_start = None

    def flush():
        nonlocal current_start, current_end, content_start
        if current_start is not None:
            raw = text[content_start:current_end].strip()
            if len(raw) >= 3:
                spans.append((current_start, current_end, raw))
        current_start = current_end = content_start = None

    for match in re.finditer(r'[^\r\n]*(?:\r\n|\n|\r|$)', text):
        line = match.group().rstrip('\r\n')
        if not line:
            continue
        was_quoted = bool(quotes)
        _advance_quotes(quotes, line)
        if match.start() < continuation_end:
            continue
        if was_quoted:
            # An instruction may itself quote a multi-line title or question.
            # Preserve that continuation; a quoted block outside an instruction
            # still cannot start an activity, even when it contains bullets.
            if current_start is not None:
                current_end = match.start() + len(line.rstrip())
            continue
        if _MOMENT.match(line):
            flush()
            active, labelled, base_indent = True, False, None
            continue
        if _LABELLED_ACTIVITY.match(line) and (current_start is None or _STRONG_ACTIVITY_LABEL.match(line)
                                               or _SENTENCE_END.search(text[content_start:current_end].strip())):
            flush()
            labelled = True
            continue
        bullet = _BULLET.match(line)
        if not bullet and _SUBSECTION.match(line.strip()):
            flush()
            labelled, base_indent = False, None
            continue
        generic_heading = _GENERIC_HEADING.match(line.strip()) and (
            current_start is None or _SENTENCE_END.search(text[content_start:current_end].strip()))
        if not bullet and (_SECTION.match(line) or generic_heading):
            flush()
            active = False
            continue
        if not active or labelled:
            continue
        if bullet:
            indent = len(bullet.group(1).expandtabs(4))
            if base_indent is None or indent <= base_indent:
                flush()
                base_indent = indent
                # Exclude indentation, preserve bullet and exact original text.
                current_start = match.start() + len(bullet.group(1))
                content_start = match.start() + bullet.start(2)
            if current_start is not None:
                current_end = match.start() + len(line.rstrip())
        elif current_start is not None:
            # A bare quotation delimiter must not be added to the prior task.
            if line.strip() in {'«', '»', '“', '”', '"'}:
                flush()
            else:
                current_end = match.start() + len(line.rstrip())
    # A detached quote/section flushed after the last task must not let the
    # following page attach its prose to that already-finished task.
    tail_activity = current_start is not None
    flush()
    context.update(active=active, labelled=labelled, base_indent=base_indent, quotes=quotes,
                   tail_activity=tail_activity)
    return spans


def leading_activity_continuation(text: str, previous_description: str, context: dict) -> tuple[int, int] | None:
    """A non-final instruction may continue on an already admitted source page.

    Never creates/adopts a page or crosses a fresh structural heading. Closed
    sentences do not absorb unlabelled explanatory paragraphs from another page.
    """
    if not context.get('active') or context.get('labelled') or not context.get('tail_activity', True):
        return None
    complete = bool(_SENTENCE_END.search(previous_description.strip()))
    base_indent = context.get('base_indent')
    quotes = list(context.get('quotes', []))
    start = end = None
    for match in re.finditer(r'[^\r\n]*(?:\r\n|\n|\r|$)', text):
        line = match.group().rstrip('\r\n')
        if not line.strip():
            if start is not None and not quotes and _SENTENCE_END.search(text[start:end].strip()):
                next_line = next((part for part in text[match.end():].splitlines() if part.strip()), '')
                next_bullet = _BULLET.match(next_line)
                if not (next_bullet and base_indent is not None
                        and len(next_bullet.group(1).expandtabs(4)) > base_indent):
                    break
            continue
        quoted = bool(quotes)
        _advance_quotes(quotes, line)
        bullet = _BULLET.match(line)
        nested = (bullet is not None and base_indent is not None
                  and len(bullet.group(1).expandtabs(4)) > base_indent)
        if start is None and complete and not nested and not quoted:
            break
        preceding = previous_description if start is None else text[start:end]
        generic_heading = (_GENERIC_HEADING.match(line.strip())
                           and _SENTENCE_END.search(preceding.strip()))
        if not quoted and (_MOMENT.match(line) or (bullet and not nested) or _SECTION.match(line)
                           or generic_heading or _STRONG_ACTIVITY_LABEL.match(line)
                           or _SUBSECTION.match(line.strip()) or re.match(r'^\s*SESI[OÓ]N\b', line, re.I)):
            break
        if start is None:
            start = match.start() if nested else match.start() + len(line) - len(line.lstrip())
        end = match.start() + len(line.rstrip())
    return (start, end) if start is not None and end is not None else None
