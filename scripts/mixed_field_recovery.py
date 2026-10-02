"""Bounded evidence-only recovery of complete combined fields, opt-in and offline.

No type assignment, new unit, AtomicClaim, source repair, provider or production
integration. All existing records survive unchanged except the added value on an
eligible combined-label abstention. The source-only contract is independently
frozen in docs/development/session-declarations-mixed-fields-v1.md.
"""
from __future__ import annotations

import copy
import hashlib
import re
import unicodedata

VERSION = 'closed-mixed-fields.v1'
MAX_VALUE_CHARACTERS = 2048
MAX_VALUE_LINES = 32
LABEL = re.compile(r'Contenidos? *(?:/|y) *PDAs? *:', re.I | re.A)
CLOSER = re.compile(r'(?:Inicio|Desarrollo|Cierre|Actividades|Descripci[oó]n de actividades|'
                    r'Recursos|Materiales|Evaluaci[oó]n|Observaciones) *:?', re.I)
META = re.compile(r'^(?:Fecha|Tiempo|Duraci[oó]n|Tema(?: de la sesi[oó]n)?|'
                  r'Organizaci[oó]n|Campos?(?: formativos?)?|Fase|P[aá]ginas(?: +[A-Z]{1,4})?) *:(.*)$', re.I)
INLINE_ACTIVITY = re.compile(r'\b(?:Inicio|Desarrollo|Cierre|Actividad(?:es)?(?: +[0-9]+)?) *:', re.I)
BULLET = re.compile(r'^(?:[-*•]|[0-9]+[.)]) *(?=\S)')
UNSAFE_ROW = re.compile(r'^(?:Actividad(?:es)?(?: +[0-9]+)? *:|(?:Nombre +del +)?Proyecto\b|'
                        r'Sesi[oó]n\b|DATOS +GENERALES\b|>|```|~~~)', re.I)


def _safe_characters(text):
    # Preserve CRLF; no strip/splitlines operation may conceal a control first.
    text = text.replace('\r\n', '\n')
    return all(c == '\n' or (unicodedata.category(c) not in {'Cc', 'Cf'}
                            and c not in '\u2028\u2029') for c in text)


def _delimiters_balanced(text):
    """Strict quotes and paired brackets, including orphan closing characters."""
    pairs = {'(': ')', '[': ']', '{': '}', '«': '»', '“': '”', '"': '"'}
    closing = {')', ']', '}', '»', '”'}
    stack = []
    for char in text:
        if stack and char == stack[-1]:
            stack.pop()
        elif char in pairs:
            stack.append(pairs[char])
        elif char in closing:
            return False
    return not stack


def _field_span(page, rows, index, label_end, session_anchors):
    from scripts.session_declarations import LITERAL_LABEL, DANGLING_END, _outside_value_quotes
    from scripts.anchor_scope_catalogue import EXAMPLE, NONAFFIRMATIVE
    end, boundary = None, None
    quotes = []
    for i in range(index, len(rows)):
        begin, _, original = rows[i]
        line = original[label_end - begin:] if i == index else original
        if not _safe_characters(line) or '|' in line:
            return None
        text = line.strip(' ')
        if not text:
            continue
        start = begin + len(original) - len(original.lstrip(' '))
        if i > index and not quotes:
            anchor = next((a for a in session_anchors
                           if a['region']['start'] == start
                           and a['excerpt'] == text), None)
            if CLOSER.fullmatch(text) or anchor is not None:
                end = begin
                boundary = (start, begin + len(original.rstrip(' ')))
                break
        outside = _outside_value_quotes(text, quotes)
        if (any(m.group().endswith(':') for m in LITERAL_LABEL.finditer(outside))
                or INLINE_ACTIVITY.search(outside) or META.match(outside)
                or UNSAFE_ROW.match(outside)):
            return None
        item = BULLET.sub('', outside, count=1)
        if (EXAMPLE.match(item) or NONAFFIRMATIVE.match(item)
                or text.startswith(('«', '»', '“', '”', '"'))
                or not BULLET.match(text) and re.match(r'^[^:]{1,80}:', outside)):
            return None
        # Standalone punctuation/header fragments cannot complete a field.
        from curriculum.overview_fields import _advance_quotes
        _advance_quotes(quotes, line)
    if end is None:
        return None
    raw = page[label_end:end]
    start = label_end + len(raw) - len(raw.lstrip())
    end = label_end + len(raw.rstrip())
    value = page[start:end]
    if (not value or len(value) > MAX_VALUE_CHARACTERS or not _safe_characters(raw)
            or sum(bool(row.strip()) for row in value.split('\n')) > MAX_VALUE_LINES
            or not _delimiters_balanced(value) or DANGLING_END.search(value)
            or not any(c.isalnum() for c in value)):
        return None
    return (start, end), boundary



