"""Synthetic regressions for the STOP source-boundary findings, entirely offline."""
import io
import socket

import pytest

from curriculum.source_interpreter import CurriculumSourceInterpreter
from curriculum.verification import verify_curriculum_dossier
from test_t15_curriculum_import import make_minimal_pdf


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Boundary acceptance is offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def prepare(pages):
    return CurriculumSourceInterpreter.prepare(io.BytesIO(make_minimal_pdf(pages)))


@pytest.mark.parametrize("resource_mention", [
    'Copias de la actividad\n"Mi revision".',
    'Copias de la actividad\n"Mi\nrevision".',
])
def test_repeated_resource_citation_is_not_a_worksheet_heading(resource_mention):
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver la actividad "Mi revision".\n'
        "Materiales:\n" + resource_mention + "\n"
        "Fase #2. Accion\nActividad 2: Compartir una idea.\n"
        "Productos y evidencias de aprendizaje\n",
        "MI REVISION\nEscribe lo que aprendiste.\n________\n",
    ])
    candidate, = dossier.annex_candidates
    assert candidate["heading_page"] == 2
    assert candidate["candidate_exercise_pages"] == [2]
    assert candidate["confirmed_pages"] is None
    reference, = dossier.sessions[0].annex_references
    assert reference.source_pages == [1] and reference.confirmed_page is None
    assert any('"Mi' in evidence.excerpt for evidence in reference.evidence)
    assert dossier.verification_report["blocked_count"] == 0


def test_wrapped_quoted_material_title_keeps_a_literal_page_local_mention():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver la ficha "Las senales\ndel patio".\nProductos y evidencias de aprendizaje\n',
        "LAS SENALES DEL PATIO\nObserva los dibujos y escribe su significado.\n________\n",
    ])
    candidate, = dossier.annex_candidates
    assert candidate["title"] == "Las senales del patio"
    assert candidate["candidate_exercise_pages"] == [2]
    ref, = dossier.sessions[0].annex_references
    assert ref.raw_mention == '"Las senales\ndel patio"'
    assert ref.evidence[0].page_number == 1
    assert ref.evidence[0].excerpt == '"Las senales\ndel patio"'
    assert dossier.sessions[0].activities[0].annex_ids == [ref.reference_id]
    assert ref.confirmed_page is None and ref.review == "pending"
    assert dossier.verification_report["blocked_count"] == 0


def test_wrapped_heading_is_one_candidate_with_its_complete_literal_span():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver la ficha "Las senales para orientarnos".\nProductos y evidencias de aprendizaje\n',
        "LAS SENALES\nPARA ORIENTARNOS\nDibuja una senal.\n________\n",
    ])
    candidate, = dossier.annex_candidates
    assert candidate["title"] == "Las senales para orientarnos"
    assert candidate["label"] == "LAS SENALES\nPARA ORIENTARNOS"
    assert candidate["source_fragments"][0]["excerpt"] == candidate["label"]
    assert candidate["candidate_exercise_pages"] == [2]
    assert dossier.verification_report["blocked_count"] == 0


def test_editorial_prefix_before_the_next_heading_is_not_previous_worksheet_content():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver las fichas "Senales grandes" y "Cruzar con cuidado".\n'
        "Productos y evidencias de aprendizaje\n",
        "SENALES GRANDES\nDibuja una senal conocida.\n________\n",
        "Marca editorial sintetica\nCRUZAR CON CUIDADO\nLee cada situacion.\n________\n",
    ])
    first, second = dossier.annex_candidates
    assert first["candidate_exercise_pages"] == [2]
    assert second["candidate_exercise_pages"] == [3]
    assert all("Marca editorial" not in f["excerpt"] for f in first["source_fragments"])
    assert any(f["excerpt"] == "Marca editorial sintetica" and f["page_number"] == 3
               for f in first["unassigned_fragments"])
    assert dossier.verification_report["blocked_count"] == 0


@pytest.mark.parametrize("mention", [
    'Resolver las fichas "Senales\ngrandes" y "Cruzar\ncon cuidado".',
    'Resolver las fichas:\n"Senales grandes" y\n"Cruzar con cuidado".',
])
def test_a_wrapped_list_of_quoted_titles_stays_in_its_local_material_context(mention):
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "Actividad 1: " + mention + "\nProductos y evidencias de aprendizaje\n",
        "SENALES GRANDES\nDibuja una senal.\n________\n",
        "CRUZAR CON CUIDADO\nLee las situaciones.\n________\n",
    ])
    assert [c["title"] for c in dossier.annex_candidates] == ["Senales grandes", "Cruzar con cuidado"]
    assert [c["candidate_exercise_pages"] for c in dossier.annex_candidates] == [[2], [3]]
    assert len(dossier.sessions[0].annex_references) == 2
    assert dossier.verification_report["blocked_count"] == 0


