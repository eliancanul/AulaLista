"""Frozen synthetic requires_annex reference: numbers are not arbitrary prose."""
import copy
import hashlib
import json
from pathlib import Path

from curriculum.annex_mentions import iter_annex_mentions
from curriculum.claims import compile_dossier_to_atomic_claims
from scripts.evaluate_activity_annex import evaluate, predict, score, validate_annex_reference
from test_project_session_context import dossier_for

FIXTURE = Path(__file__).parent / 'fixtures/interpretation/activity_annex_v1.json'


def reference():
    return json.loads(FIXTURE.read_text())


def test_frozen_reference_and_relation_specific_evidence():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == 'c49e767843a695a3fa3e760f259ab17ffc2dc29ae01367dfa4e2dc3214bac48c'
    for document in reference()['documents']:
        validate_annex_reference(document)
    total = evaluate(reference())['total']
    assert total['expected'] == total['correct'] == total['supported'] == total['asserted'] == 12
    assert total['extras'] == total['omitted'] == total['incorrect'] == 0


def test_parser_stops_number_list_before_point_or_page_prose():
    text = 'Anexos 01 y 02, resolver el punto 3 de la página 14. Luego usar anexo 5.'
    mentions = list(iter_annex_mentions(text))
    assert [m.numbers for m in mentions] == [('1', '2'), ('5',)]
    assert all(text[m.start:m.end] == m.text for m in mentions)


def test_word_fragments_and_alphanumeric_labels_are_not_numeric_annex_references():
    assert list(iter_annex_mentions('preanexo 1 anexos 2abc anexo 3X')) == []


def test_wrong_extra_target_lowers_precision_without_changing_fixed_denominator():
    doc = reference()['documents'][0]
    predictions = predict(doc)
    extra = copy.deepcopy(predictions[0]); extra['annex_number'] = '99'
    counts = score(doc, predictions + [extra])
    assert counts['expected'] == counts['correct'] == 1
    assert counts['asserted'] == 2 and counts['extras'] == 1


def test_no_predictions_is_omission_not_abstention_or_success():
    doc = reference()['documents'][0]
    counts = score(doc, [])
    assert counts['omitted'] == 1 and counts['correct'] == counts['abstained'] == 0


def test_generic_short_activity_citation_cannot_prove_late_annex_mention():
    doc = reference()['documents'][5]
    predictions = predict(doc)
    span = predictions[0]['activity_spans'][0]
    predictions[0]['citation_spans'] = [span]
    counts = score(doc, predictions)
    assert counts['correct'] == 1 and counts['supported'] == 0


def test_compiler_does_not_invent_relation_evidence_from_generic_activity_excerpt():
    dossier = dossier_for(reference()['documents'][0]['pages'])
    activity = dossier.sessions[0].activities[0]
    assert activity.annex_evidence
    activity.annex_evidence = {}
    relation, = [c for c in compile_dossier_to_atomic_claims(dossier) if c.predicate == 'requiere_anexo']
    assert relation.state == 'candidate' and relation.evidence == []


def test_foreign_source_relation_evidence_cannot_be_reused():
    dossier = dossier_for(reference()['documents'][0]['pages'])
    for refs in dossier.sessions[0].activities[0].annex_evidence.values():
        refs[0].document_sha256 = 'f' * 64
    relation, = [c for c in compile_dossier_to_atomic_claims(dossier) if c.predicate == 'requiere_anexo']
    assert relation.evidence == []


def test_textual_reference_does_not_autoconfirm_or_claim_available_resource():
    dossier = dossier_for(reference()['documents'][0]['pages'])
    annex, = dossier.sessions[0].annex_references
    assert annex.status == 'missing' and annex.confirmed_page is None and annex.review == 'pending'
    relation, = [c for c in compile_dossier_to_atomic_claims(dossier) if c.predicate == 'requiere_anexo']
    assert relation.state == 'candidate'


def test_repeated_or_wrong_parent_guesses_do_not_earn_success():
    doc = reference()['documents'][0]
    predictions = predict(doc)
    duplicate = copy.deepcopy(predictions[0])
    assert score(doc, predictions + [duplicate])['correct'] == 0
    predictions[0]['session_anchor']['start'] += 1
    counts = score(doc, predictions)
    assert counts['correct'] == 0 and counts['incorrect'] == 1


def test_every_shared_activity_target_requires_valid_reference_parent_and_id():
    import pytest
    doc = reference()['documents'][3]
    for change in ('parent', 'id'):
        bad = copy.deepcopy(doc)
        if change == 'parent':bad['relations'][1]['session_id'] = 'nonexistent'
        else:bad['relations'][1]['id'] = bad['relations'][0]['id']
        with pytest.raises(ValueError):validate_annex_reference(bad)


def test_context_only_predictions_are_excluded_but_unknown_scope_remains():
    doc = reference()['documents'][0]
    predictions = predict(doc)
    unknown = copy.deepcopy(predictions[0]); unknown['activity_spans'] = []; unknown['scope_pages'] = []
    doc['pages'].append('Scored page.\n'); doc['relations'] = []; doc['scored_pages'] = [2]
    counts = score(doc, predictions + [unknown])
    assert counts['excluded_context_predictions'] == 1
    assert counts['uncertain_scope_predictions'] == counts['extras'] == counts['asserted'] == 1


def test_coordinated_page_or_exercise_count_does_not_become_second_annex():
    for unit in ('páginas', 'ejercicios', 'preguntas', 'minutos'):
        mentions = list(iter_annex_mentions(f'Consultar el anexo 1 y 2 {unit} después responder.'))
        assert [m.numbers for m in mentions] == [('1',)]
        assert mentions[0].text == 'anexo 1'
    assert [m.numbers for m in iter_annex_mentions('Consultar los anexos 1 y 2, luego responder.')] == [('1', '2')]


def test_semantic_challenge_is_frozen_and_not_confused_with_product_accuracy():
    path = FIXTURE.with_name('activity_annex_semantics_v1.json')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '0a565876b3595209cf7969e0ee37437f7efaeafbea9f10cd82851e3424c812d9'
    challenge = json.loads(path.read_text())
    expected = [x for case in challenge['cases'] for x in case['expected']]
    assert len(challenge['cases']) == 9 and len(expected) == 11
    assert sum(x['required'] is True for x in expected) == 4
    assert sum(x['required'] is False for x in expected) == 4
    assert sum(x['required'] is None for x in expected) == 3
    assert all(x['mentioned'] is True and x['physical_sheet_resolved'] is False for x in expected)
