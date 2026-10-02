"""Source-only opt-in literal PDA recovery; descriptors never become contents.

This module has no reference/gold, source-ID, provider, network, database or
unit-assignment dependency. The caller's legacy values and claims are immutable.
"""
from __future__ import annotations

import copy
import hashlib
import re
import unicodedata

from scripts import session_declarations as legacy
from scripts.anchor_scope_catalogue import (
    EXAMPLE, NONAFFIRMATIVE, _source_prefix,
)

VERSION = 'explicit-pda-local-context.v1'
DESCRIPTION_NONAFFIRMATIVE = re.compile(r'(?<!\w)(?:' + NONAFFIRMATIVE.pattern[1:] + ')',
                                      NONAFFIRMATIVE.flags)
DESCRIPTOR = re.compile(rf'(?P<code>{legacy.LITERAL_CODE})\.{legacy.HORIZONTAL}+(?P<text>.+)')
CODED_PDA = re.compile(rf'{legacy.LITERAL_CODE}{legacy.HORIZONTAL}+PDA{legacy.HORIZONTAL}*[0-9]+', re.I)
ACTIVITY = re.compile(r'^(?:Actividades?|Actividad(?:\s+[0-9]+)?)\s*:', re.I)
DESCRIPTOR_STRUCTURAL = re.compile(
    r'\b(?:Campos?(?:\s+formativos?)?|Inicio|Desarrollo|Cierre|Actividad(?:es)?|'
    r'Proyecto|Materiales|Recursos|Evaluaci[oó]n|Instrumentos(?:\s+de\s+evaluaci[oó]n)?)\s*:', re.I)
QUOTES = '\"\'«»“”‘’'
FIELD_WORDS = [name.lower().split() for name in legacy.CANONICAL_CAMPOS]


def _next(rows, index):
    while index < len(rows) and legacy.HORIZONTAL_ONLY.fullmatch(rows[index][2]):
        index += 1
    return index


def _trimmed(rows, first, last):
    a, _, left = rows[first]
    b, _, right = rows[last]
    return a + len(left) - len(left.lstrip()), b + len(right.rstrip())


def _field(rows, index, *, abbreviated):
    """Bounded textual spelling only; never return a field identity."""
    pieces = []
    for end in range(index, min(len(rows), index + 3)):
        raw = rows[end][2]
        if not raw.strip() or legacy.RECOVERY_CONTROL.search(raw) or '|' in raw:
            return None
        pieces.append(raw.strip())
        joined = ' '.join(pieces)
        prefix = legacy.FIELD_LABEL.fullmatch(joined)
        text = prefix[1].strip() if prefix else joined
        text = unicodedata.normalize('NFC', text)  # comparison only; source spans are never normalized
        if not re.fullmatch(r'[^\W\d_]+[.,]?(?:[^\S\r\n]+[^\W\d_]+[.,]?)*', text):
            continue
        words = text.lower().split()
        for expected in FIELD_WORDS:
            if len(words) != len(expected):
                continue
            changed = [i for i, (a, b) in enumerate(zip(words, expected)) if a != b]
            if not changed or (abbreviated and len(changed) == 1 and 0 < changed[0] < len(words) - 1
                               and words[changed[0]] == expected[changed[0]][0] + '.'
                               + (',' if expected[changed[0]].endswith(',') else '')):
                return end + 1, _trimmed(rows, index, end)
    return None


def _pda(line):
    label = legacy._metadata_typed_row(line)
    return label if label and CODED_PDA.fullmatch(label['label']) else None


def _balanced(text):
    """Strict source quotation, including apostrophe-style citation pairs."""
    stack = []
    pairs = {'"': '"', "'": "'", '«': '»', '“': '”', '‘': '’'}
    for char in text:
        if stack and char == stack[-1]:
            stack.pop()
        elif char in pairs:
            stack.append(pairs[char])
        elif char in ('»', '”', '’'):
            return False
    return not stack


def _complete(text):
    return bool(text.strip() and legacy.SENTENCE_END.search(text.rstrip())
                and not legacy.DANGLING_END.search(text)
                and _balanced(text))