def test_mixed_wrapped_titles_and_footer_heading_do_not_merge_material_ranges():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver las fichas "Senales grandes", "Cruzar\ncon cuidado" y "Mi revision".\n'
        "Productos y evidencias de aprendizaje\n",
        "SENALES GRANDES\nDibuja una senal.\n________\n",
        "Escribe su significado.\n________\nCRUZAR CON\nCUIDADO\n",
        "Lee las situaciones y explica tu eleccion.\n________\n",
        "Marca editorial sintetica\nMI REVISION\n¿Qué aprendiste?\n________\n",
    ])
    assert [(c["title"], c["heading_page"], c["candidate_exercise_pages"])
            for c in dossier.annex_candidates] == [
        ("Senales grandes", 2, [2, 3]), ("Cruzar con cuidado", 3, [4]), ("Mi revision", 5, [5]),
    ]
    assert all(c["confirmed_pages"] is None for c in dossier.annex_candidates)
    assert all(ref.confirmed_page is None for ref in dossier.sessions[0].annex_references)
    assert dossier.verification_report["blocked_count"] == 0


def test_editorial_words_inside_exercise_text_are_not_silently_removed():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver la ficha "La noticia".\nProductos y evidencias de aprendizaje\n',
        "LA NOTICIA\nLee el comentario editorial y escribe tu opinion.\n"
        "La editorial del pueblo publico una noticia.\n________\n",
    ])
    candidate, = dossier.annex_candidates
    contents = [f["excerpt"] for f in candidate["source_fragments"] if f["role"] == "worksheet_content"]
    assert "Lee el comentario editorial y escribe tu opinion." in contents
    assert "La editorial del pueblo publico una noticia." in contents


def test_a_longer_wrapped_heading_is_not_split_into_a_shorter_material_title():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver las fichas "La senal" y "La senal roja".\n'
        "Productos y evidencias de aprendizaje\n",
        "LA SENAL\nROJA\nDibuja una senal.\n________\n",
    ])
    candidate, = dossier.annex_candidates
    assert candidate["title"] == "La senal roja"
    assert candidate["label"] == "LA SENAL\nROJA"


def test_unassigned_material_fragments_are_source_checked_without_other_new_metadata():
    pages = [
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver las fichas "Senales grandes" y "Cruzar con cuidado".\n'
        "Productos y evidencias de aprendizaje\n",
        "SENALES GRANDES\nDibuja una senal.\n",
        "Marca editorial sintetica\nCRUZAR CON CUIDADO\nLee las situaciones.\n",
    ]
    pdf = make_minimal_pdf(pages)
    data = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf)).to_dict()
    original = data["annex_candidates"][0]
    original["unassigned_fragments"][0]["excerpt"] = "Texto inventado."
    data["annex_candidates"][0] = {key: value for key, value in original.items()
                                    if key in {"number", "page", "label", "title", "unassigned_fragments"}}
    report = verify_curriculum_dossier(data, io.BytesIO(pdf)).to_dict()
    assert any(item["status"] == "blocked" and item["path"].startswith("annex_candidates/")
               for item in report["items"])


def test_copyright_symbol_inside_an_instruction_is_not_editorial_metadata():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Actividad 1: Resolver la ficha "La noticia".\nProductos y evidencias de aprendizaje\n',
        "LA NOTICIA\nDibuja el simbolo © junto a la imagen.\n",
    ])
    candidate, = dossier.annex_candidates
    assert candidate["candidate_exercise_pages"] == [2]
    assert any(f["excerpt"] == "Dibuja el simbolo © junto a la imagen."
               for f in candidate["source_fragments"])


def test_material_noun_after_the_title_still_grounds_the_material_mention():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Resolver "La noticia", la ficha de hoy.\nProductos y evidencias de aprendizaje\n',
        "LA NOTICIA\nDibuja una senal.\n",
    ])
    candidate, = dossier.annex_candidates
    assert candidate["title"] == "La noticia"
    ref, = dossier.sessions[0].annex_references
    assert ref.raw_mention == '"La noticia"'
    assert ref.candidate_pages == [2]
    assert dossier.verification_report["blocked_count"] == 0


def test_numbered_heading_keeps_the_preceding_named_worksheet_prefix_on_the_same_page():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Resolver la ficha "La noticia" y el Anexo 1.\nProductos y evidencias de aprendizaje\n',
        "LA NOTICIA\nDibuja una senal.\nANEXO 1\nLee la noticia.\n",
    ])
    named, numbered = dossier.annex_candidates
    assert named["candidate_exercise_pages"] == [2]
    assert any(f["excerpt"] == "Dibuja una senal." for f in named["source_fragments"])
    assert not any("Lee la noticia" in f["excerpt"] for f in named["source_fragments"])
    assert numbered["number"] == "1"
    assert dossier.verification_report["blocked_count"] == 0


def test_an_editorial_url_query_is_not_an_exercise_question_before_the_next_title():
    dossier = prepare([
        "Proyecto Carteles del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        'Resolver las fichas "La noticia" y "El cartel".\nProductos y evidencias de aprendizaje\n',
        "LA NOTICIA\nDibuja una senal.\n",
        "https://editorial.example/hojas?ficha=2\nEL CARTEL\nDibuja otro cartel.\n",
    ])
    first, _ = dossier.annex_candidates
    assert first["candidate_exercise_pages"] == [2]
    assert any(f["excerpt"].startswith("https://") for f in first["unassigned_fragments"])
