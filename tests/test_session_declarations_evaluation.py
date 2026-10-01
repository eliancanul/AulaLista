"""Adversarial scorer tests. Deliberately do not import the matcher or scanner."""
from copy import deepcopy
import builtins
import hashlib
import json
from pathlib import Path
import sys
import types

import pytest

from scripts import evaluate_session_declarations as evaluator

FIXTURE = Path(__file__).parent / 'fixtures/interpretation/session_declarations_v1.json'
FROZEN_SHA256 = '3c7a9aedf5be30b8755d12e6567d154b5d54859d1ff0a868727b8576060201f5'


@pytest.fixture
def reference():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FROZEN_SHA256
    return json.loads(FIXTURE.read_text())


def document(reference, name='simple_pair'):
    return deepcopy(next(d for d in reference['documents'] if d['id'] == name))


def source(span, sha, role):
    return dict(document_sha256=sha, page_number=span['page'], excerpt=span['quote'],
                region=dict(kind='text_offsets', start=span['start'], end=span['end']), role=role)


def prediction(doc, *, include_challenges=True):
    """An authored oracle for evaluator verification, never a product parser."""
    sha = evaluator.hash_canonical_pages(doc['pages'])
    output = dict(version='session-declarations.v1', source_doc_sha256=sha,
                  extraction_sha256=sha, records=[], limits=['Synthetic test oracle'])
    units = {u['id']: u for u in doc['units']}
    for declaration in doc['declarations']:
        gold_unit = units.get(declaration['unit_id'])
        unit = (dict(id=gold_unit['kind'] + ':' + gold_unit['id'], kind=gold_unit['kind'],
                     anchor=source(gold_unit['anchor'], sha, 'unit_anchor')) if gold_unit else None)
        evidence = [source(declaration[k], sha, k) for k in ('label', 'value')]
        label = declaration['label']
        if unit and unit['anchor']['page_number'] < label['page'] and declaration['expected_decision'] == 'candidate':
            first_line = doc['pages'][label['page'] - 1].splitlines()[0]
            continuation = dict(page=label['page'], start=0, end=len(first_line), quote=first_line)
            evidence.append(source(continuation, sha, 'unit_continuation'))
        record = dict(id=f"record:{label['page']}:{label['start']}", kind=declaration['kind'],
                      decision=declaration['expected_decision'], reason=declaration['reason'], unit=unit,
                      evidence=evidence, claim=None)
        if record['decision'] == 'candidate':
            value = evidence[1]
            record['claim'] = dict(claim_id=record['id'], claim_type='field', subject=unit['id'],
                                   predicate=evaluator.PREDICATES[record['kind']], object_value=value['excerpt'],
                                   source_doc_sha256=sha, page_number=value['page_number'], region=deepcopy(value['region']),
                                   excerpt=value['excerpt'], state='needs_human_review', confidence=None,
                                   evidence=deepcopy(evidence) + [deepcopy(unit['anchor'])])
        output['records'].append(record)
    if include_challenges:
        for challenge in doc['challenges']:
            span = challenge['anchor']
            output['records'].append(dict(id=f"challenge:{span['page']}:{span['start']}", kind=None,
                                          decision='abstained', reason=challenge['reason'], unit=None,
                                          evidence=[source(span, sha, 'label')], claim=None))
    return output


def abstain(record):
    record['decision'], record['claim'], record['reason'], record['unit'] = 'abstained', None, 'unresolved_scope', None


def synchronize_claim(record):
    """Keep a wrong-but-self-consistent prediction separate from fabrication."""
    if record['claim'] is None:
        return
    value = next(r for r in record['evidence'] if r['role'] == 'value')
    record['claim'].update(subject=record['unit']['id'], predicate=evaluator.PREDICATES[record['kind']],
                           object_value=value['excerpt'], excerpt=value['excerpt'], page_number=value['page_number'],
                           region=deepcopy(value['region']), evidence=deepcopy(record['evidence']) + [deepcopy(record['unit']['anchor'])])


def metrics(doc, output):
    return evaluator.score(doc, output)['metrics']


def test_perfect_oracle_keeps_all_frozen_denominators_separate(reference):
    report = evaluator.evaluate(reference, prediction)
    totals = report['total']
    for name, expected in [('literal_declarations', 45), ('unit_assignment', 45), ('joint_detection_unit', 45),
                           ('known_unit_assignment', 41), ('unresolved_unit_abstentions', 4),
                           ('session_candidates', 36), ('scope_abstentions', 9), ('strict_session_claims', 36)]:
        assert totals[name]['expected'] == totals[name]['correct'] == expected
        assert totals[name]['incorrect'] == totals[name]['omitted'] == 0
        assert totals[name]['recall'] == 1
    assert totals['literal_declarations']['precision'] == 1
    assert totals['strict_session_claims']['precision'] == 1
    assert totals['strict_session_claims']['emitted_claim_records'] == 36
    assert totals['challenges']['expected'] == totals['challenges']['explicit_abstentions'] == 22
    assert totals['negative_documents'] == dict(expected=15, false_candidate_emissions=0, explicit_abstentions=13,
                                                clean_silence=2, invalid_or_extra_emissions=0, false_candidate_records=0)
    assert totals['output']['invalid_records'] == totals['output']['invalid_outputs'] == 0
    assert report['reference_kind'] == reference['reference_kind']
    assert report['scope'] == reference['scope']


def test_reference_provenance_and_known_unit_denominators_are_not_relabelled(reference):
    reference['reference_kind'] = 'Independently authored development reference'
    reference['scope'] = 'Authorized supplied window'
    report = evaluator.evaluate(reference, prediction)
    assert report['reference_kind'] == reference['reference_kind']
    assert report['scope'] == reference['scope']
    assert report['total']['known_unit_assignment']['expected'] == 41
    assert report['total']['unresolved_unit_abstentions']['expected'] == 4
    assert all('synthetic' not in line for line in report['limits'])


def test_silence_is_never_explicit_scope_or_challenge_abstention(reference):
    def silent(doc):
        result = prediction(doc)
        result['records'] = []
        return result
    total = evaluator.evaluate(reference, silent)['total']
    assert total['literal_declarations']['omitted'] == 45
    assert total['scope_abstentions']['omitted'] == 9
    assert total['scope_abstentions']['correct'] == 0
    assert total['session_candidates']['omitted'] == 36
    assert total['session_candidates']['explicit_abstentions'] == 0
    assert total['challenges']['silence_no_claim'] == 22
    assert total['challenges']['explicit_abstentions'] == 0
    assert total['negative_documents']['clean_silence'] == 15
    assert total['literal_declarations']['precision'] is None
    assert total['literal_declarations']['recall'] == 0


