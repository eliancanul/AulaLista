"""Bounded synthetic matcher checks; not independent curricular gold."""
import copy
import json
from pathlib import Path

import pytest

from scripts import session_declarations as experiment

FIXTURE = Path(__file__).parent / 'fixtures/interpretation/session_declarations_v1.json'


def extract(pages):
    if isinstance(pages, str):
        pages = [pages]
    return experiment.extract_declarations(pages, source_doc_sha256=experiment.snapshot_hash(pages))


def document(name):
    return next(d for d in json.loads(FIXTURE.read_bytes())['documents'] if d['id'] == name)


def test_all_emitted_evidence_is_literal_and_governance_never_auto_approves():
    for doc in json.loads(FIXTURE.read_bytes())['documents']:
        pages = copy.deepcopy(doc['pages'])
        result = extract(pages)
        assert pages == doc['pages']
        assert result['extraction_sha256'] == experiment.snapshot_hash(pages)
        ids = [r['id'] for r in result['records']]
        assert len(ids) == len(set(ids))
        for record in result['records']:
            refs = list(record['evidence'])
            if record['unit']:
                refs.append(record['unit']['anchor'])
            if record['claim']:
                claim = record['claim']
                assert record['decision'] == 'candidate' and record['reason'] == 'explicit_session'
                assert claim['state'] == 'needs_human_review'
                assert claim['confidence'] is None
                assert claim['subject'] == record['unit']['id']
                value_ref = next(e for e in record['evidence'] if e['role'] == 'value')
                assert claim['page_number'] == value_ref['page_number']
                assert claim['region'] == value_ref['region']
                assert claim['excerpt'] == value_ref['excerpt']
                assert claim['predicate'] in {'contenido_declarado', 'pda_declarado'}
                assert claim['extraction_version'] == experiment.MATCHER_VERSION
                refs.extend(claim['evidence'])
            else:
                assert record['decision'] == 'abstained'
            for ref in refs:
                assert ref['document_sha256'] == result['source_doc_sha256']
                region = ref['region']
                assert region['kind'] == 'text_offsets'
                assert pages[ref['page_number'] - 1][region['start']:region['end']] == ref['excerpt']


def test_repeated_identical_blocks_are_distinct_and_reproducible():
    pages = document('repeated_same_session')['pages']
    output = extract(pages)
    assert output == extract(pages)
    records = output['records']
    assert len(records) == 4 and len({r['id'] for r in records}) == 4
    assert len({r['claim']['subject'] for r in records}) == 1
    assert records[0]['claim']['object_value'] == records[2]['claim']['object_value']
    assert records[0]['claim']['claim_id'] != records[2]['claim']['claim_id']


def test_multiline_crlf_and_unicode_are_not_normalized():
    records = extract(document('crlf_long_labels')['pages'])['records']
    assert len(records) == 2
    assert all('\r\n' in r['claim']['object_value'] for r in records)
    assert '\n' in extract(document('plural_multiline')['pages'])['records'][0]['claim']['object_value']
    unicode_value = extract(document('unicode_literals')['pages'])['records'][0]['claim']['object_value']
    assert '🌳' in unicode_value and '\u00a0' not in unicode_value


def test_project_declarations_are_detected_with_explicit_session_abstention():
    records = extract(document('project_no_inheritance')['pages'])['records']
    assert len(records) == 2
    assert all(r['decision'] == 'abstained' and r['reason'] == 'project_scope' and r['claim'] is None for r in records)
    assert all(r['unit']['kind'] == 'project' for r in records)
    assert all(any(e['role'] == 'value' for e in r['evidence']) for r in records)


def test_declared_negation_is_not_a_blanket_negative_word_detector():
    assert all(r['claim'] for r in extract(document('negation_inside_learning_text')['pages'])['records'])
    assert all(r['reason'] == 'negated' for r in extract(document('negated_declaration')['pages'])['records'])


def test_label_word_inside_affirmative_value_is_not_a_second_declaration():
    record, = extract('SESIÓN 1: Leer\nPDA: Explica la palabra Contenido.\nInicio:\n-Leer.\n')['records']
    assert record['decision'] == 'candidate'
    assert record['claim']['object_value'] == 'Explica la palabra Contenido.'


def test_explicit_cross_page_unit_continuation_keeps_original_anchor():
    records = extract(document('explicit_page_continuation')['pages'])['records']
    assert len(records) == 2
    for record in records:
        assert record['claim'] is not None
        assert record['unit']['anchor']['page_number'] == 1
        assert any(ref['role'] == 'unit_continuation' and ref['page_number'] == 2 for ref in record['evidence'])
        assert next(e for e in record['evidence'] if e['role'] == 'value')['page_number'] == 2


