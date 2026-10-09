"""Lossless shared values: invented data only; no inference or credentials."""
import copy
import json
import random

import pytest

from curriculum.teacher_review_context import (
    canonical_context_bytes, encode_provider_context, restore_provider_context, provider_context_instructions,
)
from curriculum.teacher_review_provider import SYSTEM
from test_teacher_review_context_encoding import synthetic_context


def repeated_context():
    context = synthetic_context()
    source_ref = {
        'document_sha256': 'a' * 64, 'page_number': 1, 'printed_label': '',
        'excerpt': '  Línea exacta inventada con Unicode: á ñ 🦉.\r\n' * 8,
        'region': None, 'role': 'source',
    }
    before = {'name': 'metodo', 'value': '  Respuesta anterior.\n' * 12,
              'origin': 'teacher_entered', 'evidence': [source_ref],
              'review': 'confirmed', 'version': 2}
    after = {**before, 'value': 'Respuesta corregida; no normalizar.\r\n' * 12,
             'version': 3}
    context['dossier']['general_fields']['metodo'] = copy.deepcopy(after)
    context['dossier']['history'][0]['deltas'] = [
        {'before': copy.deepcopy(before), 'after': copy.deepcopy(after),
         'target_id': 'session-1-method'}]
    context['turns'][0]['applied'] = [
        {'before': copy.deepcopy(before), 'after': copy.deepcopy(after),
         'target_id': 'session-1-method'}]
    context['turns'][0]['answer'] = after['value']
    context['turns'][0]['answer_history'] = [
        {'answer': before['value'], 'at': '2026-01-01T00:00:00Z'},
        {'answer': after['value'], 'at': '2026-01-01T00:01:00Z'}]
    context['source_document']['pages'][0]['text'] = source_ref['excerpt']
    for target in context['all_targets']:
        target['source_refs'] = [copy.deepcopy(source_ref)]
    context['missing_fields'] = copy.deepcopy(context['all_targets'][:2])
    context['question_policy'] = {'version': 1, 'candidate_target_ids': ['general-context'],
                                  'other_pending_items': 'explicit_human_review'}
    return context


def test_shared_values_preserve_every_literal_link_version_and_history():
    original = repeated_context()
    before = canonical_context_bytes(original)
    encoded = encode_provider_context(original)
    assert encoded['_context_encoding'] == 'shared-values-v1'
    assert '_shared_values' in encoded
    restored = restore_provider_context(encoded)
    assert canonical_context_bytes(restored) == before
    assert canonical_context_bytes(original) == before
    assert encoded['source_document'] == original['source_document']
    assert encoded['question_policy'] == original['question_policy']
    for key in ('answer', 'answer_history', 'question', 'targets', 'eligible_targets'):
        assert encoded['turns'][0][key] == original['turns'][0][key]
    assert encoded['missing_target_ids'] == [t['target_id'] for t in original['missing_fields']]
    assert isinstance(encoded['all_targets'], list)
    assert all(isinstance(t['target_id'], str) for t in encoded['all_targets'])
    legacy = copy.deepcopy(original)
    legacy.pop('missing_fields')
    legacy['missing_target_ids'] = encoded['missing_target_ids']
    assert len(canonical_context_bytes(encoded)) < len(canonical_context_bytes(legacy))
    # Neither decoding nor encoding introduces aliasing in the backend.
    restored['turns'][0]['applied'][0]['before']['value'] = 'edited'
    assert original['turns'][0]['applied'][0]['before']['value'] != 'edited'
    assert restored['dossier']['history'][0]['deltas'][0]['before']['value'] != 'edited'
    assert 'shared-values-v1' in provider_context_instructions(encoded)
    assert '$value_ref' in provider_context_instructions(encoded)


@pytest.mark.parametrize('marker', ['_context_encoding', '_shared_values', '$value_ref'])
def test_reserved_marker_anywhere_in_input_fails_closed(marker):
    context = repeated_context()
    context['dossier']['history'].append({marker: 'not provider-owned'})
    before = copy.deepcopy(context)
    with pytest.raises(ValueError, match='invalid_target_reference_context'):
        encode_provider_context(context)
    assert context == before


@pytest.mark.parametrize('kind', ['unknown_version', 'absent_values', 'empty_values',
    'duplicate_value', 'unused_value', 'nested_ref', 'cycle', 'dangling', 'negative',
    'bool_index', 'float_index', 'string_index', 'extra_key', 'marker_without_version'])
def test_malformed_encoded_data_never_restores(kind):
    encoded = encode_provider_context(repeated_context())
    if kind == 'unknown_version':
        encoded['_context_encoding'] = 'shared-values-v2'
    elif kind == 'absent_values':
        del encoded['_shared_values']
    elif kind == 'empty_values':
        encoded['_shared_values'] = []
    elif kind == 'duplicate_value':
        encoded['_shared_values'].append(copy.deepcopy(encoded['_shared_values'][0]))
    elif kind == 'unused_value':
        encoded['_shared_values'].append('unused synthetic value')
    elif kind in ('nested_ref', 'cycle'):
        encoded['_shared_values'][0] = {'$value_ref': 0 if kind == 'cycle' else 1}
    elif kind == 'marker_without_version':
        del encoded['_context_encoding']
    else:
        index = {'dangling': 100000, 'negative': -1, 'bool_index': True,
                 'float_index': 0.0, 'string_index': '0', 'extra_key': 0}[kind]
        encoded['dossier']['general_fields']['invalid'] = {'$value_ref': index}
        if kind == 'extra_key':
            encoded['dossier']['general_fields']['invalid']['value'] = 'smuggled'
    with pytest.raises(ValueError, match='invalid_target_reference_context'):
        restore_provider_context(encoded)


