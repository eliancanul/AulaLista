"""Opt-in physical-span transport, using invented data and offline doubles only."""
import copy
import json
import pytest

from curriculum.teacher_review_context import canonical_context_bytes as canon
from curriculum.teacher_review_task_context import build_task_context, provider_task_payload
from curriculum.teacher_review_table_context import encode_table_context, restore_table_context, TABLE_SYSTEM
from curriculum.teacher_review_quote_values import VALUE_QUOTE_INSTRUCTIONS
from curriculum.teacher_review import _validate_output
from curriculum.teacher_review_provider import ReviewProviderError
from curriculum.teacher_review_structure_context import (
    encode_structure_context, restore_structure_context,
)
from test_teacher_review_task_context import answered_fixture
from test_teacher_review_pi import fake_pi
from test_teacher_review_luna_cli import fake_cli
from test_teacher_review_gemini import _adapter, _receipt, fake_runtime_identity


def structure_fixture():
    context, _ = answered_fixture()
    source = context['source_document']
    text = 'A🦉áe\u0301\r\n¿Sí?\n'
    blocks = []
    for index in range(32):
        excerpt = f'Actividad inventada {index}: observar y comparar las figuras del cuaderno. '
        start = len(text)
        text += excerpt + '\r\n'
        fragment = {'document_sha256': source['source_sha256'], 'page_number': 1,
                    'text_start': start, 'text_end': start + len(excerpt), 'excerpt': excerpt}
        blocks.append({'block_id': f'invented-{index}', 'role': 'instruction',
                       'text': excerpt, 'phase_id': 'invented-phase', 'parent_id': None,
                       'evidence': [fragment], 'origin': 'proposed',
                       'status': 'ambiguous', 'review': 'pending'})
    source['pages'][0]['text'] = text
    context['dossier']['sessions'][0]['source_structure'] = {
        'schema_version': 1, 'phases': [], 'blocks': blocks}
    context['dossier']['annex_candidates'] = [{'source_fragments': [
        {'page_number': 1, 'text_start': 1, 'text_end': 5, 'excerpt': '🦉áe\u0301',
         'role': 'worksheet_heading', 'reason': None, 'future': {'literal': [True, None]}},
        {'page_number': 1, 'text_start': 7, 'text_end': 11, 'excerpt': '¿Sí?'}]}]
    return context


def test_exact_structure_roundtrip_keeps_full_v2_source_state_and_absence():
    context = structure_fixture()
    table = encode_table_context(build_task_context(context))
    before = canon(table)
    encoded = encode_structure_context(table)
    assert '_structure_transport' in encoded
    assert len(canon(encoded)) < len(before)
    assert canon(restore_structure_context(encoded)) == before
    assert restore_table_context(restore_structure_context(encoded)) == build_task_context(context)
    assert canon(table) == before
    assert encoded['source_document'] == table['source_document']
    assert len(encoded['source_document']['pages']) == 2


def test_decoder_bounds_expansion_and_returns_independent_values():
    table = encode_table_context(build_task_context(structure_fixture()))
    encoded = encode_structure_context(table)
    budget = len(canon(table))
    assert canon(restore_structure_context(encoded, max_expanded_bytes=budget)) == canon(table)
    with pytest.raises(ValueError, match='structure_context_expansion_too_large'):
        restore_structure_context(encoded, max_expanded_bytes=budget - 1)
    first = encoded['dossier']['annex_candidates'][0]['source_fragments'][0]
    encoded['dossier']['annex_candidates'][0]['source_fragments'].append(copy.deepcopy(first))
    before = canon(encoded)
    restored = restore_structure_context(encoded)
    fragments = restored['dossier']['annex_candidates'][0]['source_fragments']
    fragments[0]['future']['literal'].append('mutation')
    assert fragments[-1]['future']['literal'] == [True, None]
    assert canon(encoded) == before


