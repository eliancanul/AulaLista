"""Separate post-534 synthetic safety regressions; frozen references unchanged."""
import pytest

from scripts import session_declarations as matcher


def records(pages):
    return matcher.extract_declarations(pages, source_doc_sha256=matcher.snapshot_hash(pages))['records']


@pytest.mark.parametrize('prefix', ['-', '  - ', '\t- '])
@pytest.mark.parametrize('separator', [' ', '\t'])
@pytest.mark.parametrize('row', [
    'Contenido: Formas.{gap}PDA: Describe formas.',
    'X7 PDA2: Describe formas.{gap}Contenido: Formas.',
    'PDA: Describe formas.{gap}PDA: Compara formas.',
])
def test_format_marker_cannot_hide_multiple_typed_fields_on_one_row(prefix, separator, row):
    result = records(['SESIÓN 1: Explorar\n' + prefix + row.format(gap=separator)
                      + '\nInicio:\n-Observar.\n'])
    assert len(result) == 2
    assert all(r['decision'] == 'abstained' and r['reason'] == 'table_ambiguous'
               and r['claim'] is None for r in result)


@pytest.mark.parametrize('location', ['tail', 'prefix'])
@pytest.mark.parametrize('value', ['Parejas»', 'Parejas”', '«Parejas”', '“Parejas»'])
def test_orphan_or_mismatched_quote_closers_block_structural_scope(location, value):
    prior = 'SESIÓN 1: Explorar\n'
    current = 'PDA: Describe formas.\nInicio:\n-Observar.\n'
    metadata = 'Organización: ' + value + '\n'
    if location == 'tail':
        prior += metadata
    else:
        current = metadata + current
    result = records([prior, current])
    assert result and all(r['claim'] is None and r['unit'] is None for r in result)
    if value in ('Parejas»', 'Parejas”'):
        assert any(e['role'] == 'value' and e['excerpt'] == 'Describe formas.'
                   for r in result for e in r['evidence'])


@pytest.mark.parametrize('value', ['"Parejas"', '«Parejas»', '“Parejas”'])
def test_balanced_quotes_in_planning_metadata_remain_supported(value):
    result = records(['SESIÓN 1: Explorar\nOrganización: ' + value + '\n',
                      'PDA: Describe formas.\nInicio:\n-Observar.\n'])
    record, = result
    assert record['claim']['metadata']['unit_scope_basis'] == 'structural_scaffold_proposal'


@pytest.mark.parametrize('location', ['header', 'tail_metadata', 'prefix_metadata'])
@pytest.mark.parametrize('cut', [
    'Inicio:\t-Observar tarjetas.', 'Desarrollo: Observar tarjetas.',
    'Cierre: Compartir tarjetas.', 'Proyecto: Otro', 'SESIÓN 2: Otra', 'DATOS GENERALES',
    'Inicio\u00a0: Observar.', 'SESIÓN2: Otra', 'DATOS\u00a0GENERALES',
])
def test_inline_structural_cues_cannot_hide_in_session_header_or_metadata(location, cut):
    prior = 'SESIÓN 1: Formas\n'
    current = 'PDA: Describe formas.\nInicio:\n-Observar.\n'
    if location == 'header':
        prior = prior.rstrip() + '\t' + cut + '\n'
    elif location == 'tail_metadata':
        prior += 'Fecha: 2026-01-20\t' + cut + '\n'
    else:
        current = 'Fecha: 2026-01-20\t' + cut + '\n' + current
    result = records([prior, current])
    record, = result
    assert record['claim'] is None and record['decision'] == 'abstained'
    if location == 'prefix_metadata' and cut == 'Proyecto: Otro':
        # Existing same-page project detection still reports its own explicit
        # unit; it must not inherit the previous session or emit a session claim.
        assert record['unit']['kind'] == 'project' and record['reason'] == 'project_scope'
    else:
        assert record['unit'] is None and record['reason'] == 'unresolved_scope'
    assert any(e['role'] == 'value' and e['excerpt'] == 'Describe formas.' for e in record['evidence'])


@pytest.mark.parametrize('bullet', ['-', '*', '+', '•', '◦', '1.', '1)', '12)'])
@pytest.mark.parametrize('gap', ['', ' '])
def test_activity_bullet_shapes_do_not_become_wrapped_scaffold_content(bullet, gap):
    result = records(['SESIÓN 1: Formas\n',
                      'Contenido: Formas\n' + bullet + gap + 'Observar tarjetas.\n'
                      'PDA: Describe formas.\nInicio:\n-Compartir.\n'])
    assert len(result) == 2
    assert all(r['claim'] is None and r['unit'] is None for r in result)
    pda = next(r for r in result if r['kind'] == 'pda')
    assert any(e['role'] == 'value' and e['excerpt'] == 'Describe formas.' for e in pda['evidence'])


@pytest.mark.parametrize('indent', ['\u00a0', '\u1680', '\u2000', '\u202f', '\u205f', '\u3000'])
@pytest.mark.parametrize('bullet', ['-', '•'])
def test_unicode_horizontal_indent_cannot_disguise_activity_bullets(indent, bullet):
    result = records(['SESIÓN 1: Formas\n',
                      'Contenido: Formas\n' + indent + bullet + 'Observar tarjetas.\n'
                      'PDA: Describe formas.\nInicio:\n'])
    assert result and all(r['claim'] is None and r['unit'] is None for r in result)


@pytest.mark.parametrize('cut', ['Inicio: -Observar tarjetas.', 'Desarrollo: Comparar.',
                                 'Cierre: Compartir.', 'Proyecto: Otro', 'SESIÓN 2: Otra', 'DATOS GENERALES'])
def test_inline_scope_cuts_inside_typed_values_veto_the_structural_route(cut):
    result = records(['SESIÓN 1: Formas\n',
                      'PDA: Describe formas. ' + cut + '\nInicio:\n-Compartir.\n'])
    assert result and all(r['claim'] is None and r['unit'] is None for r in result)


def test_open_quote_from_earlier_page_cannot_enter_a_structural_scaffold():
    result = records(['Ejemplo citado:\n«\n', 'SESIÓN 1: Formas\n',
                      'PDA: Describe formas.\nInicio:\n'])
    record, = result
    assert record['reason'] == 'quoted' and record['claim'] is None and record['unit'] is None


def test_earlier_quote_closed_before_anchor_does_not_block_a_new_scaffold():
    result = records(['Ejemplo cerrado: «Una frase».\n', 'SESIÓN 1: Formas\n',
                      'PDA: Describe formas.\nInicio:\n'])
    record, = result
    assert record['claim']['metadata']['unit_scope_basis'] == 'structural_scaffold_proposal'


@pytest.mark.parametrize('location', ['header', 'tail_metadata', 'prefix_activity'])
def test_unit_separator_is_an_unsupported_control_not_horizontal_indentation(location):
    prior, current = 'SESIÓN 1: Formas\n', 'PDA: Describe formas.\nInicio:\n'
    if location == 'header':
        prior = 'SESIÓN 1: Formas\x1f\n'
    elif location == 'tail_metadata':
        prior += 'Organización: Parejas\x1f\n'
    else:
        current = 'Contenido: Formas\n\x1f-Observar tarjetas.\n' + current
    assert not matcher.HORIZONTAL_ONLY.fullmatch('\x1f')
    result = records([prior, current])
    assert result and all(r['claim'] is None and r['unit'] is None for r in result)
