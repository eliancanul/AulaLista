"""Measured mixed-field evidence; the independent reference is never rewritten."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import session_declarations as matcher
from scripts import evaluate_session_declarations as scorer
from scripts.mixed_field_recovery import recover_mixed_fields

REFERENCE = json.loads((Path(__file__).parent / 'fixtures/interpretation/'
                       'session_declarations_mixed_fields_v1.json').read_bytes())


def extract(pages, **options):
    return matcher.extract_declarations(pages, source_doc_sha256=matcher.snapshot_hash(pages), **options)


def span(ref):
    return {'page': ref['page_number'], 'start': ref['region']['start'],
            'end': ref['region']['end'], 'quote': ref['excerpt']}


@pytest.mark.parametrize('doc', REFERENCE['documents'], ids=lambda d: d['id'])
def test_recovered_evidence_is_exact_and_every_prior_fact_is_unchanged(doc):
    pages = copy.deepcopy(doc['pages'])
    baseline = extract(pages)
    assert baseline == extract(pages, mixed_fields=False)
    opted = extract(pages, mixed_fields=True)
    assert pages == doc['pages']
    expected = {tuple(x['label'].values()): x for x in doc['expected_recoveries']}
    proofs = {p['record_id']: p for p in opted['mixed_field_recovery']['recoveries']}
    assert len(baseline['records']) == len(opted['records'])
    changed = set()
    for before, after in zip(baseline['records'], opted['records']):
        if before == after:
            continue
        assert after['id'] in proofs
        changed.add(after['id'])
        assert {k: v for k, v in before.items() if k != 'evidence'} == {
            k: v for k, v in after.items() if k != 'evidence'}
        assert [e for e in after['evidence'] if e['role'] != 'value'] == before['evidence']
        assert (after['kind'], after['decision'], after['reason'], after['claim']) == (
            None, 'abstained', 'combined_label', None)
        label, = [e for e in after['evidence'] if e['role'] == 'label']
        value, = [e for e in after['evidence'] if e['role'] == 'value']
        authored = expected[tuple(span(label).values())]
        assert span(value) == authored['value']
        proof = proofs[after['id']]
        assert span(proof['boundary']) == authored['closing_heading']
        assert proof['label_utf8_sha256'] == hashlib.sha256(label['excerpt'].encode()).hexdigest()
        assert proof['value_utf8_sha256'] == hashlib.sha256(value['excerpt'].encode()).hexdigest()
        for evidence in after['evidence'] + [proof['boundary']] + proof['context']:
            e = span(evidence)
            assert pages[e['page']-1][e['start']:e['end']] == e['quote']
        assert scorer._record_errors(after, pages, matcher.snapshot_hash(pages)) == []
    assert changed == set(proofs)
    assert len(proofs) <= len(doc['expected_recoveries'])
    # Metadata and all pre-existing literals remain compatible with both opts.
    local = extract(pages, literal_recovery=True)
    together = extract(pages, literal_recovery=True, mixed_fields=True)
    assert local['literal_recovery'] == together['literal_recovery']
    assert [r for r in local['records'] if r['kind'] is not None] == [
        r for r in together['records'] if r['kind'] is not None]


def test_report_recall_omission_without_changing_the_frozen_denominator():
    recovered = 0
    omissions = []
    for doc in REFERENCE['documents']:
        output = extract(doc['pages'], mixed_fields=True)
        labels = [span(r['evidence'][0]) for r in output['records']
                  if r['id'] in {p['record_id'] for p in output['mixed_field_recovery']['recoveries']}]
        recovered += len(labels)
        omissions.extend((doc['id'], e['id']) for e in doc['expected_recoveries'] if e['label'] not in labels)
    assert sum(len(d['expected_recoveries']) for d in REFERENCE['documents']) == 24
    assert recovered == 23
    # Deliberately stricter than the source reference: an example paragraph
    # without a blank closure is not discarded merely because a session follows.
    assert omissions == [('genuine_session_reset', 'genuine_session_reset:recover:1')]


@pytest.mark.parametrize('flag', [None, 0, 1, 'yes', [], {}])
def test_only_explicit_boolean_opt_in_is_allowed(flag):
    with pytest.raises(ValueError, match='mixed fields'):
        extract(['Contenidos/PDA: Texto.\nInicio:\n'], mixed_fields=flag)


def test_existing_value_is_idempotent_and_inputs_are_not_mutated():
    pages = ['Sesión 1\nContenidos/PDA: Un bloque.\nInicio:\nLeer.']
    output = extract(pages, mixed_fields=True)
    before = copy.deepcopy(output)
    units, _ = matcher._unit_data(pages, matcher.snapshot_hash(pages))
    records, ledger = recover_mixed_fields(pages=pages, source_doc_sha256=matcher.snapshot_hash(pages),
                                          records=output['records'], units=units)
    assert records == output['records']
    assert output == before
    assert ledger['recoveries'] == []


@pytest.mark.parametrize('prefix', ['Ejemplo:', 'Propuesta:', 'No adoptado:', 'Si se elige:'])
def test_recognized_session_cannot_clear_an_unclosed_example_container(prefix):
    pages = [prefix + '\nSesión 1\nContenidos/PDA: Texto completo.\nInicio:\nLeer.']
    assert extract(pages, mixed_fields=True)['mixed_field_recovery']['recoveries'] == []


@pytest.mark.parametrize('char', ['\t', '\x00', '\v', '\f', '\x85', '\u2028', '\u2029', '\u200b', '\u202e'])
@pytest.mark.parametrize('where', ['label', 'value', 'context', 'closer'])
def test_nonphysical_and_format_controls_cannot_be_trimmed_into_admission(char, where):
    page = 'Sesión 1\nContenidos/PDA:\n* Describe colores.\nInicio:\nLeer.'
    if where == 'label':
        page = page.replace('Contenidos', char + 'Contenidos')
    elif where == 'value':
        page = page.replace('* Describe', char + '* Describe')
    elif where == 'context':
        page = page.replace('\nContenidos', '\n' + char + '\nContenidos')
    else:
        page = page.replace('Inicio:', char + 'Inicio:')
    assert extract([page], mixed_fields=True)['mixed_field_recovery']['recoveries'] == []


def test_disabled_audit_and_mixed_option_are_independent():
    from scripts.mixed_field_audit import MixedFieldAuditConfig
    pages = ['Contenidos/PDA: Un bloque.\nInicio:\n']
    assert extract(pages) == extract(pages, mixed_audit=MixedFieldAuditConfig('doc'))


@pytest.mark.parametrize('row', [
    'Tema de la sesión: Ejemplo no adoptado.',
    'Organización: Propuesta sin adoptar.',
    'Fase: Si se elige esta alternativa.',
    'Campo: No se aplica este bloque.',
])
def test_unsafe_metadata_payload_cannot_license_a_following_mixed_field(row):
    pages = ['Sesión 1\n' + row + '\nContenidos/PDA: Texto.\nInicio:\nLeer.']
    assert extract(pages, mixed_fields=True)['mixed_field_recovery']['recoveries'] == []


SUPPLEMENT = json.loads((Path(__file__).parent / 'fixtures/interpretation/'
                         'session_declarations_mixed_metadata_supplement_v1.json').read_bytes())


@pytest.mark.parametrize('doc', SUPPLEMENT['documents'], ids=lambda d: d['id'])
def test_frozen_metadata_supplement_has_no_false_or_retyped_recovery(doc):
    test_recovered_evidence_is_exact_and_every_prior_fact_is_unchanged(doc)


def test_metadata_supplement_reports_unchanged_scanner_omissions():
    found, missing = 0, []
    for doc in SUPPLEMENT['documents']:
        output = extract(doc['pages'], mixed_fields=True)
        ids = {p['record_id'] for p in output['mixed_field_recovery']['recoveries']}
        labels = [span(r['evidence'][0]) for r in output['records'] if r['id'] in ids]
        found += len(ids)
        missing.extend(doc['id'] for e in doc['expected_recoveries'] if e['label'] not in labels)
    assert sum(len(d['expected_recoveries']) for d in SUPPLEMENT['documents']) == 8
    assert found == 4
    assert missing == ['dated_suffix_crlf_spaces', 'dated_suffix_inline_tiempo',
                       'example_then_dated_reset', 'closed_quote_then_dated_reset']
    # None has a session admitted by the unchanged scanner. The evidence-only
    # route cannot invent those reset identities just to match this reference.
    for doc in SUPPLEMENT['documents']:
        if doc['id'] in missing:
            assert matcher._unit_data(doc['pages'], matcher.snapshot_hash(doc['pages']))[0] == []
