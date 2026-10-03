"""Malformed fixture envelopes stay bounded; no provider evidence or retry."""
import copy
import json
import pytest
from scripts.sprint_eval.gemini import GeminiAdapter
from scripts.sprint_eval.luna import Candidate, FrozenCase, ProviderReply, run_case
from scripts.sprint_eval.offline_v2 import run_fixtures
from test_sprint_gemini import Transport, CASE, MODEL, SCHEMA, response


def test_both_adapters_accept_the_same_real_local_v2_contract(monkeypatch):
    monkeypatch.setattr('scripts.sprint_eval.gemini._request_json', lambda *a: pytest.fail('Network forbidden'))
    result = run_fixtures()
    assert len(result['results']) == 3
    assert all(r['schema_status'] == {'gemini': 'ok', 'luna': 'validated'} for r in result['results'])
    assert result['real_response_count'] == 0 and result['model_winner'] is None
    assert all(r['semantic_status'] == 'NOT_EVALUATED' for r in result['results'])
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('bad', [True, -1, float('nan'), '12', 10**400])
def test_gemini_invalid_usage_is_not_recorded(bad):
    envelope = response()
    envelope['usageMetadata']['totalTokenCount'] = bad
    transport = Transport(generation=envelope)
    result = GeminiAdapter('fixture', transport=transport).run_corpus([CASE], model=MODEL, schema=SCHEMA, validate=lambda p: None)
    row = result['results'][0]
    assert row['status'] == 'error' and row['reason'] == 'invalid_usage'
    assert row['usage'] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('text', ['{"approval_status":"approved","approval_status":"pending"}', '[' * 1100 + '0' + ']' * 1100, '\ud800'])
def test_gemini_duplicate_json_recursion_and_unicode_are_bounded(text):
    envelope = response()
    envelope['candidates'][0]['content']['parts'][0]['text'] = text
    transport = Transport(generation=envelope)
    result = GeminiAdapter('fixture', transport=transport).run_corpus([CASE], model=MODEL, schema=SCHEMA, validate=lambda p: None)
    assert result['results'][0]['status'] == 'invalid_output'
    assert len(transport.calls) == 2


def test_gemini_evaluator_error_preserves_row_and_binds_budget():
    def fail(_):
        raise RuntimeError('private error')
    rows = []
    for budget in (100, 8000):
        result = GeminiAdapter('fixture', transport=Transport()).run_corpus([CASE], model=MODEL, schema=SCHEMA, validate=fail, max_output_tokens=budget)
        rows.append(result['results'][0])
        assert rows[-1]['status'] == 'evaluator_error'
        assert 'private error' not in json.dumps(result)
    assert rows[0]['request_sha256'] != rows[1]['request_sha256']


@pytest.mark.parametrize('text,cost', [('\ud800', None), ('{}', 10**400)])
def test_luna_unicode_and_cost_overflow_return_a_row(text, cost):
    result = run_case(FrozenCase('x', b'p', b'c', b'r'), Candidate('fixture', lambda *a: ProviderReply('fixture', text, cost_usd=cost), 'fixture'), lambda p: [])
    assert result['status'] in {'invalid_response', 'provider_error'}
    assert result['provider_evidence'] is False
    json.dumps(result, allow_nan=False)
