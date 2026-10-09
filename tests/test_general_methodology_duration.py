"""Public acceptance of general method/time fields using invented PDF text."""
import io
import socket

import pytest

from curriculum.source_interpreter import CurriculumSourceInterpreter
from curriculum.verification import verify_curriculum_dossier
from test_t15_curriculum_import import make_minimal_pdf


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("General field acceptance must remain offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def prepare(pages):
    pdf = make_minimal_pdf(pages)
    return CurriculumSourceInterpreter.prepare(io.BytesIO(pdf)), pdf


def test_methodology_stops_at_global_time_and_preserves_literal_wrapping():
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nMetodologia: Aprendizaje basado\n"
        "en proyectos\nTiempo de aplicacion: cuatro semanas\n"
        "DESARROLLO DEL PROYECTO\nFase #1. Exploracion\n* Observar figuras.\n",
    ])
    method = dossier.general_fields["metodologia"]
    assert method.value == "Aprendizaje basado en proyectos"
    assert method.evidence[0].excerpt == "Aprendizaje basado\nen proyectos"
    assert (method.origin, method.status, method.review) == ("extracted", "supported", "pending")
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert report["blocked_count"] == 0
    assert any(item["target"].startswith("general.metodologia") and item["status"] == "checked"
               for item in report["items"])


@pytest.mark.parametrize("next_heading", [
    "Fase #1. Exploracion", "DESARROLLO DEL PROYECTO", "Recursos e implicaciones",
    "Duracion del proyecto: cuatro semanas", "Sesion 1: Explorar",
    "Metodologia: Otra propuesta",
])
def test_methodology_does_not_absorb_following_structural_sections(next_heading):
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nMetodologia: Aprendizaje servicio\n"
        + next_heading + "\nTexto ajeno al campo.\n",
    ])
    method = dossier.general_fields["metodologia"]
    assert method.value == "Aprendizaje servicio"
    assert method.evidence[0].excerpt == "Aprendizaje servicio"
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert not any(item["status"] == "blocked" and item["target"].startswith("general.metodologia")
                   for item in report["items"])


def test_long_methodology_keeps_ambiguous_text_without_silent_cleanup():
    literal = (
        "Aprendizaje basado en proyectos con varias alternativas de organizacion "
        "que el documento deja abiertas para discutir con el equipo docente antes "
        "de decidir el procedimiento y su alcance."
    )
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nMetodologia: " + literal + "\nRecursos: Papel.\n",
    ])
    method = dossier.general_fields["metodologia"]
    assert method.value == literal
    assert method.evidence[0].excerpt == literal
    assert (method.origin, method.status, method.review) == ("proposed", "ambiguous", "pending")
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert not any(item["status"] == "blocked" and item["target"].startswith("general.metodologia")
                   for item in report["items"])


def test_suggested_global_time_keeps_wrapped_units_without_creating_class_time():
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nMetodologia: Aprendizaje servicio\n"
        "Tiempo de aplicacion:\nSe sugiere cuatro\nsemanas\n"
        "DESARROLLO DEL PROYECTO\nFase #1. Exploracion\n* Observar figuras.\n",
    ])
    duration = dossier.general_fields["duracion_proyecto"]
    assert duration.value == "Se sugiere cuatro semanas"
    assert duration.evidence[0].excerpt == "Se sugiere cuatro\nsemanas"
    assert (duration.origin, duration.status, duration.review) == ("proposed", "ambiguous", "pending")
    assert dossier.declared_session_count == 0
    assert all(session.fields["duracion"].status == "missing" for session in dossier.sessions)
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert report["blocked_count"] == 0
    assert any(item["target"] == "general.duracion_proyecto"
               and item["status"] == "needs_teacher_review" for item in report["items"])


def test_split_table_labels_and_values_keep_both_physical_pages():
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nDatos generales\n",
        "Metodologia: Aprendizaje basado en proyectos Tiempo de Se sugiere cuatro\n",
        "comunitarios. aplicacion semanas\nDESARROLLO DEL PROYECTO\n"
        "Fase #1. Exploracion\n* Observar figuras.\n",
    ])
    method = dossier.general_fields["metodologia"]
    duration = dossier.general_fields["duracion_proyecto"]
    assert method.value == "Aprendizaje basado en proyectos comunitarios."
    assert [(ref.page_number, ref.excerpt) for ref in method.evidence] == [
        (2, "Aprendizaje basado en proyectos"), (3, "comunitarios."),
    ]
    assert duration.value == "Se sugiere cuatro semanas"
    assert [(ref.page_number, ref.excerpt) for ref in duration.evidence] == [
        (2, "Se sugiere cuatro"), (3, "semanas"),
    ]
    assert all((field.origin, field.status, field.review) == ("proposed", "ambiguous", "pending")
               for field in (method, duration))
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert not any(item["status"] == "blocked" and item["scope"] == "general" for item in report["items"])


