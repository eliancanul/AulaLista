"""Frozen synthetic requires_annex reference: numbers are not arbitrary prose."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from curriculum.annex_mentions import iter_annex_mentions
from curriculum.claims import compile_dossier_to_atomic_claims
from scripts.evaluate_activity_annex import evaluate, predict, ratios, score, validate_annex_reference
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
    assert not [c for c in compile_dossier_to_atomic_claims(dossier) if c.predicate == 'requiere_anexo']


def test_foreign_source_relation_evidence_cannot_be_reused():
    dossier = dossier_for(reference()['documents'][0]['pages'])
    for refs in dossier.sessions[0].activities[0].annex_evidence.values():
        refs[0].document_sha256 = 'f' * 64
    assert not [c for c in compile_dossier_to_atomic_claims(dossier) if c.predicate == 'requiere_anexo']


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


def test_reference_rejects_literal_but_unrelated_quote_or_wrong_number():
    import pytest
    doc = reference()['documents'][0]
    for change in ('quote', 'number'):
        bad = copy.deepcopy(doc)
        relation = bad['relations'][0]
        if change == 'number':
            relation['annex_number'] = '99'
        else:
            page = bad['pages'][relation['activity']['page'] - 1]
            start = relation['activity']['start']
            relation['mention'] = {'page': relation['activity']['page'], 'start': start, 'end': start + 1, 'quote': page[start:start + 1]}
        with pytest.raises(ValueError, match='annotated number'):
            validate_annex_reference(bad)


def synthetic_annex_document(body, quote, number='1'):
    """Independently authored offsets; no product matcher builds these cases."""
    header = 'SESIÓN 1: Explorar'
    activity = f'Actividad 1: {body}'
    page = f'{header}\nInicio:\n{activity}\n'

    def span(text):
        start = page.index(text)
        return {'page': 1, 'start': start, 'end': start + len(text), 'quote': text}

    return {'id': 'synthetic', 'pages': [page],
            'sessions': [{'id': 's1', 'anchor': span(header)}],
            'relations': [{'id': 'r1', 'session_id': 's1', 'activity': span(activity),
                           'annex_number': number, 'mention': span(quote)}]}


def synthetic_prediction(document):
    relation, = document['relations']
    anchor = document['sessions'][0]['anchor']
    return {'activity_spans': [copy.deepcopy(relation['activity'])],
            'annex_number': relation['annex_number'],
            'session_anchor': {'page': anchor['page'], 'start': anchor['start']},
            'citation_spans': [copy.deepcopy(relation['mention'])],
            'abstained': False, 'scope_pages': [relation['activity']['page']]}


@pytest.mark.parametrize('body,quote', [
    ('Leer preanexo 1.', 'anexo 1'),
    ('Leer éanexo 1.', 'anexo 1'),
    ('Leer _anexo 1.', 'anexo 1'),
    ('Leer anexo 12.', 'anexo 1'),
    ('Leer anexo 1A.', 'anexo 1'),
    ('Leer anexo 1ñ.', 'anexo 1'),
    ('Leer anexo 1_2.', 'anexo 1'),
    ('Leer anexo 1y2.', 'anexo 1'),
    ('Leer anexo 1.2.', 'anexo 1'),
    ('Leer anexo 1:2.', 'anexo 1'),
    ('Leer anexo 1/2.', 'anexo 1'),
    ('Leer anexo 1-2.', 'anexo 1'),
])
def test_reference_rejects_token_truncated_literal_mentions(body, quote):
    with pytest.raises(ValueError, match='complete tokens'):
        validate_annex_reference(synthetic_annex_document(body, quote))


@pytest.mark.parametrize('quote', [
    'Resolver', 'preanexo 1', 'anexo 1A', 'anexo 1y2',
    'anexo 1 y resolver el punto 2', 'anexo 1/2', 'anexo -1',
    'anexo IV', 'el mismo', 'anexo １',
])
def test_reference_rejects_non_explicit_or_non_numeric_mention_grammar(quote):
    with pytest.raises(ValueError, match='annotated number'):
        validate_annex_reference(synthetic_annex_document(f'Consultar {quote}.', quote))


@pytest.mark.parametrize('number', ['01', '-1', '+1', '1.0', '١', '１', 1, True, None, [], {}])
def test_reference_requires_canonical_ascii_string_number(number):
    with pytest.raises(ValueError, match='canonical explicit annex number'):
        validate_annex_reference(synthetic_annex_document('Leer anexo 1.', 'anexo 1', number))


@pytest.mark.parametrize('number', ['0', '1', '2', '3', '4', '5'])
def test_independent_grammar_accepts_explicit_padded_multiline_lists(number):
    quote = 'ANEXOS 000, 0001,\n02 y 003 e 4 & 05'
    document = synthetic_annex_document(f'Consultar ({quote}).', quote, number)
    validate_annex_reference(document)
    counts = score(document, [synthetic_prediction(document)])
    assert counts['expected'] == counts['correct'] == counts['supported'] == 1


def test_large_literal_annex_number_does_not_depend_on_python_integer_limits():
    number = '9' * 5000
    quote = f'anexo 00{number}'
    validate_annex_reference(synthetic_annex_document(f'Leer {quote}.', quote, number))


@pytest.mark.parametrize('field,value', [
    ('page', 0), ('page', 2), ('page', True), ('page', 1.0),
    ('start', -1), ('start', 0.0), ('start', False),
    ('end', 10_000), ('quote', 'Resolver'),
])
def test_invalid_citation_coordinates_cannot_earn_support(field, value):
    document = reference()['documents'][0]
    prediction = synthetic_prediction(document)
    prediction['citation_spans'][0][field] = value
    counts = score(document, [prediction])
    assert counts['correct'] == 1
    assert counts['supported'] == 0


@pytest.mark.parametrize('field,value', [('page', True), ('start', 27.0), ('quote', 'Resolver')])
def test_invalid_activity_coordinates_cannot_earn_alignment(field, value):
    document = reference()['documents'][0]
    prediction = synthetic_prediction(document)
    prediction['activity_spans'][0][field] = value
    counts = score(document, [prediction])
    assert counts['correct'] == counts['supported'] == 0
    assert counts['omitted'] == counts['extras'] == 1


@pytest.mark.parametrize('field,value', [('page', True), ('start', False), ('start', 0.0)])
def test_session_anchor_requires_integer_coordinates(field, value):
    document = reference()['documents'][0]
    prediction = synthetic_prediction(document)
    prediction['session_anchor'][field] = value
    counts = score(document, [prediction])
    assert counts['correct'] == counts['supported'] == 0
    assert counts['incorrect'] == 1


def test_abstention_duplicates_and_empty_denominators_remain_distinct():
    document = reference()['documents'][0]
    prediction = synthetic_prediction(document)
    prediction['abstained'] = True
    counts = ratios(score(document, [prediction]))
    assert counts['expected'] == counts['abstained'] == 1
    assert counts['asserted'] == counts['correct'] == counts['supported'] == 0
    assert counts['precision'] is None and counts['recall'] == counts['supported_recall'] == 0
    counts = score(document, [prediction, copy.deepcopy(prediction)])
    assert counts['incorrect'] == counts['duplicates'] == 1
    assert counts['abstained'] == counts['correct'] == counts['supported'] == 0
    document['relations'] = []
    counts = ratios(score(document, []))
    assert counts['recall'] is counts['precision'] is counts['supported_recall'] is None


def test_validator_and_scorer_work_when_all_product_imports_are_forbidden():
    # A fresh interpreter catches even future module-level product imports.
    script = '''
import builtins, json, sys
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name == "curriculum" or name.startswith("curriculum."):
        raise AssertionError("Gold/scoring must not import product code")
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
from scripts.evaluate_activity_annex import validate_annex_reference, score
document, prediction = json.load(sys.stdin)
validate_annex_reference(document)
counts = score(document, [prediction])
assert counts["correct"] == counts["supported"] == 1
'''
    document = reference()['documents'][0]
    subprocess.run([sys.executable, '-c', script], cwd=FIXTURE.parents[3],
                   input=json.dumps([document, synthetic_prediction(document)]),
                   text=True, check=True, capture_output=True)


@pytest.mark.parametrize('body', [
    'No usar el anexo 1.', 'Si hay tiempo, consultar el anexo 1.',
])
def test_textual_prediction_is_separate_from_operational_annex_requirement(body):
    document = synthetic_annex_document(body, 'anexo 1')
    dossier = dossier_for(document['pages'])
    assert dossier.sessions[0].activities[0].annex_ids
    assert not [claim for claim in compile_dossier_to_atomic_claims(dossier)
                if claim.predicate == 'requiere_anexo']
    counts = score(document, predict(document))
    assert counts['correct'] == counts['supported'] == 1


def test_supported_covers_literal_context_but_does_not_score_semantic_necessity():
    document = synthetic_annex_document('No usar el anexo 1.', 'anexo 1')
    prediction = synthetic_prediction(document)
    prediction['citation_spans'] = [copy.deepcopy(document['relations'][0]['activity'])]
    assert score(document, [prediction])['supported'] == 1
    report = evaluate(reference())
    assert report['evaluator_version'] == 'activity-annex.v3'
    assert 'not semantic necessity' in report['evidence_metric']
    assert 'textual associations' in report['prediction_contract']


def test_declared_context_scope_cannot_hide_a_scored_activity_location():
    document = reference()['documents'][0]
    document['pages'].append('Context only.\n')
    document['scored_pages'] = [1]
    prediction = synthetic_prediction(document)
    prediction['scope_pages'] = [2]
    counts = score(document, [prediction])
    assert counts['excluded_context_predictions'] == 0
    assert counts['expected'] == counts['asserted'] == counts['correct'] == 1


@pytest.mark.parametrize('declared_page', [0, 99, True, 1.0, '1'])
def test_invalid_declared_scope_stays_visible_as_uncertain(declared_page):
    document = reference()['documents'][0]
    prediction = synthetic_prediction(document)
    prediction['activity_spans'] = []
    prediction['scope_pages'] = [declared_page]
    counts = score(document, [prediction])
    assert counts['excluded_context_predictions'] == 0
    assert counts['uncertain_scope_predictions'] == counts['extras'] == counts['asserted'] == 1
    assert counts['omitted'] == 1


def test_invalid_reference_is_rejected_before_any_product_prediction(monkeypatch):
    import scripts.evaluate_activity_annex as evaluator
    invalid = reference()
    invalid['documents'][-1] = synthetic_annex_document('Resolver anexo 1.', 'Resolver', '99')

    def forbidden_prediction(document):
        raise AssertionError('Do not run a product before validating the complete reference')

    monkeypatch.setattr(evaluator, 'predict', forbidden_prediction)
    with pytest.raises(ValueError, match='annotated number'):
        evaluator.evaluate(invalid)


def test_every_annex_target_validates_its_own_exact_mention():
    document = reference()['documents'][3]
    document['relations'][1]['mention']['start'] += 1
    with pytest.raises(ValueError, match='exact original text'):
        validate_annex_reference(document)


def test_mention_must_be_inside_its_activity_even_when_it_is_exact():
    document = reference()['documents'][1]
    document['relations'][0]['mention'] = copy.deepcopy(document['relations'][1]['mention'])
    document['relations'][0]['annex_number'] = '2'
    with pytest.raises(ValueError, match='inside its activity'):
        validate_annex_reference(document)


def test_duplicate_activity_annex_target_is_not_a_second_opportunity():
    document = reference()['documents'][0]
    duplicate = copy.deepcopy(document['relations'][0])
    duplicate['id'] = 'distinct-id-same-opportunity'
    document['relations'].append(duplicate)
    with pytest.raises(ValueError, match='Duplicate activity-annex opportunity'):
        validate_annex_reference(document)
