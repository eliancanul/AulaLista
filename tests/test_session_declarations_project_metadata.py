"""Post-freeze behavior and adversarial tests for literal metadata only."""
import copy
import json
from pathlib import Path
import unicodedata

import pytest

from scripts import session_declarations as matcher
from scripts import evaluate_session_declarations as scorer


FIXTURES = Path(__file__).parent / 'fixtures/interpretation'
REFERENCE = json.loads((FIXTURES / 'session_declarations_project_metadata_v1.json').read_bytes())


def extract(pages):
    return matcher.extract_declarations(pages, source_doc_sha256=matcher.snapshot_hash(pages))


def span(reference):
    return dict(page=reference['page_number'], start=reference['region']['start'],
                end=reference['region']['end'], quote=reference['excerpt'])


def literals(pages):
    return [record for record in extract(pages)['records']
            if any(e['role'] == 'value' for e in record['evidence'])]


def value(record):
    return next(e['excerpt'] for e in record['evidence'] if e['role'] == 'value')


@pytest.mark.parametrize('document', REFERENCE['documents'], ids=lambda d: d['id'])
def test_frozen_literal_opportunities_and_challenges(document):
    pages = copy.deepcopy(document['pages'])
    records = extract(pages)['records']
    assert pages == document['pages']
    assert len(records) == len(document['declarations']) + len(document['challenges'])
    assert len({r['id'] for r in records}) == len(records)
    for expected in document['declarations']:
        record, = [r for r in records if span(r['evidence'][0]) == expected['label']]
        assert (record['kind'], record['decision'], record['reason']) == (
            expected['kind'], expected['expected_decision'], expected['reason'])
        assert span(next(e for e in record['evidence'] if e['role'] == 'value')) == expected['value']
        if expected['unit_id'] is None:
            assert record['unit'] is None
        else:
            unit = next(u for u in document['units'] if u['id'] == expected['unit_id'])
            assert (record['unit']['kind'], span(record['unit']['anchor'])) == (unit['kind'], unit['anchor'])
        assert [e['role'] for e in record['evidence']] == ['label', 'value']
        if record['decision'] == 'candidate':
            assert record['claim']['metadata']['unit_scope_basis'] == 'same_page_explicit'
            assert record['claim']['object_value'] == expected['value']['quote']
            assert record['claim']['state'] == 'needs_human_review'
            assert record['claim']['confidence'] is None
        else:
            assert record['claim'] is None
    for expected in document['challenges']:
        record, = [r for r in records if span(r['evidence'][0]) == expected['anchor']]
        assert record['decision'] == 'abstained' and record['claim'] is None
        assert not any(e['role'] == 'value' for e in record['evidence'])


def test_existing_independent_scorer_separates_all_frozen_denominators():
    report = scorer.evaluate(REFERENCE)
    total = report['total']
    for key, expected in [('literal_declarations', 28), ('known_unit_assignment', 12),
                          ('unresolved_unit_abstentions', 16), ('joint_detection_unit', 28),
                          ('scope_abstentions', 26), ('strict_session_claims', 2)]:
        assert total[key]['expected'] == total[key]['correct'] == expected
    assert total['challenges']['expected'] == total['challenges']['explicit_abstentions'] == 40
    assert total['negative_documents']['expected'] == 27
    assert total['negative_documents']['clean_silence'] == 2
    assert total['negative_documents']['false_candidate_records'] == 0
    assert total['output']['extras'] == total['output']['invalid_records'] == 0


@pytest.mark.parametrize('field', matcher.CANONICAL_CAMPOS)
@pytest.mark.parametrize('prefix', ['', 'Campo: ', 'Campos: ', 'Campo formativo: ', 'Campos formativos: '])
@pytest.mark.parametrize('case', [str.lower, str.upper])
def test_exact_field_names_allow_case_and_horizontal_indentation(field, prefix, case):
    page = '\tDATOS\u00a0GENERALES\n\u2002' + case(prefix + field) + '\t\n-Contenido: Dos marcas.'
    record, = literals([page])
    assert record['unit'] is None and record['claim'] is None
    assert value(record) == 'Dos marcas.'