@pytest.mark.parametrize('previous,continuation', [
    ('SESIÓN 1: Observar\nInicio:\n-Observar.\n', 'Continuación de la sesión 2'),
    ('SESIÓN 1: Observar\nInicio:\n-Observar.\nProyecto: Otro\n', 'Continuación de la sesión 1'),
    ('SESIÓN 1: Observar\nInicio:\n-Observar.\nDATOS GENERALES\n', 'Continuación de la sesión 1'),
    ('SESIÓN 1: Observar\nInicio:\n-Observar.\nSESIÓN 1: Otra\nInicio:\n-Leer.\n', 'Continuación de la sesión 1'),
])
def test_continuation_never_crosses_resets_projects_or_ambiguous_identity(previous, continuation):
    result = extract([previous, continuation + '\nPDA: Describe formas.\nInicio:\n-Observar.\n'])
    record, = result['records']
    assert record['unit'] is None and record['reason'] == 'unresolved_scope'
    assert record['claim'] is None


def test_cross_page_value_is_not_partially_promoted_or_joined():
    records = extract(document('cross_page_not_joined')['pages'])['records']
    assert len(records) == 2
    assert records[0]['reason'] == 'uncertain_boundary'
    assert records[1]['reason'] == 'unresolved_scope'
    assert all(r['claim'] is None for r in records)


@pytest.mark.parametrize('tail', ['Formas y\n', 'Formas\n', 'Formas de\n', 'Formas y\nInicio:\n-Observar.\n'])
def test_end_of_window_is_not_evidence_of_complete_value(tail):
    record, = extract('SESIÓN 1: Observar\nContenido: ' + tail)['records']
    assert record['reason'] == 'uncertain_boundary'
    assert record['claim'] is None


@pytest.mark.parametrize('value', ['No será trabajado en esta sesión.', 'No fue seleccionado.',
                                  'No está previsto.', 'No se contempla en esta sesión.',
                                  'No se trabajó en esta sesión.'])
def test_passive_nonadoption_does_not_become_affirmative_declaration(value):
    record, = extract('SESIÓN 1: Observar\nPDA: ' + value + '\nInicio:\n-Observar.\n')['records']
    assert record['decision'] == 'abstained' and record['reason'] == 'negated'
    assert record['claim'] is None


@pytest.mark.parametrize('value', ['Se propone describir formas.', 'Se recomienda describir formas.',
                                  'Opcional: Describe formas.', 'Podría trabajarse la descripción.'])
def test_unadopted_proposals_are_not_affirmative_candidates(value):
    record, = extract('SESIÓN 1: Observar\nPDA: ' + value + '\nInicio:\n-Observar.\n')['records']
    assert record['decision'] == 'abstained'
    assert record['reason'] in {'conditional', 'nonaffirmative'}
    assert record['claim'] is None


@pytest.mark.parametrize('value', ['Ninguno.', 'N/A.', 'No definido.', 'Se omite en esta sesión.',
                                  'Sin especificar.', 'N.A.', 'Ninguna.'])
def test_explicit_absence_placeholders_do_not_become_curricular_values(value):
    record, = extract('SESIÓN 1: Observar\nPDA: ' + value + '\nInicio:\n-Observar.\n')['records']
    assert record['decision'] == 'abstained' and record['reason'] == 'nonaffirmative'
    assert record['claim'] is None


def test_unclosed_source_quote_cannot_reset_at_page_boundary():
    pages = ['Ejemplo citado:\n«\nSESIÓN 1: Leer\n',
             'SESIÓN 2: Observar\nPDA: Describe formas.\nInicio:\n-Observar.\n']
    record, = extract(pages)['records']
    assert record['reason'] == 'quoted' and record['claim'] is None


def test_absence_does_not_invent_abstentions():
    assert extract(document('missing_labels')['pages'])['records'] == []
    assert extract(document('empty_document')['pages'])['records'] == []


def test_source_identity_binds_ids_without_changing_extraction_hash():
    pages = document('simple_pair')['pages']
    a = experiment.extract_declarations(pages, source_doc_sha256='a' * 64)
    b = experiment.extract_declarations(pages, source_doc_sha256='b' * 64)
    assert a['extraction_sha256'] == b['extraction_sha256']
    assert [r['id'] for r in a['records']] != [r['id'] for r in b['records']]


@pytest.mark.parametrize('pages,sha', [([], 'a' * 64), ('page', 'a' * 64), ([True], 'a' * 64), (['text'], 'fake')])
def test_malformed_input_rejected(pages, sha):
    with pytest.raises(ValueError):
        experiment.extract_declarations(pages, source_doc_sha256=sha)


def test_input_and_output_limits_fail_without_silent_truncation(monkeypatch):
    monkeypatch.setattr(experiment, 'MAX_CHARACTERS', 2)
    with pytest.raises(ValueError, match='character limit'):
        extract(['long'])
    monkeypatch.setattr(experiment, 'MAX_CHARACTERS', 10000)
    monkeypatch.setattr(experiment, 'MAX_RECORDS', 1)
    with pytest.raises(ValueError, match='record limit'):
        extract(document('simple_pair')['pages'])