def _ascii_metadata_spacing(text):
    return _safe_characters(text) and not any(c.isspace() and c not in ' \r\n' for c in text)


def _anchor_theme_suffix(anchor):
    # Inspect an existing whole anchor only; never shorten it or admit a unit.
    from scripts.anchor_scope_catalogue import DAY, SESSION_BASE
    return bool(re.fullmatch(
        rf'{SESSION_BASE} +Fecha *: *(?:(?:{DAY}) +)?(?:0?[1-9]|[12][0-9]|3[01]) +Tema de la *',
        anchor['excerpt'], re.I))


def _context(pages, source, number, start, units):
    from scripts.session_declarations import _lines, _ref, _scaffold_quotes_balanced
    from scripts.anchor_scope_catalogue import _source_prefix, example_context, EXAMPLE, NONAFFIRMATIVE
    history = _source_prefix(pages, number, start)
    if not _scaffold_quotes_balanced(history):
        return None
    resets = []
    for unit in units:
        anchor = unit['anchor']
        n, low, high = anchor['page_number'], anchor['region']['start'], anchor['region']['end']
        if unit['kind'] != 'session' or (n, high) > (number, start):
            continue
        prefix = _source_prefix(pages, n, low)
        if (_ascii_metadata_spacing(anchor['excerpt']) and _scaffold_quotes_balanced(prefix)
                and not example_context(prefix, len(prefix))):
            resets.append(anchor)
    anchor = max(resets, key=lambda a: (a['page_number'], a['region']['end']), default=None)
    begin_page, begin_offset = (anchor['page_number'], anchor['region']['end']) if anchor else (1, 0)
    context = [dict(anchor, role='mixed_field_context')] if anchor else []
    rows = ['Tema de la'] if anchor and _anchor_theme_suffix(anchor) else []
    for n in range(begin_page, number + 1):
        low = begin_offset if n == begin_page else 0
        high = start if n == number else len(pages[n - 1])
        text = pages[n - 1][low:high]
        if not _ascii_metadata_spacing(text) or '|' in text:
            return None
        rows.extend(line for _, _, line in _lines(text) if line.strip())
        if text.strip():
            context.append(_ref(pages, source, n, low, high, 'mixed_field_context'))
    active, active_theme = None, False
    i = 0
    while i < len(rows):
        row = rows[i].strip(' ')
        i += 1
        # A wrapped label is one metadata label, never a new numbered session.
        if re.search(r'(?:^| +)Tema de la *$', row, re.I) and i < len(rows):
            following = rows[i].strip(' ')
            if re.match(r'^sesi[oó]n *:', following, re.I):
                row += ' ' + following
                i += 1
        if (EXAMPLE.match(row) or NONAFFIRMATIVE.match(row)
                or INLINE_ACTIVITY.search(row) or CLOSER.fullmatch(row)
                or row.startswith(('>', '```', '~~~'))):
            return None
        if re.fullmatch(r'DATOS +GENERALES *:?', row, re.I):
            if active is not None or i != 1:
                return None
            continue
        # Only initial explicit project metadata is context, never a reset.
        if re.fullmatch(r'(?:Nombre +del +)?Proyecto *: *\S.*', row, re.I):
            if i != 1 or anchor is not None:
                return None
            active = None
            continue
        meta = META.match(row)
        if meta:
            payload = BULLET.sub('', meta[1].strip(), count=1)
            if EXAMPLE.match(payload) or NONAFFIRMATIVE.match(payload):
                return None
            joined_theme = re.fullmatch(r'Fecha *: *[^:]* Tema de la sesi[oó]n *:(.*)', row, re.I)
            active_theme = bool(joined_theme or re.match(r'Tema(?: de la sesi[oó]n)? *:', row, re.I))
            active = (joined_theme[1] if joined_theme else meta[1]).strip()
            if EXAMPLE.match(BULLET.sub('', active, count=1)) or NONAFFIRMATIVE.match(BULLET.sub('', active, count=1)):
                return None
            continue
        inline_time = re.fullmatch(r'([^:]+) +Tiempo *: *([^:]+)', row, re.I)
        if active is not None and active_theme and inline_time and not active.endswith(('.', '!', '?')):
            if not _delimiters_balanced(active + '\n' + inline_time[1]):
                return None
            if EXAMPLE.match(inline_time[2]) or NONAFFIRMATIVE.match(inline_time[2]):
                return None
            active, active_theme = inline_time[2], False
            continue
        if (active is None or active.endswith(('.', '!', '?')) or ':' in row
                or UNSAFE_ROW.match(row) or LABEL.search(row)):
            return None
        active += ('\n' if active else '') + row
    return context


