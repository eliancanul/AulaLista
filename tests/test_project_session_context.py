"""Authored structural fixtures for #141; no pedagogical gold/holdout claims."""

import copy
import hashlib

import pytest

from curriculum.claims import compile_dossier_to_atomic_claims
from curriculum.source_interpreter import (
    CurriculumSourceInterpreter, ImportDossier, SessionPlan,
    derive_operational_queue,
)
from curriculum.verification import verify_curriculum_dossier


def session_text(title="Observar", start="Mirar el paisaje.", end="Compartir hallazgos."):
    return f"SESIÓN 1: {title}\nInicio: {start}\nDesarrollo: Dibujar registros.\nCierre: {end}\n"


def source(pages):
    content = "\n---PAGE---\n".join(pages).encode()
    return content, hashlib.sha256(content).hexdigest(), pages


def dossier_for(pages):
    _, sha, _ = source(pages)
    return ImportDossier(
        source_sha256=sha, source_name="synthetic.pdf", page_count=len(pages),
        general_fields=CurriculumSourceInterpreter._extract_general_fields(pages, sha, {}),
        sessions=CurriculumSourceInterpreter._detect_sessions(pages, sha, [], {}),
    )


def paired_page(same=False):
    first = "Proyecto: Senderos del río\n" + session_text()
    second = first if same else "Proyecto: Guardianes del jardín\n" + session_text("Medir", "Explorar el jardín.", "Comparar registros.")
    return first + second


def test_project_occurrences_delimit_sessions_in_physical_order():
    dossier = dossier_for([paired_page()])
    a, b = dossier.sessions
    assert [a.session_id, b.session_id] == ["p1_s1", "p1_s1_2"]
    assert [a.project_title, b.project_title] == ["Senderos del río", "Guardianes del jardín"]
    assert "Proyecto" not in a.fields["cierre"].value
    assert "Guardianes" not in a.fields["cierre"].value
    assert a.header_anchor["occurrence"] == 1
    assert b.header_anchor["occurrence"] == 2
    assert a.project_context["anchor"]["occurrence"] == 1
    assert b.project_context["anchor"]["occurrence"] == 2


def test_identical_projects_and_sessions_retain_distinct_anchors():
    a, b = dossier_for([paired_page(same=True)]).sessions
    assert a.project_title == b.project_title
    assert a.project_context["project_id"] != b.project_context["project_id"]
    assert a.header_anchor != b.header_anchor
    assert a.fields["cierre"].value == b.fields["cierre"].value


def test_session_before_first_project_has_explicit_missing_context_and_no_queue_fallback():
    d = dossier_for([session_text() + "Proyecto: Posterior\n" + session_text("Medir")])
    first = d.sessions[0]
    assert first.project_title == ""
    assert first.project_context["status"] == "missing"
    assert first.project_context["anchor"] is None
    assert all(not item.project_title for item in derive_operational_queue(d).items if item.session_id == first.session_id)


@pytest.mark.parametrize("title,source_status", [("", "missing"), ("Guardianes de\nla comunidad", "ambiguous"), ('"Guardianes de\nla comunidad"', "supported")])
def test_empty_and_multiline_project_candidates_are_honest(title, source_status):
    s = dossier_for([f"Proyecto: {title}\n" + session_text()]).sessions[0]
    assert s.project_title == " ".join(title.split())
    assert s.project_context["title_status"] == source_status
    assert s.project_context["review"] == "pending"
    assert s.project_context["origin"] == "proposed"
    assert s.project_context["reason"]


@pytest.mark.parametrize("prose", [
    "Proyecto cultural que exploraremos colectivamente.",
    "El Proyecto: Jardines es una frase del relato.",
    'Leer "Proyecto: Jardines" en una tarjeta.',
    "SESIÓN 2 del cuento se menciona como ejemplo.",
    "Lunes iremos al parque.",
])
def test_prose_does_not_change_project_context_or_open_a_session(prose):
    page = "Proyecto: Senderos\n" + session_text(end=prose) + session_text("Continuar")
    sessions = dossier_for([page]).sessions
    assert len(sessions) == 2
    assert all(s.project_title == "Senderos" for s in sessions)


def test_project_after_last_session_cuts_it_without_needing_another_session():
    d = dossier_for(["Proyecto: Primero\n" + session_text() + "Proyecto: Segundo\nPropósito: Observar plantas."])
    assert "Segundo" not in d.sessions[0].fields["cierre"].value


