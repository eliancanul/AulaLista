"""Listed tasks retain physical text and stay within bounded session moments."""
import hashlib
import json
from pathlib import Path

import pytest

from curriculum.activity_spans import listed_activity_spans
from scripts.evaluate_activity_session import evaluate
from test_project_session_context import dossier_for

FIXTURE = Path(__file__).parent / 'fixtures/interpretation/activity_session_bullets_v1.json'


def test_frozen_listed_activity_development_opportunities():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == '79eebb377323b3a060f5243cd9d80fa459e956a774781c1937d16b84d59399b6'
    total = evaluate(json.loads(FIXTURE.read_text()))['total']
    assert total['expected'] == total['correct'] == total['asserted'] == 11
    assert total['extras'] == total['omitted'] == total['incorrect'] == 0


@pytest.mark.parametrize('label', ['Materiales:', 'Recursos', 'Recursos didácticos: Evidencias: Indicadores:', 'Evaluación:', 'Contenidos/PDA:', 'Propósito:', 'Aspectos a evaluar', 'Producto del proyecto:', 'Evidencias de aprendizaje:', 'Adecuaciones curriculares:', 'Anexos:'])
def test_nonactivity_sections_stop_list_even_inside_session(label):
    page = 'SESIÓN 1: Explorar\nInicio:\n-Observar hojas.\n' + label + '\n-Lápices de colores.\nCierre:\n-Compartir observaciones.\n'
    session, = dossier_for([page]).sessions
    assert [a.description for a in session.activities] == ['Observar hojas.', 'Compartir observaciones.']


def test_nested_steps_keep_literal_text_without_inventing_extra_activities():
    text = 'Inicio:\n-Preparar el registro.\n  -Elegir colores.\n  -Trazar tabla.\n-Comparar registros.\n'
    spans = listed_activity_spans(text)
    assert len(spans) == 2
    assert text[spans[0][0]:spans[0][1]] == '-Preparar el registro.\n  -Elegir colores.\n  -Trazar tabla.'
    assert spans[0][2] == 'Preparar el registro.\n  -Elegir colores.\n  -Trazar tabla.'


def test_wrapped_instruction_preserves_full_description_and_literal_excerpt():
    page = 'SESIÓN 1: Explorar\nInicio:\n-Observar las plantas\ndel patio.\nCierre: Compartir.\n'
    activity, = dossier_for([page]).sessions[0].activities
    assert activity.description == 'Observar las plantas\ndel patio.'
    assert activity.evidence[0].excerpt == '-Observar las plantas\ndel patio.'
    assert activity.evidence[0].excerpt in page


@pytest.mark.parametrize('quote', ['«', '“', '"'])
def test_open_quote_does_not_let_later_bullets_become_tasks(quote):
    assert listed_activity_spans('Inicio:\nTexto citado: ' + quote + '\n-No es una instrucción.\n') == []


def test_unlabelled_bullets_are_not_interpreted_as_activities():
    assert listed_activity_spans('-Observar plantas.\n-Compartir registros.\n') == []


def test_wrapped_noun_actividad_and_materiales_are_not_a_new_task_or_section():
    page = ('SESIÓN 1: Explorar\nInicio:\n-Resolver la\nactividad sobre plantas usando los\n'
            'materiales que se encuentran en el aula.\n-Compartir resultados.\n')
    activities = dossier_for([page]).sessions[0].activities
    assert len(activities) == 2
    assert activities[0].description == 'Resolver la\nactividad sobre plantas usando los\nmateriales que se encuentran en el aula.'


def test_continuation_inherits_moment_but_not_materials_or_open_quotes():
    good = ['SESIÓN 1: Explorar\nDesarrollo:\n-Preparar dibujos.\n',
            '-Comparar dibujos.\nCierre:\n-Compartir registros.\n']
    assert [a.description for a in dossier_for(good).sessions[0].activities] == ['Preparar dibujos.', 'Comparar dibujos.', 'Compartir registros.']
    for stop in ('Recursos:\n', 'Texto citado: «\n'):
        bad = ['SESIÓN 1: Explorar\nDesarrollo:\n-Preparar dibujos.\n' + stop,
               '-Material citado.\nCierre:\n-Otra frase.\n']
        activities = dossier_for(bad).sessions[0].activities
        assert not any(a.description == 'Material citado.' for a in activities)


