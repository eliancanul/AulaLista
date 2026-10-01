"""Authored development regressions, not unseen or pedagogical validation."""

import io

import pytest
from pypdf import PdfReader

from curriculum.claims import compile_dossier_to_atomic_claims
from curriculum.overview_fields import extract_overview_spans
from curriculum.source_interpreter import CurriculumSourceInterpreter, ImportDossier, resolve
from curriculum.verification import verify_curriculum_dossier
from test_t15_curriculum_import import make_minimal_pdf


METHOD = "Metodología Aprendizaje basado en problemas (ABP)"
COLUMNS = "Campos Contenidos Proceso de desarrollo de aprendizajes"
TABLE_BODY = "Lenguajes\nRegistro de preguntas.\nFormula preguntas sobre su entorno."


def _field(pages, key="proposito", warnings=None):
    return CurriculumSourceInterpreter._extract_general_fields(pages, "synthetic-sha", warnings or {})[key]


@pytest.mark.parametrize("label,key", [("Propósito", "proposito"), ("Finalidad", "finalidad")])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("columns", [COLUMNS, "Campos Contenidos PDA"])
@pytest.mark.parametrize("method", [
    METHOD,
    "Metodología Aprendizaje basado en proyectos comunitarios (ABPC)",
    "Metodología Aprendizaje basado en indagación (STEAM)",
    "Metodología Aprendizaje servicio (AS)",
])
def test_complete_metadata_pair_bounds_objective_before_table_body(label, key, newline, columns, method):
    raw = f"Observar el patio.{newline}Comparar preguntas y explicar hallazgos."
    page = f"{label}:{newline}{raw}{newline}{method}{newline}{columns}{newline}{TABLE_BODY}"
    field = _field([page], key)
    span = extract_overview_spans([page])[key]
    expected_value = raw if key == "finalidad" else " ".join(raw.split())

    assert field.value == expected_value
    assert field.status == "supported"
    assert field.review == "pending"
    assert field.operational_state == "needs_review"
    assert field.evidence[0].excerpt == raw
    assert span.excerpt == raw
    assert span.text_start == 0
    assert span.value_start == page.index(raw)
    assert span.text_end == page.index(raw) + len(raw)
    assert page[span.value_start:span.text_end] == raw
    assert span.termination == "header"
    assert TABLE_BODY in page[span.text_end:]


def test_tab_delimited_columns_keep_the_existing_objective_boundary():
    raw = "Observar  el patio.\r\nComparar\tpreguntas."
    page = (
        f"Propósito:\r\n{raw}\r\n"
        "Metodología\tAprendizaje basado en proyectos comunitarios (ABPC)\r\n"
        f"Campos\tContenidos\tPDA\r\n{TABLE_BODY}"
    )
    field = _field([page])
    span = extract_overview_spans([page])["proposito"]
    assert field.value == " ".join(raw.split())
    assert field.status == "supported"
    assert field.review == "pending"
    assert field.evidence[0].excerpt == raw
    assert page[span.value_start:span.text_end] == raw


@pytest.mark.parametrize("raw", [
    f"Comprender la organización del trabajo.\n{METHOD}\npermite formular nuevas preguntas.",
    f"Reconocer la organización de una ficha.\n{COLUMNS}\nson palabras que aparecen en sus etiquetas.",
    f"Reconocer una ficha.\n{METHOD}\nse relaciona con sus apartados.\n{COLUMNS}\nTambién se comentan sus nombres.",
    f"Examinar las etiquetas\n{METHOD}\n{COLUMNS}\ny explicar su significado.",
    f"Comprender la organización del trabajo.\n{METHOD}\nCampos Contenidos\nson dos etiquetas de una ficha.",
    f"Comprender la organización del trabajo.\n{METHOD}\nCampos PDA\nson dos etiquetas de una ficha.",
    "Comprender el producto y la metodología.\nContenido cultural que permite formular preguntas.\n"
    "Explicar la frase Evaluación: lista y su finalidad.",
])
@pytest.mark.parametrize("label,key", [("Propósito", "proposito"), ("Finalidad", "finalidad")])
def test_label_words_and_uncorroborated_rows_preserve_the_complete_candidate(raw, label, key):
    page = f"{label}: {raw}\nProducto: Cuaderno"
    field = _field([page], key)
    expected_value = raw if key == "finalidad" else " ".join(raw.split())
    assert field.value == expected_value
    assert field.status == "ambiguous"
    assert field.review == "pending"
    assert field.evidence[0].excerpt == raw


