"""Public parser acceptance, with invented PDF text and no provider access."""
import io
import socket

import pytest
from django.template.loader import render_to_string

from curriculum.source_interpreter import CurriculumSourceInterpreter, ImportDossier, derive_operational_queue
from curriculum.verification import verify_curriculum_dossier
from test_t15_curriculum_import import make_minimal_pdf


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Structure acceptance must remain offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def prepare(pages):
    pdf = make_minimal_pdf(pages)
    return CurriculumSourceInterpreter.prepare(io.BytesIO(pdf)), pdf


def test_resources_between_phases_do_not_drop_or_promote_instructions():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "Recursos e\nimplicaciones\n* Observar las senales del patio.\n-Marcadores.\n",
        "* Comparar los dibujos.\nFase #2. Accion\nRecursos e\nimplicaciones\n"
        "* Redactar una regla para cada cartel.\nFase #3. Intervencion\n"
        "Recursos e\nimplicaciones\n* Exhibir los carteles.\n"
        "Productos y evidencias de aprendizaje\nCarteles colectivos.\n",
    ])
    unit = dossier.to_dict()["sessions"][0]
    assert unit["unit_kind"] == "project_review"
    assert dossier.declared_session_count == 0
    assert [p["title"] for p in unit["source_structure"]["phases"]] == [
        "Planeacion", "Accion", "Intervencion",
    ]
    blocks = unit["source_structure"]["blocks"]
    assert [b["text"] for b in blocks if b["role"] == "instruction"] == [
        "Observar las senales del patio.", "Comparar los dibujos.",
        "Redactar una regla para cada cartel.", "Exhibir los carteles.",
    ]
    assert [b["text"] for b in blocks if b["role"] == "resource"] == ["Marcadores."]
    assert unit["activities"] == []
    assert not {"inicio", "desarrollo", "cierre"}.intersection(unit["fields"])
    assert not any(item.field_name in {"inicio", "desarrollo", "cierre"}
                   and item.session_id == unit["session_id"]
                   for item in derive_operational_queue(dossier).items)
    assert dossier.verification_report["blocked_count"] == 0


def test_bare_work_phase_and_directives_with_introductory_phrases_are_preserved():
    dossier, _ = prepare([
        "Fase 4 Grado 3 Campo Lenguajes\nProyecto Carteles del patio\n"
        "DESARROLLO DEL PROYECTO\nFase 1\nRecursos e implicaciones\n"
        "* De manera grupal, comparar las senales.\n* En equipos, elaborar un cartel.\n"
        "-Libro de lecturas.\n",
    ])
    structure = dossier.to_dict()["sessions"][0]["source_structure"]
    assert [p["number"] for p in structure["phases"]] == ["1"]
    assert [b["text"] for b in structure["blocks"] if b["role"] == "instruction"] == [
        "De manera grupal, comparar las senales.", "En equipos, elaborar un cartel.",
    ]


def test_bullets_without_an_action_or_resource_scope_remain_unassigned():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "* Observar las senales.\n-Marcadores.\n* Informacion de alcance incierto.\n",
    ])
    blocks = dossier.to_dict()["sessions"][0]["source_structure"]["blocks"]
    assert [b["text"] for b in blocks if b["role"] == "instruction"] == ["Observar las senales."]
    assert {b["text"] for b in blocks if b["role"] == "unassigned"} == {
        "Marcadores.", "Informacion de alcance incierto.",
    }


def test_a_phase_local_evaluation_does_not_disable_the_next_explicit_phase():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "* Observar las senales.\nEvaluacion de la fase\nLista de cotejo.\n"
        "Fase #2. Accion\n* Dibujar una senal.\n",
    ])
    structure = dossier.to_dict()["sessions"][0]["source_structure"]
    assert [p["number"] for p in structure["phases"]] == ["1", "2"]
    assert [b["text"] for b in structure["blocks"] if b["role"] == "instruction"] == [
        "Observar las senales.", "Dibujar una senal.",
    ]