def test_quotes_inside_instruction_can_wrap_without_becoming_new_tasks():
    page = ('SESIÓN 1: Leer\nInicio:\n-Leer el texto «El jardín\n'
            '-de las mariposas» y comentarlo.\n-Comparar lecturas.\n')
    activities = dossier_for([page]).sessions[0].activities
    assert len(activities) == 2
    assert activities[0].description == 'Leer el texto «El jardín\n-de las mariposas» y comentarlo.'


def test_explicit_homework_stays_an_activity_of_the_current_session():
    page = 'SESIÓN 1: Explorar\nCierre:\n-Comparar dibujos.\nTarea:\n-Traer una cartulina.\nRecursos:\n-Lápices.\n'
    activities = dossier_for([page]).sessions[0].activities
    assert [a.description for a in activities] == ['Comparar dibujos.', 'Traer una cartulina.']


def test_display_subheadings_do_not_contaminate_prior_task_or_assign_curricular_field():
    page = ('SESIÓN 1: Explorar\nDesarrollo:\n-Observar plantas.\n'
            'Saberes y Pensamiento Científico – Registramos observaciones\n-Medir tallos.\n'
            'Integración para el producto final\n-Comparar registros.\n')
    activities = dossier_for([page]).sessions[0].activities
    assert [a.description for a in activities] == ['Observar plantas.', 'Medir tallos.', 'Comparar registros.']
    assert all('campo' not in a.to_dict() for a in activities)


def test_wrapped_colon_introduces_nested_steps_not_an_unrelated_section():
    page = ('SESIÓN 1: Explorar\nInicio:\n-En plenaria responder las siguientes\n'
            'preguntas guía:\n  -¿Qué observan?\n  -¿Cómo podemos cuidar las plantas?\n')
    activity, = dossier_for([page]).sessions[0].activities
    assert activity.description == 'En plenaria responder las siguientes\npreguntas guía:\n  -¿Qué observan?\n  -¿Cómo podemos cuidar las plantas?'


def test_wrapped_actividad_number_is_not_a_new_numbered_activity():
    page = 'SESIÓN 1: Explorar\nInicio:\n-Revisar en equipo la\nactividad 1 que realizaron de tarea.\n'
    activity, = dossier_for([page]).sessions[0].activities
    assert activity.description == 'Revisar en equipo la\nactividad 1 que realizaron de tarea.'


def test_one_instruction_can_continue_over_admitted_page_boundary():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Observar las plantas y registrar\n',
             'las características en el anexo 1.\nCierre:\n-Compartir registros.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert len(activities) == 2
    first = activities[0]
    assert first.description == 'Observar las plantas y registrar\nlas características en el anexo 1.'
    assert [e.page_number for e in first.evidence] == [1, 2]
    assert all(e.excerpt in pages[e.page_number - 1] for e in first.evidence)
    assert first.annex_ids and all(first.annex_evidence.values())


def test_completed_instruction_does_not_absorb_explanatory_next_page_paragraph():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Observar las plantas.\n',
             'Una explicación adicional sin instrucción.\nCierre:\n-Compartir registros.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert activities[0].description == 'Observar las plantas.'


def test_wrapped_activity_word_on_next_page_does_not_suppress_following_bullets():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Revisar en equipo la\n',
             'actividad 1 que realizaron de tarea.\n-Comparar registros.\nCierre: Conversar.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert [a.description for a in activities] == ['Revisar en equipo la\nactividad 1 que realizaron de tarea.', 'Comparar registros.']


def test_admitted_continuation_preserves_blank_lines_in_literal_evidence():
    from curriculum.claims import compile_dossier_to_atomic_claims
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Preparar registros.\n',
             '-Observar las plantas\n\ny registrar sus rasgos en el anexo 1.\nCierre:\n-Compartir registros.\n']
    dossier = dossier_for(pages)
    activity = dossier.sessions[0].activities[1]
    assert activity.description == 'Observar las plantas\n\ny registrar sus rasgos en el anexo 1.'
    for claim in compile_dossier_to_atomic_claims(dossier):
        if claim.predicate in {'pertenece_a_sesion', 'requiere_anexo'}:
            assert all(e.excerpt in pages[e.page_number - 1] for e in claim.evidence)


def test_admitted_continuation_keeps_nested_first_line_with_prior_activity():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Responder las siguientes preguntas:\n  -¿Qué observan?\n',
             '  -¿Cómo cuidar las plantas?\nCierre:\n-Compartir respuestas.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert len(activities) == 2
    assert activities[0].description == 'Responder las siguientes preguntas:\n  -¿Qué observan?\n  -¿Cómo cuidar las plantas?'
    assert [e.page_number for e in activities[0].evidence] == [1, 2]
    assert all(e.excerpt in pages[e.page_number - 1] for a in activities for e in a.evidence)