def test_project_context_persists_across_pages_until_a_new_header():
    d = dossier_for(["Proyecto: Primero\nEscenario: Aula", session_text(), "Proyecto: Segundo\n" + session_text()])
    assert [s.project_title for s in d.sessions] == ["Primero", "Segundo"]
    assert [s.project_context["anchor"]["page_number"] for s in d.sessions] == [1, 3]
    assert d.sessions[0].pages == [2]


def test_project_on_next_page_stops_continuation():
    d = dossier_for(["Proyecto: Primero\n" + session_text(), "Proyecto: Segundo\nCierre: Otra actividad.\n" + session_text("Medir")])
    assert d.sessions[0].pages == [1]
    assert "Otra actividad" not in d.sessions[0].fields["cierre"].value


def test_recomputed_segments_do_not_trust_subset_of_declared_sessions():
    pages = [paired_page()]
    d = dossier_for(pages)
    first, second = d.sessions
    first.fields["inicio"] = copy.deepcopy(second.fields["inicio"])
    d.sessions = [first]
    items = verify_curriculum_dossier(d, source(pages)).items
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1.inicio") for i in items)


def test_evidence_from_first_repeated_session_is_not_checked_for_second():
    pages = [paired_page()]
    d = dossier_for(pages)
    d.sessions[1].fields["inicio"] = copy.deepcopy(d.sessions[0].fields["inicio"])
    items = verify_curriculum_dossier(d, source(pages)).items
    target = "session.p1_s1_2.inicio"
    assert not any(i["status"] == "checked" and i["target"].startswith(target) for i in items)
    assert any(i["status"] == "needs_teacher_review" and i["target"].startswith(target) for i in items)


def test_new_and_legacy_round_trip_and_claim_surface_unchanged():
    d = dossier_for([paired_page()])
    restored = ImportDossier.from_dict(d.to_dict())
    assert restored.sessions[1].header_anchor == d.sessions[1].header_anchor
    assert restored.sessions[1].project_context == d.sessions[1].project_context
    legacy = copy.deepcopy(d.to_dict())
    for s in legacy["sessions"]:
        s.pop("header_anchor", None)
        s.pop("project_context", None)
    old = ImportDossier.from_dict(legacy)
    assert old.sessions[0].header_anchor is None
    assert old.sessions[0].project_context is None
    new_claims = compile_dossier_to_atomic_claims(d)
    old_claims = compile_dossier_to_atomic_claims(old)
    assert [(c.claim_id, c.claim_type, c.predicate, c.state) for c in new_claims] == [(c.claim_id, c.claim_type, c.predicate, c.state) for c in old_claims]
    entity = next(c for c in new_claims if c.subject == "session:p1_s1" and c.predicate == "es_entidad")
    assert entity.metadata["project_context"] == d.sessions[0].project_context
    assert not any(c.predicate == "pertenece_a_proyecto" for c in new_claims)


@pytest.mark.parametrize("key,value", [("text_start", True), ("text_start", "1"), ("text_start", -1), ("text_end", "bogus"), ("occurrence", False), ("page_number", "01"), ("schema_version", True), ("document_sha256", "foreign-sha"), ("excerpt", "SESIÓN 99: Manipulada")])
def test_tampered_session_anchor_is_never_coerced_or_accepted(key, value):
    pages = [paired_page()]
    d = dossier_for(pages)
    raw = d.to_dict()
    raw["sessions"][0]["header_anchor"][key] = value
    restored = ImportDossier.from_dict(raw)
    assert restored.sessions[0].header_anchor[key] == value
    report = verify_curriculum_dossier(restored, source(pages))
    assert any(i["status"] == "blocked" and i["target"] == "session.p1_s1.header_anchor" for i in report.items)


def test_valid_but_foreign_occurrence_anchor_is_blocked():
    pages = [paired_page(same=True)]
    d = dossier_for(pages)
    d.sessions[0].header_anchor = copy.deepcopy(d.sessions[1].header_anchor)
    report = verify_curriculum_dossier(d, source(pages))
    assert any(i["status"] == "blocked" and i["target"] == "session.p1_s1.header_anchor" for i in report.items)