@pytest.mark.parametrize('label', [
    'Contenido:', 'Contenidos:', 'Contenido curricular:', 'Contenidos curriculares:',
    'PDA:', 'PDAs:', 'PDA 002:', 'Ñ7 PDA1:',
    'Proceso de desarrollo de aprendizaje:', 'Procesos de desarrollo de aprendizajes (PDAs):',
])
def test_existing_typed_families_gain_only_literal_field_context(label):
    record, = literals(['Lenguajes\n-' + label + ' Describe dos marcas.'])
    assert record['evidence'][0]['excerpt'] == label
    assert record['unit'] is None and record['claim'] is None


@pytest.mark.parametrize('code', ['Á1', 'É2', 'Í3', 'Ó4', 'Ú5', 'Ü6', 'Ñ7', 'á1', 'é2', 'í3', 'ó4', 'ú5', 'ü6', 'ñ7', 'ÁÜÑZ1234'])
@pytest.mark.parametrize('form', ['NFC', 'NFD'])
def test_spanish_letters_and_decomposed_pairs_keep_full_raw_label(code, form):
    code = unicodedata.normalize(form, code)
    label = code + '\u00a0PDA\t0002:'
    text = 'Describe una sen\u0303al.'
    page = 'Lenguajes\n' + code + ' Marcas escritas.\n\t-\u2002' + label + ' ' + text
    record, = literals([page])
    assert record['evidence'][0]['excerpt'] == label
    assert value(record) == text
    for evidence in record['evidence']:
        assert page[evidence['region']['start']:evidence['region']['end']] == evidence['excerpt']


@pytest.mark.parametrize('code', [
    'K7', 'İ7', 'ſ7', 'ı7', 'Ω7', 'Ж7', 'ß7', 'Ñ', 'Ñ00000', 'ABCDE7',
    'A\u0300B7', 'Ñ\u03017', 'U\u0308\u03017', 'A\u03417', 'A-7', 'Á\u20287',
    unicodedata.normalize('NFD', 'ÁÜÑZA7'),
])
@pytest.mark.parametrize('prefix', ['', '-'])
def test_malformed_codes_never_gain_a_cropped_or_normalized_positive(code, prefix):
    pages = ['SESIÓN 1: Taller\nLenguajes\n' + prefix + code + ' PDA1: Describe una marca.']
    assert not literals(pages)
    assert all(r['claim'] is None for r in extract(pages)['records'])


@pytest.mark.parametrize('code', ['Ñ2', 'ÁÜÑZ1234', unicodedata.normalize('NFD', 'ÜÑ2')])
def test_unmarked_local_code_extension_preserves_existing_explicit_session_scope(code):
    record, = literals(['SESIÓN 1: Taller\n' + code + ' PDA2: Describe marcas.'])
    assert record['decision'] == 'candidate'
    assert record['claim']['metadata']['unit_scope_basis'] == 'same_page_explicit'
    assert record['evidence'][0]['excerpt'] == code + ' PDA2:'


@pytest.mark.parametrize('stop', [
    '-Leer tarjetas.', 'Actividad 1: Leer tarjetas.', 'Inicio: Leer.', 'Desarrollo:', 'Cierre:',
    'Ejemplo:', 'Propuesta no adoptada:', 'Tema desconocido:', '«Lenguajes»',
    'Contenido | PDA', '•Leer tarjetas.', 'DATOS GENERALES',
])
def test_stop_cannot_be_skipped_by_a_later_field_or_general_heading(stop):
    pages = ['Lenguajes\n-L1 PDA1: Describe una marca.\n' + stop
             + '\nDATOS GENERALES\nSaberes y pensamiento científico\n-S1 PDA1: Compara figuras.']
    records = extract(pages)['records']
    later = [r for r in records if r['evidence'][0]['excerpt'] == 'S1 PDA1:']
    assert later and all(r['claim'] is None and not any(e['role'] == 'value' for e in r['evidence']) for r in later)


