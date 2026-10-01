"""Additional synthetic label reference, frozen before matcher v2."""
import hashlib
import json
from pathlib import Path

from scripts.evaluate_session_declarations import evaluate, validate_reference
from scripts.session_declarations import extract_declarations, snapshot_hash

FIXTURE = Path(__file__).parent / 'fixtures/interpretation/session_declarations_labels_v1.json'
SHA256 = 'a5674e0ef46a8b8e6f374df3e6198bdf917ff3b2ec04ec6c96b23e9b2105d9e9'


def test_additional_reference_freeze_and_separate_denominators():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
    reference = json.loads(FIXTURE.read_bytes())
    validate_reference(reference)
    assert isinstance(reference['scope'], dict)
    docs = reference['documents']
    assert len(docs) == 18
    declarations = [d for doc in docs for d in doc['declarations']]
    assert len(declarations) == 17
    assert sum(d['expected_decision'] == 'candidate' for d in declarations) == 16
    assert sum(d['expected_decision'] == 'abstained' for d in declarations) == 1
    assert sum(len(d['challenges']) for d in docs) == 13
    assert sum(d['absence_expected'] for d in docs) == 9


def test_additional_fixed_opportunities_are_reported_without_challenge_credit_in_recall():
    report = evaluate(json.loads(FIXTURE.read_bytes()))
    assert report['total']['literal_declarations']['expected'] == 17
    assert report['total']['literal_declarations']['correct'] == 17
    strict = report['total']['strict_session_claims']
    assert strict['expected'] == strict['correct'] == strict['emitted_claim_records'] == 16
    assert strict['precision'] == strict['recall'] == 1
    assert report['total']['scope_abstentions']['expected'] == report['total']['scope_abstentions']['correct'] == 1
    challenges = report['total']['challenge_opportunities_v1_2']
    assert challenges['expected'] == challenges['explicit_abstention'] == challenges['no_claim_safe'] == 13
    assert report['total']['output']['invalid_records'] == report['total']['output']['extras'] == 0


def test_numbered_local_label_evidence_is_complete_without_sep_identity():
    document = next(d for d in json.loads(FIXTURE.read_bytes())['documents'] if d['id'] == 'local_code_pda')
    output = extract_declarations(document['pages'], source_doc_sha256=snapshot_hash(document['pages']))
    assert [r['evidence'][0]['excerpt'] for r in output['records']] == ['X7 PDA2:', 'L12 PDA003:', 'Q2 PDA0:']
    for record in output['records']:
        assert record['kind'] == 'pda'
        assert record['claim']['predicate'] == 'pda_declarado'
        assert record['claim']['metadata']['validation'] == 'literal_declaration_not_SEP_alignment'
        assert not any('sep_id' in key for key in record['claim']['metadata'])


def test_container_is_layout_and_child_preserves_its_own_literal_label():
    page = 'SESIÓN 1: Explorar\nContenidos/PDA: Contenido: Lectura de la palabra PDA.\nInicio:\n-Leer.\n'
    record, = extract_declarations([page], source_doc_sha256=snapshot_hash([page]))['records']
    assert record['decision'] == 'candidate'
    assert record['evidence'][0]['excerpt'] == 'Contenido:'
    assert record['claim']['object_value'] == 'Lectura de la palabra PDA.'


def test_v2_new_labels_do_not_inherit_cross_page_unit_by_proximity():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Explorar.\n', 'X7 PDA2: Describe formas.\nInicio:\n-Observar.\n']
    record, = extract_declarations(pages, source_doc_sha256=snapshot_hash(pages))['records']
    assert record['decision'] == 'abstained' and record['reason'] == 'unresolved_scope'
    assert record['unit'] is None and record['claim'] is None