def test_project_detection_is_positive_but_project_omission_is_not_abstention(reference):
    doc = document(reference, 'project_no_inheritance')
    output = prediction(doc)
    assert metrics(doc, output)['literal_declarations']['correct'] == 2
    assert metrics(doc, output)['scope_abstentions']['correct'] == 2
    assert metrics(doc, output)['session_candidates']['expected'] == 0
    output['records'].pop()
    result = metrics(doc, output)
    assert result['scope_abstentions']['correct'] == 1
    assert result['scope_abstentions']['omitted'] == 1
    assert result['literal_declarations']['omitted'] == 1


def test_needs_human_review_is_not_abstention_or_accuracy_by_itself(reference):
    doc = document(reference)
    output = prediction(doc)
    result = metrics(doc, output)
    assert result['session_candidates']['correct'] == 2
    assert result['session_candidates']['explicit_abstentions'] == 0
    abstain(output['records'][0])
    result = metrics(doc, output)
    assert result['session_candidates']['correct'] == 1
    assert result['session_candidates']['explicit_abstentions'] == 1
    assert result['literal_declarations']['correct'] == 2


def test_wrong_parent_preserves_literal_detection_and_loses_joint_credit(reference):
    doc = document(reference, 'two_sessions')
    output = prediction(doc)
    output['records'][0]['unit'] = deepcopy(output['records'][2]['unit'])
    synchronize_claim(output['records'][0])
    result = metrics(doc, output)
    assert result['output']['invalid_records'] == 0
    assert result['literal_declarations']['correct'] == 4
    assert result['unit_assignment']['correct'] == result['joint_detection_unit']['correct'] == 3
    assert result['session_candidates']['correct'] == 4
    assert result['strict_session_claims']['correct'] == 3
    assert result['strict_session_claims']['incorrect'] == 1
    assert result['strict_session_claims']['precision'] == result['strict_session_claims']['recall'] == 0.75


def test_gold_unit_ids_are_not_required_for_physical_assignment(reference):
    doc = document(reference)
    output = prediction(doc)
    for record in output['records']:
        record['unit']['id'] = 'session:a-stable-physical-id'
        synchronize_claim(record)
    assert metrics(doc, output)['unit_assignment']['correct'] == 2


@pytest.mark.parametrize('mutation', ['value_excerpt', 'value_contamination', 'wrong_type', 'label_excerpt'])
def test_partial_contaminated_or_wrong_type_never_earns_literal_credit(reference, mutation):
    doc = document(reference)
    output = prediction(doc)
    record = output['records'][0]
    if mutation == 'wrong_type':
        record['kind'] = 'pda'
    else:
        target = record['evidence'][0 if mutation == 'label_excerpt' else 1]
        if mutation == 'value_contamination':
            target['region']['end'] += 4
        else:
            target['region']['end'] -= 1
        target['excerpt'] = doc['pages'][0][target['region']['start']:target['region']['end']]
    synchronize_claim(record)
    result = metrics(doc, output)
    assert result['literal_declarations']['correct'] == 1
    assert result['literal_declarations']['incorrect'] == 1
    assert result['unit_assignment']['correct'] == 2
    assert result['joint_detection_unit']['correct'] == 1
    assert result['literal_declarations']['precision'] == 0.5


@pytest.mark.parametrize('mutation', ['source_hash', 'extraction_hash', 'evidence_hash', 'fabricated_quote', 'negative_span',
                                     'boolean_page', 'geometric_region', 'backed_state', 'confidence', 'claim_value',
                                     'claim_subject', 'claim_predicate', 'claim_hash', 'claim_primary', 'claim_evidence',
                                     'missing_value', 'duplicate_value', 'null_claim', 'abstained_claim', 'unknown_kind', 'unknown_decision'])
def test_invalid_outputs_never_receive_credit(reference, mutation):
    doc = document(reference)
    output = prediction(doc)
    record = output['records'][0]
    if mutation in ('source_hash', 'extraction_hash'):
        output['source_doc_sha256' if mutation == 'source_hash' else 'extraction_sha256'] = 'f' * 64
    elif mutation == 'evidence_hash':
        record['evidence'][1]['document_sha256'] = 'f' * 64
    elif mutation == 'fabricated_quote':
        record['evidence'][1]['excerpt'] = 'invented'
    elif mutation == 'negative_span':
        record['evidence'][1]['region']['start'] = -1
    elif mutation == 'boolean_page':
        record['evidence'][1]['page_number'] = True
    elif mutation == 'geometric_region':
        record['evidence'][1]['region']['kind'] = 'bbox'
    elif mutation == 'backed_state':
        record['claim']['state'] = 'backed'
    elif mutation == 'confidence':
        record['claim']['confidence'] = 1
    elif mutation == 'claim_value':
        record['claim']['object_value'] = 'invented'
    elif mutation == 'claim_subject':
        record['claim']['subject'] = 'session:not-the-unit'
    elif mutation == 'claim_predicate':
        record['claim']['predicate'] = 'objetivo'
    elif mutation == 'claim_hash':
        record['claim']['source_doc_sha256'] = 'f' * 64
    elif mutation == 'claim_primary':
        record['claim']['region']['end'] -= 1
    elif mutation == 'claim_evidence':
        record['claim']['evidence'].pop()
    elif mutation == 'missing_value':
        record['evidence'].pop(1)
    elif mutation == 'duplicate_value':
        record['evidence'].append(deepcopy(record['evidence'][1]))
    elif mutation == 'null_claim':
        record['claim'] = None
    elif mutation == 'abstained_claim':
        record['decision'] = 'abstained'
    elif mutation == 'unknown_kind':
        record['kind'] = 'tema'
    elif mutation == 'unknown_decision':
        record['decision'] = 'verified'
    scored = evaluator.score(doc, output)
    assert scored['output_errors'] or scored['record_errors']
    assert scored['metrics']['literal_declarations']['correct'] <= 1
    assert scored['metrics']['joint_detection_unit']['correct'] <= 1


