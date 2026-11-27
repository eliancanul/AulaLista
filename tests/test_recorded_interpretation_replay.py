"""Purely synthetic saved responses; no source corpus or external invocation."""
import copy
import json

import pytest

from scripts.replay_interpretation import ReplayError, digest, replay, source_digest


def example(kind='activity_session'):
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Resolver el anexo 1.\n-Revisar el anexo anterior.\n']
    source = {'id': 'S001', 'pages': [{'page': 1, 'lines': [{'line': i + 1, 'text': line} for i, line in enumerate(pages[0].splitlines())]}]}
    if kind == 'activity_session':
        rows = [{'activity_page': 1, 'activity_start_line': 3, 'activity_end_line': 3, 'session_page': 1, 'session_line': 1, 'abstained': False}]
        key, marker = 'relations', '\nDOCUMENT:\n'
    else:
        rows = [{'activity_page': 1, 'activity_start_line': 3, 'activity_end_line': 3, 'annex_number': 1,
                 'basis': 'explicit_number', 'mention_page': 1, 'mention_quote': 'anexo 1',
                 'antecedent_page': None, 'antecedent_quote': None, 'abstained': False}]
        key, marker = 'references', 'Sources:\n'
    response = {'id': 'S001', key: rows}
    request = 'Synthetic instruction.' + marker + json.dumps(source, ensure_ascii=False)
    kwargs = dict(kind=kind, document_id='S001', pages=pages, source_sha256=source_digest(pages),
                  request_text=request, request_sha256=digest(request), request_hash_timing='pre_run_protocol',
                  stream_text=json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'response': json.dumps(response)}}), model='synthetic-test-only')
    kwargs['stream_sha256'] = digest(kwargs['stream_text'])
    return kwargs, response


def set_response(kwargs, response):
    kwargs['stream_text'] = json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'response': json.dumps(response)}})
    kwargs['stream_sha256'] = digest(kwargs['stream_text'])


@pytest.mark.parametrize('kind', ['activity_session', 'activity_annex'])
def test_valid_recordings_remain_review_only_without_mutating_inputs(kind):
    kwargs, _ = example(kind)
    before = copy.deepcopy(kwargs)
    result = replay(**kwargs)
    assert kwargs == before
    assert result['proposals'][0]['state'] == 'needs_human_review'
    assert not result['production_applied'] and not result['semantic_validation']
    assert result['external_calls'] == 0
    assert result['source_kind'] == 'exact_extracted_page_snapshot_not_pdf_bytes'
    assert result['recorded_stream_sha256'] == digest(kwargs['stream_text'])


@pytest.mark.parametrize('field, value, code', [
    ('source_sha256', '0' * 64, 'source_hash_mismatch'),
    ('request_sha256', '0' * 64, 'request_hash_mismatch'),
    ('request_hash_timing', 'assumed_frozen', 'invalid_hash_timing'),
    ('kind', 'production', 'unsupported_kind'),
    ('pages', [], 'invalid_pages'),
])
def test_integrity_mismatches_fail_closed(field, value, code):
    kwargs, _ = example()
    kwargs[field] = value
    with pytest.raises(ReplayError, match=code):
        replay(**kwargs)


def test_matching_request_hash_does_not_excuse_different_source_content():
    kwargs, _ = example()
    kwargs['request_text'] = kwargs['request_text'].replace('Resolver', 'Inventar')
    kwargs['request_sha256'] = digest(kwargs['request_text'])
    with pytest.raises(ReplayError, match='request_source_mismatch'):
        replay(**kwargs)


@pytest.mark.parametrize('mutation, code', [
    (lambda r: r['relations'][0].update(activity_page=True), 'invalid_page'),
    (lambda r: r['relations'][0].update(activity_end_line=99), 'invalid_lines'),
    (lambda r: r['relations'][0].update(abstained=1), 'invalid_abstention'),
    (lambda r: r['relations'][0].update(abstained=True), 'abstention_with_target'),
    (lambda r: r['relations'].append(copy.deepcopy(r['relations'][0])), 'duplicate_proposal'),
    (lambda r: r['relations'][0].update(confidence=1), 'session_contract'),
    (lambda r: r.update(id='wrong'), 'response_contract'),
])
def test_malformed_session_response_rejects_atomically(mutation, code):
    kwargs, response = example()
    mutation(response)
    set_response(kwargs, response)
    with pytest.raises(ReplayError, match=code):
        replay(**kwargs)