def test_continuation_preserves_crlf_and_ignores_only_exterior_boilerplate():
    pages = ['SESIÓN 1: Explorar\r\nInicio:\r\n-Preparar registros.\r\n',
             'Planeación Didáctica\r\nPágina 2\r\n\r\n-Observar plantas\r\n\r\ny registrar el anexo 1.\r\nCierre:\r\n-Compartir.\r\n']
    activities = dossier_for(pages).sessions[0].activities
    assert len(activities) == 3
    assert activities[1].description == 'Observar plantas\r\n\r\ny registrar el anexo 1.'
    assert all(e.excerpt in pages[e.page_number - 1] for a in activities for e in a.evidence)


def test_url_instruction_is_not_discarded_as_continuation_boilerplate():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Observar hojas.\n',
             '-Consultar https://example.org/plantas y registrar tres ideas.\nCierre:\n-Compartir registros.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert len(activities) == 3
    assert activities[1].description == 'Consultar https://example.org/plantas y registrar tres ideas.'
    assert all(e.excerpt in pages[e.page_number - 1] for a in activities for e in a.evidence)


def test_page_header_words_inside_an_open_instruction_quote_are_literal_content():
    pages = ['SESIÓN 1: Leer\nInicio:\n-Leer el texto «\n',
             'Página 2\nUn jardín abierto» y responder.\nCierre:\n-Comparar.\n']
    activity = dossier_for(pages).sessions[0].activities[0]
    assert activity.description == 'Leer el texto «\nPágina 2\nUn jardín abierto» y responder.'
    assert all(e.excerpt in pages[e.page_number - 1] for e in activity.evidence)


def test_blank_line_inside_unfinished_cross_page_instruction_is_preserved():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Observar las plantas y registrar\n',
             'sus hojas\n\ny raíces en el anexo 1.\nCierre:\n-Compartir.\n']
    activity = dossier_for(pages).sessions[0].activities[0]
    assert activity.description == 'Observar las plantas y registrar\nsus hojas\n\ny raíces en el anexo 1.'
    assert activity.annex_ids
    assert all(e.excerpt in pages[e.page_number - 1] for e in activity.evidence)


def test_cross_page_wrapped_colon_keeps_its_nested_substeps():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Responder las siguientes\n',
             'preguntas guía:\n  -¿Qué observan?\n  -¿Qué pueden medir?\nCierre:\n-Comparar.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert len(activities) == 2
    assert activities[0].description == 'Responder las siguientes\npreguntas guía:\n  -¿Qué observan?\n  -¿Qué pueden medir?'


def test_quoted_tail_label_cannot_cut_an_instruction_continuation():
    pages = ['SESIÓN 1: Leer\nInicio:\n-Leer el texto «\n',
             'Una guía\nAspectos a evaluar\nson variados» y comentarlo.\nCierre:\n-Comparar.\n']
    activity = dossier_for(pages).sessions[0].activities[0]
    assert activity.description == 'Leer el texto «\nUna guía\nAspectos a evaluar\nson variados» y comentarlo.'


def test_complete_continuation_does_not_absorb_a_separate_paragraph():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Observar las plantas y registrar\n',
             'sus hojas.\n\nUna explicación separada.\nCierre:\n-Comparar.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert activities[0].description == 'Observar las plantas y registrar\nsus hojas.'


@pytest.mark.parametrize('indent', ['', ' ', '\t', '  '])
def test_indented_tail_section_cannot_borrow_a_later_moment_to_admit_the_page(indent):
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Observar.\n',
             '-Continuar.\n' + indent + 'Aspectos a evaluar:\n-Lápices.\nCierre:\n-No corresponde.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert [a.description for a in activities] == ['Observar.']


def test_detached_quote_cannot_continue_the_preceding_completed_task():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Preparar dibujos.\n«\n',
             'Texto de ejemplo»\nCierre:\n-Compartir registros.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert [a.description for a in activities] == ['Preparar dibujos.', 'Compartir registros.']


def test_blank_lines_between_continued_nested_steps_preserve_all_substeps():
    pages = ['SESIÓN 1: Explorar\nInicio:\n-Preparar dibujos.\n',
             '  -Subpaso 1.\n\n  -Subpaso 2.\nCierre:\n-Compartir registros.\n']
    activities = dossier_for(pages).sessions[0].activities
    assert activities[0].description == 'Preparar dibujos.\n  -Subpaso 1.\n\n  -Subpaso 2.'
    assert len(activities) == 2