def _descriptor(page, rows, index):
    if index >= len(rows):
        return None
    first = rows[index][2]
    match = DESCRIPTOR.fullmatch(first.strip())
    if not match:
        return None
    description = []
    for end in range(index, min(len(rows), index + 8)):
        raw = rows[end][2]
        text = match['text'] if end == index else raw.strip()
        if end > index and (DESCRIPTOR.fullmatch(raw.strip()) or _field(rows, end, abbreviated=True)):
            return None
        if (not text or legacy.RECOVERY_CONTROL.search(raw) or '|' in raw
                or any(c in text for c in QUOTES) or legacy.LITERAL_LABEL.search(text)
                or legacy.CODE_ROW_CUT.search(text) or DESCRIPTOR_STRUCTURAL.search(text)
                or legacy.SCAFFOLD_INLINE_CUT.search(text)
                or legacy.SCAFFOLD_ACTIVITY.match(text) or EXAMPLE.match(text)
                or NONAFFIRMATIVE.match(text) or legacy.SESSION_OR_RESET.match(text)):
            return None
        if DESCRIPTION_NONAFFIRMATIVE.search(text):
            return None
        description.append(text)
        if _complete('\n'.join(description)):
            following = _next(rows, end + 1)
            if following < len(rows) and _pda(rows[following][2]):
                return following, _trimmed(rows, index, end)
            return None
    return None


def _history_safe(pages, number, start, units):
    """Unsafe source history can block a fresh page, never grant scope."""
    history = _source_prefix(pages, number, start)
    if not _balanced(history):
        return False
    resets = []
    for unit in units:
        anchor = unit['anchor']
        position = (anchor['page_number'], anchor['region']['end'])
        if position <= (number, start):
            before = _source_prefix(pages, anchor['page_number'], anchor['region']['start'])
            if (_balanced(before)
                    and not legacy.RECOVERY_CONTROL.search(anchor['excerpt']) and '|' not in anchor['excerpt']):
                resets.append(position)
    reset = max(resets, default=(1, 0))
    active = history[len(_source_prefix(pages, *reset)):]
    return not any(legacy.RECOVERY_CONTROL.search(line)
                   or line.lstrip().startswith('>')
                   or EXAMPLE.match(line.strip()) or NONAFFIRMATIVE.match(line.strip())
                   or legacy.MOMENT.match(line) or ACTIVITY.match(line.strip())
                   for _, _, line in legacy._lines(active))


def _value(page, rows, index, label, *, corroborate=True):
    """Return one closed slice and a source-proven next structural edge."""
    start = rows[index][0] + label.end()
    end, edge, boundary = rows[-1][1], len(rows), None
    for i in range(index + 1, len(rows)):
        begin, _, line = rows[i]
        if legacy.RECOVERY_CONTROL.search(line):
            return None
        if legacy.HORIZONTAL_ONLY.fullmatch(line):
            continue
        preceding = page[start:begin].strip()
        quotes = []
        legacy._advance_quotes(quotes, preceding)
        if not quotes:
            field = _field(rows, i, abbreviated=True)
            descriptor = DESCRIPTOR.fullmatch(line.strip())
            if field or descriptor:
                next_descriptor = _next(rows, field[0]) if field else i
                corroborated = _descriptor(page, rows, next_descriptor)
                if not _complete(preceding) or not corroborated:
                    return None
                if corroborate:
                    next_label = _pda(rows[corroborated[0]][2])
                    if not _value(page, rows, corroborated[0], next_label, corroborate=False):
                        return None
                end, edge, boundary = begin, i, _trimmed(rows, i, i)
                break
            if legacy._metadata_typed_row(line):
                end, edge, boundary = begin, i, _trimmed(rows, i, i)
                break
        if legacy._metadata_stop(line, quotes=quotes):
            if not _complete(preceding):
                return None
            end, edge, boundary = begin, i, _trimmed(rows, i, i)
            break
    value, reason = legacy._checked_value_span(page, start, end)
    if not value or not _complete(page[value[0]:value[1]]) or legacy.RECOVERY_CONTROL.search(page[value[0]:value[1]]):
        return None
    text = page[value[0]:value[1]]
    if (EXAMPLE.match(text) or NONAFFIRMATIVE.match(text) or legacy.HEADING.match(text)
            or ACTIVITY.match(text) or text.startswith((*QUOTES, '>'))):
        return None
    clauses = re.split(r'[.!?;:,]\s*', text)
    if any(EXAMPLE.match(part.lstrip()) or NONAFFIRMATIVE.match(part.lstrip()) for part in clauses):
        return None
    return value, edge, boundary


