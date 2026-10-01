"""Authored structural regressions; not a holdout or semantic-quality score."""

import io

import pytest

from curriculum.claims import compile_dossier_to_atomic_claims
from curriculum.source_interpreter import CurriculumSourceInterpreter, ImportDossier
from curriculum.verification import verify_curriculum_dossier
from test_t15_curriculum_import import make_minimal_pdf


def fields(pages, warnings=None):
    return CurriculumSourceInterpreter._extract_general_fields(pages, "synthetic-sha", warnings or {})


def test_multiline_title_is_preserved_as_a_reviewable_candidate():
    raw = "Guardianes de\nla comunidad"
    page = f"Proyecto: {raw}\nEscenario: Aula"
    field = fields([page])["proyecto"]
    assert field.value == "Guardianes de la comunidad"
    assert field.status == "ambiguous"
    assert field.review == "pending"
    assert field.evidence[0].excerpt == raw


def test_quoted_multiline_title_has_an_explicit_closing_boundary():
    raw = '"Guardianes de\nla comunidad"'
    field = fields([f"Proyecto: {raw}\nEscenario: Aula"])["proyecto"]
    assert field.value == '"Guardianes de la comunidad"'
    assert field.status == "supported"
    assert field.evidence[0].excerpt == raw


def test_title_block_with_prose_is_never_declared_inequivocal():
    raw = "Guardianes\nConversaremos sobre el barrio."
    field = fields([f"Proyecto: {raw}\nEscenario: Aula"])["proyecto"]
    assert field.status == "ambiguous"
    assert field.value == "Guardianes Conversaremos sobre el barrio."
    assert field.evidence[0].excerpt == raw


@pytest.mark.parametrize("label,key,next_header", [
    ("Proyecto", "proyecto", "Escenario: Aula"),
    ("Propósito", "proposito", "Producto: Herbario"),
    ("Finalidad", "finalidad", "Evaluación: Lista"),
])
def test_empty_label_does_not_consume_the_next_header(label, key, next_header):
    field = fields([f"{label}:\n{next_header}"])[key]
    assert field.value == ""
    assert field.status == "missing"


@pytest.mark.parametrize("label,key", [("Propósito", "proposito"), ("Finalidad", "finalidad")])
@pytest.mark.parametrize("barrier", [
    "Producto: Herbario", "Productos esperados: Carteles", "Evaluacion: Lista",
    "Evaluación formativa: Registro", "Campo: Lenguajes", "Campos formativos: Lenguajes",
    "Materiales: Papel", "Recursos: Tijeras", "Instrumentos de evaluación: Rúbrica",
    "PDA: Describe su entorno", "SESIÓN 1: Observación",
])
def test_explicit_objectives_stop_at_real_structural_headers(label, key, barrier):
    raw = "Identificar plantas del entorno."
    field = fields([f"{label}: {raw}\n{barrier}"])[key]
    assert field.value == raw
    assert field.status == "supported"
    assert field.evidence[0].excerpt == raw


@pytest.mark.parametrize("prose", [
    "Producto cultural que se construye de forma colectiva.",
    "Evaluación colectiva permite revisar decisiones.",
    "Campos formativos se relacionan con el proyecto.",
    "Contenido cultural que compartimos en el grupo.",
])
def test_structural_words_in_continuous_prose_do_not_cut_an_objective(prose):
    raw = f"Comprender el entorno.\n{prose}"
    field = fields([f"Propósito: {raw}\nMateriales: Papel"])["proposito"]
    assert field.value == " ".join(raw.split())
    assert field.evidence[0].excerpt == raw


@pytest.mark.parametrize("prose", [
    "La actividad tiene como propósito observar plantas.",
    "El propósito: observar plantas, se discutirá después.",
    'Leer la frase "Propósito: Observar" en una ficha.',
])
def test_prose_mentions_do_not_create_an_explicit_purpose(prose):
    assert fields([prose])["proposito"].status == "missing"


