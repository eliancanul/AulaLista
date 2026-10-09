"""Lossless provider-only target references; canonical backend context is unchanged."""
import copy
import json


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


def restore_provider_context(encoded):
    if not isinstance(encoded, dict) or 'missing_fields' in encoded:
        raise ValueError('invalid_target_reference_context')
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
    all_by_id = _index_targets(context.get('all_targets'))
    missing_by_id = _index_targets(context.get('missing_fields'))
    for target_id, record in missing_by_id.items():
        if target_id not in all_by_id or canonical_context_bytes(record) != canonical_context_bytes(all_by_id[target_id]):
            raise ValueError('invalid_target_reference_context')
    encoded = copy.deepcopy(context)
    encoded.pop('missing_fields')
    encoded['missing_target_ids'] = list(missing_by_id)
    if canonical_context_bytes(restore_provider_context(encoded)) != canonical_context_bytes(context):
        raise ValueError('invalid_target_reference_context')
    return encoded