@pytest.mark.parametrize('row', [
    'L1 Ejemplo de un mensaje.', 'L1 Propuesta no adoptada.', 'L1 Inicio de la actividad.',
    'L1 Texto | otro texto.', 'L1 «Texto citado».', 'L1 Texto PDA1: Describe marcas.',
    'L1: Representaciones escritas.', 'L1 Representaciones y', 'L1 Representaciones',
])
def test_ambiguous_context_row_cannot_license_a_later_marker(row):
    records = extract(['Lenguajes\n' + row + '\n-L2 PDA2: Compara marcas.'])['records']
    record = next(r for r in records if r['evidence'][0]['excerpt'] == 'L2 PDA2:')
    assert record['claim'] is None
    assert not any(e['role'] == 'value' for e in record['evidence'])


@pytest.mark.parametrize('row', ['L2 Otra representación.', 'Saberes y pensamiento científico',
                                 'Campo: Lenguajes'])
def test_final_context_row_without_corroboration_cannot_crop_the_value(row):
    assert not literals(['Lenguajes\n-PDA: Describe una marca.\n' + row])


@pytest.mark.parametrize('row', ['L2 Otra representación.', 'Saberes y pensamiento científico',
                                 'Campo: Lenguajes'])
def test_switch_requires_already_completed_value_even_with_corroboration(row):
    records = extract(['Lenguajes\n-PDA: Describe una marca mediante\n' + row
                       + '\n-PDA2: Compara figuras.'])['records']
    assert not any(e['role'] == 'value' for r in records for e in r['evidence'])
    assert all(r['claim'] is None for r in records)


@pytest.mark.parametrize('row', ['L2 Otra representación.', 'Saberes y pensamiento científico'])
def test_corroborated_switch_uses_original_full_values(row):
    records = literals(['Lenguajes\n-PDA: Describe una marca.\n' + row
                        + '\n\n-PDA2: Compara figuras.'])
    assert [value(r) for r in records] == ['Describe una marca.', 'Compara figuras.']
    assert all(r['unit'] is None and r['claim'] is None for r in records)


@pytest.mark.parametrize('ending', ['', '\nInicio: Leer tarjetas.'])
@pytest.mark.parametrize('current', [
    'Lenguajes\n-PDA: Describe una marca.',
    'Campo formativo: Lenguajes\nL1 Marcas escritas.\n-L1 PDA1: Describe una marca.',
    'Lenguajes\nL1 Marcas escritas.\n-Ñ7 PDA1: Describe una marca.',
])
def test_new_literal_context_never_becomes_a_previous_page_scaffold(current, ending):
    record, = literals(['SESIÓN 1: Taller', current + ending])
    assert record['unit'] is None and record['claim'] is None
    assert record['reason'] == 'unresolved_scope'
    assert [e['role'] for e in record['evidence']] == ['label', 'value']
    assert not matcher._planning_structure(current, declarations=True)


def test_unicode_code_in_previous_page_prefix_does_not_expand_old_scaffold_grammar():
    record, = literals(['SESIÓN 1: Taller', 'Ñ7 PDA1: Describe una marca.\nInicio: Leer.'])
    assert record['unit'] is None and record['claim'] is None
    assert not matcher._planning_structure('Ñ7 PDA1: Describe una marca.', declarations=True)


@pytest.mark.parametrize('value_text', ['Describe marcas.»', 'Describe marcas.”', 'Describe «marcas”.'])
def test_orphan_or_mismatched_value_quotes_are_uncertain_in_new_context(value_text):
    assert not literals(['Lenguajes\n-PDA: ' + value_text])


@pytest.mark.parametrize('prefix', ['--', '•', '*', '+', '-Leer ', '-\u2028'])
def test_new_field_context_does_not_broaden_marker_grammar(prefix):
    assert not literals(['Lenguajes\n' + prefix + 'Ñ7 PDA1: Describe una marca.'])


@pytest.mark.parametrize('field', [
    'lenguajes para la convivencia', 'Lenguaje', 'Saberes y pensamiento cientifico',
    'Ética, naturaleza y sociedades.', '«Lenguajes»', 'Campoſ: Lenguajes',
    'Campos: Lenguajes; Saberes y pensamiento científico',
])
def test_noncanonical_names_and_aliases_do_not_establish_context(field):
    assert not matcher._field_line(field)
    assert not literals([field + '\nL1 Marcas escritas.\n-L1 PDA1: Describe una marca.'])


