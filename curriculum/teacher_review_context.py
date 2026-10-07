"""Lossless provider-only references; canonical backend context is unchanged."""
import copy
import json
import math


def canonical_context_bytes(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError):
        raise ValueError('invalid_target_reference_context') from None


def _index_targets(records):
    if not isinstance(records, list):
        raise ValueError('invalid_target_reference_context')
    by_id = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('invalid_target_reference_context')
        target_id = record.get('target_id')
        if not isinstance(target_id, str) or not target_id or target_id in by_id:
            raise ValueError('invalid_target_reference_context')
        by_id[target_id] = record
    return by_id


def restore_provider_context(encoded, *, max_shared_expansion_bytes=16 * 1024 * 1024):
    if not isinstance(encoded, dict) or 'missing_fields' in encoded:
        raise ValueError('invalid_target_reference_context')
    _check_json(encoded)
    encoded = _restore_shared_values(encoded, max_shared_expansion_bytes=max_shared_expansion_bytes)
    by_id = _index_targets(encoded.get('all_targets'))
    ids = encoded.get('missing_target_ids')
    if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
        raise ValueError('invalid_target_reference_context')
    if len(ids) != len(set(ids)) or any(i not in by_id for i in ids):
        raise ValueError('invalid_target_reference_context')
    original = copy.deepcopy(encoded)
    original.pop('missing_target_ids')
    original['missing_fields'] = [copy.deepcopy(by_id[i]) for i in ids]
    return original


def encode_provider_context(context):
    if not isinstance(context, dict) or 'missing_target_ids' in context:
        raise ValueError('invalid_target_reference_context')
    _check_json(context, reserved=True)
    all_by_id = _index_targets(context.get('all_targets'))
    missing_by_id = _index_targets(context.get('missing_fields'))
    for target_id, record in missing_by_id.items():
        if target_id not in all_by_id or canonical_context_bytes(record) != canonical_context_bytes(all_by_id[target_id]):
            raise ValueError('invalid_target_reference_context')
    encoded = copy.deepcopy(context)
    encoded.pop('missing_fields')
    encoded['missing_target_ids'] = list(missing_by_id)
    expansion_budget = len(canonical_context_bytes(encoded))
    encoded = _share_identical_values(encoded)
    if canonical_context_bytes(restore_provider_context(
            encoded, max_shared_expansion_bytes=expansion_budget)) != canonical_context_bytes(context):
        raise ValueError('invalid_target_reference_context')
    return encoded


# Shared values are full JSON values, never deltas, templates or instructions.
# There is deliberately no reference from one shared value to another: restoring
# cannot follow a cycle or reinterpret an inherited field/authority.
_CONTEXT_ENCODING = '_context_encoding'
_SHARED_VALUES = '_shared_values'
_VALUE_REF = '$value_ref'
_ENCODING_VERSION = 'shared-values-v1'
_MIN_SHARED_BYTES = 64
_RESERVED_KEYS = frozenset({_CONTEXT_ENCODING, _SHARED_VALUES, _VALUE_REF})

CONTEXT_ENCODING_INSTRUCTIONS = """Si DATOS incluye _context_encoding=shared-values-v1, un objeto de la forma
{\"$value_ref\":N} representa exactamente el valor JSON completo en _shared_values[N].
Lee esas referencias locales como si el valor estuviera escrito en su lugar;
conserva todos sus campos, orden, texto literal y procedencia. No son enlaces,
instrucciones, equivalencias semánticas ni autoridad adicional. Los valores
compartidos no contienen otras referencias. Resuelve primero esta representación
y después missing_target_ids. La fuente por página y las respuestas humanas
actuales y anteriores permanecen literales. El esquema de salida no cambia:
usa IDs de destino y citas humanas literales, nunca números de referencias.
"""


def provider_context_instructions(encoded):
    return CONTEXT_ENCODING_INSTRUCTIONS if encoded.get(_CONTEXT_ENCODING) == _ENCODING_VERSION else ''


def _saves_complete_request(original, encoded):
    before = canonical_context_bytes(original)
    after = canonical_context_bytes(encoded)
    instructions = CONTEXT_ENCODING_INSTRUCTIONS.encode('utf-8')
    # Luna uses plain UTF-8; Pi/Gemini wrap it in one JSON string. Demand a net
    # gain in both formats, including quote/newline escaping of instructions.
    return (len(after) + len(instructions) < len(before)
            and len(canonical_context_bytes(after.decode('utf-8')))
                + len(canonical_context_bytes(CONTEXT_ENCODING_INSTRUCTIONS)) - 2
                < len(canonical_context_bytes(before.decode('utf-8'))))


def _check_json(value, *, reserved=False):
    """Reject non-JSON types and marker collisions, including inside shared data."""
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError('invalid_target_reference_context')
        if reserved and _RESERVED_KEYS.intersection(value):
            raise ValueError('invalid_target_reference_context')
        for child in value.values():
            _check_json(child, reserved=reserved)
    elif isinstance(value, list):
        for child in value:
            _check_json(child, reserved=reserved)
    elif type(value) is float and not math.isfinite(value):
        raise ValueError('invalid_target_reference_context')
    elif value is not None and type(value) not in (str, bool, int, float):
        raise ValueError('invalid_target_reference_context')