@pytest.mark.parametrize('same_id', [True, False])
def test_duplicate_guess_poisons_opportunity_even_with_one_correct_record(reference, same_id):
    doc = document(reference)
    output = prediction(doc)
    duplicate = deepcopy(output['records'][0])
    if not same_id:
        duplicate['id'] += ':again'
        duplicate['claim']['claim_id'] += ':again'
    # A malformed duplicate cannot hide behind the valid original guess.
    duplicate['evidence'][1]['excerpt'] = 'fabricated'
    output['records'].append(duplicate)
    result = metrics(doc, output)
    assert result['literal_declarations']['duplicates'] == 1
    assert result['literal_declarations']['correct'] == 1
    assert result['literal_declarations']['incorrect'] == 1
    assert result['literal_declarations']['emitted_typed_values'] == 3
    assert result['literal_declarations']['precision'] == pytest.approx(1 / 3)
    assert result['strict_session_claims']['correct'] == 1
    assert result['strict_session_claims']['emitted_claim_records'] == 3
    assert result['strict_session_claims']['precision'] == pytest.approx(1 / 3)


def test_repeated_equal_texts_are_separate_physical_opportunities(reference):
    doc = document(reference, 'repeated_same_session')
    output = prediction(doc)
    assert len({r['id'] for r in output['records']}) == 4
    assert metrics(doc, output)['literal_declarations']['correct'] == 4
    output['records'] = output['records'][:2]
    assert metrics(doc, output)['literal_declarations']['omitted'] == 2


def test_one_unit_id_cannot_collapse_two_identical_physical_headers(reference):
    doc = document(reference, 'identical_session_headers')
    output = prediction(doc)
    output['records'][1]['unit']['id'] = output['records'][0]['unit']['id']
    synchronize_claim(output['records'][1])
    scored = evaluator.score(doc, output)
    assert scored['metrics']['output']['invalid_unit_assignments'] == 2
    assert scored['metrics']['unit_assignment']['correct'] == 0
    assert scored['metrics']['literal_declarations']['correct'] == 2


def test_unresolved_null_requires_explicit_record_and_withheld_claim(reference):
    doc = document(reference, 'no_unit')
    output = prediction(doc)
    assert metrics(doc, output)['unit_assignment']['correct'] == 2
    output['records'][0]['decision'] = 'candidate'
    assert metrics(doc, output)['scope_abstentions']['correct'] == 1
    assert metrics(doc, output)['output']['invalid_records'] == 1


def test_challenge_silence_explicit_invalid_duplicate_and_candidate_are_separate(reference):
    doc = document(reference, 'negated_declaration')
    output = prediction(doc)
    assert metrics(doc, output)['challenges']['explicit_abstentions'] == 2
    output['records'].pop()
    assert metrics(doc, output)['challenges']['silence_no_claim'] == 1
    duplicate = deepcopy(output['records'][0])
    duplicate['id'] += ':again'
    output['records'].append(duplicate)
    assert metrics(doc, output)['challenges']['duplicates'] == 1
    output = prediction(doc)
    output['records'][0]['evidence'][0]['excerpt'] = 'invented'
    assert metrics(doc, output)['challenges']['invalid_records'] == 1
    # Build a self-consistent false candidate on the actual negated block.
    output = prediction(doc)
    record = output['records'][0]
    record.update(kind='pda', decision='candidate', reason='explicit_session')
    label = doc['challenges'][0]['anchor']
    page = doc['pages'][label['page'] - 1]
    start = label['end'] + 1
    end = page.index('\n', start)
    record['evidence'].append(source(dict(page=label['page'], start=start, end=end, quote=page[start:end]), output['source_doc_sha256'], 'value'))
    unit = doc['units'][0]
    record['unit'] = dict(id='session:' + unit['id'], kind='session', anchor=source(unit['anchor'], output['source_doc_sha256'], 'unit_anchor'))
    record['claim'] = dict(claim_id=record['id'], claim_type='field', state='needs_human_review', confidence=None, source_doc_sha256=output['source_doc_sha256'])
    synchronize_claim(record)
    result = metrics(doc, output)
    assert result['challenges']['wrong_candidates'] == 1
    assert result['challenges']['explicit_abstentions'] == 1
    assert result['negative_documents']['false_candidate_emissions'] == 1
    assert result['literal_declarations']['expected'] == 0
    assert result['literal_declarations']['precision'] == 0
    assert result['literal_declarations']['recall'] is None


def test_unknown_extra_and_clean_negative_document_do_not_raise_positive_recall(reference):
    doc = document(reference, 'missing_labels')
    output = prediction(doc)
    assert metrics(doc, output)['negative_documents']['clean_silence'] == 1
    sha = output['source_doc_sha256']
    extra = dict(id='extra', kind='contenido', decision='abstained', reason='unresolved_scope', unit=None, claim=None,
                 evidence=[source(dict(page=1, start=0, end=2, quote=doc['pages'][0][:2]), sha, 'label'),
                           source(dict(page=1, start=3, end=5, quote=doc['pages'][0][3:5]), sha, 'value')])
    output['records'].append(extra)
    result = metrics(doc, output)
    assert result['literal_declarations']['expected'] == result['literal_declarations']['correct'] == 0
    assert result['literal_declarations']['extras'] == result['output']['extras'] == 1
    assert result['literal_declarations']['emitted_typed_values'] == 1
    assert result['negative_documents']['invalid_or_extra_emissions'] == 1
    assert result['negative_documents']['clean_silence'] == 0