@pytest.mark.parametrize('corruption', [
    'version', 'contract', 'columns', 'extra_header', 'duplicate_attributes',
    'unused_attributes', 'attribute_collision', 'nested_reference', 'wrong_sha',
    'bool_attribute', 'float_attribute', 'missing_attribute', 'bool_page',
    'unknown_page', 'duplicate_page', 'negative_start', 'past_end', 'extra_cell',
    'extra_reference_key', 'short_block', 'extra_block_key', 'bool_excerpt',
    'past_excerpt', 'extra_excerpt_key', 'reference_outside_scope',
    'block_text_wrong_type', 'block_evidence_wrong_type',
])
def test_decoder_rejects_malformed_or_ambiguous_transport(corruption):
    encoded = encode_structure_context(encode_table_context(build_task_context(structure_fixture())))
    transport = encoded['_structure_transport']
    attributes = transport['fragment_attributes']
    blocks = encoded['dossier']['sessions'][0]['source_structure']['blocks']
    block = blocks[0]['$block']
    fragment = block[5][0]
    row = fragment['$fragment']
    if corruption == 'version': transport['version'] = 'physical-spans-v999'
    elif corruption == 'contract': encoded['context_contract'] = 'unknown'
    elif corruption == 'columns': transport['block_columns'].reverse()
    elif corruption == 'extra_header': transport['defaults'] = {}
    elif corruption == 'duplicate_attributes': attributes.append(copy.deepcopy(attributes[0]))
    elif corruption == 'unused_attributes': attributes.append({'future': 'unused'})
    elif corruption == 'attribute_collision': attributes[0]['excerpt'] = 'forged'
    elif corruption == 'nested_reference': attributes[0]['future'] = {'$fragment': row[:]}
    elif corruption == 'wrong_sha': attributes[0]['document_sha256'] = 'b' * 64
    elif corruption == 'bool_attribute': row[0] = False
    elif corruption == 'float_attribute': row[0] = 0.0
    elif corruption == 'missing_attribute': row[0] = 999
    elif corruption == 'bool_page': row[1] = True
    elif corruption == 'unknown_page': row[1] = 99
    elif corruption == 'duplicate_page': encoded['source_document']['pages'].append(copy.deepcopy(encoded['source_document']['pages'][0]))
    elif corruption == 'negative_start': row[2] = -1
    elif corruption == 'past_end': row[3] = 10**9
    elif corruption == 'extra_cell': row.append(0)
    elif corruption == 'extra_reference_key': fragment['extra'] = 0
    elif corruption == 'short_block': block.pop()
    elif corruption == 'extra_block_key': blocks[0]['extra'] = 0
    elif corruption == 'bool_excerpt': block[2]['$excerpt'] = False
    elif corruption == 'past_excerpt': block[2]['$excerpt'] = 99
    elif corruption == 'extra_excerpt_key': block[2]['extra'] = 0
    elif corruption == 'reference_outside_scope': encoded['turns'][0]['answer'] = copy.deepcopy(fragment)
    elif corruption == 'block_text_wrong_type': block[2] = 42
    elif corruption == 'block_evidence_wrong_type':
        block[2] = 'Literal text'
        block[5] = {'wrong': 'not a list'}
    with pytest.raises(ValueError):
        restore_structure_context(encoded)


@pytest.mark.parametrize('difference', [
    'utf8_offsets', 'utf16_offsets', 'nfc_excerpt', 'normalized_newline',
    'wrong_offset', 'bool_offset', 'float_offset', 'unknown_page', 'duplicate_page',
    'foreign_sha', 'foreign_source_sha', 'null_sha', 'cross_page', 'missing_offset',
])
def test_inexact_unknown_foreign_and_cross_page_fragments_stay_literal(difference):
    context = structure_fixture()
    fragment = {'page_number': 1, 'text_start': 1, 'text_end': 5, 'excerpt': '🦉áe\u0301'}
    if difference == 'utf8_offsets': fragment['text_end'] = 10
    elif difference == 'utf16_offsets': fragment['text_end'] = 6
    elif difference == 'nfc_excerpt': fragment['excerpt'] = '🦉áé'
    elif difference == 'normalized_newline': fragment.update(text_start=5, text_end=7, excerpt='\n')
    elif difference == 'wrong_offset': fragment['text_start'] = 0
    elif difference == 'bool_offset': fragment['text_start'] = True
    elif difference == 'float_offset': fragment['text_start'] = 1.0
    elif difference == 'unknown_page': fragment['page_number'] = 999
    elif difference == 'duplicate_page': context['source_document']['pages'].append(copy.deepcopy(context['source_document']['pages'][0]))
    elif difference == 'foreign_sha': fragment['document_sha256'] = 'b' * 64
    elif difference == 'foreign_source_sha': fragment['source_sha256'] = 'b' * 64
    elif difference == 'null_sha': fragment['document_sha256'] = None
    elif difference == 'cross_page':
        first, second = context['source_document']['pages'][:2]
        fragment.update(text_start=len(first['text']) - 2, text_end=len(first['text']) + 3,
                        excerpt=first['text'][-2:] + second['text'][:3])
    elif difference == 'missing_offset': fragment.pop('text_start')
    context['dossier']['annex_candidates'][0]['source_fragments'] = [fragment]
    table = encode_table_context(build_task_context(context))
    encoded = encode_structure_context(table)
    assert encoded['dossier']['annex_candidates'][0]['source_fragments'] == [fragment]
    assert canon(restore_structure_context(encoded)) == canon(table)


