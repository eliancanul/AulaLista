"""All provider behavior here is a synthetic test double, never an LLM call."""
import copy

import pytest

from curriculum.interpretation_shadow import RetryableProposalError, ShadowLimits, propose_in_shadow

PAGES = ['SESIÓN 1\nInicio:\n-Observar hojas.\n']
SHA = 'a' * 64


def span(quote):
    start = PAGES[0].index(quote)
    return dict(page=1, start=start, end=start + len(quote), quote=quote)


class SyntheticProvider:
    kind = 'synthetic_test'

    def __init__(self, mutate=None):
        self.calls = 0
        self.mutate = mutate
        self.request = None

    def propose(self, request):
        self.calls += 1
        self.request = request
        entity = dict(id='e1', claim_type='entity', subject='session:s1', predicate='es_entidad', object_value='session', basis='explicit', rationale='Synthetic explicit header.', alternatives=[], evidence=[span('SESIÓN 1')], context=[span('SESIÓN 1')])
        relation = dict(id='r1', claim_type='relation', subject='activity:a1', predicate='pertenece_a_sesion', object_value='session:s1', basis='explicit', rationale='Synthetic layout association, awaiting review.', alternatives=[], evidence=[span('-Observar hojas.')], context=[span('SESIÓN 1'), span('-Observar hojas.')])
        payload = dict(source_sha256=request.source_sha256, extraction_sha256=request.extraction_sha256, claims=[entity, relation])
        if self.mutate:
            self.mutate(payload)
        return payload


def run(provider, **kwargs):
    return propose_in_shadow(pages=PAGES, source_sha256=SHA, provider=provider, **kwargs)


def test_off_by_default_never_calls_provider():
    provider = SyntheticProvider()
    outcome = run(provider)
    assert outcome.status == 'disabled' and provider.calls == 0
    assert outcome.provider_cost is outcome.provider_latency_seconds is None


def test_external_providers_are_blocked_even_when_shadow_is_enabled():
    provider = SyntheticProvider(); provider.kind = 'external'
    outcome = run(provider, enabled=True)
    assert outcome.status == 'blocked' and provider.calls == 0


def test_synthetic_proposal_sees_source_for_omissions_and_never_becomes_backed():
    provider = SyntheticProvider()
    outcome = run(provider, enabled=True)
    assert provider.request.pages == tuple(PAGES) and provider.request.existing_claims == ()
    assert 'absent from existing claims' in provider.request.instruction
    assert outcome.status == 'proposed_for_review'
    assert all(c.state == 'needs_human_review' and c.confidence is None for c in outcome.claims)
    assert outcome.provenance == 'synthetic_test'
    assert outcome.provider_cost is outcome.provider_latency_seconds is None


@pytest.mark.parametrize('mutation,error', [
    (lambda p: p.update(source_sha256='b' * 64), 'source_binding'),
    (lambda p: p['claims'][1]['evidence'][0].update(quote='Fabricated.'), 'evidence_mismatch'),
    (lambda p: p['claims'][1].update(predicate='aprendizaje_logrado'), 'unsupported_claim'),
    (lambda p: p['claims'][1].update(object_value='session:other'), 'dangling_session'),
    (lambda p: p['claims'][1].update(alternatives=['session:other']), 'dangling_alternative'),
    (lambda p: p['claims'][1].update(context=[]), 'missing_context'),
    (lambda p: p['claims'][1].update(confidence=0.99), 'claim_contract'),
    (lambda p: p['claims'][1].update(id='e1'), 'duplicate_id'),
    (lambda p: p['claims'][1]['evidence'][0].update(page=True), 'evidence_mismatch'),
])
def test_invalid_payload_is_rejected_atomically(mutation, error):
    outcome = run(SyntheticProvider(mutation), enabled=True)
    assert outcome.status == 'invalid' and outcome.claims == []
    assert error in outcome.errors


def test_abstention_preserves_null_and_reasons():
    outcome = run(SyntheticProvider(lambda p: p['claims'][1].update(basis='abstained', object_value=None, rationale='Unclear relationship.')), enabled=True)
    assert outcome.claims[1].object_value is None
    assert outcome.claims[1].state == 'insufficient_evidence'


def test_input_limit_abstains_without_truncating_or_calling():
    provider = SyntheticProvider()
    outcome = run(provider, enabled=True, limits=ShadowLimits(max_input_characters=2))
    assert outcome.status == 'abstained' and provider.calls == 0


def test_output_and_retry_limits_are_enforced_for_test_double():
    outcome = run(SyntheticProvider(), enabled=True, limits=ShadowLimits(max_output_characters=2))
    assert outcome.errors == ['output_limit']
    class FailingProvider(SyntheticProvider):
        def propose(self, request):
            self.calls += 1
            raise RetryableProposalError('Synthetic failure, not a network request')
    provider = FailingProvider()
    outcome = run(provider, enabled=True, limits=ShadowLimits(max_attempts=2))
    assert outcome.status == 'abstained' and provider.calls == outcome.attempts == 2
    assert run(provider, enabled=True, limits=ShadowLimits(max_attempts=3)).status == 'blocked'


def test_failure_logs_do_not_echo_source_or_provider_exception():
    class FailingProvider(SyntheticProvider):
        def propose(self, request):
            raise RuntimeError('PRIVATE SOURCE QUOTE')
    outcome = run(FailingProvider(), enabled=True)
    assert outcome.errors == ['provider_failure']
    assert 'PRIVATE' not in repr(outcome)


def test_existing_claims_are_not_mutated_by_provider():
    original = [{'metadata': {'flag': 'original'}}]
    class MutatingProvider(SyntheticProvider):
        def propose(self, request):
            request.existing_claims[0]['metadata']['flag'] = 'mutated'
            return super().propose(request)
    propose_in_shadow(pages=PAGES, source_sha256=SHA, existing_claims=original, enabled=True, provider=MutatingProvider())
    assert original == [{'metadata': {'flag': 'original'}}]
