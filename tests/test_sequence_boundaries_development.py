"""Synthetic development regressions derived from #144's structural pattern.

Authored text only: no pilot PDF, extracted pilot output, or held-out evaluation.
These assertions measure software behavior, not pedagogical/human validation.
"""

import copy
import hashlib
import io

import pytest

from curriculum.source_interpreter import (
    CurriculumSourceInterpreter, ImportDossier, InterpretedField, SessionPlan,
    SourceReference, preserve_reextract_decisions, resolve,
)
from curriculum.source_segments import planning_boundary_positions, scan_session_segments
from curriculum.verification import verify_curriculum_dossier
from test_t15_curriculum_import import make_minimal_pdf


OLD_METADATA = (
    "DATOS GENERALES\nCampo formativo: Lenguajes\n"
    "INTENCIÓN DIDÁCTICA: Describir objetos del entorno.\n"
)
NEW_METADATA = (
    "DATOS GENERALES\nCampo formativo: Saberes y pensamiento científico\n"
    "INTENCIÓN DIDÁCTICA: Comparar longitudes con unidades propias.\n"
)
SESSION = (
    "SESIÓN 1: Describir\nInicio: Observar una piedra.\n"
    "Desarrollo: Dibujar sus detalles.\nCierre: Compartir la descripción.\n"
    "Producto del proyecto: Un dibujo.\nEvaluación: Registro breve.\n"
    "Recursos: Papel y colores.\n"
)
NEXT_BODY = "Inicio: Comparar dos listones.\nDesarrollo: Registrar sus longitudes.\nCierre: Explicar la comparación.\n"


def source(pages):
    content = "\n---DEVELOPMENT-PAGE---\n".join(pages).encode()
    return content, hashlib.sha256(content).hexdigest(), pages


def dossier_for(pages):
    _, sha, _ = source(pages)
    return ImportDossier(
        source_sha256=sha, source_name="synthetic-development-144.pdf", page_count=len(pages),
        general_fields=CurriculumSourceInterpreter._extract_general_fields(pages, sha, {}),
        sessions=CurriculumSourceInterpreter._detect_sessions(pages, sha, [], {}),
    )


def fixture_pages(next_body=NEXT_BODY):
    return [OLD_METADATA + "Proyecto: Objetos cercanos\n" + SESSION, NEW_METADATA + next_body]


def checked_for(report, prefix):
    return any(item["status"] == "checked" and item["target"].startswith(prefix) for item in report.items)


def test_new_untitled_planning_block_does_not_continue_previous_session():
    body = NEXT_BODY + "Actividad de comparación: Ordenar listones por longitud.\n"
    pages = fixture_pages(body)
    d = dossier_for(pages)
    assert len(d.sessions) == 1  # Do not invent another session/project.
    s = d.sessions[0]
    assert s.pages == [1]
    assert s.continues_on == []
    assert all("listones" not in a.description and "longitudes" not in a.description for a in s.activities)
    assert NEW_METADATA + body in s.layout_notes
    assert "página física 2" in s.layout_notes
    assert s.status == "ambiguous"
    assert s.fields["cierre"].status == "ambiguous"


def test_untitled_restart_invalidates_prior_project_context_for_later_explicit_session():
    pages = fixture_pages("SESIÓN 2: Comparar\n" + NEXT_BODY)
    first, second = dossier_for(pages).sessions
    assert first.project_title == "Objetos cercanos"
    assert second.project_title == ""
    assert second.project_context["status"] == "missing"
    assert second.project_context["anchor"] is None
    assert second.project_context["project_id"] is None
    assert second.project_context["review"] == "pending"


def test_verifier_recomputes_restart_even_when_dossier_hides_uncertainty():
    pages = fixture_pages()
    d = dossier_for(pages)
    s = d.sessions[0]
    s.pages = [1, 2]
    s.layout_notes = ""
    s.status = "supported"
    s.fields["inicio"].value = "Comparar dos listones."
    s.fields["inicio"].origin, s.fields["inicio"].status = "extracted", "supported"
    s.fields["inicio"].evidence[0].page_number = 2
    s.fields["inicio"].evidence[0].excerpt = "Comparar dos listones."
    assert not checked_for(verify_curriculum_dossier(d, source(pages)), "session.p1_s1.inicio")