def test_explicit_abstention_is_not_conflated_with_editorial_review():
    kwargs, response = example()
    response['relations'][0].update(abstained=True, session_page=None, session_line=None)
    set_response(kwargs, response)
    proposal, = replay(**kwargs)['proposals']
    assert proposal['state'] == 'insufficient_evidence' and proposal['target'] is None


@pytest.mark.parametrize('mutation, code', [
    (lambda r: r['references'][0].update(mention_quote=''), 'empty_evidence'),
    (lambda r: r['references'][0].update(mention_quote='invented'), 'quote_not_in_source'),
    (lambda r: r['references'][0].update(mention_quote='anexo anterior'), 'mention_outside_activity'),
    (lambda r: r['references'][0].update(annex_number=True), 'invalid_annex_number'),
    (lambda r: r['references'][0].update(basis='contextual_anaphora'), 'invalid_page'),
])
def test_invalid_annex_evidence_rejects_atomically(mutation, code):
    kwargs, response = example('activity_annex')
    mutation(response)
    set_response(kwargs, response)
    with pytest.raises(ReplayError, match=code):
        replay(**kwargs)


def test_contextual_annex_retains_both_literal_spans_without_certifying_meaning():
    kwargs, response = example('activity_annex')
    response['references'][0].update(activity_start_line=4, activity_end_line=4, mention_quote='anexo anterior',
                                     basis='contextual_anaphora', antecedent_page=1, antecedent_quote='anexo 1')
    kwargs['request_hash_timing'] = 'post_run_verification'
    set_response(kwargs, response)
    result = replay(**kwargs)
    proposal, = result['proposals']
    assert proposal['context'][0]['quote'] == 'anexo 1'
    assert not proposal['necessity_validated'] and not proposal['physical_sheet_resolved']
    assert result['request_hash_timing'] == 'post_run_verification'


@pytest.mark.parametrize('event, code', [
    ({'event': 'step_update', 'step_update': {'step_type': 'tool_call'}}, 'unexpected_tool_step'),
    ({'event': 'result', 'result': {'status': 'SUCCESS', 'response': '{}'}}, 'missing_or_multiple_results'),
])
def test_tools_or_multiple_results_reject(event, code):
    kwargs, _ = example()
    kwargs['stream_text'] += '\n' + json.dumps(event)
    kwargs['stream_sha256'] = digest(kwargs['stream_text'])
    with pytest.raises(ReplayError, match=code):
        replay(**kwargs)


def test_interrupted_stream_is_not_an_empty_success():
    kwargs, _ = example()
    kwargs['stream_text'] = json.dumps({'event': 'agent_response', 'partial': 'incomplete'})
    kwargs['stream_sha256'] = digest(kwargs['stream_text'])
    with pytest.raises(ReplayError, match='missing_or_multiple_results'):
        replay(**kwargs)


def test_duplicate_json_keys_reject_even_when_values_match():
    kwargs, _ = example()
    kwargs['stream_text'] = kwargs['stream_text'].replace('"event":', '"event":"result","event":', 1)
    kwargs['stream_sha256'] = digest(kwargs['stream_text'])
    with pytest.raises(ReplayError, match='duplicate_json_key'):
        replay(**kwargs)


def test_single_outer_fence_normalization_is_recorded():
    kwargs, response = example()
    kwargs['stream_text'] = json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'response': '```json\n' + json.dumps(response) + '\n```'}})
    kwargs['stream_sha256'] = digest(kwargs['stream_text'])
    assert replay(**kwargs)['response_normalization'] == 'single_outer_json_fence'


def test_mention_repeated_outside_predicted_activity_uses_source_range_not_gold():
    from scripts.replay_interpretation import _line_span, _quote_span
    kwargs, _ = example('activity_annex')
    activity = _line_span(kwargs['pages'], 1, 3, 3)
    assert _quote_span(kwargs['pages'], 1, 'anexo', within=activity)['quote'] == 'anexo'


@pytest.mark.parametrize('mutation, code', [
    (lambda r: r['references'][0].update(annex_number=99), 'mention_number_mismatch'),
    (lambda r: r['references'][0].update(mention_quote='Resolver'), 'mention_number_mismatch'),
    (lambda r: r['references'][0].update(mention_quote='anexo'), 'mention_number_mismatch'),
])
def test_numbered_annex_target_must_be_attested_by_its_literal_quote(mutation, code):
    kwargs, response = example('activity_annex')
    mutation(response)
    set_response(kwargs, response)
    with pytest.raises(ReplayError, match=code):
        replay(**kwargs)