@pytest.mark.parametrize('ending', [
    'Ejemplo:\nLenguajes\n-PDA2: Otra marca.',
    '-Leer tarjetas.\nLenguajes\n-PDA2: Otra marca.',
    'Texto libre.\n-PDA2: Otra marca.',
])
def test_context_switch_is_not_corroborated_through_an_intervening_stop(ending):
    assert not literals(['Lenguajes\n-PDA: Describe una marca.\nL2 Otras marcas.\n' + ending])


def test_page_break_never_carries_a_field_block_forward():
    assert not literals(['Lenguajes\nL1 Marcas escritas.', 'L1 Marcas escritas.\n-L1 PDA1: Describe una marca.'])


def test_new_recognized_session_restarts_metadata_after_a_project_activity():
    pages = ['Proyecto: Tarjetas\n\nInicio: Leer tarjetas.\nSESIÓN 2: Taller\n'
             'Lenguajes\n-L1 PDA1: Describe una marca.']
    record, = literals(pages)
    assert record['unit']['kind'] == 'session'
    assert record['unit']['anchor']['excerpt'] == 'SESIÓN 2: Taller'
    assert record['claim']['metadata']['unit_scope_basis'] == 'same_page_explicit'


def test_a_context_only_block_never_invents_a_declaration():
    for field in matcher.CANONICAL_CAMPOS:
        assert extract([field + '\nÑ2 Marcas escritas.\nÁ3 Representaciones.'])['records'] == []


@pytest.mark.parametrize('stop', [
    'Nota auxiliar: Texto distinto.', 'L2 Actividad: Leer tarjetas.',
    'L2 Actividad de lectura.', 'L2 Ejemplo de representación.', 'L2 Descripción abierta mediante',
])
@pytest.mark.parametrize('complete', [False, True])
def test_rejected_labelled_rows_stop_values_and_cannot_license_later_markers(stop, complete):
    first_value = 'Describe figuras.' if complete else 'Describe figuras mediante'
    records = extract(['SESIÓN 1: Taller\nLenguajes\n-PDA: ' + first_value
                       + '\n' + stop + '\n-PDA2: Compara marcas.'])['records']
    first, later = records
    assert first['evidence'][0]['excerpt'] == 'PDA:'
    assert later['evidence'][0]['excerpt'] == 'PDA2:'
    if complete:
        assert value(first) == first_value
        assert first['decision'] == 'candidate'
        assert first['claim']['object_value'] == first_value
        assert first['claim']['metadata']['unit_scope_basis'] == 'same_page_explicit'
    else:
        assert first['decision'] == 'abstained' and first['reason'] == 'uncertain_boundary'
        assert first['claim'] is None
        assert not any(e['role'] == 'value' for e in first['evidence'])
    assert later['decision'] == 'abstained' and later['claim'] is None
    assert not any(e['role'] == 'value' for e in later['evidence'])


@pytest.mark.parametrize('opening,closing', [('«', '»'), ('“', '”'), ('"', '"')])
@pytest.mark.parametrize('layout', ['same_line', 'next_line', 'spanning_lines', 'closing_starts_next_line'])
def test_quoted_colons_are_literal_across_physical_value_lines(opening, closing, layout):
    phrase = opening + 'Aviso: cuidar el agua' + closing
    other = opening + 'Cerrar la llave' + closing
    if layout == 'same_line':
        literal = 'Compara mediante las frases ' + phrase + ' y ' + other + '.'
    elif layout == 'next_line':
        literal = 'Compara mediante\nlas frases ' + phrase + ' y ' + other + '.'
    elif layout == 'spanning_lines':
        literal = ('Compara mediante las frases ' + opening + 'Aviso\nActividad: cuidar el agua'
                   + closing + ' y ' + other + '.')
    else:
        literal = ('Compara mediante las frases ' + opening + 'Aviso: cuidar el agua\n'
                   + closing + ' y ' + other + '.')
    page = 'SESIÓN 1: Taller\nLenguajes\n-PDA: ' + literal + '\n-PDA2: Describe una diferencia.'
    records = extract([page])['records']
    assert [value(r) for r in records] == [literal, 'Describe una diferencia.']
    assert all(r['decision'] == 'candidate' for r in records)
    assert [r['claim']['object_value'] for r in records] == [literal, 'Describe una diferencia.']
    for record in records:
        assert record['claim']['metadata']['unit_scope_basis'] == 'same_page_explicit'
        for evidence in record['evidence']:
            assert page[evidence['region']['start']:evidence['region']['end']] == evidence['excerpt']