@pytest.mark.parametrize('name', ['crlf_long_labels', 'unicode_literals', 'plural_multiline', 'physical_second_page', 'explicit_page_continuation'])
def test_original_unicode_crlf_and_physical_page_spans_round_trip(reference, name):
    doc = document(reference, name)
    result = metrics(doc, prediction(doc))
    assert result['literal_declarations']['correct'] == len(doc['declarations'])
    assert result['output']['invalid_records'] == 0
    assert evaluator.hash_canonical_pages(doc['pages']) == hashlib.sha256(json.dumps(doc['pages'], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


@pytest.mark.parametrize('mutation', ['quote', 'offset', 'boolean_page', 'unit_id', 'candidate_project', 'absence', 'duplicate', 'missing_field'])
def test_reference_validation_rejects_malformed_gold_before_predictor(reference, mutation):
    doc = reference['documents'][0]
    declaration = doc['declarations'][0]
    if mutation == 'quote':
        declaration['value']['quote'] += ' invented'
    elif mutation == 'offset':
        declaration['value']['start'] += 1
    elif mutation == 'boolean_page':
        declaration['value']['page'] = True
    elif mutation == 'unit_id':
        declaration['unit_id'] = 'missing'
    elif mutation == 'candidate_project':
        doc['units'][0]['kind'] = 'project'
    elif mutation == 'absence':
        doc['absence_expected'] = True
    elif mutation == 'duplicate':
        doc['declarations'].append(deepcopy(declaration))
    elif mutation == 'missing_field':
        del declaration['value']
    def never_run(_):
        pytest.fail('Predictor ran before full reference validation')
    with pytest.raises(ValueError):
        evaluator.evaluate(reference, never_run)


def test_empty_reference_has_na_ratios():
    report = evaluator.evaluate(dict(version='session-declarations-reference.v1', reference_kind='custom synthetic', scope='none', documents=[]), prediction)
    assert report['total']['literal_declarations']['expected'] == 0
    assert report['total']['literal_declarations']['recall'] is None
    assert report['total']['literal_declarations']['precision'] is None
    assert report['total']['strict_session_claims']['recall'] is None
    assert report['total']['strict_session_claims']['precision'] is None
    assert report['total']['negative_documents']['expected'] == 0


def test_scoring_and_validation_never_import_matcher_or_scanner(reference, monkeypatch):
    original_import = builtins.__import__
    def restricted(name, *args, **kwargs):
        if name.startswith('curriculum') or name == 'scripts.session_declarations':
            pytest.fail('Scorer imported matcher or production code')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', restricted)
    evaluator.validate_reference(reference)
    report = evaluator.evaluate(reference, prediction)
    assert report['total']['literal_declarations']['correct'] == 45


def test_optional_adapter_passes_exact_pages_and_canonical_snapshot_hash(reference, monkeypatch):
    doc = document(reference, 'unicode_literals')
    stub = types.ModuleType('scripts.session_declarations')
    calls = []
    def extract(pages, *, source_doc_sha256):
        calls.append((pages, source_doc_sha256))
        return {'detached': True}
    stub.extract_declarations = extract
    monkeypatch.setitem(sys.modules, 'scripts.session_declarations', stub)
    assert evaluator.predict(doc) == {'detached': True}
    assert calls == [(doc['pages'], evaluator.hash_canonical_pages(doc['pages']))]


def test_cli_honors_custom_reference_and_output_without_citations(reference, monkeypatch, tmp_path, capsys):
    reference['documents'] = [document(reference)]
    reference['reference_kind'] = 'independent custom reference'
    reference['scope'] = 'one explicit document'
    raw = json.dumps(reference, ensure_ascii=False).encode()
    input_file, output_file = tmp_path / 'reference.json', tmp_path / 'report.json'
    input_file.write_bytes(raw)
    real_evaluate = evaluator.evaluate
    monkeypatch.setattr(evaluator, 'evaluate', lambda ref: real_evaluate(ref, prediction))
    assert evaluator.main(['--reference', str(input_file), '--output', str(output_file)]) == 0
    report = json.loads(output_file.read_text())
    assert report == json.loads(capsys.readouterr().out)
    assert report['reference_kind'] == reference['reference_kind']
    assert report['scope'] == reference['scope']
    assert report['reference_sha256'] == hashlib.sha256(raw).hexdigest()
    assert report['total']['literal_declarations']['expected'] == 2
    assert 'Descripción de objetos.' not in output_file.read_text()


def replace_unit_anchor(output, anchor):
    for record in output['records']:
        if record.get('unit') is not None:
            record['unit']['anchor'] = source(anchor, output['source_doc_sha256'], 'unit_anchor')
            synchronize_claim(record)


def test_anchor_identity_accepts_complete_identifier_prefix_both_directions(reference):
    doc = document(reference)
    output = prediction(doc)
    original = deepcopy(doc['units'][0]['anchor'])
    prefix = deepcopy(original)
    prefix['end'] = len('SESIÓN 1')
    prefix['quote'] = doc['pages'][0][:prefix['end']]
    replace_unit_anchor(output, prefix)
    result = metrics(doc, output)
    assert result['unit_assignment']['correct'] == 2
    assert result['unit_assignment']['expected_anchored'] == 2
    assert result['unit_assignment']['anchor_span_exact'] == 0
    # Reverse: gold covers just the complete identifier; predicted header title
    # is permitted without equating annotation span completeness with identity.
    doc['units'][0]['anchor'] = prefix
    replace_unit_anchor(output, original)
    result = metrics(doc, output)
    assert result['unit_assignment']['correct'] == 2
    assert result['unit_assignment']['anchor_span_exact'] == 0
    assert result['strict_session_claims']['correct'] == 2
    replace_unit_anchor(output, prefix)
    assert metrics(doc, output)['unit_assignment']['anchor_span_exact'] == 2


def test_project_prefix_requires_complete_label_through_colon(reference):
    doc = document(reference, 'project_no_inheritance')
    output = prediction(doc)
    anchor = deepcopy(doc['units'][0]['anchor'])
    anchor['end'], anchor['quote'] = len('Proyecto:'), 'Proyecto:'
    replace_unit_anchor(output, anchor)
    assert metrics(doc, output)['unit_assignment']['correct'] == 2
    anchor['end'], anchor['quote'] = len('Proyecto'), 'Proyecto'
    replace_unit_anchor(output, anchor)
    assert metrics(doc, output)['unit_assignment']['correct'] == 0
    assert metrics(doc, output)['literal_declarations']['correct'] == 2


@pytest.mark.parametrize('invalid_anchor', ['missing_number', 'partial_number', 'whole_page', 'through_next_line', 'wrong_start'])
def test_anchor_prefix_rejects_incomplete_identifier_and_scope_contamination(reference, invalid_anchor):
    doc = document(reference)
    # Insert a second digit; adjust authored offsets independently, without a
    # product scanner or changing the checked-in frozen reference.
    at = len('SESIÓN 1')
    doc['pages'][0] = doc['pages'][0][:at] + '0' + doc['pages'][0][at:]
    doc['units'][0]['anchor']['end'] += 1
    doc['units'][0]['anchor']['quote'] = doc['pages'][0][:doc['units'][0]['anchor']['end']]
    for declaration in doc['declarations']:
        for role in ('label', 'value'):
            declaration[role]['start'] += 1
            declaration[role]['end'] += 1
    output = prediction(doc)
    anchor = deepcopy(doc['units'][0]['anchor'])
    if invalid_anchor == 'missing_number':
        anchor['end'] = len('SESIÓN')
    elif invalid_anchor == 'partial_number':
        anchor['end'] = len('SESIÓN 1')
    elif invalid_anchor == 'whole_page':
        anchor['end'] = len(doc['pages'][0])
    elif invalid_anchor == 'through_next_line':
        anchor['end'] = doc['declarations'][0]['label']['end']
    elif invalid_anchor == 'wrong_start':
        anchor['start'] = 1
    anchor['quote'] = doc['pages'][0][anchor['start']:anchor['end']]
    replace_unit_anchor(output, anchor)
    result = metrics(doc, output)
    assert result['literal_declarations']['correct'] == 2
    assert result['unit_assignment']['correct'] == 0
    assert result['unit_assignment']['anchor_span_exact'] == 0
    assert result['strict_session_claims']['correct'] == 0


def test_anchor_extension_cannot_consume_same_line_declaration(reference):
    doc = document(reference)
    # Replace only the header newline with a space, keeping all offsets exact.
    at = doc['units'][0]['anchor']['end']
    doc['pages'][0] = doc['pages'][0][:at] + ' ' + doc['pages'][0][at + 1:]
    output = prediction(doc)
    anchor = deepcopy(doc['units'][0]['anchor'])
    anchor['end'] = doc['declarations'][0]['value']['end']
    anchor['quote'] = doc['pages'][0][:anchor['end']]
    replace_unit_anchor(output, anchor)
    assert metrics(doc, output)['unit_assignment']['correct'] == 0


def test_anchor_extension_cannot_consume_second_unit_on_same_line(reference):
    doc = document(reference)
    # Existing "Observar" is a separately authored unit anchor for this narrow
    # identity-safety test; no lexical scanner is used to create that reference.
    anchor = doc['units'][0]['anchor']
    start = doc['pages'][0].index('Observar')
    doc['units'].append(dict(id='second-physical-unit', kind='session',
                             anchor=dict(page=1, start=start, end=anchor['end'], quote='Observar')))
    output = prediction(doc)
    # A minimal reference plus a whole-header prediction intersects the second
    # unit and must not get identity credit through the prefix amendment.
    doc['units'][0]['anchor'] = dict(page=1, start=0, end=len('SESIÓN 1'), quote='SESIÓN 1')
    assert metrics(doc, output)['unit_assignment']['correct'] == 0


def test_unsupported_anchor_grammar_falls_back_to_exact_equality(reference):
    doc = document(reference)
    # Same-length replacement makes all original declaration offsets invariant.
    doc['pages'][0] = 'JORNAD' + doc['pages'][0][6:]
    doc['units'][0]['anchor']['quote'] = doc['pages'][0][:doc['units'][0]['anchor']['end']]
    output = prediction(doc)
    assert metrics(doc, output)['unit_assignment']['correct'] == 2
    anchor = dict(page=1, start=0, end=len('JORNAD 1'), quote=doc['pages'][0][:len('JORNAD 1')])
    replace_unit_anchor(output, anchor)
    assert metrics(doc, output)['unit_assignment']['correct'] == 0


@pytest.mark.parametrize('bad', [None, [], '', 12, True, {'records': [None]}, {'version': 'session-declarations.v1', 'records': [{'kind': [], 'decision': {}, 'unit': {}, 'claim': {}, 'evidence': [{'role': {}}]}]}])
def test_malformed_json_outputs_are_reported_instead_of_crashing(reference, bad):
    scored = evaluator.score(document(reference), bad)
    assert scored['output_errors'] or scored['record_errors']
    assert scored['metrics']['literal_declarations']['correct'] == 0


@pytest.mark.parametrize('mutation', ['missing', 'wrong_session', 'not_standalone', 'metadata_reset', 'unannotated_new_unit', 'annotated_new_unit'])
def test_cross_page_candidate_requires_named_literal_continuation_without_boundaries(reference, mutation):
    doc = document(reference, 'explicit_page_continuation')
    prefix = ''
    if mutation == 'wrong_session':
        doc['pages'][1] = doc['pages'][1].replace('sesión 1', 'sesión 2')
    elif mutation == 'not_standalone':
        prefix = 'Un ejemplo: '
    elif mutation == 'metadata_reset':
        prefix = 'DATOS GENERALES\n'
    elif mutation in ('unannotated_new_unit', 'annotated_new_unit'):
        prefix = 'SESIÓN 2: Distinta\n'
    if prefix:
        doc['pages'][1] = prefix + doc['pages'][1]
        for declaration in doc['declarations']:
            for role in ('label', 'value'):
                declaration[role]['start'] += len(prefix)
                declaration[role]['end'] += len(prefix)
    if mutation == 'annotated_new_unit':
        doc['units'].append(dict(id='second-session', kind='session', anchor=dict(page=2, start=0, end=len(prefix) - 1, quote=prefix.rstrip('\n'))))
    output = prediction(doc)
    for record in output['records']:
        record['evidence'] = [r for r in record['evidence'] if r['role'] != 'unit_continuation']
        if mutation != 'missing':
            start = doc['pages'][1].index('Continuación')
            end = doc['pages'][1].index('\n', start)
            record['evidence'].append(source(dict(page=2, start=start, end=end, quote=doc['pages'][1][start:end]), output['source_doc_sha256'], 'unit_continuation'))
        synchronize_claim(record)
    scored = evaluator.score(doc, output)
    assert scored['metrics']['literal_declarations']['correct'] == 2
    assert scored['metrics']['unit_assignment']['correct'] == 0
    assert scored['metrics']['joint_detection_unit']['correct'] == 0
    assert scored['metrics']['session_candidates']['correct'] == 0
    assert scored['metrics']['session_candidates']['incorrect'] == 2
    assert scored['metrics']['strict_session_claims']['correct'] == 0
    assert scored['metrics']['strict_session_claims']['incorrect'] == 2
    assert scored['metrics']['output']['invalid_unit_assignments'] == 2
    assert not scored['record_errors']
    if mutation == 'metadata_reset':
        assert 'metadata reset' in scored['unit_errors'][0]['errors'][0]
    elif mutation == 'annotated_new_unit':
        assert 'authored physical unit' in scored['unit_errors'][0]['errors'][0]


def test_same_physical_unit_with_different_ids_invalidates_scope_not_literal_detection(reference):
    doc = document(reference)
    output = prediction(doc)
    for i, record in enumerate(output['records']):
        record['unit']['id'] = f'session:alias{i}'
        synchronize_claim(record)
    result = metrics(doc, output)
    assert result['literal_declarations']['correct'] == 2
    assert result['output']['invalid_unit_assignments'] == 2
    assert result['unit_assignment']['correct'] == result['joint_detection_unit']['correct'] == 0
    assert result['session_candidates']['correct'] == 0
    assert result['strict_session_claims']['correct'] == 0


def test_same_physical_id_with_minimum_and_full_header_is_consistent(reference):
    doc = document(reference)
    output = prediction(doc)
    record = output['records'][0]
    anchor = dict(page=1, start=0, end=len('SESIÓN 1'), quote='SESIÓN 1')
    record['unit']['anchor'] = source(anchor, output['source_doc_sha256'], 'unit_anchor')
    synchronize_claim(record)
    result = metrics(doc, output)
    assert result['output']['invalid_unit_assignments'] == 0
    assert result['literal_declarations']['correct'] == 2
    assert result['unit_assignment']['correct'] == result['joint_detection_unit']['correct'] == 2
    assert result['unit_assignment']['anchor_span_exact'] == 1


@pytest.mark.parametrize('reason', ['project_scope', 'unresolved_scope', 'negated', 'unknown_reason'])
def test_candidate_reason_must_agree_with_explicit_session_scope(reference, reason):
    doc = document(reference)
    output = prediction(doc)
    output['records'][0]['reason'] = reason
    result = metrics(doc, output)
    assert result['output']['invalid_records'] == 1
    assert result['session_candidates']['correct'] == 1
    assert result['joint_detection_unit']['correct'] == 1


@pytest.mark.parametrize('mutation', ['project_without_unit', 'unresolved_with_project', 'project_on_session', 'challenge_candidate'])
def test_abstention_reason_agrees_with_unit_and_decision(reference, mutation):
    doc = document(reference, 'project_no_inheritance')
    output = prediction(doc)
    record = output['records'][0]
    if mutation == 'project_without_unit':
        record['unit'] = None
    elif mutation == 'unresolved_with_project':
        record['reason'] = 'unresolved_scope'
    elif mutation == 'project_on_session':
        record['unit']['kind'] = 'session'
        record['unit']['id'] = 'session:altered'
    else:
        record['reason'] = 'negated'
        record['decision'] = 'candidate'
    assert metrics(doc, output)['scope_abstentions']['correct'] == 1
    assert metrics(doc, output)['output']['invalid_records'] == 1


# v1.2 adversarial cases are independently authored mutations in these tests;
# the frozen reference and its fixed opportunity denominators remain untouched.


def test_structured_scope_is_lossless_and_report_does_not_alias_inputs(reference):
    reference['scope'] = {
        'window': {'pages': [1, 2], 'labels': ['á\r\n🙂', '  unchanged  ']},
        'not_teacher_gold': True, 'optional': None, 'empty': {}, 'ratio': 0.25,
    }
    original = deepcopy(reference)
    outputs = {d['id']: prediction(d) for d in reference['documents']}
    original_outputs = deepcopy(outputs)
    report = evaluator.evaluate(reference, lambda doc: outputs[doc['id']])
    assert report['evaluator_version'] == 'session-declarations-evaluation.v1.3.3'
    assert report['scope'] == original['scope']
    assert json.loads(json.dumps(report, ensure_ascii=False))['scope'] == original['scope']
    assert reference == original
    assert outputs == original_outputs
    report['scope']['window']['labels'].append('report-only change')
    assert reference == original


@pytest.mark.parametrize('scope', [None, [], 1, True, '', {'invalid': float('nan')},
                                  {'invalid': float('inf')}, {1: 'coerced key'}, {'tuple': (1, 2)}])
def test_scope_rejects_non_json_or_non_object_non_string_without_coercion(reference, scope):
    reference['scope'] = scope
    with pytest.raises(ValueError, match='Invalid reference envelope'):
        evaluator.evaluate(reference, lambda _: pytest.fail('Predictor should not run'))


def test_empty_json_object_scope_is_valid(reference):
    reference['scope'] = {}
    assert evaluator.evaluate(reference, prediction)['scope'] == {}


@pytest.mark.parametrize('extra', [
    {'decision': 'candidate'},
    {'decision': 'candidate', 'kind': None, 'claim': None, 'evidence': []},
    {'claim': {}},
    {'decision': 'abstained', 'claim': False},
    {'decision': 'unknown', 'claim': 'unsupported claim'},
])
def test_strict_claim_precision_includes_every_malformed_assertion_even_without_value(reference, extra):
    doc = document(reference)
    output = prediction(doc)
    output['records'].append(extra)
    result = metrics(doc, output)
    assert result['strict_session_claims'] == dict(expected=2, correct=2, incorrect=0, omitted=0,
                                                  explicit_abstentions=0, emitted_claim_records=3,
                                                  precision=pytest.approx(2 / 3), recall=1)
    assert result['literal_declarations']['emitted_typed_values'] == 2
    assert result['output']['malformed_records'] == 1


def test_valid_but_extra_candidate_is_a_strict_false_positive(reference):
    doc = document(reference)
    output = prediction(doc)
    extra = deepcopy(output['records'][0])
    extra['id'] += ':extra'
    extra['claim']['claim_id'] += ':extra'
    extra['evidence'][0] = source(doc['units'][0]['anchor'], output['source_doc_sha256'], 'label')
    synchronize_claim(extra)
    output['records'].append(extra)
    result = metrics(doc, output)
    assert result['output']['malformed_records'] == 0
    assert result['output']['extras'] == 1
    assert result['strict_session_claims']['correct'] == 2
    assert result['strict_session_claims']['emitted_claim_records'] == 3
    assert result['strict_session_claims']['precision'] == pytest.approx(2 / 3)


def test_strict_claim_positive_denominator_never_credits_abstention_silence_or_negatives(reference):
    def withhold(doc):
        output = prediction(doc)
        for record in output['records']:
            if record['decision'] == 'candidate':
                abstain(record)
        return output
    total = evaluator.evaluate(reference, withhold)['total']
    assert total['strict_session_claims'] == dict(expected=36, correct=0, incorrect=0, omitted=0,
                                                  explicit_abstentions=36, emitted_claim_records=0,
                                                  precision=None, recall=0)
    assert total['literal_declarations']['correct'] == 45
    assert total['challenge_opportunities_v1_2']['no_claim_safe'] == 22
    def silence(doc):
        output = prediction(doc)
        output['records'] = []
        return output
    total = evaluator.evaluate(reference, silence)['total']
    assert total['strict_session_claims'] == dict(expected=36, correct=0, incorrect=0, omitted=36,
                                                  explicit_abstentions=0, emitted_claim_records=0,
                                                  precision=None, recall=0)
    assert total['challenge_opportunities_v1_2']['silence'] == 22
    assert total['negative_documents']['clean_silence'] == 15


def test_strict_claim_partition_stays_on_fixed_positive_opportunities(reference):
    doc = document(reference, 'two_sessions')
    output = prediction(doc)
    abstain(output['records'][1])
    output['records'][2]['unit'] = deepcopy(output['records'][0]['unit'])
    synchronize_claim(output['records'][2])
    output['records'].pop()
    strict = metrics(doc, output)['strict_session_claims']
    assert strict == dict(expected=4, correct=1, incorrect=1, omitted=1, explicit_abstentions=1,
                          emitted_claim_records=2, precision=0.5, recall=0.25)


def test_incomplete_abstention_is_failed_recovery_without_false_emitted_claim(reference):
    doc = document(reference)
    output = prediction(doc)
    for record in output['records']:
        abstain(record)
        record['evidence'] = [ref for ref in record['evidence'] if ref['role'] == 'label']
    result = metrics(doc, output)
    assert result['strict_session_claims']['incorrect'] == 2
    assert result['strict_session_claims']['explicit_abstentions'] == 0
    assert result['strict_session_claims']['emitted_claim_records'] == 0
    assert result['strict_session_claim_diagnostics'] == dict(wrong_emitted_claim_records=0,
                                                             response_abstention_opportunities=2)


def test_wrong_emitted_diagnostic_counts_assertions_instead_of_missed_opportunities(reference):
    doc = document(reference, 'two_sessions')
    output = prediction(doc)
    output['records'][2]['unit'] = deepcopy(output['records'][0]['unit'])
    synchronize_claim(output['records'][2])
    output['records'].pop()
    result = metrics(doc, output)
    assert result['strict_session_claims']['correct'] == 2
    assert result['strict_session_claims']['emitted_claim_records'] == 3
    assert result['strict_session_claims']['omitted'] == 1
    assert result['strict_session_claim_diagnostics'] == dict(wrong_emitted_claim_records=1,
                                                             response_abstention_opportunities=0)


@pytest.mark.parametrize('claim_has_challenge_locator', [True, False])
def test_contradictory_claim_locator_never_becomes_safe_challenge_silence(claim_has_challenge_locator):
    page = 'SESIÓN 1: Observar\nContenido: Formas.\nPDA: No aplica.\nInicio:\n-Observar.\n'
    def span(quote):
        start = page.index(quote)
        return dict(page=1, start=start, end=start + len(quote), quote=quote)
    doc = dict(id='contradictory-locators', pages=[page],
               units=[dict(id='s1', kind='session', anchor=span('SESIÓN 1: Observar'))],
               declarations=[dict(id='d1', kind='contenido', label=span('Contenido:'), value=span('Formas.'),
                                  unit_id='s1', expected_decision='candidate', reason='explicit_session')],
               challenges=[dict(id='c1', anchor=span('PDA:'), reason='negated')], absence_expected=False)
    output = prediction(doc, include_challenges=False)
    claim = output['records'][0]['claim']
    claim['predicate'] = 'pda_declarado'
    claim['object_value'] = 'No aplica.'
    claim['evidence'] = [source(span('No aplica.'), output['source_doc_sha256'], 'value'),
                         deepcopy(output['records'][0]['unit']['anchor'])]
    if claim_has_challenge_locator:
        claim['evidence'].insert(0, source(span('PDA:'), output['source_doc_sha256'], 'label'))
    result = evaluator.score(doc, output)
    assert result['record_errors']
    assert result['metrics']['strict_session_claims']['correct'] == 0
    safety = result['metrics']['challenge_opportunities_v1_2']
    assert safety['no_claim_safe'] == safety['silence'] == 0
    assert safety['candidate_or_claim' if claim_has_challenge_locator else 'no_claim_unknown'] == 1


def test_challenge_larger_exact_source_span_is_mismatch_not_malformed(reference):
    doc = document(reference, 'negated_declaration')
    output = prediction(doc)
    label = output['records'][0]['evidence'][0]
    label['region']['end'] += 1
    label['excerpt'] = doc['pages'][label['page_number'] - 1][label['region']['start']:label['region']['end']]
    result = evaluator.score(doc, output)
    assert not result['record_errors']
    assert not result['malformed_record_errors']
    total = result['metrics']
    assert total['legacy_challenges_v1_1'] == total['challenges']
    assert total['legacy_challenges_v1_1']['invalid_records'] == 1
    assert total['challenge_records_v1_2'] == dict(emitted_records=2, candidate_or_claim_records=0,
                                                   malformed_records=0, invalid_provenance_records=0,
                                                   explicit_abstention_records=2, exact_label_records=1,
                                                   label_span_mismatch_records=1, duplicate_id_records=0)
    diagnostic = total['challenge_opportunities_v1_2']
    assert diagnostic['no_claim_safe'] == diagnostic['explicit_abstention'] == 2
    assert diagnostic['label_span_mismatch'] == 1
    assert diagnostic['malformed_record'] == diagnostic['no_claim_unknown'] == 0


@pytest.mark.parametrize('same_id', [False, True])
def test_challenge_multiplicity_is_not_individual_record_malformation(reference, same_id):
    doc = document(reference, 'negated_declaration')
    output = prediction(doc)
    duplicate = deepcopy(output['records'][0])
    if not same_id:
        duplicate['id'] += ':again'
    output['records'].append(duplicate)
    result = evaluator.score(doc, output)
    assert not result['malformed_record_errors']
    total = result['metrics']
    assert total['challenges'] == total['legacy_challenges_v1_1']
    assert total['challenges']['duplicates'] == 1
    assert total['challenge_records_v1_2']['emitted_records'] == 3
    assert total['challenge_records_v1_2']['explicit_abstention_records'] == 3
    assert total['challenge_records_v1_2']['malformed_records'] == 0
    assert total['challenge_records_v1_2']['duplicate_id_records'] == (2 if same_id else 0)
    assert total['challenge_opportunities_v1_2']['explicit_abstention'] == 2
    assert total['challenge_opportunities_v1_2']['no_claim_safe'] == 2
    assert total['challenge_opportunities_v1_2']['multiplicity'] == 1
    assert total['challenge_opportunities_v1_2']['malformed_record'] == 0


def test_one_record_spanning_two_challenges_counts_once_as_record_and_twice_as_opportunity(reference):
    doc = document(reference, 'negated_declaration')
    output = prediction(doc)
    record = output['records'][0]
    first, last = doc['challenges'][0]['anchor'], doc['challenges'][1]['anchor']
    span = dict(page=first['page'], start=first['start'], end=last['end'],
                quote=doc['pages'][first['page'] - 1][first['start']:last['end']])
    record['evidence'] = [source(span, output['source_doc_sha256'], 'label')]
    output['records'] = [record]
    result = metrics(doc, output)
    assert result['output']['extras'] == 1
    assert result['challenge_records_v1_2']['emitted_records'] == 1
    assert result['challenge_records_v1_2']['malformed_records'] == 0
    assert result['challenge_records_v1_2']['label_span_mismatch_records'] == 1
    assert result['challenge_opportunities_v1_2']['label_span_mismatch'] == 2
    assert result['challenge_opportunities_v1_2']['no_claim_safe'] == 2
    assert result['challenge_opportunities_v1_2']['explicit_abstention'] == 2


@pytest.mark.parametrize('mutation', ['source_hash', 'extraction_hash', 'reference_hash', 'fabricated_quote', 'shape', 'unlocalizable'])
def test_no_claim_safety_is_unknown_with_invalid_output_provenance_or_unlocalizable_record(reference, mutation):
    doc = document(reference, 'negated_declaration')
    output = prediction(doc)
    if mutation in ('source_hash', 'extraction_hash'):
        output['source_doc_sha256' if mutation == 'source_hash' else 'extraction_sha256'] = 'f' * 64
    elif mutation == 'reference_hash':
        output['records'][0]['evidence'][0]['document_sha256'] = 'f' * 64
    elif mutation == 'fabricated_quote':
        output['records'][0]['evidence'][0]['excerpt'] = 'fabricated'
    elif mutation == 'shape':
        output['records'][0]['decision'] = 'unknown'
    else:
        output['records'].append(None)
    result = metrics(doc, output)
    diagnostic = result['challenge_opportunities_v1_2']
    affected = 2 if mutation in ('source_hash', 'extraction_hash', 'unlocalizable') else 1
    assert diagnostic['no_claim_unknown'] == affected
    assert diagnostic['no_claim_safe'] == 2 - affected
    assert diagnostic['candidate_or_claim'] == 0
    assert diagnostic['silence'] == 0
    if mutation in ('source_hash', 'extraction_hash'):
        assert result['output']['malformed_records'] == 0
        assert result['challenge_records_v1_2']['malformed_records'] == 0
        assert diagnostic['invalid_provenance'] == 2
    elif mutation in ('reference_hash', 'fabricated_quote'):
        assert result['challenge_records_v1_2']['invalid_provenance_records'] == 1


@pytest.mark.parametrize('claim_only', [False, True])
def test_malformed_challenge_assertion_defeats_safety_and_enters_strict_precision(reference, claim_only):
    doc = document(reference, 'negated_declaration')
    output = prediction(doc)
    if claim_only:
        output['records'][0]['claim'] = {}
    else:
        output['records'][0]['decision'] = 'candidate'
    result = metrics(doc, output)
    assert result['strict_session_claims']['expected'] == 0
    assert result['strict_session_claims']['emitted_claim_records'] == 1
    assert result['strict_session_claims']['precision'] == 0
    assert result['strict_session_claims']['recall'] is None
    assert result['challenge_records_v1_2']['malformed_records'] == 1
    assert result['challenge_opportunities_v1_2']['candidate_or_claim'] == 1
    # A malformed claim may have additional or missing locators. v1.2.1 does
    # not certify the other challenge as safe merely from the record label.
    assert result['challenge_opportunities_v1_2']['no_claim_safe'] == 0
    assert result['challenge_opportunities_v1_2']['no_claim_unknown'] == 1


def test_candidate_hidden_in_challenge_multiplicity_cannot_earn_no_claim_safety(reference):
    doc = document(reference, 'negated_declaration')
    output = prediction(doc)
    duplicate = deepcopy(output['records'][0])
    duplicate.update(id='candidate-hidden-in-multiplicity', decision='candidate')
    output['records'].append(duplicate)
    result = metrics(doc, output)
    assert result['legacy_challenges_v1_1']['duplicates'] == 1
    assert result['challenge_opportunities_v1_2']['multiplicity'] == 1
    assert result['challenge_opportunities_v1_2']['candidate_or_claim'] == 1
    assert result['challenge_opportunities_v1_2']['no_claim_safe'] == 0
    assert result['challenge_opportunities_v1_2']['no_claim_unknown'] == 1
    # Both opportunities still have an explicit abstention, a separate flag
    # which cannot conceal the candidate or become positive detection credit.
    assert result['challenge_opportunities_v1_2']['explicit_abstention'] == 2


def test_unlocalizable_candidate_prevents_claiming_challenge_silence_is_safe(reference):
    doc = document(reference, 'negated_declaration')
    output = prediction(doc)
    output['records'] = [{'decision': 'candidate', 'claim': None}]
    result = metrics(doc, output)
    assert result['challenge_opportunities_v1_2']['no_claim_unknown'] == 2
    assert result['challenge_opportunities_v1_2']['no_claim_safe'] == 0
    assert result['challenge_opportunities_v1_2']['silence'] == 0
    assert result['challenge_records_v1_2']['emitted_records'] == 0
    assert result['output']['emitted_records'] == 1
    assert result['strict_session_claims']['emitted_claim_records'] == 1