def test_contextual_antecedent_must_attest_target_number_without_certifying_anaphora():
    kwargs, response = example('activity_annex')
    response['references'][0].update(activity_start_line=4, activity_end_line=4, mention_quote='anexo anterior',
                                     basis='contextual_anaphora', antecedent_page=1, antecedent_quote='anexo 1', annex_number=99)
    set_response(kwargs, response)
    with pytest.raises(ReplayError, match='antecedent_number_mismatch'):
        replay(**kwargs)


@pytest.mark.parametrize('text, quote', [
    ('anexo 12', 'anexo 1'), ('preanexo 1', 'anexo 1'), ('anexo 1a', 'anexo 1'),
    ('anexo 1.2', 'anexo 1'), ('anexo 1:2', 'anexo 1'), ('anexo 1/2', 'anexo 1'), ('anexo 1-2', 'anexo 1'),
])
def test_cropped_label_or_number_cannot_establish_annex_target(text, quote):
    from scripts.replay_interpretation import _has_explicit_number, _quote_span
    pages = [text]
    assert not _has_explicit_number(pages, _quote_span(pages, 1, quote), 1)


def test_mention_repeated_inside_predicted_range_stays_ambiguous():
    kwargs, response = example('activity_annex')
    response['references'][0].update(activity_end_line=4, mention_quote='anexo')
    set_response(kwargs, response)
    with pytest.raises(ReplayError, match='ambiguous_quote'):
        replay(**kwargs)


def test_tampered_stream_fails_expected_hash_before_replay():
    kwargs, response = example()
    original_hash = kwargs['stream_sha256']
    response['relations'][0]['session_line'] = 2
    set_response(kwargs, response)
    kwargs['stream_sha256'] = original_hash
    with pytest.raises(ReplayError, match='stream_hash_mismatch'):
        replay(**kwargs)


def test_boolean_source_line_is_not_equal_to_integer_line():
    kwargs, _ = example()
    kwargs['request_text'] = kwargs['request_text'].replace('"line": 1', '"line": true')
    kwargs['request_sha256'] = digest(kwargs['request_text'])
    with pytest.raises(ReplayError, match='request_source_mismatch'):
        replay(**kwargs)


def test_nonstring_basis_is_sanitized():
    kwargs, response = example('activity_annex')
    response['references'][0]['basis'] = []
    set_response(kwargs, response)
    with pytest.raises(ReplayError, match='invalid_basis'):
        replay(**kwargs)


def test_nonstring_step_type_is_sanitized():
    kwargs, _ = example()
    kwargs['stream_text'] += '\n' + json.dumps({'event': 'step_update', 'step_update': {'step_type': []}})
    kwargs['stream_sha256'] = digest(kwargs['stream_text'])
    with pytest.raises(ReplayError, match='unexpected_tool_step'):
        replay(**kwargs)


def test_cli_hashes_exact_crlf_saved_bytes_and_refuses_overwrite(tmp_path):
    import subprocess
    import sys
    from scripts import replay_interpretation as module
    kwargs, _ = example()
    kwargs['request_text'] += '\r\n'
    kwargs['stream_text'] += '\r\n'
    (tmp_path / 'source.json').write_text(json.dumps({'id': kwargs['document_id'], 'pages': kwargs['pages']}))
    (tmp_path / 'request.txt').write_bytes(kwargs['request_text'].encode())
    (tmp_path / 'stream.ndjson').write_bytes(kwargs['stream_text'].encode())
    output = tmp_path / 'output.json'
    cmd = [sys.executable, module.__file__, '--source', str(tmp_path / 'source.json'), '--kind', kwargs['kind'],
           '--source-sha256', kwargs['source_sha256'], '--request', str(tmp_path / 'request.txt'),
           '--request-sha256', digest(kwargs['request_text']), '--request-hash-timing', 'pre_run_protocol',
           '--stream', str(tmp_path / 'stream.ndjson'), '--stream-sha256', digest(kwargs['stream_text']),
           '--model', kwargs['model'], '--output', str(output)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    original = output.read_bytes()
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 2 and output.read_bytes() == original
