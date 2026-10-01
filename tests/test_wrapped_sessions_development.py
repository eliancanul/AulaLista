"""Eight authored development fixture families; no external source text or gold.

Only the label + one LF/CRLF + standalone positive number + immediate moment
form is newly admitted. Unknown headings still cut scope without becoming units.
"""

import copy
import io

import pytest

from curriculum.source_interpreter import (
    CurriculumSourceInterpreter, ImportDossier, preserve_reextract_decisions, resolve,
)
from curriculum.source_segments import scan_session_segments
from curriculum.verification import verify_curriculum_dossier
from test_project_session_context import dossier_for, session_text, source


@pytest.mark.parametrize("newline,space,number,moment,separator", [
    ("\n", "", "6", "Inicio", "\n"),
    ("\n", "", "8", "Inicio", ": "),
    ("\r\n", " ", "2", "Inicio", ": "),
    ("\n", "\t", "0012", "Inicio", ": "),
    ("\n", "\u00a0", "3", "Inicio", ": "),
    ("\r\n", "\u202f", "4", "Inicio", ": "),
    ("\n", "\u2009", "5", "Desarrollo", ": "),
    ("\n", "\u3000", "7", "Cierre", ": "),
])
def test_standalone_wrapped_number_preserves_literal_physical_anchor(newline, space, number, moment, separator):
    header = f"{space}SESIÓN{space}{newline}{space}{number}{space}"
    page = "Proyecto: Semillas\n" + header + newline + f"{space}{moment}{separator}Observar semillas.\n"
    d = dossier_for([page])
    assert len(d.sessions) == 1
    s = d.sessions[0]
    assert s.session_id == f"p1_s{int(number)}"
    assert s.session_number == int(number)
    a = s.header_anchor
    assert a["excerpt"] == page[a["text_start"]:a["text_end"]]
    assert a["excerpt"].strip() == header.strip()
    assert a["kind"] == "session" and a["occurrence"] == 1
    assert a["page_number"] == 1 and a["document_sha256"] == d.source_sha256
    assert s.review == "pending" and s.layout_fidelity == "linearized_heuristics"
    assert s.project_context["origin"] == "proposed"
    assert s.project_context["review"] == "pending"
    assert s.project_context["status"] == "ambiguous"


def test_wrapped_session_continues_only_to_prefix_before_next_session():
    pages = [
        "Proyecto: Semillas\n" + session_text(end="Cerrar observación inicial.")
        + "SESIÓN\n6\nInicio: Preparar macetas.\n",
        "Desarrollo: Sembrar semillas.\nCierre: Compartir registros.\n"
        "SESIÓN 7: Otra tarea\nInicio: Medir piedras.\nCierre: Guardar piedras.\n",
    ]
    d = dossier_for(pages)
    assert [s.session_id for s in d.sessions] == ["p1_s1", "p1_s6", "p2_s7"]
    first, wrapped, following = d.sessions
    assert first.pages == [1] and wrapped.pages == [1, 2] and following.pages == [2]
    assert wrapped.continues_on == [2]
    assert "Preparar macetas" not in first.fields["cierre"].value
    assert "piedras" not in wrapped.fields["cierre"].value
    assert all(not s.unassigned_segments for s in scan_session_segments(pages, d.source_sha256))
    for name, page_number in (("inicio", 1), ("desarrollo", 2), ("cierre", 2)):
        assert wrapped.fields[name].evidence
        for evidence in wrapped.fields[name].evidence:
            assert evidence.page_number == page_number
            assert evidence.excerpt in pages[page_number - 1]
    report = verify_curriculum_dossier(d, source(pages))
    assert report.blocked_count == 0
    assert any(i["status"] == "checked" and i["target"].startswith("session.p1_s6.desarrollo") for i in report.items)
    wrapped.fields["inicio"] = copy.deepcopy(following.fields["inicio"])
    wrapped.header_anchor = wrapped.project_context = None
    d.sessions = [wrapped]
    items = verify_curriculum_dossier(d, source(pages)).items
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s6.inicio") for i in items)


