"""Lossless context-reference gates using invented data and fake AGY capture only."""
import copy
import json

import pytest

from curriculum.teacher_review_context import (
    canonical_context_bytes, encode_provider_context, restore_provider_context,
)
from curriculum.teacher_review import _validate_output
from curriculum.teacher_review_provider import ReviewProviderError, RESPONSE_SCHEMA
from curriculum.gemini_review_provider import VERIFIED_MODEL
from test_teacher_review_gemini import _adapter, _receipt, fake_runtime_identity


def synthetic_context():
    targets = [
        {'target_id': 'general-context', 'scope': 'general', 'field_name': 'contexto',
         'session_id': '', 'human_label': 'Contexto sintético',
         'operational_state': 'needs_resolution',
         'provenance': {'excerpt': '  Texto de fuente sintética.\n', 'page': 1}},
        {'target_id': 'session-2-annex', 'scope': 'annex', 'field_name': '',
         'session_id': 'session-2', 'human_label': 'Anexo sintético',
         'operational_state': 'pending_review',
         'provenance': {'excerpt': 'Consultar anexo sintético.', 'page': 2}},
        {'target_id': 'session-1-method', 'scope': 'session', 'field_name': 'metodo',
         'session_id': 'session-1', 'human_label': 'Método sintético',
         'operational_state': 'resolved', 'provenance': {'origin': 'teacher_entered'}},
    ]
    return {
        'dossier': {'source_sha256': 'a' * 64, 'version': 3, 'page_count': 3,
                    'general_fields': {'proyecto': {'value': 'Proyecto inventado', 'evidence': []}},
                    'sessions': [
                        {'session_id': 'session-1', 'activities': [{'activity_id': 'activity-1'}]},
                        {'session_id': 'session-2', 'annex_references': [{'reference_id': 'annex-2', 'confirmed_page': None}]},
                    ],
                    'verification_report': {'status': 'synthetic-test-only', 'items': [{'id': 'retained-item', 'message': 'Retener texto exacto'}]},
                    'history': [{'version': 3, 'action': 'teacher_review_answer', 'actor': 'synthetic-user'}]},
        'source_document': {'source_sha256': 'a' * 64, 'page_count': 3,
                            'representation': 'pypdf_digital_text', 'ocr_performed': False,
                            'missing_text_pages': [2, 3],
                            'pages': [{'page_number': 1, 'text': '  Texto de fuente sintética.\n', 'status': 'text'},
                                      {'page_number': 2, 'text': None, 'status': 'extraction_unavailable'},
                                      {'page_number': 3, 'text': '', 'status': 'no_digital_text'}]},
        'turns': [{'id': 'turn-1', 'question': '¿Qué método usarás?',
                   'targets': ['session-1-method'], 'answer': 'Conversación guiada', 'skipped': False,
                   'eligible_targets': ['session-1-method'],
                   'answer_history': [{'answer': 'Conversación guiada', 'at': '2026-01-01T00:00:00Z'}],
                   'applied': []}],
        'all_targets': targets, 'missing_fields': copy.deepcopy(targets[:2]),
        'questions_asked': 1, 'max_questions': 6, 'questions_remaining': 5,
    }


@pytest.mark.parametrize('positions', [(0, 1, 2), (1, 0), ()])
def test_encoding_roundtrips_every_field_preserves_order_and_input(positions):
    original = synthetic_context()
    original['missing_fields'] = [copy.deepcopy(original['all_targets'][index]) for index in positions]
    before = canonical_context_bytes(original)
    encoded = encode_provider_context(original)
    assert canonical_context_bytes(original) == before
    assert 'missing_fields' not in encoded
    assert encoded['missing_target_ids'] == [original['all_targets'][index]['target_id'] for index in positions]
    assert canonical_context_bytes(restore_provider_context(encoded)) == before
    for key in original.keys() - {'missing_fields'}:
        assert canonical_context_bytes(encoded[key]) == canonical_context_bytes(original[key])
    encoded['dossier']['sessions'][0]['activities'][0]['activity_id'] = 'only-copy-changed'
    assert canonical_context_bytes(original) == before