def test_project_phases_do_not_gain_a_numbered_session_anchor():
    d = dossier_for(["Proyecto: Guardianes\nEscenario: Aula\nDESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Mirar el jardín.\nFase 2\nActividad 2: Compartir registros."])
    assert len(d.sessions) == 1
    s = d.sessions[0]
    assert s.session_id.endswith("_project_review")
    assert s.header_anchor is None
    assert s.project_context["title"] == "Guardianes"
    assert s.status == "ambiguous"


def test_removed_anchors_and_reordered_sessions_do_not_reopen_page_fallback():
    pages = [paired_page()]
    d = dossier_for(pages)
    a, b = d.sessions
    b.fields["inicio"] = copy.deepcopy(a.fields["inicio"])
    a.header_anchor = b.header_anchor = None
    a.project_context = b.project_context = None
    d.sessions.reverse()
    items = verify_curriculum_dossier(d, source(pages)).items
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1_2.inicio") for i in items)


@pytest.mark.parametrize("key,value", [("title", "Título inventado"), ("origin", "extracted"), ("review", "confirmed"), ("status", "supported"), ("schema_version", True)])
def test_project_context_tampering_is_blocked(key, value):
    pages = [paired_page()]
    d = dossier_for(pages)
    d.sessions[0].project_context[key] = value
    report = verify_curriculum_dossier(d, source(pages))
    assert any(i["status"] == "blocked" and i["target"] == "session.p1_s1.project_context" for i in report.items)


def test_project_evidence_on_previous_page_does_not_authorize_session_moment():
    pages = ["Proyecto: Dibujar registros.\nEscenario: Aula", session_text()]
    d = dossier_for(pages)
    s = d.sessions[0]
    s.pages.insert(0, 1)
    s.fields["desarrollo"].evidence[0].page_number = 1
    items = verify_curriculum_dossier(d, source(pages)).items
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p2_s1.desarrollo") for i in items)


def test_same_source_reextract_preserves_corrected_values_and_confirmation_by_anchor():
    from curriculum.source_interpreter import preserve_reextract_decisions, resolve
    pages = [paired_page()]
    old = resolve(dossier_for(pages), {"session_id": "p1_s1_2", "session_fields": {"inicio": "Decisión docente."}, "reviews": {"desarrollo": "confirmed"}}, actor="Docente")
    fresh = dossier_for(pages)
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    assert fresh.sessions[1].fields["inicio"].to_dict() == old.sessions[1].fields["inicio"].to_dict()
    assert fresh.sessions[1].fields["desarrollo"].review == "confirmed"
    assert fresh.sessions[0].fields["inicio"].review == "pending"
    assert any(d["change_type"] == "retained_decision" for d in deltas)


def test_changed_extraction_keeps_teacher_value_but_requires_review():
    from curriculum.source_interpreter import preserve_reextract_decisions, resolve
    pages = [paired_page()]
    old = resolve(dossier_for(pages), {"session_id": "p1_s1", "session_fields": {"cierre": "Cierre docente."}}, actor="Docente")
    old.sessions[0].fields["cierre"].original_value += " Proyecto: Guardianes del jardín"
    fresh = dossier_for(pages)
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    f = fresh.sessions[0].fields["cierre"]
    assert f.value == "Cierre docente."
    assert f.origin == "teacher_entered"
    assert f.review == "pending"
    assert "reextracción" in f.reason.lower()
    assert any(d["change_type"] == "decision_requires_review" for d in deltas)


def test_changed_extraction_does_not_confirm_new_value():
    from curriculum.source_interpreter import preserve_reextract_decisions, resolve
    pages = [paired_page()]
    old = resolve(dossier_for(pages), {"session_id": "p1_s1", "reviews": {"cierre": "confirmed"}}, actor="Docente")
    old.sessions[0].fields["cierre"].value += " Proyecto: Guardianes del jardín"
    fresh = dossier_for(pages)
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    assert fresh.sessions[0].fields["cierre"].review == "pending"
    assert fresh.sessions[0].fields["cierre"].value == "Compartir hallazgos."
    assert any(d["before"]["review"] == "confirmed" for d in deltas)