def test_complete_time_label_can_have_value_continuation_on_a_later_page():
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\n",
        "Tiempo de aplicacion: Se sugiere cuatro\n",
        "semanas\nRecursos: Papel.\n",
    ])
    duration = dossier.general_fields["duracion_proyecto"]
    assert duration.value == "Se sugiere cuatro semanas"
    assert [(ref.page_number, ref.excerpt) for ref in duration.evidence] == [
        (2, "Se sugiere cuatro"), (3, "semanas"),
    ]
    assert (duration.origin, duration.status, duration.review) == ("proposed", "ambiguous", "pending")
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert not any(item["status"] == "blocked" and item["target"].startswith("general.duracion_proyecto")
                   for item in report["items"])


@pytest.mark.parametrize("value", ["cuatro", "por acordar con el grupo", "cuatro semanas o el plazo que se determine"])
def test_incomplete_or_open_global_time_remains_a_literal_pending_candidate(value):
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nTiempo de aplicacion: " + value + "\nRecursos: Papel.\n",
    ])
    duration = dossier.general_fields["duracion_proyecto"]
    assert duration.value == value
    assert duration.evidence[0].excerpt == value
    assert (duration.origin, duration.status, duration.review) == ("proposed", "ambiguous", "pending")
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert any(item["target"] == "general.duracion_proyecto" and item["status"] == "needs_teacher_review"
               for item in report["items"])


@pytest.mark.parametrize("field_name,label,value", [
    ("metodologia", "Metodologia sugerida", "Aprendizaje servicio"),
    ("duracion_proyecto", "Duracion sugerida del proyecto", "cuatro semanas"),
    ("duracion_proyecto", "Temporalidad sugerida", "cuatro semanas"),
])
def test_suggestion_in_label_is_preserved_as_proposed_with_literal_evidence(field_name, label, value):
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\n" + label + ": " + value + "\nRecursos: Papel.\n",
    ])
    field = dossier.general_fields[field_name]
    assert field.value == value
    assert (field.origin, field.status, field.review) == ("proposed", "ambiguous", "pending")
    assert field.evidence[0].excerpt == label + ": " + value
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert any(item["target"] == "general." + field_name and item["status"] == "needs_teacher_review"
               for item in report["items"])


def test_methodology_continuation_is_a_proposal_with_separate_page_fragments():
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nMetodologia: Aprendizaje basado en\n",
        "proyectos comunitarios.\nTiempo de aplicacion: cuatro semanas\n",
    ])
    method = dossier.general_fields["metodologia"]
    assert method.value == "Aprendizaje basado en proyectos comunitarios."
    assert [(ref.page_number, ref.excerpt) for ref in method.evidence] == [
        (1, "Aprendizaje basado en"), (2, "proyectos comunitarios."),
    ]
    assert (method.origin, method.status, method.review) == ("proposed", "ambiguous", "pending")
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert any(item["target"] == "general.metodologia" and item["status"] == "needs_teacher_review"
               for item in report["items"])


def test_unresolved_methodology_page_boundary_is_not_silently_certified():
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nMetodologia: Aprendizaje basado en proyectos\n",
        "Recursos: Papel.\n",
    ])
    method = dossier.general_fields["metodologia"]
    assert method.value == "Aprendizaje basado en proyectos"
    assert [(ref.page_number, ref.excerpt) for ref in method.evidence] == [
        (1, "Aprendizaje basado en proyectos"),
    ]
    assert (method.origin, method.status, method.review) == ("proposed", "ambiguous", "pending")


@pytest.mark.parametrize("body", [
    "DESARROLLO DEL PROYECTO\nFase #1. Exploracion\n"
    "Metodologia: Dialogar en parejas\nTiempo de aplicacion: diez minutos\n",
    "Sesion 1: Observar\nMetodologia: Dialogar en parejas\nTiempo de aplicacion: diez minutos\n",
    "Explicar la metodologia: dialogar en parejas.\nRevisar el tiempo de aplicacion: diez minutos.\n",
])
def test_local_or_prose_mentions_do_not_become_global_methodology_and_time(body):
    dossier, _ = prepare(["Proyecto: Jardines de papel\n" + body])
    assert dossier.general_fields["metodologia"].status == "missing"
    assert "duracion_proyecto" not in dossier.general_fields


