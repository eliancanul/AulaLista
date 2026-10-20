"""Synthetic reference and evaluator adversarial checks; no teacher gold."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.evaluate_activity_session import evaluate, predict, ratios, score, validate_reference

FIXTURE = Path(__file__).parent / 'fixtures/interpretation/activity_session_v1.json'


def reference():
    return json.loads(FIXTURE.read_text())


def test_frozen_reference_has_twelve_opportunities_and_four_negative_documents():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == '9fb8fdc7595e24c065bfba0f8babd833d74f2eae208f2f228aaa4c8055a8b347'
    docs = reference()['documents']
    assert sum(len(d['relations']) for d in docs) == 12
    assert sum(not d['relations'] for d in docs) == 4
    for document in docs:
        validate_reference(document)


def test_current_dated_header_repair_recovers_fixed_synthetic_opportunities():
    total = evaluate(reference())['total']
    assert total['expected'] == total['correct'] == total['asserted'] == 12
    assert total['incorrect'] == total['omitted'] == total['extras'] == total['duplicates'] == 0


def test_emitting_nothing_is_zero_recall_not_success():
    total = evaluate(reference(), lambda document: [])['total']
    assert total['recall'] == 0 and total['precision'] is None
    assert total['omitted'] == 12 and total['abstained'] == 0


def test_wrong_parent_is_incorrect_not_omitted_or_correct():
    doc = reference()['documents'][0]
    predictions = predict(doc)
    predictions[0]['session_anchor']['start'] += 1
    counts = score(doc, predictions)
    assert counts['incorrect'] == 1 and counts['correct'] == counts['omitted'] == 0


def test_duplicate_right_and_wrong_guess_cannot_game_recall():
    doc = reference()['documents'][0]
    predictions = predict(doc)
    predictions += copy.deepcopy(predictions)
    predictions[1]['session_anchor']['start'] += 1
    counts = score(doc, predictions)
    assert counts['correct'] == 0 and counts['incorrect'] == counts['duplicates'] == 1
    assert counts['asserted'] == 2


def test_explicit_abstention_is_separate_from_omission_and_not_a_true_positive():
    doc = reference()['documents'][0]
    predictions = predict(doc)
    predictions[0]['abstained'] = True
    counts = ratios(score(doc, predictions))
    assert counts['abstained'] == 1 and counts['abstention_rate'] == 1
    assert counts['recall'] == 0 and counts['precision'] is None
    assert counts['omitted'] == 0


def test_unknown_and_unlocalized_predictions_are_counted_as_extras():
    doc = reference()['documents'][0]
    predictions = predict(doc)
    predictions[0]['activity_spans'] = []
    counts = score(doc, predictions)
    assert counts['extras'] == counts['omitted'] == counts['asserted'] == 1
    assert counts['correct'] == 0


def test_no_opportunities_is_not_one_hundred_percent():
    counts = ratios(score(reference()['documents'][5], []))
    assert counts['recall'] is None and counts['precision'] is None


def test_reference_rejects_wrong_quotes_duplicate_opportunities_and_unknown_parents():
    doc = reference()['documents'][0]
    for mutation in ('quote', 'duplicate', 'parent'):
        bad = copy.deepcopy(doc)
        if mutation == 'quote':
            bad['relations'][0]['activity']['quote'] = 'fabricated'
        elif mutation == 'duplicate':
            extra = copy.deepcopy(bad['relations'][0]); extra['id'] = 'new-id'
            bad['relations'].append(extra)
        else:
            bad['relations'][0]['session_id'] = 'unknown'
        with pytest.raises(ValueError):
            validate_reference(bad)


def test_one_token_can_align_fragment_but_never_claim_full_activity_recovery():
    doc = reference()['documents'][0]
    prediction = predict(doc)[0]
    span = prediction['activity_spans'][0]
    prediction['activity_spans'] = [{**span, 'end': span['start'] + len('Actividad')}]
    prediction['coverage_spans'] = prediction['activity_spans']
    counts = ratios(score(doc, [prediction]))
    assert counts['recall'] == 1  # explicitly fragment-to-session, not full recovery
    assert counts['complete_activity_recall'] == 0
    assert 0 < counts['mean_activity_text_coverage'] < 1


def test_overextended_description_is_complete_but_contaminated():
    doc = reference()['documents'][0]
    prediction = predict(doc)[0]
    prediction['coverage_spans'] = [{'page': 1, 'start': 0, 'end': len(doc['pages'][0])}]
    counts = ratios(score(doc, [prediction]))
    assert counts['recall'] == counts['complete_activity_recall'] == 1
    assert counts['clean_complete_activity_recall'] == 0
    assert 0 < counts['activity_text_precision'] < 1


def test_context_only_pages_are_excluded_but_uncertain_scope_is_visible():
    doc = reference()['documents'][0]
    original = predict(doc)[0]
    doc['pages'].append('Context scoring page.\n')
    doc['scored_pages'] = [2]
    doc['relations'] = []
    uncertain = copy.deepcopy(original)
    uncertain['scope_pages'] = []
    uncertain['activity_spans'] = []
    counts = score(doc, [original, uncertain])
    assert counts['excluded_context_predictions'] == 1
    assert counts['uncertain_scope_predictions'] == counts['extras'] == counts['asserted'] == 1


def test_reference_opportunity_cannot_silently_disappear_outside_scope():
    doc = reference()['documents'][0]
    doc['pages'].append('Another page.\n')
    doc['scored_pages'] = [2]
    with pytest.raises(ValueError):
        validate_reference(doc)


def test_review_required_is_not_an_abstention_for_shadow_comparison():
    from curriculum.claims import AtomicClaim
    from scripts.evaluate_activity_session import claim_is_abstention
    claim = AtomicClaim('r', 'relation', 'activity:a', 'pertenece_a_sesion', 'session:s', state='needs_human_review', metadata={'basis': 'explicit'})
    assert claim_is_abstention(claim) is False
    claim.metadata['basis'] = 'abstained'; claim.object_value = None
    assert claim_is_abstention(claim) is True


def test_text_only_correctness_is_separate_from_correct_parent_assignment():
    doc = reference()['documents'][0]
    prediction = predict(doc)[0]; prediction['session_anchor']['start'] += 99
    counts = ratios(score(doc, [prediction]))
    assert counts['activity_text_precision'] == 1
    assert counts['correctly_assigned_text_precision'] == counts['clean_complete_activity_recall'] == counts['recall'] == 0


def test_overextended_identification_remains_a_strict_contract_mismatch():
    doc = reference()['documents'][0]
    prediction = predict(doc)[0]; prediction['activity_spans'][0]['start'] -= 1
    counts = score(doc, [prediction])
    assert counts['extras'] == counts['omitted'] == 1