def test_old_context_cannot_be_transplanted_after_restart():
    pages = fixture_pages("SESIÓN 2: Comparar\n" + NEXT_BODY)
    d = dossier_for(pages)
    d.sessions[1].project_context = copy.deepcopy(d.sessions[0].project_context)
    d.sessions[1].project_title = d.sessions[0].project_title
    report = verify_curriculum_dossier(d, source(pages))
    assert any(i["status"] == "blocked" and i["target"] == "session.p2_s2.project_context" for i in report.items)


@pytest.mark.parametrize("prefix", [
    "",
    OLD_METADATA,
    "DATOS GENERALES\n",  # An isolated heading is not a universal boundary.
    "Campo formativo: Saberes y pensamiento científico\n",
    "INTENCIÓN DIDÁCTICA: Comparar longitudes.\n",
    "El texto menciona DATOS GENERALES y Campo formativo: Lenguajes.\n",
    'Leer el siguiente ejemplo: "\n' + NEW_METADATA + '"\n',
])
def test_legitimate_continuation_and_repeated_or_quoted_headings_are_retained(prefix):
    pages = [OLD_METADATA + "Proyecto: Objetos cercanos\n" + SESSION, prefix + "Cierre: Continuar la descripción.\n"]
    segments = scan_session_segments(pages, source(pages)[1])
    assert [p for p, _ in segments[0].page_segments] == [1, 2]
    assert "Continuar la descripción." in segments[0].page_segments[1][1]
    assert not segments[0].unassigned_segments


@pytest.mark.parametrize("metadata", [
    NEW_METADATA.replace("Campo formativo:", "Campos formativos:\n"),
    NEW_METADATA.replace("INTENCIÓN DIDÁCTICA:", "Intencion didactica\n"),
    NEW_METADATA.replace(" ", "\u00a0"),
])
def test_label_variants_preserve_literal_offsets_and_page_numbers(metadata):
    pages = fixture_pages()
    pages[1] = metadata + NEXT_BODY
    segment = scan_session_segments(pages, source(pages)[1])[0]
    assert segment.page_segments == [(1, SESSION)]
    assert segment.unassigned_segments == [(2, metadata + NEXT_BODY)]
    anchor = segment.header_anchor
    assert anchor["document_sha256"] == source(pages)[1]
    assert anchor["excerpt"] == pages[0][anchor["text_start"]:anchor["text_end"]]


@pytest.mark.parametrize("metadata", [
    OLD_METADATA.replace("Lenguajes", "LENGUAJES."),
    OLD_METADATA.replace("Describir objetos del entorno.", "Otra intención dentro del mismo campo."),
    NEW_METADATA.replace("Saberes y pensamiento científico", "El grupo lee sobre Lenguajes"),
    NEW_METADATA.replace("Saberes y pensamiento científico", ""),
    NEW_METADATA.replace("INTENCIÓN DIDÁCTICA:", "Inicio: Una actividad intermedia.\nINTENCIÓN DIDÁCTICA:"),
    NEW_METADATA.replace("DATOS GENERALES", "Los DATOS GENERALES se mencionan en este relato."),
    NEW_METADATA.replace("DATOS GENERALES", "DATOS GENERALES para el ejemplo"),
    "INTENCIÓN DIDÁCTICA: Comparar.\nDATOS GENERALES\nCampo formativo: Saberes y pensamiento científico\n",
])
def test_incomplete_or_repeated_structure_does_not_infer_a_boundary(metadata):
    pages = fixture_pages()
    pages[1] = metadata + NEXT_BODY
    assert not any(planning_boundary_positions(pages).values())


def test_same_page_reset_cuts_at_exact_physical_position():
    pages = ["".join(fixture_pages())]
    d = dossier_for(pages)
    segment = scan_session_segments(pages, d.source_sha256)[0]
    assert segment.page_segments == [(1, SESSION)]
    assert segment.unassigned_segments == [(1, NEW_METADATA + NEXT_BODY)]
    assert NEW_METADATA + NEXT_BODY in d.sessions[0].layout_notes
    assert d.sessions[0].fields["cierre"].value == "Compartir la descripción."