@pytest.mark.parametrize("parts", [
    ["SESIÓN\n1: Observar\nInicio: Mirar semillas."],
    ["SESIÓN\n1. Observar\nInicio: Mirar semillas."],
    ["SESIÓN\n1.\nInicio: Mirar semillas."],
    ["SESIÓN\n1)\nInicio: Mirar semillas."],
    ["SESIÓN\n6 de noviembre\nInicio: Mirar semillas."],
    ["SESIÓN\n06/11/2026\nInicio: Mirar semillas."],
    ["SESIÓN\n2026-11-06\nInicio: Mirar semillas."],
    ["SESIÓN\n0\nInicio: Mirar semillas."],
    ["SESIÓN\n000\nInicio: Mirar semillas."],
    ["SESIÓN\n-1\nInicio: Mirar semillas."],
    ["SESIÓN\n+1\nInicio: Mirar semillas."],
    ["SESIÓN\n1.5\nInicio: Mirar semillas."],
    ["SESIÓN\n\n6\nInicio: Mirar semillas."],
    ["SESIÓN\n6\n\nInicio: Mirar semillas."],
    ["SESIÓN\n6\nNota intermedia.\nInicio: Mirar semillas."],
    ["SESIÓN\n6\nInicio de una historia sobre semillas."],
    ["SESIÓN\n6"],
    ["SESIÓN\u20286\nInicio: Mirar semillas."],
    ["SESIÓN\u20296\nInicio: Mirar semillas."],
    ["SESIÓN\n6\u2028Inicio: Mirar semillas."],
    ["SESIÓN\n6\u2029Inicio: Mirar semillas."],
    ["SESIÓN", "6\nInicio: Mirar semillas."],
    ["SESIÓN\n6", "Inicio: Mirar semillas."],
])
def test_unsupported_wrapped_headers_do_not_create_sessions(parts):
    pages = ["Proyecto: Semillas\n" + parts[0], *parts[1:]]
    assert dossier_for(pages).sessions == []


@pytest.mark.parametrize("close_quote", [True, False])
def test_quoted_wrapped_header_remains_only_a_conservative_cut(close_quote):
    quote = 'Texto citado:\n"\nSESIÓN\n6\nInicio: Texto dentro de una cita.\n'
    if close_quote:
        quote += '"\n'
    pages = ["Proyecto: Semillas\n" + session_text() + quote]
    d = dossier_for(pages)
    assert [s.session_id for s in d.sessions] == ["p1_s1"]
    s = d.sessions[0]
    assert s.status == "ambiguous" and s.review == "pending"
    assert "Texto dentro de una cita" not in s.fields["cierre"].value
    assert "Tramo sin asignar" in s.layout_notes
    s.layout_notes = ""
    s.status = "supported"
    s.fields["inicio"].status = "supported"
    s.fields["inicio"].origin = "extracted"
    items = verify_curriculum_dossier(d, source(pages)).items
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1.inicio") for i in items)


def test_mixed_inline_and_wrapped_repetitions_keep_occurrences_and_scope():
    pages = [
        "Proyecto: Semillas\nSESIÓN\n01\nInicio: Mirar semillas.\nCierre: Dibujar semillas.\n"
        + session_text(start="Mirar piedras.", end="Dibujar piedras.")
        + "SESIÓN\n1\nInicio: Mirar hojas.\nCierre: Dibujar hojas.\n",
    ]
    d = dossier_for(pages)
    assert [s.session_id for s in d.sessions] == ["p1_s1", "p1_s1_2", "p1_s1_3"]
    assert [s.header_anchor["occurrence"] for s in d.sessions] == [1, 2, 3]
    assert [s.fields["inicio"].value for s in d.sessions] == ["Mirar semillas.", "Mirar piedras.", "Mirar hojas."]
    assert len({s.header_anchor["text_start"] for s in d.sessions}) == 3
    original = copy.deepcopy(d.sessions[0].header_anchor)
    d.sessions[0].header_anchor = copy.deepcopy(d.sessions[2].header_anchor)
    items = verify_curriculum_dossier(d, source(pages)).items
    assert any(i["status"] == "blocked" and i["target"] == "session.p1_s1.header_anchor" for i in items)
    d.sessions[0].header_anchor = original
    d.sessions[0].fields["inicio"] = copy.deepcopy(d.sessions[2].fields["inicio"])
    d.sessions[0].header_anchor = d.sessions[0].project_context = None
    d.sessions = d.sessions[:1]
    items = verify_curriculum_dossier(d, source(pages)).items
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1.inicio") for i in items)