@pytest.mark.parametrize("opening,closing", [('"', '"'), ("«", "»"), ("“", "”")])
def test_metadata_pair_inside_balanced_quote_remains_objective_text(opening, closing):
    raw = (
        f"Leer el ejemplo {opening}Organizar el trabajo.\n{METHOD}\n{COLUMNS}\n"
        f"Escribir preguntas.{closing} y explicar sus etiquetas."
    )
    field = _field([f"Propósito: {raw}\nProducto: Cuaderno"])
    assert field.value == " ".join(raw.split())
    assert field.status == "supported"
    assert field.review == "pending"
    assert field.evidence[0].excerpt == raw


def test_metadata_pair_inside_unclosed_quote_is_preserved_for_review():
    raw = f'Leer el ejemplo "Organizar el trabajo.\n{METHOD}\n{COLUMNS}\nEscribir preguntas.'
    field = _field([f"Propósito: {raw}"])
    assert field.value == " ".join(raw.split())
    assert field.status == "ambiguous"
    assert field.review == "pending"
    assert field.evidence[0].excerpt == raw


def test_unclosed_quote_in_later_table_body_cannot_hide_prior_objective_boundary():
    raw = "Observar el patio.\nComparar preguntas y explicar hallazgos."
    page = f'Propósito: {raw}\n{METHOD}\n{COLUMNS}\nLenguajes\nLeer el texto "Preguntas abiertas.'
    field = _field([page])
    assert field.value == " ".join(raw.split())
    assert field.status == "supported"
    assert field.review == "pending"
    assert field.evidence[0].excerpt == raw


def test_pair_rule_does_not_change_ambiguous_project_title_semantics():
    raw = f"Agenda de campo.\n{METHOD}\n{COLUMNS}\n{TABLE_BODY}"
    field = _field([f"Proyecto: {raw}"], "proyecto")
    assert field.value == " ".join(raw.split())
    assert field.status == "ambiguous"
    assert field.review == "pending"
    assert field.evidence[0].excerpt == raw


def test_two_metadata_cues_on_different_pages_do_not_create_a_joint_boundary():
    raw = f"Observar el patio.\n{METHOD}"
    pages = [f"Propósito: {raw}", f"{COLUMNS}\n{TABLE_BODY}"]
    field = _field(pages)
    # The already supported single complete row can bound the objective on p1.
    # The separate p2 cue must not be incorporated into its value or evidence.
    assert field.value == "Observar el patio."
    assert len(field.evidence) == 1
    assert field.evidence[0].page_number == 1
    assert field.evidence[0].excerpt == "Observar el patio."


def test_trailing_table_cannot_supply_an_objective_missing_on_this_page():
    pages = ["Propósito: Observar el patio", f"{METHOD}\n{COLUMNS}\n{TABLE_BODY}"]
    field = _field(pages)
    assert field.value == "Observar el patio"
    assert field.status == "ambiguous"
    assert field.review == "pending"
    assert field.evidence[0].page_number == 1
    assert field.evidence[0].excerpt == "Observar el patio"


def test_bounded_objective_keeps_source_page_warning_and_pending_review():
    page = f"Propósito: Observar el patio.\n{METHOD}\n{COLUMNS}\n{TABLE_BODY}"
    field = _field(["Portada", page], warnings={2: "Captura parcial"})
    assert field.value == "Observar el patio."
    assert field.status == "ambiguous"
    assert field.review == "pending"
    assert field.evidence[0].page_number == 2
    assert field.evidence[0].excerpt == "Observar el patio."