def test_continuation_prefix_before_a_reset_is_retained_without_crossing_it():
    pages = fixture_pages()
    prefix = "Cierre: Terminar el dibujo anterior.\n"
    pages[1] = prefix + pages[1]
    segment = scan_session_segments(pages, source(pages)[1])[0]
    assert segment.page_segments == [(1, SESSION), (2, prefix.strip())]
    assert segment.unassigned_segments == [(2, NEW_METADATA + NEXT_BODY)]


def test_context_reset_survives_a_page_without_sessions_and_later_project_restores_context():
    pages = fixture_pages()
    pages += ["SESIÓN 2: Comparar\n" + NEXT_BODY, "Proyecto: Medidas cercanas\nSESIÓN 3: Repetir\n" + NEXT_BODY]
    sessions = dossier_for(pages).sessions
    assert [s.project_title for s in sessions] == ["Objetos cercanos", "", "Medidas cercanas"]
    assert sessions[1].project_context["anchor"] is None
    assert sessions[2].project_context["anchor"]["page_number"] == 4


def test_initial_metadata_after_a_project_does_not_erase_it():
    pages = ["Proyecto: Objetos cercanos\n" + OLD_METADATA + SESSION]
    assert not any(planning_boundary_positions(pages).values())
    assert dossier_for(pages).sessions[0].project_context["anchor"] is not None


@pytest.mark.parametrize("mutation", ["legacy", "wrong_page", "wrong_sha"])
def test_transferred_citation_never_becomes_checked_by_changing_metadata(mutation):
    pages = fixture_pages("SESIÓN 2: Comparar\n" + NEXT_BODY)
    d = dossier_for(pages)
    d.sessions[0].fields["inicio"] = copy.deepcopy(d.sessions[1].fields["inicio"])
    d.sessions = d.sessions[:1]  # A declared subset cannot change source limits.
    s = d.sessions[0]
    s.pages = [1, 2]
    if mutation == "legacy":
        s.header_anchor = s.project_context = None
        s.layout_notes = ""
    elif mutation == "wrong_page":
        s.fields["inicio"].evidence[0].page_number = 1
    else:
        s.fields["inicio"].evidence[0].document_sha256 = "foreign-sha"
    report = verify_curriculum_dossier(ImportDossier.from_dict(d.to_dict()), source(pages))
    assert not checked_for(report, "session.p1_s1.inicio")
    if mutation != "legacy":
        assert any(i["status"] == "blocked" and i["target"].startswith("session.p1_s1.inicio") for i in report.items)


@pytest.mark.parametrize("review", ["corrected", "confirmed", "postponed"])
def test_reextract_retains_human_work_in_history_without_confirming_changed_scope(review):
    pages = fixture_pages()
    old = dossier_for(pages)
    action = {"session_id": "p1_s1", "reviews": {"inicio": review}}
    if review == "corrected":
        action["session_fields"] = {"inicio": "Decisión escrita por la docente."}
    old = resolve(old, action, actor="Docente de prueba sintética")
    before = old.sessions[0].fields["inicio"].to_dict()
    old.history = []  # Exercise legacy dossiers with no earlier decision snapshot.
    fresh = dossier_for(pages)
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    f = fresh.sessions[0].fields["inicio"]
    assert f.review == "pending"
    assert any(d["before"] == before and d["change_type"] == "decision_requires_review" for d in deltas)
    if review == "corrected":
        assert f.value == "Decisión escrita por la docente."
        assert f.origin == "teacher_entered"
        assert f.evidence == old.sessions[0].fields["inicio"].evidence


def test_reextract_preserves_unchanged_decision_in_later_explicit_session():
    pages = fixture_pages("SESIÓN 2: Comparar\n" + NEXT_BODY)
    old = resolve(dossier_for(pages), {"session_id": "p2_s2", "reviews": {"inicio": "confirmed"}}, actor="Docente")
    fresh = dossier_for(pages)
    before = copy.deepcopy(old.to_dict())
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    assert fresh.sessions[1].fields["inicio"].review == "confirmed"
    assert fresh.sessions[1].project_title == ""
    assert old.to_dict() == before
    assert any(d["change_type"] == "retained_decision" for d in deltas)


