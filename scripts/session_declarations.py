"""Detached, deterministic v1 candidates for literal session declarations.

Never imported by production. No PDF access, database, external provider, network,
dossier mutation or pedagogical approval. Default literal extraction is unchanged;
the explicit scope_audit option adds detached source-catalogue replay candidates.
See docs/development/session-declarations-contract.md and anchor-scope-audit-contract.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from curriculum.claims import AtomicClaim
from curriculum.overview_fields import _advance_quotes
from curriculum.source_interpreter import SourceReference
from curriculum.source_segments import (
    project_occurrences, safety_boundary_positions, scan_session_segments,
)
from curriculum.vocabulary import CANONICAL_CAMPOS

VERSION = 'session-declarations.v1'
MATCHER_VERSION = 'session-declarations-matcher.v3.1.2'
PREDICATES = {'contenido': 'contenido_declarado', 'pda': 'pda_declarado'}
MAX_CHARACTERS = 2_000_000
MAX_RECORDS = 2_000
H = r'[^\S\r\n]'
# Unicode horizontal whitespace only. Keep the older label grammar separate;
# the v2 numbered/container admissions must not join physical lines.
HORIZONTAL = r'[ \t\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]'
HORIZONTAL_ONLY = re.compile(rf'{HORIZONTAL}*')
VERTICAL = re.compile(r'[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]')
CONTENT = rf'Contenidos?(?:{H}+curricular(?:es)?)?'
LOCAL_CODE = r'[A-Za-z]{1,4}[0-9]{1,4}'
NUMBERED_PDA = rf'(?:{LOCAL_CODE}{HORIZONTAL}+)?PDA{HORIZONTAL}*[0-9]+'
PDA = rf'(?:{NUMBERED_PDA}|PDAs?|Procesos?{H}+de{H}+desarrollo{H}+de{H}+aprendizajes?(?:{H}*\(PDAs?\))?)'
COMBINED = rf'Contenidos?{H}*(?:/|y){H}*PDAs?'
LABEL = re.compile(rf'(?<!\w)(?P<label>{COMBINED}|{CONTENT}|{PDA})(?!\w)(?:{H}*:)?', re.I)
# Literal extraction alone gains Spanish local codes. Keep LABEL/PDA above
# frozen for the old marker and structural-scope proofs. Scoped case handling
# excludes Python re.I lookalikes (Kelvin sign, dotted I and long s), and the
# explicit decompositions count as one letter without normalizing source text.
LITERAL_CODE = (r'(?-i:(?:[AEIOUaeiou]\u0301|[Uu]\u0308|[Nn]\u0303|'
                r'[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]){1,4}[0-9]{1,4})')
LITERAL_NUMBERED_PDA = rf'(?:{LITERAL_CODE}{HORIZONTAL}+)?PDA{HORIZONTAL}*[0-9]+'
LITERAL_PDA = rf'(?:{LITERAL_NUMBERED_PDA}|PDAs?|Procesos?{H}+de{H}+desarrollo{H}+de{H}+aprendizajes?(?:{H}*\(PDAs?\))?)'
LITERAL_LABEL = re.compile(
    rf'(?<![\w\u0300-\u036f])(?P<label>{COMBINED}|{CONTENT}|{LITERAL_PDA})(?!\w)(?:{H}*:)?', re.I)
COMBINED_ONLY = re.compile(COMBINED, re.I)
HEADING = re.compile(
    r'^(?:Inicio|Desarrollo|Cierre|Tarea|Actividad(?:\s+\d+)?|'
    r'Campos?(?:\s+formativos?)?|Materiales(?:\s+did[aá]cticos)?|Recursos(?:\s+did[aá]cticos)?|'
    r'Evaluaci[oó]n|Productos?|Evidencias|Observaciones|Proyecto|DATOS GENERALES|'
    r'Tema(?:\s+de\s+la\s+sesi[oó]n)?|Objetivo|Prop[oó]sito|Finalidad|Tiempo|'
    r'Organizaci[oó]n|Fase|Anexos?|Metodolog[ií]a|Escenario|Grado|Temporalidad)\b\s*(?::|$)', re.I)
GENERIC_HEADING = re.compile(r'^[^\W\d_][^:\n]{0,79}:\s*$', re.UNICODE)
SESSION_OR_RESET = re.compile(r'^(?:SESI[OÓ]N\b|DATOS\s+GENERALES\b|(?:Nombre\s+del\s+)?Proyecto\s*:)', re.I)
CONTINUATION = re.compile(r'^Continuaci[oó]n\s+de\s+(?:la\s+)?sesi[oó]n\s+([1-9][0-9]*)\s*:?\s*$', re.I)
NEGATED = re.compile(r'^(?:No\s+(?:se\s+)?(?:trabaj|abord|aplic|inclu|contempl|correspon|selec)|'
                     r'No\s+(?:ser[aá](?:n)?|fue|fueron|es|son|est[aá](?:n)?)\s+'
                     r'(?:trabajad|abordad|aplicad|incluid|contemplad|seleccionad|adoptad|previst|programad)|'
                     r'Sin\s+(?:PDA|contenidos?)\b|Ning[uú]n\s+(?:PDA|contenido)\b)', re.I)
CONDITIONAL = re.compile(r'^(?:Si\s|En\s+caso\s+de\b|De\s+ser\s+posible\b|'
                         r'(?:Puede|Podr[ií]a)\s+(?:trabajarse|abordarse|incluirse)\b)', re.I)
NONAFFIRMATIVE = re.compile(r'^(?:Se\s+(?:sugiere|propone|recomienda)\b|Sugerid[oa]s?\b|'
                          r'Sugerencia\b|Propuest[oa]s?\b|Opcional\b|Tentativ[oa]\b|'
                          r'No\s+(?:definid[oa]|especificad[oa])\b|Se\s+omite\b|'
                          r'Pendiente\b|Por\s+definir\b|Posible\b)', re.I)
UNSPECIFIED = re.compile(r'^(?:N/?A|N\.A\.?|Ningun[oa]?|Ning[uú]n|Sin\s+(?:definir|especificar))[.!]?$', re.I)
SENTENCE_END = re.compile(r'[.!?][»”"\)\]]*$')
DANGLING_END = re.compile(r'(?:\b(?:y|e|o|u|de|del|para|con|en|a)|[,;:–—-])\s*$', re.I)
BULLET = re.compile(r'^(?:[-•*]|[0-9]+[.)])\s*\S')
MARKER_PREFIX = re.compile(rf'{HORIZONTAL}*-{HORIZONTAL}*')
PLANNING_META = re.compile(
    rf'^(?:Fecha|Tiempo|Duraci[oó]n|Tema{HORIZONTAL}+de{HORIZONTAL}+la{HORIZONTAL}+sesi[oó]n|'
    rf'Organizaci[oó]n|Campos?){HORIZONTAL}*:{HORIZONTAL}*(.*)$', re.I)
MOMENT = re.compile(rf'^{HORIZONTAL}*(Inicio|Desarrollo|Cierre){HORIZONTAL}*(?::|$)', re.I)
SCAFFOLD_ACTIVITY = re.compile(rf'^(?:[-+•*◦]|[0-9]+[.)]){HORIZONTAL}*\S')
SCAFFOLD_INLINE_CUT = re.compile(
    rf'\b(?:(?:Inicio|Desarrollo|Cierre|(?:Nombre{HORIZONTAL}+del{HORIZONTAL}+)?Proyecto){HORIZONTAL}*:'
    rf'|DATOS{HORIZONTAL}+GENERALES\b|SESI[OÓ]N{HORIZONTAL}*[0-9]+\b)', re.I)
FIELD_LABEL = re.compile(rf'^Campos?(?:{HORIZONTAL}+formativos?)?{HORIZONTAL}*:{HORIZONTAL}*(.*)$', re.I | re.A)
FIELD_NAMES = {name.lower() for name in CANONICAL_CAMPOS}
CODE_ROW = re.compile(rf'^{LITERAL_CODE}{HORIZONTAL}+(?P<description>.+)$')
EXAMPLE_BLOCK = re.compile(r'^(?:Ejemplos?\b|Propuesta\b|Sugerencia\b|No\s+adoptad[oa]\b)', re.I)
CODE_ROW_CUT = re.compile(
    r'\b(?:Ejemplos?|Propuestas?|Sugerencias?|No\s+adoptad[oa]s?|'
    r'Inicio|Desarrollo|Cierre|Actividades?|Actividad)\b', re.I)


def snapshot_hash(pages):
    return hashlib.sha256(json.dumps(list(pages), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _ref(pages, source, page, start, end, role):
    return SourceReference(document_sha256=source, page_number=page,
                           excerpt=pages[page - 1][start:end],
                           region={'kind': 'text_offsets', 'start': start, 'end': end}, role=role).to_dict()


def _lines(page):
    return [(m.start(), m.end(), m.group().rstrip('\r\n'))
            for m in re.finditer(r'[^\r\n]*(?:\r\n|\n|\r|$)', page) if m.group()]


def _bare_header(line):
    stripped = line.strip()
    return bool(re.fullmatch(r'Campos?(?:\s+formativos?)?', stripped, re.I)
                or re.fullmatch(rf'(?:{CONTENT}|{PDA})', stripped, re.I))


def _table_lines(lines):
    marked = set()
    for i in range(len(lines) - 2):
        run = [line[2].strip() for line in lines[i:i + 3]]
        if all(_bare_header(line) for line in run) and any(re.match(r'Campos?\b', line, re.I) for line in run):
            marked.update(range(i, i + 3))
    return marked


def _explicit_container_child(line, mentions, quotes):
    """One immediate typed child under a combined heading, not a table row.

    The display container is not a declaration. Child evidence begins at its
    own full typed label; this never splits an unlabeled combined value or
    resolves multiple typed values on one row.
    """
    typed = [mention for mention in mentions if mention.group().endswith(':')]
    if quotes or '|' in line or len(typed) != 2:
        return None
    container, child = typed
    if (not HORIZONTAL_ONLY.fullmatch(line[:container.start()])
            or VERTICAL.search(line[container.start():child.end()])
            or not COMBINED_ONLY.fullmatch(container['label'])
            or not container.group().endswith(':') or not child.group().endswith(':')
            or not HORIZONTAL_ONLY.fullmatch(line[container.end():child.start()])
            or COMBINED_ONLY.fullmatch(child['label'])):
        return None
    return child.start()


def _boundary(line):
    text = line.strip()
    if not text:
        return False
    if text.startswith('-'):
        marked = text[1:].lstrip()
        typed = LABEL.match(marked)
        if typed and typed.group().endswith(':') or PLANNING_META.match(marked):
            return True
    label = LABEL.match(text)
    standalone_label = label and (text[label.end():].strip() == '' or label.group().endswith(':'))
    return bool(standalone_label or HEADING.match(text) or GENERIC_HEADING.fullmatch(text)
                or SESSION_OR_RESET.match(text) or CONTINUATION.fullmatch(text))


def _unit_data(pages, source):
    units = []
    for segment in scan_session_segments(pages, source):
        a = segment.header_anchor
        admitted = []
        for number, literal in segment.page_segments:
            page = pages[number - 1]
            if literal and page.count(literal) == 1:
                start = page.index(literal)
                admitted.append((number, start, start + len(literal)))
        units.append({'id': 'session:' + segment.session_id, 'kind': 'session',
                      'anchor': _ref(pages, source, a['page_number'], a['text_start'], a['text_end'], 'unit_anchor'),
                      '_number': segment.session_number, '_admitted': admitted})
    for project in project_occurrences(pages, source):
        a = project['anchor']
        # A missing or ambiguous project title does not define a resolved unit.
        if project['title_status'] != 'supported':
            continue
        units.append({'id': f"project:p{a['page_number']}_o{a['occurrence']}", 'kind': 'project',
                      'anchor': _ref(pages, source, a['page_number'], a['text_start'], a['text_end'], 'unit_anchor')})
    barriers = safety_boundary_positions(pages)
    for number, page in enumerate(pages, 1):
        # Any explicit general-data reset cuts this detached conservative scope,
        # without changing the product's separate compound reset grammar.
        barriers[number].extend(m.start() for m in re.finditer(r'(?im)^[ \t]*DATOS\s+GENERALES\b', page))
    return units, barriers


def _scaffold_quotes_balanced(text):
    """Local strict pairs: an orphan closer is not a balanced quotation."""
    stack = []
    closing = {'»': '«', '”': '“'}
    for char in text:
        if char == '"':
            if stack and stack[-1] == char:
                stack.pop()
            else:
                stack.append(char)
        elif char in ('«', '“'):
            stack.append(char)
        elif char in closing:
            if not stack or stack.pop() != closing[char]:
                return False
    return not stack


def _complete_planning_value(value):
    return (bool(value.strip()) and not DANGLING_END.search(value)
            and _scaffold_quotes_balanced(value)
            and not SCAFFOLD_INLINE_CUT.search(value))


def _planning_structure(text, *, declarations):
    """Source-only bounded metadata rows; never discover scope from gold spans."""
    active = None
    for _, _, line in _lines(text):
        if VERTICAL.search(line) or '\x1f' in line:
            return False
        text_line = line.strip()
        if not text_line:
            continue
        if text_line.startswith('-'):
            text_line = text_line[1:].lstrip()
        meta = PLANNING_META.fullmatch(text_line)
        mentions = list(LABEL.finditer(text_line)) if declarations else []
        child = _explicit_container_child(text_line, mentions, []) if mentions else None
        label = next((m for m in mentions if m.start() == (child or 0)), None)
        typed = (label and label.group().endswith(':') and not COMBINED_ONLY.fullmatch(label['label'])
                 and (len([m for m in mentions if m.group().endswith(':')]) == 1 or child is not None)
                 and '|' not in text_line)
        if meta or typed:
            if active is not None and not _complete_planning_value(active):
                return False
            if meta:
                if not _complete_planning_value(meta[1]):
                    return False
                active = None
            else:
                active = text_line[label.end():].strip()
            continue
        # A new sentence after a complete block is loose prose, not metadata.
        if (active is None or SENTENCE_END.search(active) or SCAFFOLD_ACTIVITY.match(line.strip())
                or ':' in text_line or text_line.isupper() or _boundary(text_line)):
            return False
        active += '\n' + text_line
    return active is None or _complete_planning_value(active)


def _prior_scaffold(pages, number, units, barriers):
    if number < 2:
        return None
    previous = [u for u in units if u['anchor']['page_number'] == number - 1]
    sessions = [u for u in previous if u['kind'] == 'session']
    if len(sessions) != 1:
        return None
    unit = sessions[0]
    start, end = (unit['anchor']['region'][key] for key in ('start', 'end'))
    header = unit['anchor']['excerpt']
    identifier = re.search(rf'\bSESI[OÓ]N{HORIZONTAL}*[0-9]+\b', header, re.I)
    if not identifier or '\x1f' in header or SCAFFOLD_INLINE_CUT.search(header[identifier.end():]):
        return None
    if any(u['anchor']['region']['start'] > start for u in previous):
        return None
    if any(b > start for b in barriers[number - 1]):
        return None
    preceding = ''.join(pages[:number - 2]) + pages[number - 2][:end]
    if (not _scaffold_quotes_balanced(preceding)
            or not _planning_structure(pages[number - 2][end:], declarations=False)):
        return None
    return unit


def _first_moment(page):
    return next(((begin, match[1].casefold()) for begin, _, line in _lines(page)
                 if (match := MOMENT.match(line))), None)


def _structural_scope(pages, source, number, start, value_end, units, barriers):
    unit = _prior_scaffold(pages, number, units, barriers)
    first = _first_moment(pages[number - 1])
    if not unit or not first or first[1] != 'inicio' or value_end is None:
        return None, [], None
    prefix_end = first[0]
    if (not start < value_end <= prefix_end or any(b < prefix_end for b in barriers[number])
            or not _planning_structure(pages[number - 1][:prefix_end], declarations=True)
            or not any(p == number and begin <= start < value_end <= end
                       for p, begin, end in unit['_admitted'])):
        return None, [], None
    proof = [
        _ref(pages, source, number - 1, unit['anchor']['region']['start'], len(pages[number - 2]), 'unit_scaffold_tail'),
        _ref(pages, source, number, 0, prefix_end, 'unit_scaffold_prefix'),
    ]
    return {k: v for k, v in unit.items() if not k.startswith('_')}, proof, 'structural_scaffold_proposal'


def _marker_allowed(pages, number, start, units):
    same_page = [u for u in units if u['anchor']['page_number'] == number and u['anchor']['region']['end'] <= start]
    if same_page:
        current = max(same_page, key=lambda u: u['anchor']['region']['start'])
        if current['kind'] != 'session':
            return False
        begin = current['anchor']['region']['end']
    else:
        begin = 0
        first = next((line for line in _lines(pages[number - 1]) if line[2].strip()), None)
        if first and CONTINUATION.fullmatch(first[2].strip()):
            begin = first[1]
    return _planning_structure(pages[number - 1][begin:start], declarations=True)


def _scope(pages, source, number, start, units, barriers, *, value_end=None):
    same_page = [u for u in units if u['anchor']['page_number'] == number and u['anchor']['region']['end'] <= start]
    if same_page:
        current = max(same_page, key=lambda u: u['anchor']['region']['start'])
        if any(current['anchor']['region']['start'] < b <= start for b in barriers[number]):
            return None, [], None
        return {k: v for k, v in current.items() if not k.startswith('_')}, [], 'same_page_explicit'
    if number == 1:
        return None, [], None
    first = next((line for line in _lines(pages[number - 1]) if line[2].strip()), None)
    continuation = CONTINUATION.fullmatch(first[2].strip()) if first else None
    if not continuation or first[1] > start or any(b < start for b in barriers[number]):
        return _structural_scope(pages, source, number, start, value_end, units, barriers)
    previous = [u for u in units if u['anchor']['page_number'] == number - 1]
    matching = [u for u in previous if u['kind'] == 'session' and u['_number'] == int(continuation[1])]
    if len(matching) != 1:
        return None, [], None
    current = matching[0]
    if any(u['anchor']['region']['start'] > current['anchor']['region']['start'] for u in previous):
        return None, [], None
    if any(b > current['anchor']['region']['start'] for b in barriers[number - 1]):
        return None, [], None
    begin = first[0] + len(first[2]) - len(first[2].lstrip())
    proof = _ref(pages, source, number, begin, first[0] + len(first[2].rstrip()), 'unit_continuation')
    return {k: v for k, v in current.items() if not k.startswith('_')}, [proof], 'explicit_continuation'


def _field_line(line):
    """Exact existing names are textual context, never field/unit identities."""
    if VERTICAL.search(line) or '\x1f' in line:
        return False
    text = line.strip()
    labelled = FIELD_LABEL.fullmatch(text)
    return (labelled[1].strip() if labelled else text).lower() in FIELD_NAMES


def _code_context_row(line):
    if VERTICAL.search(line) or '\x1f' in line or any(c in line for c in '|:«»“”"'):
        return False
    match = CODE_ROW.fullmatch(line.strip())
    return bool(match and SENTENCE_END.search(match['description'])
                and not DANGLING_END.search(match['description'])
                and not LITERAL_LABEL.search(match['description'])
                and not CODE_ROW_CUT.search(match['description'])
                and not NONAFFIRMATIVE.match(match['description'])
                and not NEGATED.match(match['description'])
                and not CONDITIONAL.match(match['description']))


def _metadata_typed_row(line):
    """One physical typed label, with at most the single formatting hyphen."""
    if VERTICAL.search(line) or '\x1f' in line or '|' in line:
        return None
    mentions = [m for m in LITERAL_LABEL.finditer(line) if m.group().endswith(':')]
    if len(mentions) != 1:
        return None
    label, = mentions
    prefix = line[:label.start()]
    if (COMBINED_ONLY.fullmatch(label['label'])
            or not (HORIZONTAL_ONLY.fullmatch(prefix) or MARKER_PREFIX.fullmatch(prefix))):
        return None
    return label


def _outside_value_quotes(line, quotes):
    """Mask quoted characters for structure checks, never for evidence."""
    stack, outside = list(quotes), []
    for char in line:
        was_quoted = bool(stack)
        _advance_quotes(stack, char)
        outside.append(' ' if was_quoted or stack else char)
    return ''.join(outside)


def _metadata_stop(line, *, quotes):
    outside = _outside_value_quotes(line, quotes)
    text = outside.strip()
    # Typed and valid context rows are handled before this check. An unquoted
    # colon or an externally code-shaped row is a structural rejection, even
    # when a rejected code description itself contains balanced quoted text.
    # Carry the active value's quote state across its physical lines, but never
    # use a separate quote-led block to continue a value or resume metadata.
    return bool(line.strip() and (VERTICAL.search(line) or '\x1f' in line or '|' in line or ':' in outside
                         or not quotes and CODE_ROW.fullmatch(line.strip())
                         or CODE_ROW.fullmatch(text) or _boundary(outside) or SCAFFOLD_ACTIVITY.match(text)
                         or not quotes and line.strip().startswith(('«', '»', '“', '”', '"'))
                         or EXAMPLE_BLOCK.match(text) or NONAFFIRMATIVE.match(text)
                         or text.isupper()))


def _metadata_value_span(page, lines, line_index, label_end):
    """Bound literals in a field block without making a scope proof from it."""
    end = len(page)
    for index in range(line_index + 1, len(lines)):
        begin, _, line = lines[index]
        if not line.strip():
            continue
        preceding = page[label_end:begin].strip()
        quotes = []
        _advance_quotes(quotes, preceding)
        complete = bool(SENTENCE_END.search(preceding)
                        and not DANGLING_END.search(preceding)
                        and _scaffold_quotes_balanced(preceding))
        if not quotes and (_field_line(line) or _code_context_row(line)):
            following = next((row for _, _, row in lines[index + 1:] if row.strip()), None)
            corroborated = following is not None and (
                _field_line(following) or _code_context_row(following) or _metadata_typed_row(following))
            if not complete or not corroborated:
                return None, 'uncertain_boundary'
            end = begin
            break
        if not quotes and _metadata_typed_row(line):
            end = begin
            break
        if _metadata_stop(line, quotes=quotes):
            if not complete:
                return None, 'uncertain_boundary'
            end = begin
            break
    if not _scaffold_quotes_balanced(page[label_end:end]):
        return None, 'uncertain_boundary'
    return _checked_value_span(page, label_end, end)


def _field_marker_allowed(page, lines, line_index, number, units):
    """Page-local extraction context, deliberately separate from _scope.

    Only a product-recognized explicit unit restarts a blocked region. A later
    campo or DATOS GENERALES cannot skip an activity, example, or unknown row.
    Completed declaration values are consumed using their original slices.
    """
    target = lines[line_index][0]
    anchors = [u['anchor'] for u in units if u['anchor']['page_number'] == number
               and u['anchor']['region']['end'] <= target]
    begin = max(anchors, key=lambda a: a['region']['start'])['region']['end'] if anchors else 0
    field, initial, consumed = False, True, begin
    for index, (start, end, original) in enumerate(lines[:line_index]):
        if end <= consumed:
            continue
        line = original[max(0, consumed - start):]
        text = line.strip()
        if not text:
            continue
        if VERTICAL.search(line) or '\x1f' in line:
            return False
        if _field_line(line):
            field, initial = True, False
            continue
        if not field:
            if initial and re.fullmatch(rf'DATOS{HORIZONTAL}+GENERALES{HORIZONTAL}*:?', text, re.I):
                initial = False
                continue
            initial = False
            if re.fullmatch(rf'Proyecto{HORIZONTAL}*:', text, re.I):
                continue
            metadata = PLANNING_META.fullmatch(text[1:].lstrip() if text.startswith('-') else text)
            if metadata and _complete_planning_value(metadata[1]):
                continue
            return False
        if _code_context_row(line):
            continue
        label = _metadata_typed_row(line)
        if label:
            # Here consumed never starts inside a declaration's physical row.
            value, reason = _metadata_value_span(page, lines, index, start + label.end())
            if value:
                consumed = value[1]
                continue
        return False
    return field


def _value_span(page, lines, line_index, label_end, *, closed_block=False):
    end = len(page)
    for begin, _, line in lines[line_index + 1:]:
        if _boundary(line) or _metadata_typed_row(line):
            end = begin
            break
        # Only a new scaffold context may retain a completed literal block
        # before loose prose. That prose still vetoes structural scope.
        if closed_block and SENTENCE_END.search(page[label_end:begin].rstrip()) and line.strip():
            end = begin
            break
    return _checked_value_span(page, label_end, end)


def _checked_value_span(page, label_end, end):
    raw = page[label_end:end]
    start = label_end + len(raw) - len(raw.lstrip())
    end = label_end + len(raw.rstrip())
    if start >= end:
        return None, 'empty_value'
    value = page[start:end]
    quotes = []
    _advance_quotes(quotes, value)
    if quotes:
        return None, 'uncertain_boundary'
    nonempty = [line.strip() for line in value.splitlines() if line.strip()]
    for left, right in zip(nonempty, nonempty[1:]):
        if SENTENCE_END.search(left) and not (BULLET.match(left) and BULLET.match(right)):
            return None, 'uncertain_boundary'
    # The supplied window may itself end mid-declaration. Absence of a later
    # supplied page is never proof that a page-final fragment is complete.
    if DANGLING_END.search(value) or end == len(page.rstrip()) and not SENTENCE_END.search(value):
        return None, 'uncertain_boundary'
    if NEGATED.match(value):
        return None, 'negated'
    if CONDITIONAL.match(value):
        return None, 'conditional'
    if NONAFFIRMATIVE.match(value) or UNSPECIFIED.fullmatch(value):
        return None, 'nonaffirmative'
    return (start, end), None


def extract_declarations(pages, *, source_doc_sha256, scope_audit=None):
    """Return detached proposals; reject malformed/bounded inputs without truncation."""
    if (not isinstance(pages, (list, tuple)) or not pages or any(not isinstance(p, str) for p in pages)
            or not isinstance(source_doc_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', source_doc_sha256)):
        raise ValueError('Invalid source contract')
    pages = tuple(pages)
    if sum(map(len, pages)) > MAX_CHARACTERS:
        raise ValueError('Input exceeds explicit character limit; no silent truncation')
    extraction = snapshot_hash(pages)
    units, barriers = _unit_data(pages, source_doc_sha256)
    records, quotes = [], []
    for number, page in enumerate(pages, 1):
        # An unresolved quotation cannot become a declaration merely because
        # extraction moved to another physical page.
        lines, consumed_until = _lines(page), -1
        tabular = _table_lines(lines)
        for index, (begin, _, line) in enumerate(lines):
            mentions = list(LITERAL_LABEL.finditer(line))
            child_start = _explicit_container_child(line, mentions, quotes)
            row_is_table = ('|' in line or index in tabular or
                            child_start is None and len(mentions) > 1 and ((line[:mentions[0].start()].strip() == ''
                                                  or MARKER_PREFIX.fullmatch(line[:mentions[0].start()])) and
                                                  sum(m.group().endswith(':') for m in mentions) > 1
                                                  or re.match(r'^\s*Campos?\b', line, re.I)))
            for mention in mentions:
                if child_start is not None and mention.start() != child_start:
                    continue
                start, end = begin + mention.start(), begin + mention.end()
                if start < consumed_until:
                    continue
                prefix_quotes = list(quotes)
                _advance_quotes(prefix_quotes, line[:mention.start()])
                label = _ref(pages, source_doc_sha256, number, start, end, 'label')
                raw_kind = mention['label']
                kind = 'pda' if re.fullmatch(LITERAL_PDA, raw_kind, re.I) else 'contenido'
                field_context = _field_marker_allowed(page, lines, index, number, units)
                marker = (MARKER_PREFIX.fullmatch(line[:mention.start()])
                          and mention.group().endswith(':') and not VERTICAL.search(mention.group())
                          and (_marker_allowed(pages, number, begin, units) or field_context))
                value, reason = None, None
                if prefix_quotes:
                    reason = 'quoted'
                elif COMBINED_ONLY.fullmatch(raw_kind):
                    kind, reason = None, 'combined_label'
                elif row_is_table:
                    reason = 'table_ambiguous'
                elif (re.fullmatch(LITERAL_NUMBERED_PDA, raw_kind, re.I)
                      and (VERTICAL.search(mention.group())
                           or child_start is None and not marker and not HORIZONTAL_ONLY.fullmatch(line[:mention.start()]))):
                    reason = 'label_mention'
                elif line[:mention.start()].strip() and mention.start() != child_start and not marker:
                    reason = 'label_mention'
                elif not mention.group().endswith(':') and line[mention.end():].strip():
                    reason = 'nonaffirmative' if NONAFFIRMATIVE.match(line[mention.end():].strip(' :')) else 'label_mention'
                else:
                    scaffold_prior = _prior_scaffold(pages, number, units, barriers)
                    first_moment = _first_moment(page)
                    closed_block = bool(scaffold_prior and first_moment and first_moment[1] == 'inicio'
                                        and not any(u['anchor']['page_number'] == number
                                                    and u['anchor']['region']['end'] <= start for u in units))
                    if field_context:
                        value, reason = _metadata_value_span(page, lines, index, end)
                    else:
                        value, reason = _value_span(page, lines, index, end, closed_block=closed_block)
                unit, scope_proofs, scope_basis = _scope(
                    pages, source_doc_sha256, number, start, units, barriers,
                    value_end=value[1] if value else None)
                evidence = [label]
                if value:
                    evidence.append(_ref(pages, source_doc_sha256, number, *value, 'value'))
                    consumed_until = value[1]
                    reason = 'unresolved_scope' if unit is None else 'project_scope' if unit['kind'] == 'project' else 'explicit_session'
                evidence.extend(scope_proofs)
                decision = 'candidate' if reason == 'explicit_session' else 'abstained'
                identity = [VERSION, source_doc_sha256, extraction, number, start, end, kind]
                record_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:16]
                claim = None
                if decision == 'candidate':
                    refs = [SourceReference.from_dict(ev) for ev in evidence + [unit['anchor']]]
                    value_ref = next(ev for ev in evidence if ev['role'] == 'value')
                    claim = AtomicClaim(
                        claim_id=record_id, claim_type='field', subject=unit['id'],
                        predicate=PREDICATES[kind], object_value=page[value[0]:value[1]],
                        source_doc_sha256=source_doc_sha256, page_number=number,
                        region=dict(value_ref['region']), excerpt=value_ref['excerpt'],
                        extraction_method='detached_literal_declarations', extraction_version=MATCHER_VERSION,
                        state='needs_human_review', confidence=None, evidence=refs,
                        metadata={'basis': 'explicit', 'contract_version': VERSION, 'matcher_version': MATCHER_VERSION,
                                  'unit_scope_basis': scope_basis,
                                  'extraction_sha256': extraction,
                                  'validation': 'literal_declaration_not_SEP_alignment'},
                    ).to_dict()
                records.append({'id': record_id, 'kind': kind, 'decision': decision, 'reason': reason,
                                'unit': unit, 'evidence': evidence, 'claim': claim})
                if len(records) > MAX_RECORDS:
                    raise ValueError('Output exceeds explicit record limit; no silent truncation')
            _advance_quotes(quotes, line)
    result = {'version': VERSION, 'source_doc_sha256': source_doc_sha256, 'extraction_sha256': extraction,
            'records': records,
            'limits': ['Matcher implementation: ' + MATCHER_VERSION,
                       'Extracted text only; no PDF/OCR or table reconstruction.',
                       'Page-local values; cross-page scope needs named continuation or a bounded structural proposal.',
                       'Candidates pending human review; no SEP alignment or pedagogical approval.',
                       'Bounded textual grammar; ambiguous or unrecognized discourse may be omitted or abstained.']}
    if scope_audit is not None and getattr(scope_audit, 'enabled', False):
        from scripts.anchor_scope_audit import audit_scopes
        result['scope_audit'] = audit_scopes(pages=pages, declarations=result, config=scope_audit)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='JSON with pages and source_doc_sha256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_bytes())
    result = extract_declarations(data['pages'], source_doc_sha256=data['source_doc_sha256'])
    # Detached output only, and no accidental replacement of a previous run.
    with args.output.open('x', encoding='utf-8', newline='') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