def _scan_region(page, rows):
    index = _next(rows, 0)
    if index >= len(rows):
        return []
    if re.fullmatch(rf'DATOS{legacy.HORIZONTAL}+GENERALES{legacy.HORIZONTAL}*:?', rows[index][2].strip(), re.I):
        index = _next(rows, index + 1)
    field = _field(rows, index, abbreviated=False)
    if not field:
        return []
    index, field_span = _next(rows, field[0]), field[1]
    descriptor_span, proposals = None, []
    while index < len(rows):
        descriptor = _descriptor(page, rows, index)
        if descriptor:
            index, descriptor_span = descriptor
        label = _pda(rows[index][2]) if index < len(rows) else None
        if not label or descriptor_span is None:
            return proposals
        parsed = _value(page, rows, index, label)
        if not parsed:
            return proposals
        value, edge, boundary = parsed
        proposals.append({'label': (rows[index][0] + label.start(), rows[index][0] + label.end()),
                          'value': value, 'descriptor': descriptor_span, 'field': field_span,
                          'boundary': boundary})
        index = _next(rows, edge)
        if index >= len(rows):
            return proposals
        field = _field(rows, index, abbreviated=True)
        if field:
            index, field_span = _next(rows, field[0]), field[1]
            descriptor_span = None
        elif not _pda(rows[index][2]) and not DESCRIPTOR.fullmatch(rows[index][2].strip()):
            return proposals
    return proposals


def apply_pda_context(pages, result):
    """Add only missing PDA values; preserve every other legacy record exactly."""
    result = copy.deepcopy(result)
    source = result['source_doc_sha256']
    units, _ = legacy._unit_data(pages, source)
    proposals = {}
    for number, page in enumerate(pages, 1):
        anchors = sorted((u['anchor']['region'] for u in units if u['anchor']['page_number'] == number),
                         key=lambda r: r['start'])
        regions = [(0, anchors[0] if anchors else None)]
        regions.extend((a['end'], anchors[i + 1] if i + 1 < len(anchors) else None)
                       for i, a in enumerate(anchors))
        for begin, closing_unit in regions:
            end = closing_unit['start'] if closing_unit else len(page)
            if not _history_safe(pages, number, begin, units):
                continue
            rows = [(a + begin, b + begin, line) for a, b, line in legacy._lines(page[begin:end])]
            if closing_unit:
                rows.append((closing_unit['start'], closing_unit['end'],
                             page[closing_unit['start']:closing_unit['end']]))
            for proposal in _scan_region(page, rows):
                proposals[(number, *proposal['label'])] = proposal
    recoveries = []
    for record in result['records']:
        if (record['kind'] != 'pda' or record['decision'] != 'abstained'
                or record['reason'] != 'label_mention' or record['claim'] is not None
                or any(e['role'] == 'value' for e in record['evidence'])):
            continue
        labels = [e for e in record['evidence'] if e['role'] == 'label']
        if len(labels) != 1:
            continue
        label = labels[0]
        number = label['page_number']
        proposal = proposals.get((number, label['region']['start'], label['region']['end']))
        if not proposal:
            continue
        value = legacy._ref(pages, source, number, *proposal['value'], 'value')
        record.update(evidence=[label, value], unit=None, reason='unresolved_scope')
        recoveries.append({
            'record_id': record['id'], 'method': VERSION,
            'label_utf8_sha256': hashlib.sha256(label['excerpt'].encode()).hexdigest(),
            'value_utf8_sha256': hashlib.sha256(value['excerpt'].encode()).hexdigest(),
            'descriptor': legacy._ref(pages, source, number, *proposal['descriptor'], 'pda_descriptor_context'),
            'field': legacy._ref(pages, source, number, *proposal['field'], 'pda_field_context'),
            'boundary': (legacy._ref(pages, source, number, *proposal['boundary'], 'pda_value_boundary')
                         if proposal['boundary'] else None),
            'boundary_kind': 'source_row' if proposal['boundary'] else 'page_end',
        })
    result['pda_context'] = {'version': VERSION, 'enabled': True, 'recoveries': recoveries,
                             'limits': ['Literal PDA only; descriptors are untyped textual context.',
                                        'No field/code identity, content declaration, unit assignment or new claim.',
                                        'Source-only page-local recovery; new scope replay requires a separate contract.']}
    return result