def recover_mixed_fields(*, pages, source_doc_sha256, records, units):
    """Return isolated records plus a source-bound ledger; never rewrite a claim."""
    from scripts.session_declarations import _lines, _ref
    result = copy.deepcopy(records)
    recoveries = []
    for record in result:
        if (record.get('kind') is not None or record.get('decision') != 'abstained'
                or record.get('reason') != 'combined_label' or record.get('claim') is not None):
            continue
        evidence = record.get('evidence', [])
        labels = [e for e in evidence if e.get('role') == 'label']
        if len(labels) != 1 or any(e.get('role') == 'value' for e in evidence):
            continue
        label = labels[0]
        if not LABEL.fullmatch(label['excerpt']) or not _safe_characters(label['excerpt']):
            continue
        number = label['page_number']
        page = pages[number - 1]
        low, high = label['region']['start'], label['region']['end']
        if page[low:high] != label['excerpt']:
            continue
        rows = _lines(page)
        indexes = [i for i, (a, b, _) in enumerate(rows) if a <= low < b]
        if len(indexes) != 1:
            continue
        index = indexes[0]
        if page[rows[index][0]:low].strip(' '):
            continue
        context = _context(pages, source_doc_sha256, number, low, units)
        if context is None:
            continue
        anchors = [u['anchor'] for u in units if u['kind'] == 'session'
                   and u['anchor']['page_number'] == number]
        found = _field_span(page, rows, index, high, anchors)
        if found is None:
            continue
        value, boundary = found
        value_ref = _ref(pages, source_doc_sha256, number, *value, 'value')
        record['evidence'] = evidence + [value_ref]
        recoveries.append({'record_id': record['id'], 'method': VERSION,
                           'label_utf8_sha256': hashlib.sha256(label['excerpt'].encode()).hexdigest(),
                           'value_utf8_sha256': hashlib.sha256(value_ref['excerpt'].encode()).hexdigest(),
                           'boundary': _ref(pages, source_doc_sha256, number, *boundary, 'mixed_field_boundary'),
                           'context': context})
    return result, {'version': VERSION, 'enabled': True, 'recoveries': recoveries,
                    'limits': ['Whole page-local mixed fields only; no type partition or code expansion.',
                               'No new units, claims, scope proof, semantic validation or production apply.']}