def test_empty_labels_do_not_steal_the_next_field():
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nMetodologia\nTiempo de aplicacion\nRecursos: Papel.\n",
    ])
    assert dossier.general_fields["metodologia"].status == "missing"
    assert "duracion_proyecto" not in dossier.general_fields


def test_label_alone_at_page_end_keeps_next_page_time_as_a_proposal():
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nTiempo de aplicacion\n",
        "cuatro semanas\nRecursos: Papel.\n",
    ])
    duration = dossier.general_fields["duracion_proyecto"]
    assert duration.value == "cuatro semanas"
    assert [(ref.page_number, ref.excerpt) for ref in duration.evidence] == [
        (1, "Tiempo de aplicacion"), (2, "cuatro semanas"),
    ]
    assert (duration.origin, duration.status, duration.review) == ("proposed", "ambiguous", "pending")
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert any(item["target"] == "general.duracion_proyecto" and item["status"] == "needs_teacher_review"
               for item in report["items"])


@pytest.mark.parametrize("next_heading", [
    "Materiales: Papel", "Evaluacion: Lista de cotejo", "Productos: Figura colectiva",
    "Anexo 1: Figuras", "Inicio: Observar", "Cierre: Conversar",
])
def test_general_details_stop_before_remaining_planning_sections(next_heading):
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nMetodologia: Aprendizaje servicio\n" + next_heading + "\n",
    ])
    assert dossier.general_fields["metodologia"].value == "Aprendizaje servicio"


def test_unrelated_application_prose_does_not_complete_a_split_time_label():
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nTiempo de Se sugiere cuatro\n",
        "Hoy describiremos la aplicacion de recortes en un dibujo.\nRecursos: Papel.\n",
    ])
    duration = dossier.general_fields["duracion_proyecto"]
    assert duration.value == "Se sugiere cuatro"
    assert [(ref.page_number, ref.excerpt) for ref in duration.evidence] == [(1, "Se sugiere cuatro")]
    assert (duration.origin, duration.status, duration.review) == ("proposed", "ambiguous", "pending")


def test_inline_explicit_labels_are_separated_from_global_duration():
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nTiempo de aplicacion: cuatro semanas "
        "Metodologia: Aprendizaje servicio Recursos: Papel.\n",
    ])
    assert dossier.general_fields["duracion_proyecto"].value == "cuatro semanas"
    assert dossier.general_fields["metodologia"].value == "Aprendizaje servicio"


def test_methodology_suggested_in_its_value_is_not_promoted_to_extracted_fact():
    literal = "Se sugiere Aprendizaje servicio"
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nMetodologia: " + literal + "\nRecursos: Papel.\n",
    ])
    method = dossier.general_fields["metodologia"]
    assert method.value == literal
    assert method.evidence[0].excerpt == literal
    assert (method.origin, method.status, method.review) == ("proposed", "ambiguous", "pending")


def test_time_label_on_another_section_does_not_resume_the_methodology():
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nMetodologia: Aprendizaje servicio\n"
        "Recursos: Papel.\nTiempo de Se sugiere cuatro\n",
        "Otro dato. aplicacion semanas\nRecursos: Tijeras.\n",
    ])
    assert dossier.general_fields["metodologia"].value == "Aprendizaje servicio"
    assert len(dossier.general_fields["metodologia"].evidence) == 1


@pytest.mark.parametrize("value", ["Se sugiere cuatro semanas", "aproximadamente cuatro semanas"])
def test_time_value_after_a_page_break_retains_its_suggested_modality(value):
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nTiempo de aplicacion:\n",
        value + "\nRecursos: Papel.\n",
    ])
    duration = dossier.general_fields["duracion_proyecto"]
    assert duration.value == value
    assert [(ref.page_number, ref.excerpt) for ref in duration.evidence] == [
        (1, "Tiempo de aplicacion:"), (2, value),
    ]
    assert (duration.origin, duration.status, duration.review) == ("proposed", "ambiguous", "pending")


@pytest.mark.parametrize("field_name,label,value", [
    ("metodologia", "Metodologia sugerida", "Aprendizaje servicio"),
    ("duracion_proyecto", "Temporalidad sugerida", "cuatro semanas"),
])
def test_suggestion_label_and_wrapped_value_keep_an_actual_source_slice(field_name, label, value):
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\n" + label + ":\n" + value + "\nRecursos: Papel.\n",
    ])
    field = dossier.general_fields[field_name]
    assert field.value == value
    assert field.evidence[0].excerpt == label + ":\n" + value
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert not any(item["status"] == "blocked" and item["target"].startswith("general." + field_name)
                   for item in report["items"])


