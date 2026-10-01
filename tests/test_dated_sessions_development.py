"""Narrow dated-header admission; synthetic development examples only."""
import pytest

from curriculum.source_segments import scan_session_segments
from test_project_session_context import dossier_for, source


@pytest.mark.parametrize('header', [
    'Sesión 1 Fecha: Lunes 21 Tiempo: 40 minutos Organización: Equipo',
    'Sesión 1 FECHA: Lunes 21 Tiempo: Jornada.',
    'Sesión 1 Fecha: Lunes 7 Tema de la',
    'SESIÓN 001 Fecha: 21/09/2026',
    'Sesión 1 Fecha: 21 de septiembre',
    'Sesión\t1\tFecha:\tLunes 21',
    'Sesión\u00a01\u00a0Fecha:\u00a0Lunes 21',
])
def test_dated_headers_keep_original_anchor_without_calendar_inference(header):
    page = header + '\nInicio:\nActividad 1: Clasificar fichas.\nCierre: Compartir.\n'
    session, = dossier_for([page]).sessions
    anchor = session.header_anchor
    assert anchor['excerpt'] == header
    assert page[anchor['text_start']:anchor['text_end']] == header
    assert len(session.activities) == 1
    assert session.review == 'pending'
    assert session.title == 'Sesión 1: Sesión 1'


@pytest.mark.parametrize('text', [
    'Sesión 1 Fecha:\nInicio: Observar.',
    'Sesión 1 Fecha: lunes\nInicio: Observar.',
    'Sesión 1 Fecha: 999\nInicio: Observar.',
    'Sesión 0 Fecha: Lunes 21\nInicio: Observar.',
    'Sesión -1 Fecha: Lunes 21\nInicio: Observar.',
    'Sesión 1 del cuento Fecha: Lunes 21\nInicio: Observar.',
    'Sesión 1 Fecha: Lunes 21\nInicio de una historia.',
    'Sesión 1 Fecha: Lunes 21\nTexto citado: «Inicio: Observar.»',
    'Texto citado:\n«Sesión 1 Fecha: Lunes 21\nInicio: Observar.\n»',
    'Sesión\n1 Fecha: Lunes 21\nInicio: Observar.',
])
def test_narratives_incomplete_and_uncorroborated_dates_do_not_create_session(text):
    assert dossier_for([text]).sessions == []


def test_following_session_or_project_cannot_corroborate_previous_dated_mention():
    for boundary in ('SESIÓN 2: Explorar\n', 'Proyecto: Río\n', 'DATOS GENERALES\n'):
        page = 'Sesión 1 Fecha: Lunes 21\nÍndice.\n' + boundary + 'Inicio: Observar.\nActividad 1: Dibujar.\n'
        sessions = dossier_for([page]).sessions
        assert all(s.session_number != 1 for s in sessions)


def test_strong_dated_boundary_prevents_activity_leaking_into_previous_session():
    page = ('SESIÓN 1: Explorar\nInicio: Observar.\nActividad 1: Dibujar hojas.\n'
            'Sesión 2 Fecha: Martes 22\nInicio: Preparar.\nActividad 1: Medir piedras.\n')
    a, b = dossier_for([page]).sessions
    assert [x.description for x in a.activities] == ['Dibujar hojas.']
    assert [x.description for x in b.activities] == ['Medir piedras.']
    _, sha, _ = source([page])
    assert not any(s.unassigned_segments for s in scan_session_segments([page], sha))


def test_existing_standalone_header_admission_is_unchanged():
    session, = dossier_for(['Sesión 1\nFecha: Lunes 21\nInicio: Observar.']).sessions
    assert session.header_anchor['excerpt'] == 'Sesión 1'


def test_dated_footer_with_metadata_and_next_page_activity_label_is_one_session():
    pages = ['Sesión 3 Fecha: Lunes 7\nCampo: Lenguajes\nContenidos/PDA: Describir objetos.',
             'Descripción de actividades:\nInicio:\n-Observar hojas.\nCierre:\n-Compartir dibujos.\n']
    session, = dossier_for(pages).sessions
    assert session.session_number == 3 and session.pages == [1, 2]
    assert [a.description for a in session.activities] == ['Observar hojas.', 'Compartir dibujos.']


@pytest.mark.parametrize('suffix,prefix', [
    ('Índice general.', 'Descripción de actividades:\nInicio:\n-Observar hojas.'),
    ('Campo: Lenguajes\nContenidos/PDA: Describir objetos.', 'Inicio:\n-Observar hojas.'),
    ('Campo: Lenguajes\nContenidos/PDA: Describir objetos.', 'SESIÓN 4: Otra\nDescripción de actividades:\nInicio:\n-Observar hojas.'),
    ('Campo: Lenguajes\nContenidos/PDA: Describir objetos.', 'Proyecto: Otro\nDescripción de actividades:\nInicio:\n-Observar hojas.'),
    ('Campo: Lenguajes\nContenidos/PDA: Describir objetos.', '«\nDescripción de actividades:\nInicio:\n-Observar hojas.\n»'),
])
def test_dated_footer_does_not_borrow_unsupported_next_page_moment(suffix, prefix):
    sessions = dossier_for(['Sesión 3 Fecha: Lunes 7\n' + suffix, prefix]).sessions
    assert all(s.session_number != 3 for s in sessions)


def test_repeated_metadata_case_variants_are_one_cue_not_two():
    pages = ['Sesión 3 Fecha: Lunes 7\nCampo: Lenguajes\nCAMPO: Lenguajes',
             'Descripción de actividades:\nInicio:\n-Observar hojas.\n']
    assert dossier_for(pages).sessions == []


def test_partial_weekday_with_rich_planning_context_does_not_invent_day_number():
    page = ('Sesión 8 Fecha: Martes Tema de la\nsesión: Decisiones.\nTiempo: 60 minutos\n'
            'Campo: Lenguajes\nContenidos/PDA: Describir decisiones.\nDescripción de actividades:\n'
            'Inicio:\n-Comparar opciones.\n')
    session, = dossier_for([page]).sessions
    assert session.session_number == 8
    assert session.header_anchor['excerpt'] == 'Sesión 8 Fecha: Martes Tema de la'
    assert [a.description for a in session.activities] == ['Comparar opciones.']


def test_dated_footer_can_continue_with_phase_purpose_then_moment():
    pages = ['Sesión 2 FECHA: Martes 22 Tiempo: Jornada.',
             'FASE: Explorar.\nPropósito: Observar objetos.\nInicio:\n-Comparar hojas.\n']
    session, = dossier_for(pages).sessions
    assert session.session_number == 2 and session.pages == [1, 2]
    assert [a.description for a in session.activities] == ['Comparar hojas.']


@pytest.mark.parametrize('prefix', [
    'Propósito: Observar objetos.\nInicio:\n-Comparar hojas.\n',
    'FASE: Explorar.\nInicio:\n-Comparar hojas.\n',
    'SESIÓN 9: Otro\nFASE: Explorar.\nPropósito: Observar objetos.\nInicio:\n-Comparar hojas.\n',
    'Proyecto: Otro\nFASE: Explorar.\nPropósito: Observar objetos.\nInicio:\n-Comparar hojas.\n',
    '«FASE: Explorar.\nPropósito: Observar objetos.\nInicio:\n-Comparar hojas.\n»',
])
def test_incomplete_or_foreign_phase_context_cannot_admit_footer(prefix):
    sessions = dossier_for(['Sesión 2 FECHA: Martes 22 Tiempo: Jornada.', prefix]).sessions
    assert all(s.session_number != 2 for s in sessions)
