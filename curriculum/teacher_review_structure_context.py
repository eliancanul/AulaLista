"""Opt-in lossless physical spans over v2; never a source or authority repair."""
import copy
import json

from curriculum.teacher_review_context import canonical_context_bytes, _check_json
from curriculum.teacher_review_table_context import CONTRACT

TRANSPORT_KEY = '_structure_transport'
VERSION = 'physical-spans-v1'
BLOCK_COLUMNS = ('block_id', 'role', 'text', 'phase_id', 'parent_id', 'evidence',
                 'origin', 'status', 'review')
FRAGMENT_KEYS = frozenset({'page_number', 'text_start', 'text_end', 'excerpt'})
RESERVED = frozenset({TRANSPORT_KEY, '$fragment', '$block', '$excerpt'})
STRUCTURE_INSTRUCTIONS = """physical-spans-v1 transport: _structure_transport holds fragment_attributes
and block_columns. Resolve before v2 tables. {$fragment:[a,p,s,e]}
is the exact fragment_attributes[a] object plus page_number=p, text_start=s,
text_end=e, excerpt=page.text[s:e], selecting the unique source_document.pages
entry with page_number=p, never array position. Offsets
are zero-based Python Unicode code points, end-exclusive, NOT bytes/UTF-16;
preserve every character, CRLF and Unicode form. No searching or normalization.
{$block:row} uses block_columns; its text={$excerpt:n} repeats only its own
evidence[n].excerpt. No implicit attributes, omitted source pages or authority.
"""


def structure_context_instructions(encoded):
    return STRUCTURE_INSTRUCTIONS if TRANSPORT_KEY in encoded else ''


def _wire_sizes(context, instructions=''):
    text = instructions + canonical_context_bytes(context).decode('utf-8')
    return len(text.encode('utf-8')), len(json.dumps(text, ensure_ascii=False).encode('utf-8'))


def _check_reserved(value):
    if isinstance(value, dict):
        if RESERVED.intersection(value):
            raise ValueError('reserved_structure_context_key')
        for child in value.values():
            _check_reserved(child)
    elif isinstance(value, list):
        for child in value:
            _check_reserved(child)


def _pages(context):
    source = context['source_document']
    if not isinstance(source, dict) or not isinstance(source.get('pages'), list):
        raise ValueError('invalid_structure_context')
    pages = {}
    for page in source['pages']:
        if not isinstance(page, dict):
            continue
        number = page.get('page_number')
        if type(number) is int and number > 0:
            pages.setdefault(number, []).append(page.get('text'))
    return {number: values[0] for number, values in pages.items()
            if len(values) == 1 and isinstance(values[0], str)}


def _scope(path):
    return (path[:2] == ('dossier', 'annex_candidates') or
            len(path) >= 4 and path[:2] == ('dossier', 'sessions')
            and type(path[2]) is int and path[3] == 'source_structure')


def _block_path(path):
    return (len(path) == 6 and path[:2] == ('dossier', 'sessions')
            and _scope(path) and path[4] == 'blocks' and type(path[5]) is int)


def _own_sha(value, sha):
    return (isinstance(value, str) and value == sha or
            isinstance(value, dict) and set(value) == {'$source'} and value['$source'] is True)


def _span(value, pages, sha):
    if not isinstance(value, dict) or not FRAGMENT_KEYS.issubset(value):
        return None
    page, start, end = (value[name] for name in ('page_number', 'text_start', 'text_end'))
    if (any(type(number) is not int for number in (page, start, end))
            or page not in pages or not 0 <= start <= end <= len(pages[page])
            or not isinstance(value['excerpt'], str) or pages[page][start:end] != value['excerpt']):
        return None
    if any(key in value and not _own_sha(value[key], sha)
           for key in ('document_sha256', 'source_sha256')):
        return None
    return [page, start, end]


def _encode_structure_context(table):
    """Preserve v2 data exactly, sharing only verified physical text spans."""
    _check_json(table)
    _check_reserved(table)
    if table.get('context_contract') != CONTRACT:
        raise ValueError('invalid_structure_context')
    before = canonical_context_bytes(table)
    pages, sha = _pages(table), table['source_document']['source_sha256']
    attributes, positions = [], {}

    def compact(value, path=()):
        if isinstance(value, dict):
            span = _span(value, pages, sha) if _scope(path) else None
            if span is not None:
                attrs = {key: copy.deepcopy(child) for key, child in value.items() if key not in FRAGMENT_KEYS}
                key = canonical_context_bytes(attrs)
                if key not in positions:
                    positions[key] = len(attributes)
                    attributes.append(attrs)
                return {'$fragment': [positions[key], *span]}
            result = {key: compact(child, (*path, key)) for key, child in value.items()}
            if (_block_path(path) and set(value) == set(BLOCK_COLUMNS)
                    and isinstance(value['evidence'], list) and isinstance(value['text'], str)):
                for index, fragment in enumerate(value['evidence']):
                    if _span(fragment, pages, sha) is not None and value['text'] == fragment['excerpt']:
                        result['text'] = {'$excerpt': index}
                        break
                return {'$block': [result[name] for name in BLOCK_COLUMNS]}
            return result
        if isinstance(value, list):
            return [compact(child, (*path, index)) for index, child in enumerate(value)]
        return value

    encoded = compact(table)
    encoded[TRANSPORT_KEY] = {'version': VERSION, 'fragment_attributes': attributes,
                              'block_columns': list(BLOCK_COLUMNS)}
    if canonical_context_bytes(restore_structure_context(encoded, max_expanded_bytes=len(before))) != before:
        raise ValueError('structure_context_roundtrip_failed')
    if canonical_context_bytes(table) != before:
        raise ValueError('structure_context_mutated_input')
    if any(new >= old for new, old in zip(_wire_sizes(encoded, STRUCTURE_INSTRUCTIONS), _wire_sizes(table))):
        return copy.deepcopy(table)
    return encoded