@pytest.mark.parametrize("resource_heading", ["", "Recursos\n"])
def test_homework_with_a_bullet_remains_a_separate_instruction(resource_heading):
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        + resource_heading + "* Observar las senales.\n* TAREA: Mostrar el cartel en casa.\n",
    ])
    blocks = dossier.to_dict()["sessions"][0]["source_structure"]["blocks"]
    assert [b["text"] for b in blocks if b["role"] == "instruction"] == [
        "Observar las senales.", "TAREA: Mostrar el cartel en casa.",
    ]


def test_phase_project_retains_numbered_annex_reference_without_confirmation():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "Actividad 1: Observar el Anexo 1 y comentar sus simbolos.\n",
        "Fase #2. Accion\n* Dibujar una senal.\n",
        "ANEXO 1 - Las senales del patio\nObserva los simbolos.\n",
    ])
    unit = dossier.to_dict()["sessions"][0]
    assert len(unit["annex_references"]) == 1
    ref = unit["annex_references"][0]
    assert ref["annex_number"] == "1"
    assert ref["candidate_pages"] == [3]
    assert ref["confirmed_page"] is None and ref["review"] == "pending"
    assert unit["activities"][0]["annex_ids"] == [ref["reference_id"]]
    assert dossier.verification_report["blocked_count"] == 0


def test_annex_heading_does_not_erase_an_earlier_phase_on_its_page():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "* Observar el Anexo 1.\n",
        "Fase #2. Accion\n* Compartir los dibujos.\nANEXO 1 - Senales\n"
        "Actividad 99: Trabajo de la hoja, fuera de la fase.\n",
    ])
    unit = dossier.to_dict()["sessions"][0]
    assert unit["pages"] == [1, 2]
    blocks = unit["source_structure"]["blocks"]
    assert any(b["text"] == "Compartir los dibujos." for b in blocks)
    assert not any("Actividad 99" in b["text"] for b in blocks)
    assert dossier.verification_report["blocked_count"] == 0


def test_named_worksheet_keeps_its_title_and_candidate_exercise_pages():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver la ficha "Las senales del patio". (Anexo al final del documento)\n',
        "Fase #2. Accion\n* Compartir las conclusiones.\nProductos y evidencias de aprendizaje\n",
        "LAS SENALES DEL PATIO\nObserva los simbolos y escribe lo que indican.\n________\n",
        "¿Qué senal propondrias?\n________\n",
    ])
    candidate, = dossier.annex_candidates
    assert candidate["number"] == ""
    assert candidate["title"] == "Las senales del patio"
    assert candidate["heading_page"] == 3
    assert candidate["candidate_exercise_pages"] == [3, 4]
    assert candidate["confirmed_pages"] is None
    unit = dossier.to_dict()["sessions"][0]
    ref, = unit["annex_references"]
    assert ref["annex_number"] == "" and ref["title"] == "Las senales del patio"
    assert ref["candidate_pages"] == [3, 4] and ref["confirmed_page"] is None
    assert ref["review"] == "pending" and ref["status"] == "ambiguous"
    assert ref["reference_id"] in unit["activities"][0]["annex_ids"]
    item, = [item for item in derive_operational_queue(dossier).items if item.scope == "annex"]
    assert item.human_label == "Las senales del patio"
    assert item.session_number is None
    assert dossier.verification_report["blocked_count"] == 0


@pytest.mark.parametrize("remove_identity", [False, True])
def test_worksheet_sources_and_candidate_ranges_cannot_be_tampered(remove_identity):
    dossier, pdf = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Completar la ficha "Cruzar con cuidado".\nProductos y evidencias\n',
        "CRUZAR CON CUIDADO\nDibuja una senal.\n________\n",
    ])
    data = dossier.to_dict()
    data["annex_candidates"][0]["source_fragments"][-1]["excerpt"] = "Otra cosa que no existe."
    if remove_identity:
        data["annex_candidates"][0].pop("identity")
        data["annex_candidates"][0]["candidate_exercise_pages"] = [999]
        data["annex_candidates"][0]["confirmed_pages"] = [999]
    report = verify_curriculum_dossier(data, io.BytesIO(pdf)).to_dict()
    assert any(item["status"] == "blocked" and item["path"].startswith("annex_candidates/")
               for item in report["items"])


