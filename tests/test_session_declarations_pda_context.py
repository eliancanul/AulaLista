"""Behavior, preservation and adversaries against a frozen source-first stratum."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import session_declarations as matcher
from scripts import evaluate_session_declarations as scorer
from scripts.anchor_scope_audit import ScopeAuditConfig, audit_scopes
from test_anchor_scope_audit import Stub


REFERENCE = json.loads((Path(__file__).parent / 'fixtures/interpretation/'
                        'session_declarations_pda_context_v1.json').read_bytes())
MARKED = json.loads((Path(__file__).parent / 'fixtures/interpretation/'
                     'session_declarations_pda_context_marked_v1.json').read_bytes())


def extract(pages, **options):
    return matcher.extract_declarations(pages, source_doc_sha256=matcher.snapshot_hash(pages), **options)


def span(ref):
    return {'page': ref['page_number'], 'start': ref['region']['start'],
            'end': ref['region']['end'], 'quote': ref['excerpt']}


@pytest.mark.parametrize('document', REFERENCE['documents'] + MARKED['documents'], ids=lambda d: d['id'])
def test_only_source_authored_missing_pdas_change_and_every_other_record_is_immutable(document):
    pages = copy.deepcopy(document['pages'])
    old = extract(pages)
    assert old == extract(pages, pda_context=False)
    output = extract(pages, pda_context=True)
    proofs = {p['record_id']: p for p in output['pda_context']['recoveries']}
    assert pages == document['pages']
    assert [r['id'] for r in output['records']] == [r['id'] for r in old['records']]
    for previous, record in zip(old['records'], output['records']):
        if record['id'] not in proofs:
            assert record == previous
            continue
        label, value = record['evidence']
        expected, = [d for d in document['declarations'] if d['label'] == span(label)]
        assert span(value) == expected['value']
        assert (previous['kind'], previous['reason'], previous['claim']) == ('pda', 'label_mention', None)
        assert not any(e['role'] == 'value' for e in previous['evidence'])
        assert (record['kind'], record['reason'], record['unit'], record['claim']) == ('pda', 'unresolved_scope', None, None)
        proof = proofs[record['id']]
        assert proof['label_utf8_sha256'] == hashlib.sha256(label['excerpt'].encode()).hexdigest()
        assert proof['value_utf8_sha256'] == hashlib.sha256(value['excerpt'].encode()).hexdigest()
        for ref in [label, value, proof['descriptor'], proof['field'], proof['boundary']]:
            if ref is not None:
                page = pages[ref['page_number'] - 1]
                assert page[ref['region']['start']:ref['region']['end']] == ref['excerpt']
                assert ref['document_sha256'] == output['source_doc_sha256']
        assert proof['descriptor']['region']['end'] <= label['region']['start']
        assert proof['boundary'] is None or value['region']['end'] <= proof['boundary']['region']['start']
    assert sum(r['claim'] is not None for r in output['records']) == sum(r['claim'] is not None for r in old['records'])


def test_full_frozen_stratum_reports_inherited_gaps_separately_from_recovery_safety():
    old = scorer.evaluate(REFERENCE)
    new = scorer.evaluate(REFERENCE, predictor=lambda d: extract(d['pages'], pda_context=True))
    # Prior unmarked literals/claims and prior uncertainty remain unchanged.
    # The independent reference includes unsupported multi-sentence wrapping;
    # its authoring does not license widening the immutable-legacy-value rule.
    assert new['total']['literal_declarations']['expected'] == 64
    assert old['total']['literal_declarations']['correct'] == 46
    assert new['total']['literal_declarations']['correct'] == 49
    assert new['total']['literal_declarations']['incorrect'] == 15
    assert new['total']['literal_declarations']['extras'] == old['total']['literal_declarations']['extras']
    assert new['total']['challenges']['expected'] == 104
    assert new['total']['output']['invalid_records'] == old['total']['output']['invalid_records']


@pytest.mark.parametrize('flag', [None, 0, 1, 'true', [], {}])
def test_opt_in_requires_a_real_boolean(flag):
    with pytest.raises(ValueError, match='PDA context'):
        extract(['Lenguajes'], pda_context=flag)


BLOCK = 'Lenguajes\nL1. Formas de las marcas.\n-L1 PDA1: Describe una marca.\n'


def test_context_only_never_creates_a_content_or_unit_even_with_multiple_blocks():
    pages = [BLOCK + 'Saberes y P.\nCientífico\nN2. Organización de una colección:\n'
             'formas y tamaños.\n-N2 PDA1: Clasifica figuras.\nN3. Comparación de medidas.\n'
             '-X7 PDA2: Compara medidas.\nÉtica, N. y\nSociedades\nE8. Cuidado del lugar.\n'
             '-Z9 PDA4: Explica cuidados.\nInstrumentos de evaluación:\n']
    result = extract(pages, pda_context=True)
    assert [r['evidence'][1]['excerpt'] for r in result['records']] == [
        'Describe una marca.', 'Clasifica figuras.', 'Compara medidas.', 'Explica cuidados.']
    assert len(result['pda_context']['recoveries']) == 4
    assert all(r['kind'] == 'pda' and r['unit'] is r['claim'] is None for r in result['records'])


@pytest.mark.parametrize('unsafe', [
    'Inicio: Leer tarjetas.', 'Actividad 2: Leer tarjetas.', 'Ejemplo:', 'Propuesta no adoptada:',
    'Notas desconocidas:', 'Este párrafo no es un encabezado.', '«Texto citado»', 'Texto | columna',
])
def test_a_field_or_descriptor_cannot_erase_an_unsafe_page_prefix(unsafe):
    output = extract([unsafe + '\n\nDATOS GENERALES\n' + BLOCK], pda_context=True)
    assert output['pda_context']['recoveries'] == []


@pytest.mark.parametrize('separator', ['\x00', '\x0b', '\x0c', '\x1f', '\x7f', '\x85', '\u2028', '\u2029'])
@pytest.mark.parametrize('position', ['field', 'descriptor', 'value'])
def test_physical_control_and_vertical_boundaries_never_become_whitespace(separator, position):
    values = {'field': BLOCK.replace('Lenguajes', 'Lenguajes' + separator),
              'descriptor': BLOCK.replace('L1.', 'L1.' + separator),
              'value': BLOCK.replace('una marca.', 'una' + separator + ' marca.')}
    assert extract([values[position]], pda_context=True)['pda_context']['recoveries'] == []


def test_preexisting_ambiguous_value_is_not_cropped_or_used_to_resume_recovery():
    page = BLOCK.replace('Describe una marca.', 'Describe una marca mediante') + 'X2. Otras formas.\n-X2 PDA2: Compara figuras.\n'
    old = extract([page])
    output = extract([page], pda_context=True)
    assert output['records'] == old['records']
    assert output['pda_context']['recoveries'] == []


def test_new_scope_replay_requires_matching_explicit_pda_config():
    provider = Stub(fail=True)
    result = extract([BLOCK], pda_context=True, scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True))
    assert result['scope_audit']['status'] == 'invalid'
    assert result['scope_audit']['errors'] == ['pda_context_config_mismatch']
    assert result['scope_audit']['provider_attempts'] == provider.calls == 0
    direct = audit_scopes(pages=[BLOCK], declarations=extract([BLOCK], pda_context=True),
                          config=ScopeAuditConfig('SYNTHETIC', provider, True))
    assert direct['provider_attempts'] == provider.calls == 0


def test_proof_hashes_keep_the_supplied_source_binding_not_a_rehashed_document():
    result = matcher.extract_declarations([BLOCK], source_doc_sha256='a' * 64, pda_context=True)
    proof, = result['pda_context']['recoveries']
    assert proof['descriptor']['document_sha256'] == proof['field']['document_sha256'] == 'a' * 64


def test_literal_list_option_composes_without_modifying_its_evidence_or_proof():
    pages = [BLOCK, 'DATOS GENERALES\nContenido local:\n- Formas azules.\n- Marcas rojas.\nRecursos:\n']
    old = extract(pages, literal_recovery=True)
    new = extract(pages, literal_recovery=True, pda_context=True)
    assert old['literal_recovery'] == new['literal_recovery']
    old_ids = {r['id']: r for r in old['records']}
    for r in new['records']:
        if r['kind'] == 'contenido':
            assert r == old_ids[r['id']]


def test_independent_marked_stratum_recovers_sixty_without_new_unsafe_values():
    old = scorer.evaluate(MARKED)
    output = {d['id']: extract(d['pages'], pda_context=True) for d in MARKED['documents']}
    new = scorer.evaluate(MARKED, predictor=lambda d: output[d['id']])
    assert old['total']['literal_declarations']['correct'] == 0
    assert new['total']['literal_declarations']['correct'] == 60
    assert new['total']['literal_declarations']['expected'] == 64
    assert sum(len(r['pda_context']['recoveries']) for r in output.values()) == 60
    # Four conservative gaps remain: multi-sentence wrapping, an unrecognized
    # project reset, and two cases behind a still-ambiguous prior Contenido.
    # Five preexisting false literal assertions are preserved, never hidden.
    assert new['total']['literal_declarations']['emitted_typed_values'] == 65
    assert old['total']['literal_declarations']['emitted_typed_values'] == 5
    assert new['total']['literal_declarations']['extras'] == 0


def test_cli_explicit_opt_in_and_exclusive_output(tmp_path):
    source = tmp_path / 'source.json'
    destination = tmp_path / 'output.json'
    source.write_text(json.dumps({'pages': [BLOCK], 'source_doc_sha256': 'a' * 64}))
    command = [sys.executable, 'scripts/session_declarations.py', str(source),
               '--output', str(destination), '--pda-context']
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    first = destination.read_bytes()
    assert len(json.loads(first)['pda_context']['recoveries']) == 1
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert destination.read_bytes() == first


@pytest.mark.parametrize('value', [
    'Ejemplo: Describe una señal.', 'Por ejemplo, describe una señal.',
    'Nunca se trabajará este contenido.', 'No se trabajará esta señal.',
    'Sujeto a confirmar una señal.', '«Describe una señal».', '"Describe una señal."',
])
def test_source_only_value_cannot_promote_example_nonadoption_or_quote_led_text(value):
    result = extract([BLOCK.replace('Describe una marca.', value)], pda_context=True)
    assert result['pda_context']['recoveries'] == []


@pytest.mark.parametrize('control', ['\x00', '\v', '\f', '\x1f', '\x7f', '\x85', '\u2028', '\u2029'])
@pytest.mark.parametrize('edge', [0, 1, 2, 3])
def test_control_only_rows_cannot_disappear_as_blank_lines(control, edge):
    rows = BLOCK.splitlines(keepends=True)
    rows.insert(edge, '\t' + control + '\t\n')
    result = extract([''.join(rows)], pda_context=True)
    assert result['pda_context']['recoveries'] == []


@pytest.mark.parametrize('quote', ["'", '‘', '“', '«', '"'])
def test_open_source_quotes_remain_unsafe_across_pages_and_inside_values(quote):
    assert extract([quote + 'Texto citado\n', BLOCK], pda_context=True)['pda_context']['recoveries'] == []
    assert extract([BLOCK.replace('una marca.', quote + 'una marca.')], pda_context=True)['pda_context']['recoveries'] == []


@pytest.mark.parametrize('descriptor', [
    'Formas de las marcas: No se trabajará.', 'Formas de las marcas. Nunca se aplicará.',
    'Formas de las marcas; Ejemplo: Un símbolo.', 'Formas de las marcas: Se propone comparar.',
])
def test_descriptor_nonadoption_cannot_hide_after_inline_context(descriptor):
    assert extract([BLOCK.replace('Formas de las marcas.', descriptor)], pda_context=True)['pda_context']['recoveries'] == []


@pytest.mark.parametrize('value', ['Actividad: Describe una marca.', 'Inicio: Describe una marca.',
                                   'Desarrollo: Describe una marca.', 'Cierre: Describe una marca.'])
def test_activity_value_cannot_be_recovered(value):
    assert extract([BLOCK.replace('Describe una marca.', value)], pda_context=True)['pda_context']['recoveries'] == []


def test_same_page_new_unit_has_real_source_boundary_not_page_end():
    pages = [BLOCK + 'Sesión 2: Otra sesión\nLenguajes\nX2. Otros signos.\n-X2 PDA1: Explica signos.\n']
    result = extract(pages, pda_context=True)
    first = result['pda_context']['recoveries'][0]
    assert first['boundary_kind'] == 'source_row'
    assert first['boundary']['excerpt'] == 'Sesión 2: Otra sesión'
    ref = first['boundary']
    assert pages[0][ref['region']['start']:ref['region']['end']] == ref['excerpt']


@pytest.mark.parametrize('description', [
    'Identificación de\nX2. Otras señales.',
    'Identificación de\nSaberes y Pensamiento Científico\nmarcas.',
    'Identificación de\nÉtica, N. y Sociedades\nmarcas.',
    'Señales. Sesión 9: Ordenar.', 'Señales. DATOS GENERALES.',
])
def test_nested_descriptor_field_and_inline_reset_are_not_wrapping(description):
    page = BLOCK.replace('Formas de las marcas.', description)
    assert extract([page], pda_context=True)['pda_context']['recoveries'] == []


def test_block_quote_context_does_not_reset_on_a_new_page():
    assert extract(['> Cita de la planeación\n', BLOCK], pda_context=True)['pda_context']['recoveries'] == []


@pytest.mark.parametrize('separator', [':', ';', ',', '.', ': ', '; ', ', ', ' (', ' - ', ' '])
def test_descriptor_nonadoption_is_not_dependent_on_punctuation_spacing(separator):
    description = 'Señales' + separator + 'No se trabajará.'
    assert extract([BLOCK.replace('Formas de las marcas.', description)], pda_context=True)['pda_context']['recoveries'] == []


@pytest.mark.parametrize('tail', [
    '. No se trabajará.', '. Propuesta no adoptada.', ':No se trabajará.',
    ';Nunca se aplicará.', ', No se trabajará.', '. Ejemplo: Una señal.',
])
def test_later_explicit_nonadoption_or_example_cannot_become_an_affirmative_value(tail):
    value = 'Describe una señal' + tail
    assert extract([BLOCK.replace('Describe una marca.', value)], pda_context=True)['pda_context']['recoveries'] == []