@pytest.mark.parametrize("label,key", [("Proyecto", "proyecto"), ("Propósito", "proposito"), ("Finalidad", "finalidad")])
def test_value_never_splices_across_physical_pages(label, key):
    page_one = f"{label}: Conocer las plantas de"
    field = fields([page_one, "la comunidad\nProducto: Herbario"])[key]
    assert field.value == "Conocer las plantas de"
    assert field.status == "ambiguous"
    assert len(field.evidence) == 1
    assert field.evidence[0].page_number == 1
    assert field.evidence[0].excerpt == "Conocer las plantas de"


def test_split_label_does_not_join_across_pages():
    field = fields(["Propó", "sito: Observar plantas.\nProducto: Herbario"])["proposito"]
    assert field.status == "missing"


def test_exact_source_page_is_not_found_by_a_duplicated_text_prefix():
    raw = "Observar las plantas del jardín y describir sus diferencias."
    pages = [f'Una frase citada: "Propósito: {raw}"', f"Propósito: {raw}\nProducto: Herbario"]
    field = fields(pages)["proposito"]
    assert field.value == raw
    assert field.evidence[0].page_number == 2
    assert field.evidence[0].excerpt == raw


def test_wrapped_label_and_crlf_keep_source_offsets():
    raw = "Observar  plantas\r\ny\tdescribirlas."
    field = fields(["Portada", f"Propósito para el\r\nalumno:\r\n{raw}\r\nProducto: Herbario"])["proposito"]
    assert field.value == "Observar plantas y describirlas."
    assert field.evidence[0].page_number == 2
    assert field.evidence[0].excerpt == raw


def test_long_multiparagraph_purpose_keeps_complete_literal_evidence():
    raw = ("Comprender los cambios del entorno y describir observaciones. " * 8).strip()
    raw += "\n\nComparar los registros y explicar las diferencias."
    field = fields([f"Propósito:\n{raw}\nProducto: Bitácora"])["proposito"]
    assert field.value == " ".join(raw.split())
    assert field.evidence[0].excerpt == raw
    assert len(field.evidence[0].excerpt) > 200


def test_quoted_header_words_inside_purpose_are_not_structural():
    raw = 'Explicar la etiqueta «Producto: herbario» y la frase "Evaluación: lista".'
    field = fields([f"Propósito: {raw}\nMateriales: Papel"])["proposito"]
    assert field.value == raw


def test_tabular_header_separator_bounds_an_objective_on_the_same_line():
    field = fields(["Propósito: Observar plantas.\tProducto: Herbario"])["proposito"]
    assert field.value == "Observar plantas."


@pytest.mark.parametrize("warning_page,expected", [(1, "supported"), (2, "ambiguous")])
def test_only_source_page_warning_degrades_explicit_purpose(warning_page, expected):
    field = fields(["Portada", "Propósito: Observar plantas.\nProducto: Herbario"], {warning_page: "Captura parcial"})["proposito"]
    assert field.status == expected
    assert field.review == "pending"


def test_legacy_project_scenario_header_is_preserved():
    field = fields(["Proyecto Relatos del patio Escenario Aula.\nCampo: Lenguajes"])["proyecto"]
    assert field.value == "Relatos del patio"
    assert field.status == "supported"


def test_bare_project_prose_does_not_create_supported_project_name():
    field = fields(["Proyecto comunitario orientado a conocer plantas."])["proyecto"]
    assert field.status != "supported"


def test_generated_pdf_prepare_verify_compile_preserves_page_and_pending_review():
    pdf = make_minimal_pdf([
        "Portada administrativa",
        "Proyecto: Relatos del patio\nProposito: Observar plantas.\nProducto: Herbario\n"
        "Finalidad: Desarrollar habilidades de observacion.\nEvaluacion: Lista de cotejo",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf))
    for key in ("proyecto", "proposito", "finalidad"):
        field = dossier.general_fields[key]
        assert field.status == "supported"
        assert field.review == "pending"
        assert field.evidence[0].page_number == 2
    assert dossier.general_fields["proposito"].value == "Observar plantas."
    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf))
    assert not any(i["status"] == "blocked" for i in report.items if i["scope"] == "general")
    restored = ImportDossier.from_dict(dossier.to_dict())
    original_claims = compile_dossier_to_atomic_claims(dossier)
    assert [c.to_dict() for c in compile_dossier_to_atomic_claims(restored)] == [c.to_dict() for c in original_claims]