def test_synthetic_pdf_round_trip_prepare_and_verify_keep_source_and_uncertainty():
    content = make_minimal_pdf(fixture_pages())
    d = CurriculumSourceInterpreter.prepare(io.BytesIO(content))
    restored = ImportDossier.from_dict(d.to_dict())
    s = restored.sessions[0]
    assert restored.source_sha256 == hashlib.sha256(content).hexdigest()
    assert s.pages == [1]
    assert "DATOS GENERALES" in s.layout_notes
    assert "página física 2" in s.layout_notes
    assert s.header_anchor == d.sessions[0].header_anchor
    assert s.review == "pending"
    report = verify_curriculum_dossier(restored, io.BytesIO(content))
    assert report.blocked_count == 0
    assert not checked_for(report, "session.p1_s1.inicio")


def test_planning_structure_prevents_whole_page_legacy_verification():
    pages = [OLD_METADATA + "Inicio: Observar una piedra.\n", NEW_METADATA + NEXT_BODY]
    d = dossier_for(pages)
    assert not d.sessions
    d.sessions = [SessionPlan(session_id="legacy-A", session_number=1, title="Legacy", pages=[1, 2], fields={
        "inicio": InterpretedField(name="inicio", value="Comparar dos listones.", evidence=[
            SourceReference(d.source_sha256, 2, excerpt="Comparar dos listones."),
        ]),
    })]
    assert not checked_for(verify_curriculum_dossier(d, source(pages)), "session.legacy-A.inicio")


def test_existing_phase_review_is_also_bounded_by_an_untitled_restart():
    phase_body = "DESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Observar una piedra.\n"
    pages = [OLD_METADATA + "Proyecto: Objetos cercanos\n" + phase_body, NEW_METADATA + "Actividad 1: Comparar dos listones.\n"]
    d = dossier_for(pages)
    assert len(d.sessions) == 1
    s = d.sessions[0]
    assert s.session_id.endswith("_project_review")
    assert s.pages == [1]
    assert s.status == "ambiguous"
    assert all("listones" not in a.description for a in s.activities)
    assert NEW_METADATA in s.layout_notes
    s.layout_notes = ""
    f = s.fields["inicio"]
    f.status, f.origin = "supported", "extracted"
    assert not checked_for(verify_curriculum_dossier(d, source(pages)), f"session.{s.session_id}.inicio")


def test_phase_context_cannot_reuse_a_title_from_before_an_untitled_restart():
    pages = [OLD_METADATA + "Proyecto: Objetos cercanos\nCierre: Compartir.\n", NEW_METADATA +
             "DESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Comparar dos listones.\n"]
    d = dossier_for(pages)
    assert d.sessions[0].project_title == ""
    assert d.sessions[0].project_context["status"] == "missing"


def test_repeated_multi_campo_header_is_not_a_reset_when_order_or_accents_change():
    pages = fixture_pages()
    pages[0] = pages[0].replace("Campo formativo: Lenguajes", "Campos formativos: Lenguajes; Saberes y pensamiento científico")
    pages[1] = pages[1].replace("Saberes y pensamiento científico", "Saberes y pensamiento cientifico; LENGUAJES")
    assert not any(planning_boundary_positions(pages).values())


def test_development_boundary_notes_remain_visible_in_review_ui():
    from django.template.loader import render_to_string
    from types import SimpleNamespace

    d = dossier_for(fixture_pages())
    s = d.sessions[0]
    html = render_to_string("curriculum/tutor_import_interpretation.html", {
        "dossier": d, "selected_session": s, "active_session_id": s.session_id,
        "active_session_number": 1, "job": SimpleNamespace(pk=1),
    })
    assert "Organización de la fuente pendiente de revisión" in html
    assert "Tramo sin asignar, página física 2" in html
    assert "Comparar dos listones." in html
    assert s.pages == [1]  # Review notes do not confer session membership.
    assert "Ver página física 1" in html


def test_unclosed_quote_cannot_hide_composite_restart_from_extraction_or_verifier():
    pages = fixture_pages()
    pages[1] = 'Una nota dice: “\n' + pages[1]
    d = dossier_for(pages)
    s = d.sessions[0]
    assert s.pages == [1]
    assert s.status == "ambiguous"
    assert NEW_METADATA + NEXT_BODY in s.layout_notes
    s.pages = [1, 2]
    s.layout_notes = ""
    f = s.fields["inicio"]
    f.value = f.evidence[0].excerpt = "Comparar dos listones."
    f.evidence[0].page_number = 2
    f.origin, f.status = "extracted", "supported"
    assert not checked_for(verify_curriculum_dossier(d, source(pages)), "session.p1_s1.inicio")