def test_annex_number_is_not_a_prefix_match_in_another_activity():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "Actividad 1: Observar el Anexo 1.\nActividad 2: Comparar el Anexo 10.\n",
        "ANEXO 1 - Figuras\nObserva las figuras.\n",
        "ANEXO 10 - Colores\nObserva los colores.\n",
    ])
    unit = dossier.sessions[0]
    by_number = {ref.annex_number: ref.reference_id for ref in unit.annex_references}
    assert unit.activities[0].annex_ids == [by_number["1"]]
    assert unit.activities[1].annex_ids == [by_number["10"]]


@pytest.mark.parametrize("change_id", [False, True])
def test_named_material_reference_cannot_claim_an_unrelated_candidate_page(change_id):
    dossier, pdf = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        '* Completar la ficha "Cruzar con cuidado".\nProductos y evidencias\n',
        "CRUZAR CON CUIDADO\nDibuja una senal.\n________\n",
    ])
    data = dossier.to_dict()
    data["sessions"][0]["annex_references"][0]["candidate_pages"] = [1]
    if change_id:
        data["sessions"][0]["annex_references"][0]["reference_id"] = "renamed_material"
    report = verify_curriculum_dossier(data, io.BytesIO(pdf)).to_dict()
    assert any(item["status"] == "blocked" and "annex_references" in item["path"]
               for item in report["items"])


@pytest.mark.parametrize("corruption", ["quote", "source_pages", "empty_evidence", "printed_number"])
def test_named_reference_requires_its_literal_local_mention(corruption):
    dossier, pdf = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        '* Completar la ficha "Cruzar con cuidado".\nProductos y evidencias\n',
        "CRUZAR CON CUIDADO\nDibuja una senal.\n________\n",
    ])
    data = dossier.to_dict()
    ref = data["sessions"][0]["annex_references"][0]
    if corruption == "quote":
        ref["evidence"][0]["excerpt"] = "Cita que no existe."
    elif corruption == "source_pages":
        ref["source_pages"] = [2]
    elif corruption == "printed_number":
        ref["annex_number"] = "99"
    else:
        ref["evidence"] = []
    report = verify_curriculum_dossier(data, io.BytesIO(pdf)).to_dict()
    assert any(item["status"] == "blocked" and "annex_references" in item["path"]
               for item in report["items"])


def test_footer_heading_and_exercise_pages_remain_distinct():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        '* Completar las fichas "Senales grandes" y "Cuido las esquinas".\n',
        "Fase #2. Accion\n* Compartir resultados.\nProductos y evidencias\n",
        "SENALES GRANDES\nDibuja una senal conocida.\n________\n",
        "Escribe que significa tu dibujo.\n________\nCUIDO LAS ESQUINAS\n",
        "Lee cada situacion y escribe como cruzarias.\n________\n",
        "Explica tu eleccion al equipo.\n________\n",
    ])
    assert [(c["title"], c["heading_page"], c["candidate_exercise_pages"])
            for c in dossier.annex_candidates] == [
        ("Senales grandes", 3, [3, 4]), ("Cuido las esquinas", 4, [5, 6]),
    ]
    assert all(c["confirmed_pages"] is None for c in dossier.annex_candidates)
    assert dossier.verification_report["blocked_count"] == 0


def test_legacy_units_stay_unknown_and_keep_existing_data():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nSESION 1: Senales\n"
        "Inicio: Observar una senal.\nDesarrollo: Dibujar otra.\nCierre: Compartir.\n",
    ])
    assert dossier.declared_session_count == 1
    data = dossier.to_dict()
    data["sessions"][0].pop("unit_kind")
    data["sessions"][0].pop("source_structure")
    restored = ImportDossier.from_dict(data)
    assert restored.sessions[0].unit_kind == "unknown"
    assert restored.declared_session_count == 0
    assert restored.to_dict()["sessions"][0]["fields"] == data["sessions"][0]["fields"]