@pytest.mark.parametrize('opening,closing', [('«', '»'), ('“', '”'), ('"', '"')])
@pytest.mark.parametrize('stop_position', ['before_quote', 'after_quote', 'after_continued_quote'])
def test_colons_outside_balanced_value_quotes_still_block_later_declarations(opening, closing, stop_position):
    if stop_position == 'before_quote':
        literal = 'Compara mediante\nNota auxiliar: ' + opening + 'Aviso: cuidar el agua' + closing + '.'
    elif stop_position == 'after_quote':
        literal = 'Compara mediante\nlas frases ' + opening + 'Aviso: cuidar el agua' + closing + '. Nota: otro texto.'
    else:
        literal = 'Compara mediante ' + opening + 'Aviso\ncuidar el agua' + closing + '. Nota: otro texto.'
    records = extract(['SESIÓN 1: Taller\nLenguajes\n-PDA: ' + literal
                       + '\n-PDA2: Describe una diferencia.'])['records']
    assert records[0]['reason'] == 'uncertain_boundary'
    assert all(r['claim'] is None for r in records)
    assert not any(e['role'] == 'value' for r in records for e in r['evidence'])


@pytest.mark.parametrize('opening,closing', [('«', '»'), ('“', '”'), ('"', '"')])
def test_quoted_block_after_complete_value_does_not_reopen_metadata(opening, closing):
    page = ('SESIÓN 1: Taller\nLenguajes\n-PDA: Describe figuras.\n'
            + opening + 'Nota: otro texto' + closing + '\nLenguajes\n-PDA2: Describe una diferencia.')
    records = extract([page])['records']
    assert value(records[0]) == 'Describe figuras.'
    assert records[0]['decision'] == 'candidate'
    assert records[-1]['claim'] is None
    assert not any(e['role'] == 'value' for e in records[-1]['evidence'])


@pytest.mark.parametrize('opening,closing', [('«', '»'), ('“', '”'), ('"', '"')])
@pytest.mark.parametrize('complete', [False, True])
def test_rejected_external_code_row_stays_a_stop_when_its_description_is_quoted(opening, closing, complete):
    literal = 'Describe figuras.' if complete else 'Describe figuras mediante'
    page = ('SESIÓN 1: Taller\nLenguajes\n-PDA: ' + literal + '\nL2 '
            + opening + 'Actividad: Leer tarjetas.' + closing + '\n-PDA2: Describe una diferencia.')
    records = extract([page])['records']
    if complete:
        assert value(records[0]) == literal
        assert records[0]['decision'] == 'candidate'
    else:
        assert records[0]['reason'] == 'uncertain_boundary'
        assert records[0]['claim'] is None
        assert not any(e['role'] == 'value' for e in records[0]['evidence'])
    assert records[-1]['claim'] is None
    assert not any(e['role'] == 'value' for e in records[-1]['evidence'])


@pytest.mark.parametrize('opening,closing', [('«', '»'), ('“', '”'), ('"', '"')])
def test_a_separate_quote_led_block_cannot_finish_an_open_value(opening, closing):
    page = ('SESIÓN 1: Taller\nLenguajes\n-PDA: Describe mediante\n'
            + opening + 'Nota: otro texto' + closing + '\n-PDA2: Describe una diferencia.')
    records = extract([page])['records']
    assert records[0]['reason'] == 'uncertain_boundary'
    assert all(r['claim'] is None for r in records)
    assert not any(e['role'] == 'value' for r in records for e in r['evidence'])
