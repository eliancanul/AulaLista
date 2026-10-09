"""Small contrast guards for existing rules; not an expanded PDF benchmark."""
import pytest
from curriculum.source_interpreter import CurriculumSourceInterpreter as I
from curriculum.source_segments import is_structural_barrier

@pytest.mark.parametrize('tail',[
    'Rúbrica de evaluación\nCriterios de evaluación\nCierre: Revisar una tabla.',
    'Lista de cotejo\nCierre: Marcar casillas.',
    'Evaluación: Lista de cotejo\nCierre: Marcar casillas.',
    'Cierre: Concluir el proyecto.\nRúbrica de evaluación\nNivel satisfactorio',
    'Cierre: Una actividad.\nProyecto: Otro proyecto\nEvaluación: Lista de cotejo',
    'ANEXO 12\nCierre: Texto impreso en la lámina.',
])
def test_independent_rubric_new_project_and_annex_still_stop(tail):
    from curriculum import source_segments
    assert source_segments.is_structural_barrier(tail)

@pytest.mark.parametrize('label',['Actividad 1: Dibujar una hoja.','Actividad A: Dibujar una hoja.','Actividad: Dibujar una hoja.','Actividad1: Dibujar una hoja.'])
def test_existing_singular_activity_forms_remain_detected(label):
    found=I._detect_activities_in_session('p1_s3',label,[1],'synthetic',[],[(1,label)])
    assert len(found)==1
    assert found[0].description.endswith('Dibujar una hoja.')

@pytest.mark.parametrize('tail',[
    ['Rúbrica de evaluación\nCriterios de evaluación\nCierre: Revisar una tabla.'],
    ['Texto institucional sin momento.','Desarrollo: Texto de una página distante.'],
    ['Proyecto: Otro proyecto\nInicio: Texto de otro bloque.'],
])
def test_existing_continuation_does_not_jump_barriers(tail):
    d=I._detect_sessions(['Proyecto: Semillas\nSESIÓN 6\nInicio: Preparar macetas.',*tail],'synthetic',[],{})
    assert len(d)==1 and d[0].pages==[1]


def test_inline_assessment_keeps_next_page_activity_and_missing_annex():
    pages = [
        "Proyecto: Semillas\nSESIÓN 11: Relato\nInicio: Escuchar.\nActividad 1: Dibujar lo observado.",
        "Desarrollo: Preparar el relato.\nActividad 2: Revisar con el anexo 12.\nCierre: Compartir.\nEvaluación: Lista de cotejo para el relato.",
    ]
    sessions = I._detect_sessions(pages, "synthetic", [], {})
    assert len(sessions) == 1
    session = sessions[0]
    assert session.pages == [1, 2] and session.continues_on == [2]
    assert len(session.activities) == 2
    assert session.activities[1].description == "Revisar con el anexo 12."
    assert session.activities[1].evidence[0].page_number == 2
    assert session.fields["evaluacion"].value == "Lista de cotejo para el relato."
    assert session.fields["evaluacion"].evidence[0].page_number == 2
    annex = session.annex_references[0]
    assert annex.annex_number == "12" and annex.confirmed_page is None
    assert annex.status == "missing" and annex.candidate_pages == []


def test_plural_table_header_remains_source_text_but_not_activity():
    text = "SESIÓN 3: Mapas\nDesarrollo: Comparar.\nActividad 1: Dibujar el recorrido.\nActividad 2: Comparar dos mapas.\nActividades y recursos\nCierre: Compartir."
    session = I._detect_sessions([text], "synthetic", [], {})[0]
    assert [a.description for a in session.activities] == ["Dibujar el recorrido.", "Comparar dos mapas."]
    assert "Actividades y recursos" in session.fields["desarrollo"].value