@pytest.mark.parametrize("mutation", ["sha", "swapped_anchor", "legacy_duplicate"])
def test_uncertain_reextract_identity_never_carries_decisions(mutation):
    from curriculum.source_interpreter import preserve_reextract_decisions, resolve
    pages = [paired_page(same=True)]
    old = resolve(dossier_for(pages), {"session_id": "p1_s1", "session_fields": {"inicio": "Decisión docente."}}, actor="Docente")
    if mutation == "sha":
        old.source_sha256 = "foreign-sha"
    elif mutation == "swapped_anchor":
        old.sessions[0].header_anchor = copy.deepcopy(old.sessions[1].header_anchor)
    else:
        old.sessions[0].header_anchor = None
    fresh = dossier_for(pages)
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    assert fresh.sessions[0].fields["inicio"].value == "Mirar el paisaje."
    assert fresh.sessions[0].fields["inicio"].review == "pending"
    assert any(d["change_type"] == "decision_not_reapplied" for d in deltas)


def test_unique_legacy_reextract_preserves_decision_without_title_join():
    from curriculum.source_interpreter import preserve_reextract_decisions, resolve
    pages = ["Proyecto: Senderos\n" + session_text()]
    old = resolve(dossier_for(pages), {"session_id": "p1_s1", "session_fields": {"inicio": "Decisión docente."}}, actor="Docente")
    old.sessions[0].header_anchor = None
    old.sessions[0].project_title = "Título erróneo legacy"
    fresh = dossier_for(pages)
    preserve_reextract_decisions(old, fresh, source(pages))
    assert fresh.sessions[0].fields["inicio"].value == "Decisión docente."
    assert fresh.sessions[0].project_title == "Senderos"


def test_project_title_stops_before_a_day_prefixed_session():
    s = dossier_for(["Proyecto: Senderos\nLunes - " + session_text()]).sessions[0]
    assert s.project_title == "Senderos"
    assert s.project_context["title_status"] == "supported"


def test_empty_project_resets_prior_context_and_cuts_the_session():
    d = dossier_for(["Proyecto: Primero\n" + session_text() + "Proyecto:\n" + session_text("Después")])
    assert d.sessions[1].project_title == ""
    assert d.sessions[1].project_context["status"] == "missing"
    assert d.sessions[1].project_context["anchor"]["occurrence"] == 2
    assert "Proyecto" not in d.sessions[0].fields["cierre"].value


def test_phase_review_does_not_absorb_a_later_project():
    page = "Proyecto: Primero\nDESARROLLO DEL PROYECTO\nFase 1\nActividad 1: Mirar plantas.\nProyecto: Segundo\nFase 1\nActividad 1: Medir piedras."
    d = dossier_for([page])
    assert d.sessions[0].project_title == "Primero"
    assert all("piedras" not in a.description for a in d.sessions[0].activities)


def test_days_without_numbered_sessions_get_physical_anchors():
    d = dossier_for(["Proyecto: Primero\nLunes\nInicio: Mirar plantas.\nCierre: Compartir.\nProyecto: Segundo\nMartes\nInicio: Medir piedras.\nCierre: Contar."])
    assert [s.project_title for s in d.sessions] == ["Primero", "Segundo"]
    assert [s.header_anchor["kind"] for s in d.sessions] == ["day", "day"]
    assert "Proyecto" not in d.sessions[0].fields["cierre"].value


def test_real_pdf_round_trip_selection_and_verification_for_repeated_projects():
    import io
    from test_t15_curriculum_import import make_minimal_pdf
    content = make_minimal_pdf([paired_page()])
    d = CurriculumSourceInterpreter.prepare(io.BytesIO(content), {"session_id": "p1_s1_2"})
    assert d.selection["session_id"] == "p1_s1_2"
    assert d.selection["project_title"] == "Guardianes del jardín"
    report = verify_curriculum_dossier(ImportDossier.from_dict(d.to_dict()), content)
    assert report.blocked_count == 0
    for sid in ("p1_s1", "p1_s1_2"):
        assert any(i["status"] == "checked" and i["target"].startswith(f"session.{sid}.inicio") for i in report.items)


def test_corrected_value_stays_with_second_identical_occurrence_on_reextract():
    from curriculum.source_interpreter import preserve_reextract_decisions, resolve
    pages = [paired_page(same=True)]
    old = resolve(dossier_for(pages), {"session_id": "p1_s1_2", "session_fields": {"inicio": "Decisión para segunda ocurrencia."}}, actor="Docente")
    old.sessions.reverse()
    fresh = dossier_for(pages)
    preserve_reextract_decisions(old, fresh, source(pages))
    assert fresh.sessions[0].fields["inicio"].value == "Mirar el paisaje."
    assert fresh.sessions[1].fields["inicio"].value == "Decisión para segunda ocurrencia."