@pytest.mark.parametrize('block_count', [0, 2, 32])
def test_opt_in_preserves_values_system_and_saves_net_or_falls_back_exactly(settings, block_count):
    context = structure_fixture() if block_count else answered_fixture()[0]
    if block_count == 2:
        context['dossier']['sessions'][0]['source_structure']['blocks'] = context['dossier']['sessions'][0]['source_structure']['blocks'][:2]
        context['dossier']['annex_candidates'] = []
    before = canon(context)
    settings.AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = 'semantic-v2-values'
    base_system, base_payload = provider_task_payload(context)
    settings.AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = 'semantic-v2-values-spans'
    system, payload = provider_task_payload(context)
    assert base_system == TABLE_SYSTEM + VALUE_QUOTE_INSTRUCTIONS
    assert system.startswith(base_system)
    assert canon(restore_structure_context(payload)) == canon(base_payload)
    assert canon(context) == before
    if block_count == 32:
        assert system != base_system
        for wrap in (lambda value: value, lambda value: json.dumps(value, ensure_ascii=False)):
            assert len(wrap(system + canon(payload).decode()).encode()) < len(wrap(base_system + canon(base_payload).decode()).encode())
    else:
        assert system == base_system
        assert canon(payload) == canon(base_payload)


def test_nonstandard_blocks_and_nonmatching_text_keep_literal_shape_and_values():
    context = structure_fixture()
    blocks = context['dossier']['sessions'][0]['source_structure']['blocks']
    blocks[0]['future'] = {'keep': ['every field']}
    blocks[1]['text'] = blocks[0]['text']  # Exists on the page, but not its own excerpt.
    del blocks[2]['review']
    for index, role in enumerate(('heading', 'resource', 'unassigned', 'question', 'step', 'activity')):
        blocks[index]['role'] = role
        blocks[index]['review'] = 'rejected' if index % 2 else 'pending'
    del blocks[2]['review']
    table = encode_table_context(build_task_context(context))
    encoded = encode_structure_context(table)
    actual = encoded['dossier']['sessions'][0]['source_structure']['blocks']
    assert actual[0]['future'] == {'keep': ['every field']}
    assert actual[1]['$block'][2] == blocks[0]['text']
    assert 'review' not in actual[2]
    assert canon(restore_structure_context(encoded)) == canon(table)


@pytest.mark.parametrize('budget', [True, False, 0, -1, 1.0, None])
def test_invalid_expansion_budgets_fail_closed(budget):
    encoded = encode_structure_context(encode_table_context(build_task_context(structure_fixture())))
    with pytest.raises(ValueError):
        restore_structure_context(encoded, max_expanded_bytes=budget)


@pytest.mark.parametrize('bad', [None, [], {}, 'text', {'context_contract': 'teacher-review-task-v2'}])
def test_invalid_roots_fail_closed(bad):
    with pytest.raises(ValueError):
        encode_structure_context(bad)
    with pytest.raises(ValueError):
        restore_structure_context(bad)


def test_unicode_codepoint_spans_use_physical_numbers_without_normalizing_source():
    context = structure_fixture()
    context['source_document']['pages'].reverse()  # Physical number, never list index.
    context['dossier']['annex_candidates'][0]['source_fragments'].append(
        {'page_number': 1, 'text_start': 5, 'text_end': 7, 'excerpt': '\r\n'})
    table = encode_table_context(build_task_context(context))
    encoded = encode_structure_context(table)
    fragments = encoded['dossier']['annex_candidates'][0]['source_fragments']
    assert fragments[0]['$fragment'][1:] == [1, 1, 5]
    assert fragments[1]['$fragment'][1:] == [1, 7, 11]
    assert fragments[2]['$fragment'][1:] == [1, 5, 7]
    restored = restore_structure_context(encoded)
    assert restored['source_document'] == table['source_document']
    assert canon(restored) == canon(table)


def test_fragment_fanout_exceeding_expansion_budget_is_rejected():
    table = encode_table_context(build_task_context(structure_fixture()))
    encoded = encode_structure_context(table)
    fragment = encoded['dossier']['sessions'][0]['source_structure']['blocks'][0]['$block'][5][0]
    encoded['dossier']['annex_candidates'].append({'source_fragments': [copy.deepcopy(fragment) for _ in range(2000)]})
    with pytest.raises(ValueError, match='structure_context_expansion_too_large'):
        restore_structure_context(encoded, max_expanded_bytes=2 * len(canon(table)))


@pytest.mark.parametrize('has_structure', [False, True])
def test_encoded_values_do_not_alias_original_even_on_fallback(has_structure):
    context = structure_fixture() if has_structure else answered_fixture()[0]
    table = encode_table_context(build_task_context(context))
    before = canon(table)
    encoded = encode_structure_context(table)
    encoded['source_document']['pages'][0]['status'] = 'changed'
    if has_structure:
        attrs = encoded['_structure_transport']['fragment_attributes']
        next(record for record in attrs if 'future' in record)['future']['literal'].append('changed')
    assert canon(table) == before