@pytest.mark.parametrize("member,value", [
    ("text_start", True), ("text_end", 100000), ("excerpt", "SESIÓN 6"), ("occurrence", 2),
])
def test_pdf_prepare_round_trip_and_verifier_recompute_wrapped_anchor(member, value):
    from test_t15_curriculum_import import make_minimal_pdf
    pages = [
        "Proyecto: Semillas\nSESIÓN\n6\nInicio: Preparar macetas.\n",
        "Desarrollo: Sembrar semillas.\nCierre: Compartir registros.\n",
    ]
    content = make_minimal_pdf(pages)
    d = CurriculumSourceInterpreter.prepare(io.BytesIO(content), {"session_id": "p1_s6"})
    assert d.selection["session_id"] == "p1_s6"
    restored = ImportDossier.from_dict(d.to_dict())
    assert restored.sessions[0].header_anchor == d.sessions[0].header_anchor
    assert restored.sessions[0].pages == [1, 2]
    assert restored.sessions[0].review == "pending"
    report = verify_curriculum_dossier(restored, content)
    assert report.blocked_count == 0
    assert any(i["status"] == "checked" and i["target"].startswith("session.p1_s6.cierre") for i in report.items)
    restored.sessions[0].header_anchor[member] = value
    tampered = verify_curriculum_dossier(restored, content)
    assert any(i["status"] == "blocked" and i["target"] == "session.p1_s6.header_anchor" for i in tampered.items)


@pytest.mark.parametrize("tail", [
    ["Rúbrica de evaluación\nCriterios de evaluación\nCierre: Revisar una tabla."],
    ["Texto institucional sin momento.", "Desarrollo: Texto de una página distante."],
    ["Proyecto: Otro proyecto\nInicio: Texto de otro bloque."],
])
def test_wrapped_session_keeps_existing_continuation_barriers(tail):
    pages = ["Proyecto: Semillas\nSESIÓN\n6\nInicio: Preparar macetas.\n", *tail]
    d = dossier_for(pages)
    assert len(d.sessions) == 1
    assert d.sessions[0].pages == [1]
    assert d.sessions[0].continues_on == []


@pytest.mark.parametrize("old_shape", ["same_occurrence", "previously_omitted_first_occurrence"])
def test_human_decisions_follow_literal_occurrence_after_wrapped_recovery(old_shape):
    pages = [
        "Proyecto: Semillas\nSESIÓN\n1\nInicio: Mirar semillas.\nCierre: Dibujar semillas.\n"
        + session_text(start="Mirar piedras.", end="Dibujar piedras."),
    ]
    fresh = dossier_for(pages)
    assert len(fresh.sessions) == 2
    old = copy.deepcopy(fresh)
    if old_shape == "same_occurrence":
        old = resolve(old, {"session_id": "p1_s1", "session_fields": {"inicio": "Consigna docente."}}, actor="Docente")
        expected_change = "retained_decision"
    else:
        # Historical detector emitted only the inline occurrence with its first ID.
        # Retain that physical slice while simulating its former occurrence number.
        old.sessions = [old.sessions[1]]
        old.sessions[0].session_id = "p1_s1"
        old.sessions[0].header_anchor["occurrence"] = 1
        old = resolve(old, {"session_id": "p1_s1", "session_fields": {"inicio": "Consigna para piedras."}}, actor="Docente")
        expected_change = "decision_not_reapplied"
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    assert any(d["change_type"] == expected_change for d in deltas)
    if old_shape == "same_occurrence":
        assert fresh.sessions[0].fields["inicio"].value == "Consigna docente."
        assert fresh.sessions[0].fields["inicio"].origin == "teacher_entered"
    else:
        assert [s.fields["inicio"].value for s in fresh.sessions] == ["Mirar semillas.", "Mirar piedras."]
        assert all(s.fields["inicio"].review == "pending" for s in fresh.sessions)
        assert any(d.get("before", {}).get("value") == "Consigna para piedras." for d in deltas)


@pytest.mark.parametrize("separator", ["\x1c", "\x1d", "\x1e"])
def test_other_python_line_separators_do_not_become_horizontal_space(separator):
    page = f"SESIÓN\n{separator}2\nInicio: Observar semillas."
    assert len(page.splitlines()) == 4
    assert scan_session_segments([page], "synthetic-sha") == []


def test_many_leading_zeros_do_not_overflow_number_conversion_or_rewrite_anchor():
    digits = "0" * 4300 + "17"
    page = f"SESIÓN\n{digits}\nInicio: Observar semillas."
    segment, = scan_session_segments([page], "synthetic-sha")
    assert segment.session_number == 17
    assert digits in segment.header_anchor["excerpt"]


def test_unconvertible_integer_keeps_literal_unassigned_scope_without_crashing():
    tail = "SESIÓN\n" + "9" * 4301 + "\nInicio: Texto de ámbito incierto."
    pages = ["Proyecto: Semillas\n" + session_text() + tail]
    segment, = scan_session_segments(pages, source(pages)[1])
    assert segment.session_number == 1
    assert tail not in segment.page_segments[0][1]
    assert segment.unassigned_segments == [(1, tail)]
    dossier = dossier_for(pages)
    assert len(dossier.sessions) == 1
    assert dossier.sessions[0].status == "ambiguous"