def test_a_new_explicit_project_before_metadata_resets_restart_detection():
    pages = fixture_pages()
    pages[1] = "Proyecto: Medidas cercanas\n" + NEW_METADATA + "SESIÓN 2: Comparar\n" + NEXT_BODY
    d = dossier_for(pages)
    s = d.sessions[1]
    assert s.project_context["anchor"] is not None
    assert s.project_context["anchor"]["page_number"] == 2
    assert s.project_context["anchor"]["text_start"] == 0
    assert s.project_title.startswith("Medidas cercanas")
    assert s.project_context["review"] == "pending"
    assert not any(planning_boundary_positions(pages).values())


def test_phase_reset_preserves_all_excluded_pages_up_to_the_next_project():
    phase_body = "DESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Observar una piedra.\n"
    page_three = "Actividad 2: Conservar esta página completa.\n"
    pages = [OLD_METADATA + "Proyecto: Objetos cercanos\n" + phase_body,
             NEW_METADATA + "Actividad 1: Comparar dos listones.\n", page_three,
             "Proyecto: Un título posterior\nActividad 1: Otra unidad.\n"]
    d = dossier_for(pages)
    s = d.sessions[0]
    assert s.pages == [1]
    assert pages[1] in s.layout_notes
    assert page_three in s.layout_notes
    assert "página física 3" in s.layout_notes
    assert "Un título posterior" not in s.layout_notes
    assert len(d.sessions) == 1


@pytest.mark.parametrize("barrier,retain_barrier_page", [
    ("ANEXOS\nFicha externa a la unidad.\n", False),
    ("Productos y evidencias de aprendizaje\nDibujo final.\n", True),
])
def test_phase_notes_preserve_existing_annex_and_product_stops(barrier, retain_barrier_page):
    phase_body = "DESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Observar una piedra.\n"
    pages = [OLD_METADATA + "Proyecto: Objetos cercanos\n" + phase_body,
             NEW_METADATA + "Actividad 1: Comparar dos listones.\n", barrier,
             "Texto posterior que no pertenecía a la unidad.\n"]
    s = dossier_for(pages).sessions[0]
    assert s.pages == [1]
    assert pages[1] in s.layout_notes
    assert (barrier in s.layout_notes) is retain_barrier_page
    assert pages[3] not in s.layout_notes


@pytest.mark.parametrize("sid", ["p1_project_review", "p2_project_review", "legacy_project_review"])
def test_phase_verifier_cannot_relocate_the_source_unit_using_declared_pages(sid):
    phase_a = "DESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Observar una piedra.\n"
    phase_b = "DESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Comparar dos listones.\n"
    pages = [OLD_METADATA + "Proyecto: Objetos cercanos\n" + phase_a, NEW_METADATA + phase_b]
    d = dossier_for(pages)
    assert len(d.sessions) == 1
    s = d.sessions[0]
    s.session_id, s.pages = sid, [2]
    s.project_context = s.header_anchor = None
    s.layout_notes, s.status = "", "supported"
    f = s.fields["inicio"]
    f.value, f.origin, f.status = "Comparar dos listones.", "extracted", "supported"
    f.evidence = [SourceReference(d.source_sha256, 2, excerpt="Comparar dos listones.")]
    assert not checked_for(verify_curriculum_dossier(d, source(pages)), f"session.{sid}.inicio")


def test_unique_legacy_phase_unit_still_verifies_with_its_true_source_page():
    pages = [OLD_METADATA + "Proyecto: Objetos cercanos\nDESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Observar una piedra.\n"]
    d = dossier_for(pages)
    s = d.sessions[0]
    s.session_id = "legacy_project_review"
    s.project_context = s.header_anchor = None
    f = s.fields["inicio"]
    f.origin, f.status = "extracted", "supported"
    assert checked_for(verify_curriculum_dossier(d, source(pages)), "session.legacy_project_review.inicio")
