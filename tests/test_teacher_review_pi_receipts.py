"""Synthetic receipt regressions; no provider, real runtime or credentials."""
import json

import pytest

from curriculum.pi_review_provider import PiStopped
from curriculum.teacher_review_provider import ReviewProviderError
from test_teacher_review import ready_job, start, save, advance, ask_first
from test_teacher_review_luna_cli import context
from test_teacher_review_pi import fake_pi


@pytest.mark.parametrize('mode', ['length', 'tool_content', 'big_final', 'diagnostics'])
def test_rejected_response_keeps_valid_reported_usage_without_claiming_completion(fake_pi, mode):
    _, factory, scenario, calls = fake_pi
    scenario(mode=mode)
    with pytest.raises(PiStopped) as failure:
        factory()(context())
    receipt = failure.value.provider_receipt
    assert receipt['reported_usage']['totalTokens'] == 120
    assert receipt['reported_usage']['reasoning'] is None
    assert receipt['accounting_status'] == 'unknown'
    assert receipt['usage_complete'] is False
    assert receipt['execution_status'] == 'stopped'
    assert receipt['real_cost_currency'] is None
    assert 'cost' not in receipt['reported_usage']
    assert (factory().attempt_root / 'STOP_REQUIRED.json').exists()
    before = len(calls())
    with pytest.raises(ReviewProviderError, match='pi_prior_attempt_blocked'):
        factory()(context())
    assert len(calls()) == before


@pytest.mark.parametrize('mode', ['wrong_provider', 'reroute', 'missing_usage', 'bool_usage',
                                 'sum_usage', 'reasoning_usage', 'zero_usage'])
def test_invalid_identity_or_counters_are_not_retained_as_reported_usage(fake_pi, mode):
    _, factory, scenario, _ = fake_pi
    scenario(mode=mode)
    with pytest.raises(PiStopped) as failure:
        factory()(context())
    assert failure.value.provider_receipt['reported_usage'] is None


@pytest.mark.django_db
def test_final_recording_failure_keeps_receipt_and_literal_answer_in_django(ready_job, fake_pi, monkeypatch):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, '  Respuesta durable antes del fallo.\n')
    _, factory, _, calls = fake_pi
    import curriculum.pi_review_provider as module
    original_commit = module.commit

    def fail_final(path, raw):
        if path.name == 'final.json':
            raise OSError('synthetic disk failure')
        return original_commit(path, raw)

    monkeypatch.setattr(module, 'commit', fail_final)
    review = advance(review, user, factory())
    assert review.state['error'] == 'pi_attempt_unknown'
    assert review.state['turns'][0]['answer'] == '  Respuesta durable antes del fallo.\n'
    receipt = review.state['events'][-1]['provider_receipt']
    stored = json.loads(next(factory().attempt_root.glob('*/receipt.json')).read_text())
    assert receipt == stored
    assert receipt['accounting_status'] == 'terminal_usage_reported'
    assert receipt['reported_usage']['totalTokens'] == 120
    assert (factory().attempt_root / 'STOP_REQUIRED.json').exists()
    assert not list(factory().attempt_root.glob('*/final.json'))
    before = len(calls())
    with pytest.raises(ReviewProviderError, match='pi_prior_attempt_blocked'):
        factory()(context())
    assert len(calls()) == before
    job.refresh_from_db()
    assert not job.is_approved