@pytest.mark.parametrize("member,value", [("page_number", True), ("occurrence", "2"), ("text_start", -1), ("text_end", 999999), ("excerpt", "Proyecto: Inventado"), ("document_sha256", "foreign-sha")])
def test_project_anchor_integer_sha_offset_and_excerpt_tampering(member, value):
    pages = [paired_page()]
    d = dossier_for(pages)
    d.sessions[0].project_context["anchor"][member] = value
    report = verify_curriculum_dossier(ImportDossier.from_dict(d.to_dict()), source(pages))
    assert any(i["status"] == "blocked" and i["target"] == "session.p1_s1.project_context" for i in report.items)


def test_identical_project_anchor_cannot_be_transplanted_between_occurrences():
    pages = [paired_page(same=True)]
    d = dossier_for(pages)
    d.sessions[0].project_context = copy.deepcopy(d.sessions[1].project_context)
    report = verify_curriculum_dossier(d, source(pages))
    assert any(i["status"] == "blocked" and i["target"] == "session.p1_s1.project_context" for i in report.items)


@pytest.mark.parametrize("space", ["\u00a0", "\u2009", "\u202f", "\u3000"])
def test_unicode_horizontal_space_preserves_source_offsets_and_sessions(space):
    pages = [paired_page().replace("SESIÓN 1", f"{space}SESIÓN{space}1")]
    d = dossier_for(pages)
    assert len(d.sessions) == 2
    assert [s.project_title for s in d.sessions] == ["Senderos del río", "Guardianes del jardín"]
    for s in d.sessions:
        a = s.header_anchor
        assert a["excerpt"] == pages[0][a["text_start"]:a["text_end"]]
    d.sessions[0].fields["inicio"] = copy.deepcopy(d.sessions[1].fields["inicio"])
    d.sessions[0].header_anchor = d.sessions[0].project_context = None
    d.sessions = d.sessions[:1]
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1.inicio") for i in verify_curriculum_dossier(d, source(pages)).items)


@pytest.mark.parametrize("heading", ["SESIÓN 01: Observar", "SESIÓN 1.", "SESIÓN 1. Observar"])
def test_unambiguous_legacy_numbered_headings_are_still_detected(heading):
    page = "Proyecto: Senderos\n" + session_text().replace("SESIÓN 1: Observar", heading)
    d = dossier_for([page])
    assert len(d.sessions) == 1
    assert d.sessions[0].session_id == "p1_s1"
    assert d.sessions[0].project_title == "Senderos"


@pytest.mark.parametrize("heading", ["SESIÓN 1 Observar", "SESIÓN 2 del cuento se menciona como ejemplo.", "SESIÓN\n1: Observar", "SESIÓN\u20281: Observar"])
def test_unresolved_session_like_text_never_reopens_legacy_page_fallback(heading):
    from curriculum.source_interpreter import InterpretedField, SourceReference
    page = f"Proyecto: Primero\n{heading}\nInicio: Mirar plantas.\nProyecto: Segundo\n{heading}\nInicio: Medir piedras."
    d = dossier_for([page])
    assert d.sessions == []  # Abstain from treating unknown formatting/prose as a lesson.
    d.sessions = [SessionPlan(session_id="legacy-A", session_number=1, title="A", pages=[1], fields={
        "inicio": InterpretedField(name="inicio", value="Medir piedras.", evidence=[SourceReference(d.source_sha256, 1, excerpt="Medir piedras.")]),
    })]
    report = verify_curriculum_dossier(d, source([page]))
    assert not any(i["status"] == "checked" and i["target"].startswith("session.legacy-A.inicio") for i in report.items)
    assert any(i["status"] == "needs_teacher_review" and i["target"].startswith("session.legacy-A.inicio") for i in report.items)


def test_project_title_projection_cannot_contradict_present_context():
    pages = [paired_page()]
    d = dossier_for(pages)
    d.sessions[0].project_title = "Título que no corresponde"
    report = verify_curriculum_dossier(d, source(pages))
    assert any(i["status"] == "blocked" and i["target"] == "session.p1_s1.project_title" for i in report.items)
    d.sessions[0].project_context = None
    legacy = verify_curriculum_dossier(d, source(pages))
    assert not any(i["status"] == "blocked" and i["target"] == "session.p1_s1.project_title" for i in legacy.items)