def test_legacy_encoding_still_restores_and_small_context_never_grows():
    context = synthetic_context()
    legacy = copy.deepcopy(context)
    legacy['missing_target_ids'] = [t['target_id'] for t in legacy.pop('missing_fields')]
    assert restore_provider_context(legacy) == context
    encoded = encode_provider_context(context)
    assert len(canonical_context_bytes(encoded)) <= len(canonical_context_bytes(legacy))


@pytest.mark.parametrize('scalar', [True, 1, 1.0, None, '', [], {}])
def test_type_and_absence_are_not_collapsed(scalar):
    context = repeated_context()
    context['dossier']['typed_values'] = [
        {'value': scalar, 'literal': 'same synthetically long literal ' * 10},
        {'value': 1, 'literal': 'same synthetically long literal ' * 10},
        {'literal': 'same synthetically long literal ' * 10},
    ] * 3
    assert canonical_context_bytes(restore_provider_context(encode_provider_context(context))) == canonical_context_bytes(context)


def test_distinct_provenance_roles_and_pages_stay_distinct():
    context = repeated_context()
    ref = context['all_targets'][0]['source_refs'][0]
    context['dossier']['distinct_refs'] = [copy.deepcopy(ref), {**ref, 'page_number': 2},
        {**ref, 'role': 'teacher'}, {**ref, 'region': [1, 2, 3, 4]},
        {**ref, 'document_sha256': 'b' * 64}]
    restored = restore_provider_context(encode_provider_context(context))
    assert restored['dossier']['distinct_refs'] == context['dossier']['distinct_refs']


def test_deterministic_random_nested_json_roundtrips_and_never_grows():
    rng = random.Random(64261)
    def value(depth):
        if depth == 0:
            return rng.choice([None, True, 1, 1.0, '', 'á\r\n🦉' * 30])
        return rng.choice([
            [value(depth - 1) for _ in range(3)],
            {'x': value(depth - 1), 'y': value(depth - 1)},
        ])
    for _ in range(30):
        context = repeated_context()
        nested = value(3)
        context['dossier']['random'] = [nested, copy.deepcopy(nested)]
        encoded = encode_provider_context(context)
        assert canonical_context_bytes(restore_provider_context(encoded)) == canonical_context_bytes(context)
        assert encode_provider_context(context) == encoded
        legacy = copy.deepcopy(context)
        legacy['missing_target_ids'] = [t['target_id'] for t in legacy.pop('missing_fields')]
        assert len(canonical_context_bytes(encoded)) <= len(canonical_context_bytes(legacy))


@pytest.mark.parametrize('number', [float('nan'), float('inf'), float('-inf')])
def test_nonfinite_json_is_rejected_in_encoder_and_both_decoder_versions(number):
    original = repeated_context()
    original['dossier']['invalid'] = number
    with pytest.raises(ValueError, match='invalid_target_reference_context'):
        encode_provider_context(original)
    for encoded in [encode_provider_context(repeated_context()), encode_provider_context(synthetic_context())]:
        encoded['dossier']['invalid'] = number
        with pytest.raises(ValueError, match='invalid_target_reference_context'):
            restore_provider_context(encoded)


def test_decoder_expansion_budget_is_checked_before_copying_referenced_values(monkeypatch):
    encoded = encode_provider_context(repeated_context())
    def no_copy(_):
        pytest.fail('Expansion budget must be checked before allocating shared values')
    monkeypatch.setattr('curriculum.teacher_review_context.copy.deepcopy', no_copy)
    with pytest.raises(ValueError, match='invalid_target_reference_context'):
        restore_provider_context(encoded, max_shared_expansion_bytes=100)


def test_decoder_expansion_accepts_exact_trusted_original_budget():
    context = repeated_context()
    encoded = encode_provider_context(context)
    restored = restore_provider_context(encoded, max_shared_expansion_bytes=len(canonical_context_bytes(context)))
    assert canonical_context_bytes(restored) == canonical_context_bytes(context)


@pytest.mark.parametrize('repetitions', [0, 2, 10])
def test_total_prompt_and_json_request_never_grow_even_for_marginal_repeats(repetitions):
    context = synthetic_context()
    context['dossier']['extra'] = ['dato sintético ' * 15] * repetitions
    encoded = encode_provider_context(context)
    legacy = copy.deepcopy(context)
    legacy['missing_target_ids'] = [t['target_id'] for t in legacy.pop('missing_fields')]
    def text(value):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    before = SYSTEM + '\nDATOS:\n' + text(legacy)
    after = SYSTEM + provider_context_instructions(encoded) + '\nDATOS:\n' + text(encoded)
    assert len(after.encode()) <= len(before.encode())
    assert len(text({'message': after}).encode()) <= len(text({'message': before}).encode())
    if repetitions < 3:
        assert '_context_encoding' not in encoded
        assert provider_context_instructions(encoded) == ''


def test_resolved_context_keeps_processing_corrections_with_empty_missing_fields():
    # missing_target_ids is a longer key than missing_fields; the expansion
    # budget must describe this intermediate representation, not the final one.
    context = {'all_targets': [], 'missing_fields': [],
               'dossier': {'items': ['x' * 1000] * 4}}
    encoded = encode_provider_context(context)
    assert encoded['_context_encoding'] == 'shared-values-v1'
    assert encoded['missing_target_ids'] == []
    assert restore_provider_context(encoded) == context