@pytest.mark.parametrize('marker', ['$fragment', '$block', '$excerpt', '_structure_transport'])
def test_reserved_marker_collisions_are_never_interpreted_as_data(marker):
    table = encode_table_context(build_task_context(structure_fixture()))
    table['dossier']['annex_candidates'][0]['future'] = {marker: 0}
    with pytest.raises(ValueError):
        encode_structure_context(table)


def test_nested_reserved_attribute_is_rejected_explicitly_before_interpretation():
    table = encode_table_context(build_task_context(structure_fixture()))
    table['dossier']['annex_candidates'][0]['source_fragments'][0]['future'] = {
        'nested': [{'$fragment': [0, 1, 1, 5]}]}
    with pytest.raises(ValueError, match='^reserved_structure_context_key$'):
        encode_structure_context(table)
    encoded = encode_structure_context(encode_table_context(build_task_context(structure_fixture())))
    encoded['_structure_transport']['fragment_attributes'][0]['future'] = {
        'nested': [{'$fragment': [0, 1, 1, 5]}]}
    with pytest.raises(ValueError, match='^reserved_structure_context_key$'):
        restore_structure_context(encoded)


def test_pi_opt_in_wrapper_keeps_original_ids_schema_source_and_backend_authority(fake_pi, settings):
    base, factory, scenario, _ = fake_pi
    settings.AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = 'semantic-v2-values-spans'
    context = structure_fixture()
    before = canon(context)
    target = context['turns'][0]['eligible_targets'][0]
    output = {'question': None, 'targets': [], 'answer_updates': [
        {'turn_id': context['turns'][0]['id'], 'target_id': target, 'quote': 'Comparar dos relatos.'}]}
    scenario(output=output)
    reply = factory()(context)
    request = json.loads((base / 'captured.txt').read_text())
    encoded = json.loads(request['prompt'].split('\nDATOS:\n', 1)[1])
    system, expected = provider_task_payload(context)
    assert request['system'] == system
    assert canon(encoded) == canon(expected)
    assert restore_table_context(restore_structure_context(encoded)) == build_task_context(context)
    assert _validate_output(reply, context) == output
    with pytest.raises(ReviewProviderError):
        _validate_output({**output, 'answer_updates': [{**output['answer_updates'][0], 'target_id': '0'}]}, context)
    assert canon(context) == before


@pytest.fixture
def fake_v2_cli(request, monkeypatch):
    # Extend only the invented executable boundary; production transport is real.
    import test_teacher_review_luna_cli as fixture_module
    monkeypatch.setattr(fixture_module, 'FAKE_CLI', fixture_module.FAKE_CLI.replace(
        "context['missing_target_ids']", "context.get('missing_target_ids', [])"))
    return request.getfixturevalue('fake_cli')


def test_luna_opt_in_wrapper_keeps_full_source_and_exact_system(fake_v2_cli, settings):
    base, _, factory, scenario, _ = fake_v2_cli
    settings.AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = 'semantic-v2-values-spans'
    context = structure_fixture()
    output = {'question': None, 'targets': [], 'answer_updates': []}
    scenario(output=output)
    reply = factory()(context)
    system, encoded = provider_task_payload(context)
    assert (base / 'captured.txt').read_text().startswith(system + '\nDATOS:\n')
    assert json.loads((base / 'captured-context.json').read_text()) == encoded
    assert restore_table_context(restore_structure_context(encoded)) == build_task_context(context)
    assert _validate_output(reply, context) == output


def test_gemini_opt_in_wrapper_keeps_full_source_and_exact_system(tmp_path, settings):
    from curriculum.gemini_review_provider import VERIFIED_MODEL
    settings.AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = 'semantic-v2-values-spans'
    context = structure_fixture()
    output = {'question': None, 'targets': [], 'answer_updates': []}
    seen = []
    def capture(argv, directory, limits, **kwargs):
        request = json.loads((directory / 'request.ndjson').read_text())
        system, raw = request['message']['content'].split('\nDATOS:\n', 1)
        expected_system, expected = provider_task_payload(context)
        assert system == expected_system
        assert json.loads(raw) == expected
        assert restore_table_context(restore_structure_context(expected)) == build_task_context(context)
        assert kwargs['detector']({'event': 'init', 'init': {
            'model': VERIFIED_MODEL, 'agent': 'structure-only', 'tools': []}}) == ([], [])
        seen.append(directory)
        return _receipt(), json.dumps(output).encode()
    reply = _adapter(tmp_path, capture)(context)
    assert len(seen) == 1
    assert _validate_output(reply, context) == output