def test_prepare_verify_roundtrip_and_explicit_review_keep_boundary_and_evidence():
    purpose = "Observar el patio.\nComparar preguntas y explicar hallazgos."
    page = (
        "Proyecto: Preguntas del patio\nProposito:\n"
        f"{purpose}\nMetodologia Aprendizaje basado en problemas (ABP)\n"
        f"Campos Contenidos PDA\n{TABLE_BODY}\n"
        "SESION 1: Preguntas\nInicio: Observar el patio.\n"
        "Desarrollo: Comparar preguntas.\nCierre: Compartir hallazgos."
    )
    pdf = make_minimal_pdf(["Portada", page])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf))
    field = dossier.general_fields["proposito"]
    source_page = PdfReader(io.BytesIO(pdf)).pages[1].extract_text()
    assert field.value == " ".join(purpose.split())
    assert field.status == "supported"
    assert field.review == "pending"
    assert field.operational_state == "needs_review"
    assert field.evidence[0].page_number == 2
    assert field.evidence[0].excerpt == purpose
    assert field.evidence[0].excerpt in source_page
    assert TABLE_BODY in source_page

    report = verify_curriculum_dossier(dossier, io.BytesIO(pdf))
    purpose_checks = [item for item in report.items if item["path"].startswith("general_fields/proposito")]
    assert purpose_checks
    assert not any(item["status"] == "blocked" for item in purpose_checks)
    assert field.review == "pending"

    restored = ImportDossier.from_dict(dossier.to_dict())
    assert restored.general_fields["proposito"].to_dict() == field.to_dict()
    assert [c.to_dict() for c in compile_dossier_to_atomic_claims(restored)] == [
        c.to_dict() for c in compile_dossier_to_atomic_claims(dossier)
    ]
    assert restored.general_fields["proposito"].review == "pending"
    original_evidence = [e.to_dict() for e in field.evidence]
    reviewed = resolve(restored, {"reviews": {"proposito": "confirmed"}}, actor="Docente sintética")
    assert reviewed.general_fields["proposito"].review == "confirmed"
    assert reviewed.general_fields["proyecto"].review == "pending"
    assert [e.to_dict() for e in reviewed.general_fields["proposito"].evidence] == original_evidence


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\v", "\f", "\x85", "\r", "\x1c", "\x1d", "\x1e", "\n"])
def test_table_pair_requires_adjacent_physical_lines(separator):
    raw = f"Observar el patio.\n{METHOD}\n{separator}{COLUMNS}\n{TABLE_BODY}"
    field = _field(["Propósito: " + raw])
    assert field.evidence[0].excerpt == raw
    assert field.status == "ambiguous"


@pytest.mark.parametrize("ending", ["\r\r\n", "\r \n", "\r\t\n"])
@pytest.mark.parametrize("row", ["method", "columns"])
def test_malformed_carriage_returns_do_not_corroborate_table_rows(ending, row):
    method_end, columns_end = (ending, "\n") if row == "method" else ("\n", ending)
    raw = f"Observar el patio.\n{METHOD}{method_end}{COLUMNS}{columns_end}{TABLE_BODY}"
    field = _field(["Propósito: " + raw])
    assert field.evidence[0].excerpt == raw
    assert field.status == "ambiguous"


@pytest.mark.parametrize("phase", [False, True])
@pytest.mark.parametrize("columns", ["Campos formativos Contenidos PDA", "Campo formativo Contenido Proceso de desarrollo de aprendizajes"])
def test_curricular_column_names_do_not_reset_the_known_campo(phase, columns):
    from curriculum.source_segments import planning_boundary_positions, scan_session_segments, phase_review_scope
    body = ("DESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Observar semillas.\n" if phase else
            "SESIÓN 1: Observar\nInicio: Observar semillas.\nCierre: Compartir registros.\n")
    page = ("Proyecto: Semillas\nCampo formativo: Lenguajes\n" + body
            + f"Propósito: Leer una ficha.\n{METHOD}\n{columns}\n{TABLE_BODY}\n"
            + "DATOS GENERALES\nCampo formativo: Saberes y pensamiento científico\n"
            + "Intención didáctica: Medir objetos.\n"
            + ("Fase 1\nActividad 1: Medir piedras." if phase else
               "SESIÓN 2: Medir\nInicio: Medir piedras.\nCierre: Comparar medidas."))
    assert planning_boundary_positions([page]) == {1: [page.index("DATOS GENERALES")]}
    if phase:
        assigned, unassigned = phase_review_scope([page], "synthetic-sha", 1)
        assert "Medir piedras" not in assigned[0][1]
        assert unassigned[0][1].startswith("DATOS GENERALES")
    else:
        first, second = scan_session_segments([page], "synthetic-sha")
        assert "DATOS GENERALES" not in first.page_segments[0][1]
        assert first.unassigned_segments[0][1].startswith("DATOS GENERALES")
        assert second.project_context["title_status"] == "missing"


def test_unknown_explicit_campo_still_prevents_inferred_comparison_with_older_value():
    from curriculum.source_segments import planning_boundary_positions
    page = ("Campo formativo: Lenguajes\nSESIÓN 1: Observar\nInicio: Observar.\n"
            "Campo formativo: Nombre desconocido\nDATOS GENERALES\n"
            "Campo formativo: Saberes y pensamiento científico\nIntención didáctica: Medir.")
    assert planning_boundary_positions([page]) == {1: []}