def test_legacy_corrected_value_with_empty_history_is_retained_as_a_snapshot_when_unmatched():
    from curriculum.source_interpreter import preserve_reextract_decisions
    pages = [paired_page(same=True)]
    old = dossier_for(pages)
    old.history = []
    f = old.sessions[0].fields["inicio"]
    f.value, f.origin, f.review = "Decisión legacy sin historial.", "teacher_entered", "corrected"
    old.sessions[0].header_anchor = old.sessions[0].project_context = None
    fresh = dossier_for(pages)
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    entry = next(d for d in deltas if d["change_type"] == "decision_not_reapplied")
    assert entry["before"] == f.to_dict()
    assert entry["session_id"] == "p1_s1"
    assert all(s.fields["inicio"].value == "Mirar el paisaje." for s in fresh.sessions)


@pytest.mark.parametrize("mutation", ["sha", "base"])
def test_postponed_decision_is_not_silently_reapplied_to_changed_source_or_value(mutation):
    from curriculum.source_interpreter import preserve_reextract_decisions, resolve
    pages = ["Proyecto: Senderos\n" + session_text()]
    old = resolve(dossier_for(pages), {"session_id": "p1_s1", "reviews": {"inicio": "postponed"}}, actor="Docente")
    if mutation == "sha":
        old.source_sha256 = "foreign-sha"
    else:
        old.sessions[0].fields["inicio"].value = "Texto antes del cambio de extracción."
    fresh = dossier_for(pages)
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    assert fresh.sessions[0].fields["inicio"].review == "pending"
    assert any(d["before"]["review"] == "postponed" and d["change_type"] in ("decision_not_reapplied", "decision_requires_review") for d in deltas)


def test_known_session_stops_at_unresolved_next_heading_without_inventing_a_session():
    pages = ["Proyecto: Senderos\n" + session_text() + "SESIÓN 2 Observar\nInicio: Texto ajeno.\nCierre: Otra sesión."]
    d = dossier_for(pages)
    assert len(d.sessions) == 1
    assert "Otra sesión" not in d.sessions[0].fields["cierre"].value
    d.sessions[0].fields["inicio"].value = "Texto ajeno."
    d.sessions[0].fields["inicio"].evidence[0].excerpt = "Texto ajeno."
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1.inicio") for i in verify_curriculum_dossier(d, source(pages)).items)


@pytest.mark.parametrize("mutation", ["sha", "reference"])
def test_postponed_annex_decision_is_snapshotted_when_not_reapplied(mutation):
    from curriculum.source_interpreter import preserve_reextract_decisions, resolve
    pages = ["Proyecto: Senderos\n" + session_text(start="Resolver anexo 1 del cuadernillo."), "ANEXO 1\nFicha de plantas."]
    old = dossier_for(pages)
    ref = old.sessions[0].annex_references[0]
    old = resolve(old, {"session_id": "p1_s1", "reviews": {ref.reference_id: "postponed"}}, actor="Docente")
    ref = old.sessions[0].annex_references[0]
    assert ref.review == "postponed"
    old.history = []
    if mutation == "sha":
        old.source_sha256 = "foreign-sha"
    else:
        ref.raw_mention = "Otra mención previa"
    fresh = dossier_for(pages)
    deltas = preserve_reextract_decisions(old, fresh, source(pages))
    assert fresh.sessions[0].annex_references[0].review == "pending"
    assert any(d["scope"] == "annex" and d["change_type"] == "decision_not_reapplied" and d["before"] == ref.to_dict() for d in deltas)


def test_weak_prose_boundary_retains_literal_candidate_and_explicit_uncertainty():
    tail = "SESIÓN 2 del cuento se menciona como ejemplo.\nPreguntar qué opinan del personaje."
    pages = ["Proyecto: Senderos\n" + session_text(end="Leer el cuento.") + tail]
    d = dossier_for(pages)
    assert len(d.sessions) == 1
    s = d.sessions[0]
    assert s.status == "ambiguous"
    assert s.fields["cierre"].status == "ambiguous"
    assert s.fields["cierre"].origin == "proposed"
    assert "no resuelto" in s.fields["cierre"].reason
    assert tail in s.layout_notes
    assert "página física 1" in s.layout_notes
    report = verify_curriculum_dossier(d, source(pages))
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1.cierre") for i in report.items)
    # Removing the uncertainty cannot turn a weak boundary into verified scope.
    s.fields["cierre"].status, s.fields["cierre"].origin = "supported", "extracted"
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1.cierre") for i in verify_curriculum_dossier(d, source(pages)).items)


