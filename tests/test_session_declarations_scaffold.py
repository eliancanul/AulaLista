"""Matcher regressions against the separately frozen v3 source contract."""
import copy
import json
from pathlib import Path

import pytest

from scripts import session_declarations as matcher


FIXTURES = Path(__file__).parent / 'fixtures/interpretation'
REFERENCE = json.loads((FIXTURES / 'session_declarations_scaffold_v1.json').read_bytes())
SUPPLEMENT = json.loads((FIXTURES / 'session_declarations_scaffold_supplement_v1.json').read_bytes())
REQUIREMENTS = {(r['document_id'], r['declaration_id']): r for r in SUPPLEMENT['candidate_scope_requirements']}


def extract(pages):
    return matcher.extract_declarations(pages, source_doc_sha256=matcher.snapshot_hash(pages))


def ref_span(ref):
    return {'page': ref['page_number'], 'start': ref['region']['start'],
            'end': ref['region']['end'], 'quote': ref['excerpt']}


@pytest.mark.parametrize('document', REFERENCE['documents'], ids=lambda d: d['id'])
def test_frozen_scaffold_opportunities_keep_full_literals_and_decisions(document):
    pages = copy.deepcopy(document['pages'])
    records = extract(pages)['records']
    assert pages == document['pages']
    assert len(records) == len(document['declarations']) + len(document['challenges'])
    assert len({r['id'] for r in records}) == len(records)
    for expected in document['declarations']:
        record, = [r for r in records if ref_span(r['evidence'][0]) == expected['label']]
        assert record['decision'] == expected['expected_decision']
        assert record['reason'] == expected['reason']
        assert record['kind'] == expected['kind']
        assert ref_span(next(e for e in record['evidence'] if e['role'] == 'value')) == expected['value']
        if expected['unit_id'] is None:
            assert record['unit'] is None
        else:
            unit = next(u for u in document['units'] if u['id'] == expected['unit_id'])
            assert ref_span(record['unit']['anchor']) == unit['anchor']
            assert record['unit']['kind'] == unit['kind']
        if record['decision'] == 'candidate':
            requirement = REQUIREMENTS[document['id'], expected['id']]
            claim = record['claim']
            assert claim['metadata']['unit_scope_basis'] == requirement['unit_scope_basis']
            assert claim['state'] == 'needs_human_review' and claim['confidence'] is None
            assert claim['object_value'] == expected['value']['quote']
            assert claim['subject'] == record['unit']['id']
            proof_refs = [e for e in record['evidence'] if e['role'] in {
                'unit_continuation', 'unit_scaffold_tail', 'unit_scaffold_prefix'}]
            assert [{'role': e['role'], **ref_span(e)} for e in proof_refs] == requirement['proofs']
            assert [e for e in claim['evidence'] if e['role'] in {
                'unit_continuation', 'unit_scaffold_tail', 'unit_scaffold_prefix'}] == proof_refs
        else:
            assert record['claim'] is None
    for expected in document['challenges']:
        record, = [r for r in records if ref_span(r['evidence'][0]) == expected['anchor']]
        assert record['decision'] == 'abstained' and record['claim'] is None


@pytest.mark.parametrize('document', SUPPLEMENT['additional_reference']['documents'], ids=lambda d: d['id'])
def test_five_supplemental_vetoes_preserve_exact_pda_without_unit_claim(document):
    expected, = document['declarations']
    record, = extract(document['pages'])['records']
    assert record['decision'] == 'abstained' and record['reason'] == 'unresolved_scope'
    assert record['unit'] is None and record['claim'] is None
    assert ref_span(record['evidence'][0]) == expected['label']
    assert ref_span(record['evidence'][1]) == expected['value']
    assert [e['role'] for e in record['evidence']] == ['label', 'value']


@pytest.mark.parametrize('prefix,ending', [
    ('', ''),
    ('Desarrollo:\n', 'Inicio:\n-Observar.\n'),
    ('Cierre:\n', 'Inicio:\n-Observar.\n'),
    ('Descripción de actividades:\n', 'Inicio:\n-Observar.\n'),
    ('Fecha:\n', 'Inicio:\n-Observar.\n'),
    ('Tema de la sesión: Tarjetas de\n', 'Inicio:\n-Observar.\n'),
    ('-Mirar las tarjetas.\n', 'Inicio:\n-Observar.\n'),
    ('DATOS GENERALES\n', 'Inicio:\n-Observar.\n'),
])
def test_scaffold_requires_complete_structure_and_inicio_as_first_current_moment(prefix, ending):
    pages = ['SESIÓN 1: Explorar\nFecha: 2026-01-20\n', prefix + 'PDA: Describe formas.\n' + ending]
    record, = extract(pages)['records']
    assert record['decision'] == 'abstained' and record['reason'] == 'unresolved_scope'
    assert record['unit'] is None and record['claim'] is None


@pytest.mark.parametrize('tail', [
    'Fecha:\n', 'Tema de la sesión: Tarjetas de\n', 'Inicio:\n',
    '-Observar las tarjetas.\n', 'Organización: «Parejas\n',
    'DATOS GENERALES\n', 'Proyecto: Otro\n', 'SESIÓN 2: Comparar\n',
])
def test_scaffold_never_borrows_past_incomplete_activity_quote_or_scope_cuts(tail):
    pages = ['SESIÓN 1: Explorar\n' + tail, 'PDA: Describe formas.\nInicio:\n-Observar.\n']
    records = extract(pages)['records']
    assert records and all(r['claim'] is None for r in records)


def test_product_segment_admission_is_a_prerequisite_not_just_source_proximity(monkeypatch):
    real_scan = matcher.scan_session_segments

    def without_continuation(pages, sha):
        segments = real_scan(pages, sha)
        for segment in segments:
            segment.page_segments = segment.page_segments[:1]
        return segments

    monkeypatch.setattr(matcher, 'scan_session_segments', without_continuation)
    document = next(d for d in REFERENCE['documents'] if d['id'] == 'scaffold_empty_tail')
    records = extract(document['pages'])['records']
    assert len(records) == 2
    assert all(r['reason'] == 'unresolved_scope' and r['claim'] is None for r in records)
    assert all(any(e['role'] == 'value' for e in r['evidence']) for r in records)


@pytest.mark.parametrize('prefix', ['--', '•', '*', '1. ', '-Leer ', '\v-', '-\u2028'])
def test_only_one_horizontal_hyphen_marker_can_introduce_metadata(prefix):
    pages = ['SESIÓN 1: Explorar\n' + prefix + 'X7 PDA2: Describe formas.\nInicio:\n-Observar.\n']
    records = extract(pages)['records']
    assert records and all(r['claim'] is None for r in records)


def test_same_page_marker_does_not_reset_after_an_example_or_unknown_heading():
    for prefix in ['Ejemplo:\n', 'Nota del ejemplo:\n', 'Leer el siguiente rótulo.\n']:
        pages = ['SESIÓN 1: Explorar\n' + prefix + '-PDA: Describe formas.\nInicio:\n-Observar.\n']
        record, = extract(pages)['records']
        assert record['decision'] == 'abstained' and record['claim'] is None


@pytest.mark.parametrize('heading', ['Ejemplo: tarjetas de colores.', 'MATERIALES'])
def test_unknown_heading_cannot_be_recast_as_a_wrapped_scaffold_value(heading):
    pages = ['SESIÓN 1: Explorar\n',
             'PDA: Describe formas\n' + heading + '\nInicio:\n-Observar.\n']
    record, = extract(pages)['records']
    assert record['claim'] is None and record['unit'] is None