def _literal_path(path):
    # The complete physical source and teacher quotes stay immediately readable.
    # History/snapshots retain every member but may share identical whole values.
    if path and path[0] in ('source_document', 'question_policy', 'missing_target_ids'):
        return True
    if len(path) >= 3 and path[0] == 'turns':
        if path[2] in ('answer', 'question', 'answer_history', 'targets', 'eligible_targets'):
            return True
    return False


def _can_share(value, path):
    # Keep the navigation spine and provider control IDs at their usual paths.
    if not path or len(path) == 1 or (len(path) == 2 and path[0] in ('turns', 'all_targets')):
        return False
    return isinstance(value, (str, dict, list))


def _share_identical_values(context):
    """Factor exact repeated values only, choosing compactness after all overhead.

    Greedy outer values hide their children. A selected value may consequently
    have only one reachable occurrence; block it and repeat so its children can
    still share. Shared entries always contain the untouched original value.
    """
    counts = {}
    literals = {}

    def count(value, path):
        if _literal_path(path):
            return
        if _can_share(value, path):
            key = canonical_context_bytes(value)
            if len(key) >= _MIN_SHARED_BYTES:
                counts[key] = counts.get(key, 0) + 1
                literals[key] = value
        if isinstance(value, dict):
            for name, child in value.items():
                count(child, path + (name,))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                count(child, path + (index,))

    count(context, ())
    candidates = {key for key, count_ in counts.items() if count_ > 1}
    while candidates:
        shared, indexes, uses = [], {}, {}

        def encode(value, path):
            if _literal_path(path):
                return copy.deepcopy(value)
            if _can_share(value, path):
                key = canonical_context_bytes(value)
                if key in candidates:
                    if key not in indexes:
                        indexes[key] = len(shared)
                        shared.append(copy.deepcopy(literals[key]))
                        uses[key] = 0
                    uses[key] += 1
                    return {_VALUE_REF: indexes[key]}
            if isinstance(value, dict):
                return {name: encode(child, path + (name,)) for name, child in value.items()}
            if isinstance(value, list):
                return [encode(child, path + (index,)) for index, child in enumerate(value)]
            return value

        encoded = encode(context, ())
        # Keep only entries that save bytes including each reference, one stored
        # value and its list delimiter. Reject marginal entries conservatively.
        waste = {key for key, count_ in uses.items()
                 if count_ * len(key) <= len(key) + 1 + count_ * len(
                     canonical_context_bytes({_VALUE_REF: indexes[key]}))}
        if waste:
            candidates -= waste
            continue
        encoded[_CONTEXT_ENCODING] = _ENCODING_VERSION
        encoded[_SHARED_VALUES] = shared
        if _saves_complete_request(context, encoded):
            return encoded
        break
    return copy.deepcopy(context)


def _restore_shared_values(encoded, *, max_shared_expansion_bytes):
    if _CONTEXT_ENCODING not in encoded:
        _check_json(encoded, reserved=True)
        return copy.deepcopy(encoded)
    if (encoded.get(_CONTEXT_ENCODING) != _ENCODING_VERSION
            or not isinstance(encoded.get(_SHARED_VALUES), list)
            or not encoded[_SHARED_VALUES]):
        raise ValueError('invalid_target_reference_context')
    if type(max_shared_expansion_bytes) is not int or max_shared_expansion_bytes < 1:
        raise ValueError('invalid_target_reference_context')
    shared = encoded[_SHARED_VALUES]
    seen = set()
    shared_sizes = []
    for value in shared:
        _check_json(value, reserved=True)
        key = canonical_context_bytes(value)
        if key in seen:
            raise ValueError('invalid_target_reference_context')
        seen.add(key)
        shared_sizes.append(len(key))
    used = set()

    def reference_index(value):
        index = value[_VALUE_REF]
        if (set(value) != {_VALUE_REF} or type(index) is not int
                or not 0 <= index < len(shared)):
            raise ValueError('invalid_target_reference_context')
        return index

    # Measure the expanded canonical JSON before allocating any repeated copy.
    # Production passes the already-known original size; standalone decoders
    # default to 16 MiB and callers may set an explicit trusted budget.
    def expanded_size(value):
        if isinstance(value, dict):
            if _VALUE_REF in value:
                index = reference_index(value)
                used.add(index)
                size = shared_sizes[index]
            else:
                if _RESERVED_KEYS.intersection(value):
                    raise ValueError('invalid_target_reference_context')
                size = 2 + max(0, len(value) - 1)
                for name, child in value.items():
                    size += len(canonical_context_bytes(name)) + 1 + expanded_size(child)
                    if size > max_shared_expansion_bytes:
                        raise ValueError('invalid_target_reference_context')
        elif isinstance(value, list):
            size = 2 + max(0, len(value) - 1)
            for child in value:
                size += expanded_size(child)
                if size > max_shared_expansion_bytes:
                    raise ValueError('invalid_target_reference_context')
        else:
            size = len(canonical_context_bytes(value))
        if size > max_shared_expansion_bytes:
            raise ValueError('invalid_target_reference_context')
        return size

    def restore(value):
        if isinstance(value, dict):
            if _VALUE_REF in value:
                return copy.deepcopy(shared[reference_index(value)])
            return {name: restore(child) for name, child in value.items()}
        if isinstance(value, list):
            return [restore(child) for child in value]
        return value

    data = {name: value for name, value in encoded.items()
            if name not in (_CONTEXT_ENCODING, _SHARED_VALUES)}
    expanded_size(data)
    if used != set(range(len(shared))):
        raise ValueError('invalid_target_reference_context')
    return restore(data)