@pytest.mark.parametrize("field_name", ["metodologia", "duracion_proyecto"])
def test_cross_page_candidate_still_rejects_fabricated_literal_evidence(field_name):
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\n"
        "Metodologia: Aprendizaje basado en proyectos Tiempo de Se sugiere cuatro\n",
        "comunitarios. aplicacion semanas\nRecursos: Papel.\n",
    ])
    data = dossier.to_dict()
    data["general_fields"][field_name]["evidence"][1]["excerpt"] = "Una cita inexistente."
    report = verify_curriculum_dossier(data, io.BytesIO(pdf)).to_dict()
    assert any(item["status"] == "blocked"
               and item["path"] == "general_fields/" + field_name + "/evidence/1"
               for item in report["items"])


def test_explicit_fixed_global_time_is_supported_with_its_whole_wrapped_quote():
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nTiempo de aplicacion: cuatro\nsemanas\n"
        "DESARROLLO DEL PROYECTO\nFase #1. Exploracion\n* Observar figuras.\n",
    ])
    duration = dossier.general_fields["duracion_proyecto"]
    assert duration.value == "cuatro semanas"
    assert (duration.origin, duration.status, duration.review) == ("extracted", "supported", "pending")
    assert duration.evidence[0].excerpt == "cuatro\nsemanas"
    assert all(session.fields["duracion"].status == "missing" for session in dossier.sessions)
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert report["blocked_count"] == 0
    assert any(item["target"].startswith("general.duracion_proyecto") and item["status"] == "checked"
               for item in report["items"])


@pytest.mark.parametrize("next_heading", [
    "Campos formativos: Lenguajes", "Ejes: Interculturalidad", "Proposito: Observar figuras",
    "Finalidad: Dialogar", "Contenidos: Figuras geometricas",
])
def test_tabular_inline_metadata_does_not_become_part_of_the_methodology(next_heading):
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nMetodologia: Aprendizaje servicio  "
        + next_heading + "\nRecursos: Papel.\n",
    ])
    method = dossier.general_fields["metodologia"]
    assert method.value == "Aprendizaje servicio"
    assert method.evidence[0].excerpt == "Aprendizaje servicio"


def test_global_time_keeps_an_open_qualifier_on_the_next_physical_page():
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nTiempo de aplicacion: cuatro semanas\n",
        "o el plazo que se determine\nRecursos: Papel.\n",
    ])
    duration = dossier.general_fields["duracion_proyecto"]
    assert duration.value == "cuatro semanas o el plazo que se determine"
    assert [(ref.page_number, ref.excerpt) for ref in duration.evidence] == [
        (1, "cuatro semanas"), (2, "o el plazo que se determine"),
    ]
    assert (duration.origin, duration.status, duration.review) == ("proposed", "ambiguous", "pending")
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert any(item["target"] == "general.duracion_proyecto" and item["status"] == "needs_teacher_review"
               for item in report["items"])


@pytest.mark.parametrize("continuation", [
    "recursos locales y colaboracion.", "materiales elaborados por el grupo.",
    "evaluacion entre pares y observacion.",
])
def test_methodology_prose_that_resembles_a_heading_is_preserved_for_review(continuation):
    literal = "Aprendizaje basado en proyectos que integra\n" + continuation
    dossier, pdf = prepare([
        "Proyecto: Jardines de papel\nMetodologia: " + literal
        + "\nTiempo de aplicacion: cuatro semanas\n",
    ])
    method = dossier.general_fields["metodologia"]
    assert method.value == "Aprendizaje basado en proyectos que integra " + continuation
    assert method.evidence[0].excerpt == literal
    assert (method.origin, method.status, method.review) == ("proposed", "ambiguous", "pending")
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf)).to_dict()
    assert not any(item["status"] == "blocked" and item["target"].startswith("general.metodologia")
                   for item in report["items"])


def test_methodology_explicitly_proposed_in_text_retains_proposal_status():
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nMetodologia: Se propone Aprendizaje servicio\nRecursos: Papel.\n",
    ])
    method = dossier.general_fields["metodologia"]
    assert method.value == "Se propone Aprendizaje servicio"
    assert (method.origin, method.status, method.review) == ("proposed", "ambiguous", "pending")


def test_approximate_global_time_retains_uncertainty_in_its_literal_value():
    dossier, _ = prepare([
        "Proyecto: Jardines de papel\nTiempo de aplicacion: cuatro semanas aproximadamente\nRecursos: Papel.\n",
    ])
    duration = dossier.general_fields["duracion_proyecto"]
    assert duration.value == "cuatro semanas aproximadamente"
    assert (duration.origin, duration.status, duration.review) == ("proposed", "ambiguous", "pending")
