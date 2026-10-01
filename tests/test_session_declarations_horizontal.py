"""Separate synthetic regressions for v2 horizontal-label boundaries.

These cases do not change either frozen declaration reference or its denominator.
"""
import re

import pytest

from scripts import session_declarations as experiment


VERTICALS = ('\r', '\n', '\r\n', '\v', '\f', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029')
OTHER_VERTICALS = VERTICALS[3:]
HORIZONTALS = (' ', '\t', '\u00a0', '\u1680', '\u2003', '\u202f', '\u205f', '\u3000', ' \t\u00a0')


def extract(line):
    pages = ['SESIÓN 1: Explorar\n' + line + '\nInicio:\n-Observar.\n']
    return experiment.extract_declarations(pages, source_doc_sha256=experiment.snapshot_hash(pages))['records']


@pytest.mark.parametrize('separator', VERTICALS)
@pytest.mark.parametrize('pattern', ('X7{gap}PDA2', 'PDA{gap}2'))
def test_numbered_grammar_never_joins_vertical_separators(separator, pattern):
    assert re.fullmatch(experiment.NUMBERED_PDA, pattern.format(gap=separator), re.I) is None


@pytest.mark.parametrize('separator', OTHER_VERTICALS)
@pytest.mark.parametrize('pattern', ('X7{gap}PDA2:', 'PDA{gap}2:', 'PDA2{gap}:', '{gap}X7 PDA2:'))
def test_numbered_labels_do_not_promote_nonhorizontal_token_colon_or_indent(separator, pattern):
    records = extract(pattern.format(gap=separator) + ' Describe formas.')
    assert records
    assert all(r['decision'] == 'abstained' and r['claim'] is None for r in records)


@pytest.mark.parametrize('separator', VERTICALS)
@pytest.mark.parametrize('pattern', (
    '{gap}Contenidos/PDA: Contenido: Formas.',
    'Contenidos/PDA:{gap}Contenido: Formas.',
    'Contenidos/PDA{gap}: Contenido: Formas.',
    'Contenidos{gap}/PDA: Contenido: Formas.',
    'Contenidos/PDA: Contenido{gap}: Formas.',
))
def test_container_admission_requires_one_physical_line_through_child_label(separator, pattern):
    line = pattern.format(gap=separator)
    mentions = list(experiment.LABEL.finditer(line))
    assert experiment._explicit_container_child(line, mentions, []) is None


@pytest.mark.parametrize('separator', OTHER_VERTICALS)
@pytest.mark.parametrize('pattern', (
    '{gap}Contenidos/PDA: Contenido: Formas.',
    'Contenidos/PDA:{gap}Contenido: Formas.',
    'Contenidos/PDA{gap}: Contenido: Formas.',
    'Contenidos{gap}/PDA: Contenido: Formas.',
    'Contenidos/PDA: Contenido{gap}: Formas.',
))
def test_vertical_container_paths_abstain_in_extraction(separator, pattern):
    records = extract(pattern.format(gap=separator))
    assert records
    assert all(r['decision'] == 'abstained' and r['claim'] is None for r in records)


@pytest.mark.parametrize('gap', HORIZONTALS)
def test_horizontal_numbered_label_preserves_literal_spacing(gap):
    label = f'X7{gap}PDA{gap}2{gap}:'
    record, = extract(gap + label + ' Describe formas.')
    assert record['decision'] == 'candidate'
    assert record['evidence'][0]['excerpt'] == label
    assert record['claim']['object_value'] == 'Describe formas.'


@pytest.mark.parametrize('gap', HORIZONTALS)
@pytest.mark.parametrize('child', ('Contenido:', 'X7 PDA2:'))
def test_horizontal_container_indent_and_gap_preserve_child_evidence(gap, child):
    record, = extract(gap + 'Contenidos/PDA:' + gap + child + ' Formas.')
    assert record['decision'] == 'candidate'
    assert record['evidence'][0]['excerpt'] == child
    assert record['claim']['object_value'] == 'Formas.'


@pytest.mark.parametrize('separator', VERTICALS[:3])
def test_canonical_newline_child_remains_an_independent_declaration(separator):
    # _lines already processes CR/LF. A child on its own line can be a literal
    # declaration, but the display container must not be joined into its label.
    records = extract('Contenidos/PDA:' + separator + 'Contenido: Formas.')
    assert len(records) == 2
    assert records[0]['decision'] == 'abstained'
    assert records[0]['reason'] == 'combined_label'
    assert records[1]['decision'] == 'candidate'
    assert records[1]['evidence'][0]['excerpt'] == 'Contenido:'


def test_numbered_labels_in_activity_bullets_still_abstain():
    # v3 separately admits a formatting marker in pre-moment metadata only.
    records = extract('Inicio:\n-X7 PDA2: Describe formas.')
    assert records
    assert all(r['decision'] == 'abstained' and r['claim'] is None for r in records)
