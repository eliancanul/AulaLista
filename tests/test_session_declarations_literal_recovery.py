"""Opt-in behavior against the independently frozen synthetic local-list stratum."""
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import session_declarations as matcher
from scripts import evaluate_session_declarations as scorer
from scripts.anchor_scope_audit import ScopeAuditConfig, ScopeAuditError, route_record
from scripts.replay_interpretation import replay_scope_audit
from test_anchor_scope_audit import Stub


REFERENCE = json.loads((Path(__file__).parent / 'fixtures/interpretation/'
                       'session_declarations_literal_recovery_v1.json').read_bytes())
NEW = {(item['document_id'], item['declaration_id'])
       for item in REFERENCE['scope']['new_recovery_opportunities']}


def extract(pages, **options):
    return matcher.extract_declarations(pages, source_doc_sha256=matcher.snapshot_hash(pages), **options)


def span(reference):
    return {'page': reference['page_number'], 'start': reference['region']['start'],
            'end': reference['region']['end'], 'quote': reference['excerpt']}


@pytest.mark.parametrize('document', REFERENCE['documents'], ids=lambda d: d['id'])
def test_opt_in_recovers_only_authored_full_lists_and_preserves_existing_literals(document):
    pages = copy.deepcopy(document['pages'])
    default = extract(pages)
    assert default == extract(pages, literal_recovery=False)
    opted = extract(pages, literal_recovery=True)
    assert pages == document['pages']
    proofs = opted['literal_recovery']['recoveries']
    expected_new = [d for d in document['declarations'] if (document['id'], d['id']) in NEW]
    assert len(proofs) == len(expected_new)
    assert len({r['id'] for r in opted['records']}) == len(opted['records'])
    proof_ids = {proof['record_id'] for proof in proofs}
    for expected in document['declarations']:
        actual, = [r for r in opted['records'] if span(r['evidence'][0]) == expected['label']]
        value, = [e for e in actual['evidence'] if e['role'] == 'value']
        assert span(value) == expected['value']
        if (document['id'], expected['id']) in NEW:
            assert actual['id'] in proof_ids
            assert (actual['kind'], actual['decision'], actual['reason'], actual['unit'], actual['claim']) == (
                'contenido', 'abstained', 'unresolved_scope', None, None)
            assert [e['role'] for e in actual['evidence']] == ['label', 'value']
        else:
            original, = [r for r in default['records'] if span(r['evidence'][0]) == expected['label']]
            assert actual == original
    for proof in proofs:
        record = next(r for r in opted['records'] if r['id'] == proof['record_id'])
        label, value = record['evidence']
        assert proof['label_utf8_sha256'] == hashlib.sha256(label['excerpt'].encode()).hexdigest()
        assert proof['value_utf8_sha256'] == hashlib.sha256(value['excerpt'].encode()).hexdigest()
        assert proof['boundary']['page_number'] == label['page_number']
        assert proof['boundary']['region']['start'] >= value['region']['end']
        for reference in record['evidence'] + [proof['boundary']] + proof['context']:
            page = pages[reference['page_number'] - 1]
            assert page[reference['region']['start']:reference['region']['end']] == reference['excerpt']
            assert reference['document_sha256'] == opted['source_doc_sha256']


def test_unchanged_scorer_and_fixed_denominators_are_used():
    report = scorer.evaluate(REFERENCE, predictor=lambda d: extract(d['pages'], literal_recovery=True))
    baseline = scorer.evaluate(REFERENCE, predictor=lambda d: extract(d['pages']))
    assert report['total']['literal_declarations']['expected'] == 37
    assert report['total']['literal_declarations']['correct'] == 37
    assert report['total']['strict_session_claims']['expected'] == 1
    assert report['total']['strict_session_claims'] == baseline['total']['strict_session_claims']
    # The independently authored unit opportunities are not guaranteed to be
    # recognized by the unchanged unit scanner; preserve/report that gap.
    assert report['total']['strict_session_claims']['correct'] == 0
    assert report['total']['challenges']['expected'] == 109
    # Existing baseline discourse limitations are measured separately; the
    # recovery ledger must have no asserted list outside the frozen new stratum.
    assert sum(len(extract(d['pages'], literal_recovery=True)['literal_recovery']['recoveries'])
               for d in REFERENCE['documents']) == 19


@pytest.mark.parametrize('flag', [None, 0, 1, 'true', [], {}])
def test_opt_in_is_an_explicit_boolean(flag):
    with pytest.raises(ValueError, match='literal recovery'):
        extract(['DATOS GENERALES'], literal_recovery=flag)


SCOPE_PAGES = ['Proyecto: Fichas\n\nContenido local:\n- Nombres de marcas.\n'
               '- Formas de señales.\nRecursos:\n']


def test_new_full_literal_is_consumed_by_current_mode_a_and_revalidated_from_source():
    provider = Stub()
    source = matcher.snapshot_hash(SCOPE_PAGES)
    opted = matcher.extract_declarations(
        SCOPE_PAGES, source_doc_sha256=source, literal_recovery=True,
        scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True, literal_recovery=True))
    assert provider.calls == 1
    assert provider.last_request.literal_recovery is True
    audit = opted['scope_audit']
    assert audit['status'] == 'candidates_for_review'
    candidate, = audit['candidates']
    assert candidate['state'] == 'needs_human_review'
    assert candidate['transport_status'] == 'accepted'
    assert candidate['semantic_validation'] is candidate['production_applied'] is candidate['claim_emitted'] is False
    assert all(r['claim'] is None and r['unit'] is None for r in opted['records'])
    assert candidate['label_span']['excerpt'] == 'Contenido local:'
    assert candidate['immutable_value_span']['excerpt'] == '- Nombres de marcas.\n- Formas de señales.'
    record, = opted['records']
    assert not route_record({'id': 'SYNTHETIC', 'pages': SCOPE_PAGES}, record)['eligible']
    assert route_record({'id': 'SYNTHETIC', 'pages': SCOPE_PAGES}, record, literal_recovery=True)['eligible']
    stale = replace(provider.last_request, literal_recovery=False)
    with pytest.raises(ScopeAuditError, match='current_route_reconstruction_mismatch'):
        replay_scope_audit(request=stale, recordings=provider.last_recordings)


@pytest.mark.parametrize('extract_flag, audit_flag', [(True, False), (False, True)])
def test_mismatched_opt_in_cannot_transmit_records_to_provider(extract_flag, audit_flag):
    provider = Stub()
    output = extract(SCOPE_PAGES, literal_recovery=extract_flag,
                     scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True, literal_recovery=audit_flag))
    assert output['scope_audit']['status'] == 'invalid'
    assert output['scope_audit']['errors'] == ['literal_recovery_config_mismatch']
    assert output['scope_audit']['candidates'] == [] and provider.calls == 0


def test_disabled_audit_never_issues_a_provider_call():
    provider = Stub(fail=True)
    output = extract(SCOPE_PAGES, literal_recovery=True,
                     scope_audit=ScopeAuditConfig('SYNTHETIC', provider, literal_recovery=True))
    assert provider.calls == 0 and 'scope_audit' not in output
    assert len(output['literal_recovery']['recoveries']) == 1


def test_all_recovery_proofs_preserve_the_callers_document_binding():
    source = 'a' * 64
    document = next(d for d in REFERENCE['documents'] if d['id'] == 'local_safe_source_proven_book_context')
    output = matcher.extract_declarations(document['pages'], source_doc_sha256=source, literal_recovery=True)
    proof, = output['literal_recovery']['recoveries']
    for reference in [proof['boundary']] + proof['context']:
        assert reference['document_sha256'] == source
