"""Offline token scorer contract; fabricated receipts are labelled test-only."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from scripts.teacher_review_ab import compare


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def make_run(directory, tokens):
    directory.mkdir()
    pdf = b'invented scorer fixture; not an executed PDF/model run'
    (directory / 'same-document-synthetic.pdf').write_bytes(pdf)
    dossier = {'source_sha256': hashlib.sha256(pdf).hexdigest(), 'page_count': 1,
               'general_fields': {'purpose': {'value': 'Retain same fact', 'origin': 'teacher_entered',
                                            'status': 'supported', 'review': 'corrected', 'evidence': []}},
               'sessions': [], 'version': 1, 'verification_report': {'dossier_version': 1, 'items': [], 'is_valid': True}}
    write(directory / 'live-study/initial-dossier.json', dossier)
    write(directory / 'live-study/final-dossier.json', dossier)
    write(directory / 'live-study/context-1.json', {'turns': [], 'questions_asked': 0, 'questions_remaining': 6,
        'source_document': {'source_sha256': dossier['source_sha256'], 'pages': [{'page_number': 1, 'text': 'Invented text.'}]}})
    write(directory / 'live-study/final-review-state.json', {'status': 'limited', 'turns': []})
    write(directory / 'validation/real-validation-plan.json', {'allowed_invented_answers': {'purpose': 'Retain same fact'}})
    receipt = {'attempt_id': 'synthetic-attempt', 'execution_status': 'completed', 'usage_complete': True,
               'accounting_status': 'terminal_usage_reported', 'requested_provider': 'openai-codex',
               'requested_model': 'gpt-6-luna', 'requested_effort': 'high', 'pi_version': '0.84.4',
               'reported_usage': {'input': tokens - 10, 'output': 10, 'cacheRead': 0, 'cacheWrite': 0,
                                  'totalTokens': tokens, 'reasoning': 5}, 'test_double': True}
    write(directory / 'live-study/attempts/synthetic-attempt/receipt.json', receipt)
    write(directory / 'validation-summary.json', {'calls': [receipt], 'provider': 'openai-codex',
          'requested_model': 'gpt-6-luna', 'effort': 'high', 'pi_version': '0.84.4', 'observed_model': None,
          'usage_totals_pi_normalized': {'totalTokens': tokens}})


@pytest.mark.parametrize('total, expected', [(20322, True), (20323, False), (67743, False)])
def test_threshold_uses_whole_journey_total_not_bytes_or_reasoning_double_count(tmp_path, total, expected):
    old, new = tmp_path / 'old', tmp_path / 'new'
    make_run(old, 67743); make_run(new, total)
    result = compare(old, new)
    assert result['candidate_total_tokens'] == total
    assert result['target_total_tokens_at_most'] == 20322
    assert result['token_goal_on_same_semantic_result'] is expected
    assert result['remote_model_attested'] is False


@pytest.mark.parametrize('change', ['result', 'answers', 'source', 'warning'])
def test_smaller_run_does_not_pass_when_required_result_or_case_changes(tmp_path, change):
    old, new = tmp_path / 'old', tmp_path / 'new'
    make_run(old, 67743); make_run(new, 15000)
    if change == 'answers':
        write(new / 'validation/real-validation-plan.json', {'allowed_invented_answers': {'purpose': 'Different'}})
    else:
        path = new / 'live-study/final-dossier.json'
        dossier = json.loads(path.read_text())
        if change == 'result': dossier['general_fields']['purpose']['value'] = 'Dropped original fact'
        elif change == 'warning': dossier['verification_report']['items'] = [{'status': 'needs_teacher_review', 'message': 'Lost association'}]
        else:
            dossier['source_sha256'] = 'b' * 64
        write(path, dossier)
    if change == 'source':
        with pytest.raises(ValueError, match='source_identity_mismatch'): compare(old, new)
    else:
        assert compare(old, new)['token_goal_on_same_semantic_result'] is False


@pytest.mark.parametrize('change', ['unknown', 'extra_attempt', 'bool_usage', 'duplicate'])
def test_unknown_or_unaccounted_consumption_cannot_be_zero_or_silently_omitted(tmp_path, change):
    old, new = tmp_path / 'old', tmp_path / 'new'
    make_run(old, 67743); make_run(new, 15000)
    path = new / 'live-study/attempts/synthetic-attempt/receipt.json'
    receipt = json.loads(path.read_text())
    if change == 'extra_attempt':
        (new / 'live-study/attempts/unreported').mkdir()
    elif change == 'unknown':
        receipt['usage_complete'] = False; write(path, receipt)
    elif change == 'bool_usage':
        receipt['reported_usage']['input'] = True; write(path, receipt)
    else:
        path = new / 'validation-summary.json'; summary = json.loads(path.read_text())
        summary['calls'].append(copy.deepcopy(summary['calls'][0])); write(path, summary)
    with pytest.raises(ValueError): compare(old, new)


def test_matching_call_receipt_cannot_hide_different_model_behind_summary(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    make_run(old, 67743); make_run(new, 15000)
    path = new / 'live-study/attempts/synthetic-attempt/receipt.json'
    receipt = json.loads(path.read_text()); receipt['requested_model'] = 'different-model'; write(path, receipt)
    path = new / 'validation-summary.json'; summary = json.loads(path.read_text())
    summary['calls'][0]['requested_model'] = 'different-model'; write(path, summary)
    with pytest.raises(ValueError, match='summary_receipt_identity_mismatch'):
        compare(old, new)


def test_initial_resolve_history_is_authority_not_ignorable_presentation(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    make_run(old, 67743); make_run(new, 15000)
    path = new / 'live-study/initial-dossier.json'
    dossier = json.loads(path.read_text()); dossier['history'] = [
        {'version': 2, 'action': 'resolve', 'deltas': [{'scope': 'general', 'field': 'purpose'}]}]
    write(path, dossier)
    result = compare(old, new)
    assert result['same_initial_authority_and_source_text'] is False
    assert result['token_goal_on_same_semantic_result'] is False


def test_answer_outside_frozen_bank_cannot_make_cheaper_case_comparable(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    make_run(old, 67743); make_run(new, 15000)
    write(new / 'live-study/final-review-state.json', {'status': 'limited', 'turns': [
        {'answer': 'Unapproved helpful fact', 'answer_history': [{'answer': 'Unapproved helpful fact', 'skipped': False}]}]})
    with pytest.raises(ValueError, match='answer_outside_frozen_bank'):
        compare(old, new)


def test_summary_cannot_invent_observed_remote_model(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    make_run(old, 67743); make_run(new, 15000)
    for directory in (old, new):
        path = directory / 'validation-summary.json'; summary = json.loads(path.read_text())
        summary['observed_model'] = 'gpt-6-luna'; write(path, summary)
    result = compare(old, new)
    assert result['remote_model_reported_by_all_receipts'] is False
    assert result['remote_model_attested'] is False