def test_unclosed_quote_cannot_hide_session_structure_from_legacy_verifier():
    from curriculum.source_interpreter import InterpretedField, SourceReference
    pages = ['Leer "esta narración.\n' + paired_page()]
    d = dossier_for(pages)
    assert d.sessions == []
    d.sessions = [SessionPlan(session_id="legacy-A", session_number=1, title="A", pages=[1], fields={
        "inicio": InterpretedField(name="inicio", value="Explorar el jardín.", evidence=[SourceReference(d.source_sha256, 1, excerpt="Explorar el jardín.")]),
    })]
    report = verify_curriculum_dossier(d, source(pages))
    assert not any(i["status"] == "checked" and i["target"].startswith("session.legacy-A.inicio") for i in report.items)


def test_weak_boundary_candidate_is_visible_on_the_review_surface():
    from django.template.loader import render_to_string
    from types import SimpleNamespace
    tail = "SESIÓN 2 del cuento se menciona como ejemplo.\nPreguntar qué opinan del personaje."
    d = dossier_for(["Proyecto: Senderos\n" + session_text(end="Leer el cuento.") + tail])
    s = d.sessions[0]
    d.selection = {"session_id": s.session_id, "session_number": 1}
    html = render_to_string("curriculum/tutor_import_interpretation.html", {
        "dossier": d, "selected_session": s, "active_session_id": s.session_id,
        "active_session_number": 1, "job": SimpleNamespace(pk=1),
    })
    assert "Organización de la fuente pendiente de revisión" in html
    assert "Tramo sin asignar, página física 1" in html
    assert "Preguntar qué opinan del personaje." in html
    assert "Ver página física 1" in html


def test_open_quote_inside_a_matched_session_cannot_absorb_another_project():
    pages = ["Proyecto: Senderos\n" + session_text(end='Leer "el cuento.') + "Proyecto: Jardines\n" + session_text("Medir", "Medir las plantas.")]
    d = dossier_for(pages)
    assert len(d.sessions) == 1
    s = d.sessions[0]
    assert "Proyecto: Jardines" not in s.fields["cierre"].value
    assert "Proyecto: Jardines" in s.layout_notes
    assert s.status == "ambiguous"
    s.fields["inicio"].value = s.fields["inicio"].evidence[0].excerpt = "Medir las plantas."
    s.fields["inicio"].origin, s.fields["inicio"].status = "extracted", "supported"
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1.inicio") for i in verify_curriculum_dossier(d, source(pages)).items)


@pytest.mark.parametrize("prefix,headings", [
    ("", ("Lunes Observar", "Martes Medir")),
    ('Leer "esta narración.\n', ("Lunes", "Martes")),
    ("", ("Lunes iremos al parque.", "Martes miraremos plantas.")),
])
def test_unresolved_or_quoted_days_cannot_enable_legacy_whole_page_scope(prefix, headings):
    from curriculum.source_interpreter import InterpretedField, SourceReference
    pages = [prefix + f"{headings[0]}\nInicio: Texto A\n{headings[1]}\nInicio: Texto B"]
    d = dossier_for(pages)
    assert d.sessions == []
    d.sessions = [SessionPlan(session_id="legacy-A", session_number=1, title="A", pages=[1], fields={
        "inicio": InterpretedField(name="inicio", value="Texto B", evidence=[SourceReference(d.source_sha256, 1, excerpt="Texto B")]),
    })]
    assert not any(i["status"] == "checked" and i["target"].startswith("session.legacy-A.inicio") for i in verify_curriculum_dossier(d, source(pages)).items)


def test_unresolved_day_after_known_day_retains_candidate_with_uncertainty():
    pages = ['Proyecto: Senderos\nLunes\nInicio: Mirar plantas.\nCierre: Leer "el cuento.\nMartes Medir\nInicio: Medir piedras.']
    d = dossier_for(pages)
    assert len(d.sessions) == 1
    s = d.sessions[0]
    assert s.status == "ambiguous"
    assert "Martes Medir\nInicio: Medir piedras." in s.layout_notes
    s.fields["inicio"].value = s.fields["inicio"].evidence[0].excerpt = "Medir piedras."
    s.fields["inicio"].origin, s.fields["inicio"].status = "extracted", "supported"
    assert not any(i["status"] == "checked" and i["target"].startswith("session.p1_s1.inicio") for i in verify_curriculum_dossier(d, source(pages)).items)