def _bad_context(kind):
    value = synthetic_context()
    if kind == 'duplicate_all':
        value['all_targets'].append(copy.deepcopy(value['all_targets'][0]))
    elif kind == 'duplicate_missing':
        value['missing_fields'].append(copy.deepcopy(value['missing_fields'][0]))
    elif kind == 'unknown_id':
        value['missing_fields'][0]['target_id'] = 'unknown-target'
    elif kind == 'conflicting_record':
        value['missing_fields'][0]['human_label'] = 'Different metadata'
    elif kind == 'bool_integer_not_identical':
        value['all_targets'][0]['extra'] = True
        value['missing_fields'][0]['extra'] = 1
    elif kind == 'empty_id':
        value['all_targets'][0]['target_id'] = ''
    elif kind == 'nonstring_id':
        value['all_targets'][0]['target_id'] = 12
    elif kind == 'reserved_key':
        value['missing_target_ids'] = ['would-be-overwritten']
    elif kind == 'missing_array':
        value.pop('missing_fields')
    else:
        raise AssertionError(kind)
    return value


@pytest.mark.parametrize('kind', ['duplicate_all', 'duplicate_missing', 'unknown_id',
                                  'conflicting_record', 'bool_integer_not_identical',
                                  'empty_id', 'nonstring_id', 'reserved_key', 'missing_array'])
def test_invalid_reference_context_is_rejected_without_mutating_input(kind):
    value = _bad_context(kind)
    before = canonical_context_bytes(value)
    with pytest.raises(ValueError, match='^invalid_target_reference_context$'):
        encode_provider_context(value)
    assert canonical_context_bytes(value) == before


@pytest.mark.parametrize('ids', [['unknown'], ['general-context', 'general-context'], [123]])
def test_restore_rejects_unknown_duplicate_or_nonstring_ids(ids):
    encoded = encode_provider_context(synthetic_context())
    encoded['missing_target_ids'] = ids
    with pytest.raises(ValueError, match='^invalid_target_reference_context$'):
        restore_provider_context(encoded)


@pytest.mark.parametrize('kind', ['duplicate_all', 'unknown_id', 'conflicting_record'])
def test_adapter_rejects_invalid_references_before_capture_or_admission(tmp_path, kind):
    provider = _adapter(tmp_path, lambda *a, **k: pytest.fail('Invalid context must never reach inference capture'))
    with pytest.raises(ReviewProviderError, match='^invalid_target_reference_context$'):
        provider(_bad_context(kind))
    assert not provider.attempt_root.exists()


def test_fake_request_uses_explicit_reference_contract_and_unchanged_output_schema(tmp_path):
    context = synthetic_context()
    original_bytes = canonical_context_bytes(context)
    seen = []
    output = {'question': '¿Dónde se realizará esta sesión?',
              'targets': [context['missing_fields'][0]['target_id']], 'answer_updates': []}
    def capture(argv, directory, limits, **kwargs):
        request = json.loads((directory / 'request.ndjson').read_text())
        instructions, raw = request['message']['content'].split('\nDATOS:\n', 1)
        assert 'missing_target_ids' in instructions and 'all_targets' in instructions
        encoded = json.loads(raw)
        assert 'missing_fields' not in encoded
        assert raw == json.dumps(encoded, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        assert canonical_context_bytes(restore_provider_context(encoded)) == original_bytes
        assert json.loads(argv[argv.index('--json-schema') + 1]) == RESPONSE_SCHEMA
        assert kwargs['detector']({'event': 'init', 'init': {'model': VERIFIED_MODEL, 'agent': 'structure-only', 'tools': []}}) == ([], [])
        seen.append(1)
        return _receipt(), json.dumps(output).encode()
    result = _adapter(tmp_path, capture)(context)
    assert seen == [1]
    assert dict(result) == output
    assert _validate_output(result, context) == result
    assert canonical_context_bytes(context) == original_bytes