class _TextSlice:
    def __init__(self, text, start, end):
        self.text, self.start, self.end = text, start, end


def _restore_structure_context(encoded, *, max_expanded_bytes):
    """Restore the exact v2 object, retaining absence and independent values."""
    _check_json(encoded)
    if (type(max_expanded_bytes) is not int or max_expanded_bytes < 1
            or not isinstance(encoded, dict) or encoded.get('context_contract') != CONTRACT):
        raise ValueError('invalid_structure_context')
    if TRANSPORT_KEY not in encoded:
        _check_reserved(encoded)
        transport = {'version': VERSION, 'fragment_attributes': [], 'block_columns': list(BLOCK_COLUMNS)}
    else:
        transport = encoded[TRANSPORT_KEY]
    if (not isinstance(transport, dict)
            or set(transport) != {'version', 'fragment_attributes', 'block_columns'}
            or transport['version'] != VERSION or transport['block_columns'] != list(BLOCK_COLUMNS)
            or not isinstance(transport['fragment_attributes'], list)):
        raise ValueError('invalid_structure_context')
    pages = _pages(encoded)
    sha = encoded['source_document']['source_sha256']
    attributes = transport['fragment_attributes']
    seen, used = set(), set()
    for attrs in attributes:
        _check_reserved(attrs)
        if (not isinstance(attrs, dict) or FRAGMENT_KEYS.intersection(attrs)
                or any(key in attrs and not _own_sha(attrs[key], sha)
                       for key in ('document_sha256', 'source_sha256'))):
            raise ValueError('invalid_structure_context')
        key = canonical_context_bytes(attrs)
        if key in seen:
            raise ValueError('invalid_structure_context')
        seen.add(key)

    def fragment(row):
        if (not isinstance(row, list) or len(row) != 4
                or any(type(number) is not int for number in row)):
            raise ValueError('invalid_structure_context')
        attrs, page, start, end = row
        if (not 0 <= attrs < len(attributes) or page not in pages
                or not 0 <= start <= end <= len(pages[page])):
            raise ValueError('invalid_structure_context')
        used.add(attrs)
        # Shallow descriptors only. No excerpt or nested attributes are copied
        # until the entire expanded serialization passes its byte budget.
        return {**transport['fragment_attributes'][attrs],
                'page_number': page, 'text_start': start, 'text_end': end,
                'excerpt': _TextSlice(pages[page], start, end)}

    def chunks(value, path=()):
        if isinstance(value, dict):
            if '$fragment' in value:
                if set(value) != {'$fragment'} or not _scope(path):
                    raise ValueError('invalid_structure_context')
                value = fragment(value['$fragment'])
            elif '$block' in value:
                row = value['$block']
                if (set(value) != {'$block'} or not _block_path(path)
                        or not isinstance(row, list) or len(row) != len(BLOCK_COLUMNS)):
                    raise ValueError('invalid_structure_context')
                block = dict(zip(BLOCK_COLUMNS, row))
                if (not isinstance(block['evidence'], list)
                        or not isinstance(block['text'], (str, dict))):
                    raise ValueError('invalid_structure_context')
                if isinstance(block['text'], dict) and '$excerpt' in block['text']:
                    index = block['text']['$excerpt']
                    if (set(block['text']) != {'$excerpt'} or type(index) is not int
                            or not isinstance(block['evidence'], list)
                            or not 0 <= index < len(block['evidence'])):
                        raise ValueError('invalid_structure_context')
                    own = block['evidence'][index]
                    if not isinstance(own, dict) or set(own) != {'$fragment'}:
                        raise ValueError('invalid_structure_context')
                    block['text'] = fragment(own['$fragment'])['excerpt']
                elif not isinstance(block['text'], str):
                    raise ValueError('invalid_structure_context')
                value = block
            elif RESERVED.intersection(value):
                raise ValueError('invalid_structure_context')
            yield '{'
            for index, key in enumerate(sorted(value)):
                if index:
                    yield ','
                yield json.dumps(key, ensure_ascii=False) + ':'
                yield from chunks(value[key], (*path, key))
            yield '}'
        elif isinstance(value, list):
            yield '['
            for index, child in enumerate(value):
                if index:
                    yield ','
                yield from chunks(child, (*path, index))
            yield ']'
        elif isinstance(value, (str, _TextSlice)):
            text, start, end = ((value, 0, len(value)) if isinstance(value, str)
                                else (value.text, value.start, value.end))
            yield '"'
            for offset in range(start, end, 4096):
                yield json.dumps(text[offset:min(offset + 4096, end)], ensure_ascii=False)[1:-1]
            yield '"'
        else:
            yield json.dumps(value, allow_nan=False)

    parts, size = [], 0
    for part in chunks({key: value for key, value in encoded.items() if key != TRANSPORT_KEY}):
        size += len(part.encode('utf-8'))
        if size > max_expanded_bytes:
            raise ValueError('structure_context_expansion_too_large')
        parts.append(part)
    if used != set(range(len(attributes))):
        raise ValueError('invalid_structure_context')
    return json.loads(''.join(parts))


def encode_structure_context(table):
    try:
        return _encode_structure_context(table)
    except (TypeError, KeyError, IndexError, AttributeError, RecursionError, UnicodeError):
        raise ValueError('invalid_structure_context') from None


def restore_structure_context(encoded, *, max_expanded_bytes=16 * 1024 * 1024):
    try:
        return _restore_structure_context(encoded, max_expanded_bytes=max_expanded_bytes)
    except (TypeError, KeyError, IndexError, AttributeError, RecursionError, UnicodeError):
        raise ValueError('invalid_structure_context') from None