@pytest.mark.parametrize("corruption", ["offset", "role", "unit_kind", "boolean_page"])
def test_structure_claims_must_match_the_physical_source(corruption):
    dossier, pdf = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "* Observar las senales.\n",
    ])
    data = dossier.to_dict()
    unit = data["sessions"][0]
    if corruption == "offset":
        unit["source_structure"]["blocks"][-1]["evidence"][0]["text_start"] = 0
    elif corruption == "role":
        unit["source_structure"]["blocks"][-1]["role"] = "activity"
    elif corruption == "boolean_page":
        unit["source_structure"]["blocks"][-1]["evidence"][0]["page_number"] = True
    else:
        unit["unit_kind"] = "declared_session"
    report = verify_curriculum_dossier(data, io.BytesIO(pdf)).to_dict()
    assert report["blocked_count"] > 0
    assert any(item["status"] == "blocked" and item["path"].endswith(
        "/unit_kind" if corruption == "unit_kind" else "/source_structure"
    ) for item in report["items"])


def test_continuations_questions_steps_and_homework_keep_separate_roles():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "Recursos\n-Papel de colores.\n-Observar las senales y\n",
        "comparar sus colores.\n* Conversar a partir de estas preguntas:\n"
        "  ¿Qué colores reconoces?\n  ¿Dónde se encuentran?\n"
        "* Elaborar un cartel con estos pasos:\n  1. Dibujar una senal.\n"
        "  2. Escribir su significado.\nTAREA: Mostrar el cartel en casa.\n"
        "Frase de alcance incierto.\n",
    ])
    blocks = dossier.to_dict()["sessions"][0]["source_structure"]["blocks"]
    instructions = [b for b in blocks if b["role"] == "instruction"]
    assert [b["text"] for b in instructions] == [
        "Observar las senales y comparar sus colores.",
        "Conversar a partir de estas preguntas:",
        "Elaborar un cartel con estos pasos:", "TAREA: Mostrar el cartel en casa.",
    ]
    assert [e["page_number"] for e in instructions[0]["evidence"]] == [1, 2]
    questions = [b for b in blocks if b["role"] == "question"]
    assert len(questions) == 2
    assert {b["parent_id"] for b in questions} == {instructions[1]["block_id"]}
    steps = [b for b in blocks if b["role"] == "step"]
    assert len(steps) == 2
    assert {b["parent_id"] for b in steps} == {instructions[2]["block_id"]}
    assert any(b["role"] == "unassigned" and b["text"] == "Frase de alcance incierto." for b in blocks)
    assert dossier.verification_report["blocked_count"] == 0


def test_worksheet_candidate_stops_before_a_later_project_on_the_same_page():
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        '* Completar la ficha "Cruzar con cuidado".\nProductos y evidencias\n',
        "CRUZAR CON CUIDADO\nDibuja una senal.\n________\n"
        "Proyecto El huerto\nSESION 1: Semillas\nInicio: Observar semillas.\n",
        "Otra actividad que pertenece al huerto.\n",
    ])
    candidate, = dossier.annex_candidates
    assert candidate["candidate_exercise_pages"] == [2]
    assert all("huerto" not in fragment["excerpt"] for fragment in candidate["source_fragments"])


@pytest.mark.parametrize("template", ["tutor_import_interpretation.html", "tutor_teacher_review.html"])
def test_project_review_labels_and_source_blocks_are_visible_without_fake_classes(template):
    dossier, _ = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nComentario previo sin fase asignada.\nFase #1. Planeacion\n"
        "Recursos\n-Marcadores.\n* Observar las senales del patio.\n",
    ])
    unit = dossier.sessions[0]
    html = render_to_string("curriculum/" + template, {
        "dossier": dossier, "job": type("Job", (), {"pk": 1})(),
        "selected_session": unit, "active_session_id": unit.session_id,
        "queue": derive_operational_queue(dossier),
    })
    assert "Unidad de revisión del proyecto" in html
    assert "0 sesiones declaradas" in html
    assert "Instrucciones y recursos de la fuente" in html
    assert "Observar las senales del patio." in html and "Marcadores." in html
    assert "Comentario previo sin fase asignada." in html
    assert "Sesiones de Clase" not in html and "Momentos de la sesión" not in html
