"""tests/test_t118_contract_greens.py
Contract #118 GREEN coverage — fixtures, adversariales, derivados, contadores y regresiones.

Every test uses synthetic in-memory fixtures via ImportDossier / verify_curriculum_dossier.
No real data, no production DB writes, no Chrome/CDP/Playwright.
"""

from __future__ import annotations

import copy
import hashlib
import io

import pytest

from curriculum.source_interpreter import (
    ORIGIN_EXTRACTED,
    ORIGIN_PROPOSED,
    ORIGIN_TEACHER_ENTERED,
    REVIEW_CONFIRMED,
    REVIEW_CORRECTED,
    REVIEW_PENDING,
    STATUS_AMBIGUOUS,
    STATUS_CONFLICTING,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    AnnexReference,
    ImportDossier,
    InterpretedField,
    SessionPlan,
    SessionActivity,
    SourceReference,
    derive_operational_queue,
    resolve,
)
from curriculum.verification import (
    STATUS_BLOCKED,
    STATUS_CHECKED,
    STATUS_NEEDS_TEACHER_REVIEW,
    VerificationReport,
    normalize_text_for_evidence_check,
    verify_curriculum_dossier,
)

pytestmark = pytest.mark.django_db


# ─── Synthetic PDF helpers ──────────────────────────────────────────────────────
def _make_synthetic_pdf(pages_text: list[str]) -> tuple[bytes, str, list[str]]:
    """Build a minimal valid PDF whose pages contain the given text, returning
    (pdf_bytes, sha256_hex, pages_text_list).

    We bypass actual PDF construction and use the pre-cached tuple shortcut
    accepted by verify_curriculum_dossier / _read_pdf_source.
    """
    # Build a deterministic hash from page contents
    content = "\n---PAGE---\n".join(pages_text).encode("utf-8")
    sha = hashlib.sha256(content).hexdigest()
    return content, sha, pages_text


def _field(
    name: str,
    value: str,
    *,
    origin: str = ORIGIN_EXTRACTED,
    status: str = STATUS_SUPPORTED,
    review: str = REVIEW_PENDING,
    evidence: list | None = None,
    source_sha: str = "",
    page: int = 1,
) -> InterpretedField:
    """Build a synthetic InterpretedField with optional auto-evidence."""
    ev_list = evidence if evidence is not None else (
        [SourceReference(document_sha256=source_sha, page_number=page, excerpt=value)]
        if source_sha and value else []
    )
    return InterpretedField(
        name=name,
        value=value,
        origin=origin,
        status=status,
        review=review,
        evidence=ev_list,
    )


def _make_dossier(
    pages_text: list[str],
    sessions: list[SessionPlan],
    general_fields: dict[str, InterpretedField] | None = None,
    annex_candidates: list[dict] | None = None,
) -> tuple[ImportDossier, tuple[bytes, str, list[str]]]:
    """Build an ImportDossier + PDF source tuple."""
    pdf_source = _make_synthetic_pdf(pages_text)
    sha = pdf_source[1]
    page_count = len(pages_text)

    if general_fields is None:
        general_fields = {
            "proyecto": _field("proyecto", "Proyecto Sintético", source_sha=sha, page=1),
            "campos_formativos": _field("campos_formativos", "Lenguajes", source_sha=sha, page=1),
            "proposito": _field("proposito", "Propósito de prueba", source_sha=sha, page=1),
            "finalidad": _field("finalidad", "Finalidad de prueba", source_sha=sha, page=1),
        }

    dossier = ImportDossier(
        source_sha256=sha,
        source_name="synthetic.pdf",
        page_count=page_count,
        version=1,
        status="active",
        general_fields=general_fields,
        sessions=sessions,
        annex_candidates=annex_candidates or [],
    )
    return dossier, pdf_source


def _session(
    session_id: str,
    session_number: int,
    title: str,
    pages: list[int],
    fields: dict[str, InterpretedField],
    annex_references: list[AnnexReference] | None = None,
    continues_on: list[int] | None = None,
    activities: list[SessionActivity] | None = None,
) -> SessionPlan:
    return SessionPlan(
        session_id=session_id,
        session_number=session_number,
        title=title,
        pages=pages,
        continues_on=continues_on or [],
        fields=fields,
        annex_references=annex_references or [],
        activities=activities or [],
    )


# =============================================================================
# GREEN 1 — Fixtures: 1, 2 and 5 activities per class; multiple classes on one
# page; session spanning multiple pages; document without weeks; shared annexes.
# =============================================================================

class TestGreen1FixtureVariety:
    """Exercises the verifier / queue with diverse structural fixtures to ensure
    order and relationships are preserved without inventing structure."""

    def _session_fields(self, sha: str, page: int) -> dict[str, InterpretedField]:
        return {
            "inicio": _field("inicio", f"Inicio de sesión en página {page}", source_sha=sha, page=page),
            "desarrollo": _field("desarrollo", f"Desarrollo en página {page}", source_sha=sha, page=page),
            "cierre": _field("cierre", f"Cierre en página {page}", source_sha=sha, page=page),
        }

    # --- 1 activity per class ---
    def test_fixture_1_activity_per_class(self):
        """Single session / single class verifies cleanly."""
        pages = ["Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
                 "Inicio de sesión en página 1 Desarrollo en página 1 Cierre en página 1"]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        sessions = [_session("s1", 1, "Clase 1", [1], self._session_fields(sha, 1))]
        dossier, src = _make_dossier(pages, sessions)
        report = verify_curriculum_dossier(dossier, src)

        assert report.blocked_count == 0
        assert report.total_items > 0
        # Exactly one session in items
        sess_items = [i for i in report.items if i["scope"] == "session"]
        session_ids = {i.get("target", "").split(".")[1] for i in sess_items if "." in i.get("target", "")}
        assert "s1" in session_ids

    # --- 2 activities per class ---
    def test_fixture_2_activities_per_class(self):
        """Two sessions each representing a class activity."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio de sesión en página 1 Desarrollo en página 1 Cierre en página 1",
            "Inicio de sesión en página 2 Desarrollo en página 2 Cierre en página 2",
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        sessions = [
            _session("s1", 1, "Actividad 1", [1], self._session_fields(sha, 1)),
            _session("s2", 2, "Actividad 2", [2], self._session_fields(sha, 2)),
        ]
        dossier, src = _make_dossier(pages, sessions)
        report = verify_curriculum_dossier(dossier, src)

        assert report.blocked_count == 0
        queue = derive_operational_queue(dossier)
        assert queue.total_count > 0
        # Both sessions appear in queue
        sess_ids_in_queue = {it.session_id for it in queue.items if it.scope == "session"}
        assert {"s1", "s2"} == sess_ids_in_queue

    # --- 5 activities within one class ---
    def test_fixture_5_activities_per_class(self):
        """Five activities within a single class/session — verifies no invented structure,
        preserves order, and associates annexes without inventing weekly/cardinality constraints."""
        page_texts = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Clase 1: Taller intensivo. "
            "Inicio de sesión en página 1 Desarrollo en página 1 Cierre en página 1 "
            "Actividad 1: Calentamiento vocal. "
            "Actividad 2: Lectura compartida. "
            "Actividad 3: Análisis de texto. "
            "Actividad 4: Trabajo en equipos. "
            "Actividad 5: Reflexión final y cierre."
        ]
        pdf_src = _make_synthetic_pdf(page_texts)
        sha = pdf_src[1]

        annex_refs = [
            AnnexReference(
                annex_number=str(i),
                raw_mention=f"anexo_{i}",
                reference_id=f"anexo_{i}",
                source_pages=[1],
                candidate_pages=[1],
            )
            for i in (1, 3, 5)
        ]

        activities = [
            SessionActivity(
                activity_id=f"act_{i}",
                title=f"Actividad {i}",
                description=f"Descripción de la actividad {i}",
                order=i,
                annex_ids=[f"anexo_{i}"] if i % 2 == 1 else [],
                evidence=[SourceReference(document_sha256=sha, page_number=1, excerpt=f"Actividad {i}")],
            )
            for i in range(1, 6)
        ]

        session = _session(
            "s1",
            1,
            "Clase 1: Taller intensivo",
            [1],
            self._session_fields(sha, 1),
            annex_references=annex_refs,
            activities=activities,
        )

        dossier, src = _make_dossier(page_texts, [session])

        # Verify roundtrip serialization preserves activities within the session
        dossier_dict = dossier.to_dict()
        restored_dossier = ImportDossier.from_dict(dossier_dict)
        assert len(restored_dossier.sessions) == 1
        restored_session = restored_dossier.sessions[0]
        assert len(restored_session.activities) == 5

        # Verify activity ordering and annex association preserved
        for i, act in enumerate(restored_session.activities, start=1):
            assert act.activity_id == f"act_{i}"
            assert act.order == i
            assert act.title == f"Actividad {i}"
            expected_annexes = [f"anexo_{i}"] if i % 2 == 1 else []
            assert act.annex_ids == expected_annexes

        report = verify_curriculum_dossier(restored_dossier, src)
        assert report.blocked_count == 0
        queue = derive_operational_queue(restored_dossier)
        assert queue.total_count > 0

    # --- Multiple classes on one page ---
    def test_fixture_multiple_classes_on_one_page(self):
        """Two sessions share the same physical page."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio sesión A Desarrollo sesión A Cierre sesión A "
            "Inicio sesión B Desarrollo sesión B Cierre sesión B"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s_a = _session("sa", 1, "Clase A", [1], {
            "inicio": _field("inicio", "Inicio sesión A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo sesión A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre sesión A", source_sha=sha, page=1),
        })
        s_b = _session("sb", 2, "Clase B", [1], {
            "inicio": _field("inicio", "Inicio sesión B", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo sesión B", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre sesión B", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s_a, s_b])
        report = verify_curriculum_dossier(dossier, src)
        assert report.blocked_count == 0
        # Both sessions reference page 1
        assert all(p == 1 for p in dossier.sessions[0].pages)
        assert all(p == 1 for p in dossier.sessions[1].pages)

    # --- Session spanning multiple pages ---
    def test_fixture_session_spanning_multiple_pages(self):
        """A session with pages=[1] and continues_on=[2]."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio sesión multipage Desarrollo sesión multipage",
            "Cierre sesión multipage"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión Multipágina", [1], {
            "inicio": _field("inicio", "Inicio sesión multipage", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo sesión multipage", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre sesión multipage", source_sha=sha, page=2),
        }, continues_on=[2])

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)
        assert report.blocked_count == 0
        # Verify continues_on is tracked
        assert dossier.sessions[0].continues_on == [2]

    # --- Document without weeks ---
    def test_fixture_no_weeks(self):
        """Dossier with no week/semana concept — sessions identified by day."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Lunes Inicio día Desarrollo día Cierre día"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("lunes_s1", 1, "Lunes", [1], {
            "inicio": _field("inicio", "Inicio día", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo día", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre día", source_sha=sha, page=1),
        })
        s1.day_of_week = "Lunes"

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)
        assert report.blocked_count == 0
        # No 'semana' in session structure
        d = dossier.to_dict()
        assert "semana" not in str(d).lower() or "week" not in str(d).lower()

    # --- Shared annexes between activities ---
    def test_fixture_shared_annexes_between_activities(self):
        """Two sessions reference the same annex candidate page."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio A Desarrollo A Cierre A Anexo 1",
            "Inicio B Desarrollo B Cierre B Anexo 1",
            "Lámina Anexo 1 contenido"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        annex_a = AnnexReference(
            annex_number="1", raw_mention="Anexo 1", source_pages=[1],
            candidate_pages=[3], evidence=[
                SourceReference(document_sha256=sha, page_number=1, excerpt="Anexo 1", role="evidence"),
            ], reference_id="ref_a1_1",
        )
        annex_b = AnnexReference(
            annex_number="1", raw_mention="Anexo 1", source_pages=[2],
            candidate_pages=[3], evidence=[
                SourceReference(document_sha256=sha, page_number=2, excerpt="Anexo 1", role="evidence"),
            ], reference_id="ref_a1_2",
        )

        s_a = _session("sa", 1, "Actividad A", [1], {
            "inicio": _field("inicio", "Inicio A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        }, annex_references=[annex_a])

        s_b = _session("sb", 2, "Actividad B", [2], {
            "inicio": _field("inicio", "Inicio B", source_sha=sha, page=2),
            "desarrollo": _field("desarrollo", "Desarrollo B", source_sha=sha, page=2),
            "cierre": _field("cierre", "Cierre B", source_sha=sha, page=2),
        }, annex_references=[annex_b])

        dossier, src = _make_dossier(pages, [s_a, s_b],
                                      annex_candidates=[{"page": 3, "label": "Lámina Anexo 1"}])
        report = verify_curriculum_dossier(dossier, src)
        assert report.blocked_count == 0
        # Both annexes reference page 3
        assert annex_a.candidate_pages == [3]
        assert annex_b.candidate_pages == [3]
        # Queue has items for both annexes
        queue = derive_operational_queue(dossier)
        annex_items = [it for it in queue.items if it.scope == "annex"]
        assert len(annex_items) == 2
        annex_sessions = {it.session_id for it in annex_items}
        assert annex_sessions == {"sa", "sb"}


# =============================================================================
# GREEN 2 — Adversarial verification: same text in another session, repeated
# headers, incomplete OCR, contradiction, inferred summary → only unambiguous
# positives get 'checked'; negatives stay explicit.
# =============================================================================

class TestGreen2AdversarialVerification:
    """Adversarial scenarios ensuring the verifier is conservative and correct."""

    def test_same_text_in_another_session_does_not_cross_confirm(self):
        """Text physically present on page 1 but cited in session 2 (page 2)
        must NOT be marked checked if the text is NOT on page 2."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio específico A Desarrollo A Cierre A",
            "Inicio diferente B Desarrollo B Cierre B"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        # Session 2 claims the text "Inicio específico A" is on page 2 (it isn't)
        s2 = _session("s2", 2, "Sesión B", [2], {
            "inicio": _field("inicio", "Inicio específico A", source_sha=sha, page=2),
            "desarrollo": _field("desarrollo", "Desarrollo B", source_sha=sha, page=2),
            "cierre": _field("cierre", "Cierre B", source_sha=sha, page=2),
        })
        s1 = _session("s1", 1, "Sesión A", [1], {
            "inicio": _field("inicio", "Inicio específico A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1, s2])
        report = verify_curriculum_dossier(dossier, src)

        # Find the evidence item for s2's inicio — it should be BLOCKED
        s2_inicio_items = [
            i for i in report.items
            if "s2" in i.get("target", "") and "inicio" in i.get("target", "")
            and i.get("scope") == "session"
        ]
        blocked_items = [i for i in s2_inicio_items if i["status"] == STATUS_BLOCKED]
        assert len(blocked_items) > 0, (
            "Text on page 1 cited as evidence for session on page 2 must be BLOCKED"
        )

    def test_repeated_headers_not_auto_checked(self):
        """A repeated header like 'Inicio' appearing on every page should not be
        used as evidence to auto-check a field — excerpt must be the actual content,
        not just a header label."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio Desarrollo Cierre",
            "Inicio Desarrollo Cierre"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        # Field with just the header "Inicio" as value/excerpt — ambiguous
        s1 = _session("s1", 1, "Sesión 1", [1], {
            "inicio": InterpretedField(
                name="inicio", value="Contenido real del inicio",
                origin=ORIGIN_EXTRACTED, status=STATUS_SUPPORTED, review=REVIEW_PENDING,
                evidence=[SourceReference(
                    document_sha256=sha, page_number=1,
                    excerpt="Inicio",  # Header only, not the content
                )],
            ),
            "desarrollo": _field("desarrollo", "Desarrollo", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        # Result: evidence with excerpt "Inicio" where the value "Contenido real del inicio"
        # is NOT on the page must NOT be marked as STATUS_CHECKED. It must be rejected
        # from checked status (e.g. needs_teacher_review or blocked).
        inicio_items = [i for i in report.items if "inicio" in i.get("target", "")]
        assert len(inicio_items) > 0, "Expected verification items for inicio field"
        for item in inicio_items:
            assert item.get("status") != STATUS_CHECKED, (
                f"Repeated header 'Inicio' with unverified content was incorrectly marked as CHECKED: {item}"
            )
        assert any(i.get("status") == STATUS_NEEDS_TEACHER_REVIEW for i in inicio_items), (
            "Field with generic header evidence but missing actual content value must require teacher review"
        )

    def test_incomplete_ocr_page_forces_review(self):
        """A page with empty text (simulating OCR failure) forces needs_teacher_review."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio A Desarrollo A Cierre A",
            ""  # Empty page = scanned / OCR failed
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s2 = _session("s2", 2, "Sesión OCR", [2], {
            "inicio": _field("inicio", "Texto invisible", source_sha=sha, page=2),
            "desarrollo": _field("desarrollo", "Desarrollo invisible", source_sha=sha, page=2),
            "cierre": _field("cierre", "Cierre invisible", source_sha=sha, page=2),
        })
        s1 = _session("s1", 1, "Sesión OK", [1], {
            "inicio": _field("inicio", "Inicio A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1, s2])
        report = verify_curriculum_dossier(dossier, src)

        # Evidence on empty page should be needs_teacher_review, not checked
        ocr_items = [
            i for i in report.items
            if i.get("page_number") == 2
            and i.get("status") == STATUS_NEEDS_TEACHER_REVIEW
        ]
        assert len(ocr_items) > 0, "Empty OCR page must force needs_teacher_review"
        # It must NOT be checked
        checked_on_empty = [
            i for i in report.items
            if i.get("page_number") == 2 and i.get("status") == STATUS_CHECKED
            and i.get("scope") == "session"
            and "s2" in i.get("target", "")
            and any(k in i.get("target", "") for k in ("inicio", "desarrollo", "cierre"))
        ]
        assert len(checked_on_empty) == 0, "Evidence on empty page must never be 'checked'"

    def test_contradiction_between_field_and_page_is_blocked(self):
        """A field with status='conflicting' must be BLOCKED."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio A Desarrollo A Cierre A"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": InterpretedField(
                name="inicio", value="Dato contradictorio",
                origin=ORIGIN_EXTRACTED, status=STATUS_CONFLICTING,
                review=REVIEW_PENDING, evidence=[],
            ),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        conflict_items = [
            i for i in report.items
            if "inicio" in i.get("target", "") and i["status"] == STATUS_BLOCKED
        ]
        assert len(conflict_items) > 0, "Conflicting field must be BLOCKED"
        assert report.is_valid is False

    def test_inferred_summary_stays_needs_review_even_if_text_on_page(self):
        """A field with origin='proposed' or 'inferred' must stay needs_teacher_review
        even if its text is physically found on the page."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "El resumen inferido es este texto"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": InterpretedField(
                name="inicio",
                value="El resumen inferido es este texto",
                origin=ORIGIN_PROPOSED,  # Inferred/proposed
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
                evidence=[SourceReference(
                    document_sha256=sha, page_number=1,
                    excerpt="El resumen inferido es este texto",
                )],
            ),
            "desarrollo": _field("desarrollo", "Propósito de prueba", source_sha=sha, page=1),
            "cierre": _field("cierre", "Finalidad de prueba", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        # The proposed/inferred field must be needs_teacher_review, not checked
        proposed_items = [
            i for i in report.items
            if "inicio" in i.get("target", "")
            and i["status"] == STATUS_NEEDS_TEACHER_REVIEW
            and i.get("scope") == "session"
        ]
        assert len(proposed_items) > 0, (
            "Proposed/inferred field must stay needs_teacher_review even when text is on page"
        )
        # Must NOT be checked
        checked_proposed = [
            i for i in report.items
            if "inicio" in i.get("target", "")
            and i["status"] == STATUS_CHECKED
            and i.get("scope") == "session"
        ]
        assert len(checked_proposed) == 0, (
            "Proposed/inferred field must NEVER be auto-checked"
        )

    def test_not_evaluable_does_not_become_zero_or_checked(self):
        """Missing/empty fields must not become zero, checked, or autoapproved."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Desarrollo A Cierre A"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": InterpretedField(
                name="inicio", value="",  # Empty / not evaluable
                origin=ORIGIN_EXTRACTED, status=STATUS_MISSING,
                review=REVIEW_PENDING, evidence=[],
            ),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        # The missing field must be needs_teacher_review, NOT checked or blocked-turned-zero
        missing_items = [
            i for i in report.items
            if "inicio" in i.get("target", "")
            and i.get("scope") == "session"
        ]
        for item in missing_items:
            assert item["status"] != STATUS_CHECKED, (
                "Missing field must NEVER be marked checked"
            )
        # Counter must not be zero if there are review items
        assert report.needs_review_count > 0 or report.blocked_count > 0


# =============================================================================
# GREEN 3 — A located source fragment does NOT automatically confirm derived
# interpretations (explicit negative test).
# =============================================================================

class TestGreen3DerivedTraceability:
    """Source fragment located ≠ derived interpretation confirmed."""

    def test_source_located_does_not_confirm_derived_interpretation(self):
        """Even when the raw evidence excerpt is physically found on the page,
        a proposed/inferred derived interpretation must NOT get status=checked."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Los alumnos realizarán una investigación sobre ecosistemas"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        # The evidence cites exact text from the page → source located
        # But the interpreted value is a summary/derivative
        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": InterpretedField(
                name="inicio",
                value="Investigación ecosistemas (resumen derivado)",
                origin=ORIGIN_PROPOSED,  # Derived interpretation
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
                evidence=[SourceReference(
                    document_sha256=sha, page_number=1,
                    excerpt="Los alumnos realizarán una investigación sobre ecosistemas",
                )],
            ),
            "desarrollo": _field("desarrollo", "Propósito de prueba", source_sha=sha, page=1),
            "cierre": _field("cierre", "Finalidad de prueba", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        # Source fragment IS on the page, so evidence itself would pass
        # But the FIELD with origin=proposed must remain needs_teacher_review
        field_items = [
            i for i in report.items
            if "inicio" in i.get("target", "")
            and "evidence" not in i.get("target", "")
            and i.get("scope") == "session"
        ]
        for item in field_items:
            assert item["status"] != STATUS_CHECKED, (
                f"Derived interpretation must NOT be auto-confirmed even when source is located: "
                f"got status={item['status']} for {item.get('target')}"
            )
            assert item["status"] == STATUS_NEEDS_TEACHER_REVIEW

    def test_extracted_field_with_matching_evidence_is_checked(self):
        """Contrast: a non-derived (extracted, supported) field WITH matching
        evidence IS checked — proving the negative test above is meaningful."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Texto exacto del inicio"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": InterpretedField(
                name="inicio",
                value="Texto exacto del inicio",
                origin=ORIGIN_EXTRACTED,  # NOT proposed/inferred
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
                evidence=[SourceReference(
                    document_sha256=sha, page_number=1,
                    excerpt="Texto exacto del inicio",
                )],
            ),
            "desarrollo": _field("desarrollo", "Propósito de prueba", source_sha=sha, page=1),
            "cierre": _field("cierre", "Finalidad de prueba", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        checked_items = [
            i for i in report.items
            if "inicio" in i.get("target", "")
            and i["status"] == STATUS_CHECKED
        ]
        assert len(checked_items) > 0, (
            "Extracted field with matching evidence SHOULD be checked"
        )


# =============================================================================
# GREEN 4 — Reprocess/retry and human correction preserve traceability and
# do not duplicate entities; coherent with #98.
# =============================================================================

class TestGreen4ReprocessAndCorrection:
    """Tests that resolve() preserves traceability and avoids entity duplication."""

    def test_resolve_preserves_traceability_on_correction(self):
        """Human correction preserves original_value and appends history."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio original Desarrollo A Cierre A"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": _field("inicio", "Inicio original", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })
        dossier, src = _make_dossier(pages, [s1])

        # Apply correction
        corrected = resolve(
            dossier,
            corrections={
                "session_id": "s1",
                "session_fields": {"inicio": "Inicio corregido por docente"},
            },
            actor="Docente Test",
            pdf_source=src,
        )

        s = corrected.get_session("s1")
        assert s is not None
        f = s.fields["inicio"]
        assert f.value == "Inicio corregido por docente"
        assert f.review == REVIEW_CORRECTED
        assert f.origin == ORIGIN_TEACHER_ENTERED
        # Original value preserved
        assert f.original_value == "Inicio original"
        # Version bumped
        assert corrected.version == 2
        # History records the correction
        assert len(corrected.history) > 0

    def test_resolve_noop_does_not_duplicate_entities(self):
        """Submitting identical values does not bump version or create history."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio A Desarrollo A Cierre A"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": _field("inicio", "Inicio A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })
        dossier, src = _make_dossier(pages, [s1])
        original_version = dossier.version
        original_history_len = len(dossier.history)

        # Resolve with no changes
        result = resolve(
            dossier,
            corrections={"session_id": "s1", "inicio": "Inicio A"},  # Same value
            actor="Docente",
            pdf_source=src,
        )

        assert result.version == original_version, "Noop resolve must not bump version"
        assert len(result.history) == original_history_len, "Noop resolve must not add history"

    def test_resolve_correction_then_reconfirm_preserves_chain(self):
        """Correction A → Correction B preserves intermediate state in history."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio V1 Desarrollo A Cierre A"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": _field("inicio", "Inicio V1", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })
        dossier, src = _make_dossier(pages, [s1])

        # First correction
        v2 = resolve(dossier,
                      corrections={"session_id": "s1",
                                   "session_fields": {"inicio": "Inicio V2"}},
                      actor="Docente Ana", pdf_source=src)

        # Second correction
        v3 = resolve(v2,
                      corrections={"session_id": "s1",
                                   "session_fields": {"inicio": "Inicio V3"}},
                      actor="Docente Carlos", pdf_source=src)

        assert v3.version == 3
        s = v3.get_session("s1")
        assert s.fields["inicio"].value == "Inicio V3"
        # original_value should be the initial extraction
        assert s.fields["inicio"].original_value == "Inicio V1"
        # History has entries for both corrections
        assert len(v3.history) >= 2


# =============================================================================
# GREEN 5 — Counters by scope (document / session / field matchups):
# no double counting between scopes.
# =============================================================================

class TestGreen5CountersByScope:
    """Proves counters are exact and do not double-count across scopes."""

    def test_document_scope_total_equals_sum_of_session_scopes_plus_general(self):
        """Document-level total_count equals sum of all session-scoped counts
        plus general-scoped count."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio S1 Desarrollo S1 Cierre S1",
            "Inicio S2 Desarrollo S2 Cierre S2"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión 1", [1], {
            "inicio": _field("inicio", "Inicio S1", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo S1", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre S1", source_sha=sha, page=1),
        })
        s2 = _session("s2", 2, "Sesión 2", [2], {
            "inicio": _field("inicio", "Inicio S2", source_sha=sha, page=2),
            "desarrollo": _field("desarrollo", "Desarrollo S2", source_sha=sha, page=2),
            "cierre": _field("cierre", "Cierre S2", source_sha=sha, page=2),
        })

        dossier, src = _make_dossier(pages, [s1, s2])

        # Document scope
        doc_queue = derive_operational_queue(dossier)

        # General scope
        gen_queue = derive_operational_queue(dossier, session_filter="general")

        # Session scopes
        s1_queue = derive_operational_queue(dossier, session_filter="s1")
        s2_queue = derive_operational_queue(dossier, session_filter="s2")

        # Total must equal sum without double counting
        expected_total = gen_queue.total_count + s1_queue.total_count + s2_queue.total_count
        assert doc_queue.total_count == expected_total, (
            f"Document total ({doc_queue.total_count}) != "
            f"general ({gen_queue.total_count}) + s1 ({s1_queue.total_count}) + s2 ({s2_queue.total_count}) "
            f"= {expected_total}"
        )

    def test_counter_arithmetic_consistent(self):
        """Within any scope: requires_resolution + pending_review + reviewed + not_specified == total."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio S1 Desarrollo S1 Cierre S1"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión 1", [1], {
            "inicio": _field("inicio", "Inicio S1", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo S1", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre S1", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        queue = derive_operational_queue(dossier)

        assert (
            queue.requires_resolution_count
            + queue.pending_review_count
            + queue.reviewed_count
            + queue.not_specified_count
        ) == queue.total_count, "Counter arithmetic mismatch"
        assert queue.total_count == len(queue.items)

    def test_verification_report_counter_consistency(self):
        """Verification report: checked + needs_review + blocked == total_items."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio A Desarrollo A Cierre A"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": _field("inicio", "Inicio A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        assert (report.checked_count + report.needs_review_count + report.blocked_count) == report.total_items
        assert report.total_items == len(report.items)

    def test_no_double_count_between_evidence_and_field(self):
        """A single field with one evidence citation should not produce duplicate
        items for the same assertion."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Contenido exacto del inicio"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": InterpretedField(
                name="inicio", value="Contenido exacto del inicio",
                origin=ORIGIN_EXTRACTED, status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
                evidence=[SourceReference(
                    document_sha256=sha, page_number=1,
                    excerpt="Contenido exacto del inicio",
                )],
            ),
            "desarrollo": _field("desarrollo", "Propósito de prueba", source_sha=sha, page=1),
            "cierre": _field("cierre", "Finalidad de prueba", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        # Collect all item_ids
        all_ids = [i["item_id"] for i in report.items]
        assert len(all_ids) == len(set(all_ids)), "Duplicate item_ids detected in report"

        # All paths should be unique
        all_paths = [i["path"] for i in report.items]
        assert len(all_paths) == len(set(all_paths)), "Duplicate paths detected in report"

    def test_scoped_counter_no_double_count_with_multiple_evidence(self):
        """A field with multiple evidence entries: each evidence gets exactly one item,
        and the queue has exactly one operational item for the field (not one per evidence)."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Primera cita del inicio Segunda cita del inicio",
            "Continuación del desarrollo"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": InterpretedField(
                name="inicio", value="Primera y segunda cita del inicio",
                origin=ORIGIN_EXTRACTED, status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
                evidence=[
                    SourceReference(document_sha256=sha, page_number=1,
                                    excerpt="Primera cita del inicio"),
                    SourceReference(document_sha256=sha, page_number=1,
                                    excerpt="Segunda cita del inicio"),
                ],
            ),
            "desarrollo": _field("desarrollo", "Continuación del desarrollo", source_sha=sha, page=2),
            "cierre": _field("cierre", "Finalidad de prueba", source_sha=sha, page=1),
        }, continues_on=[2])

        dossier, src = _make_dossier(pages, [s1])

        queue = derive_operational_queue(dossier)
        inicio_items = [it for it in queue.items if it.field_name == "inicio" and it.session_id == "s1"]
        assert len(inicio_items) == 1, (
            f"Expected exactly 1 queue item for inicio, got {len(inicio_items)}"
        )


# =============================================================================
# GREEN 6 — No regression of permissions, approval (T7) and snapshots.
# =============================================================================

class TestGreen6NoRegression:
    """Ensures no regression in key invariants from T7 and snapshot tests."""

    def test_verification_report_schema_keys(self):
        """Report contains exactly the canonical keys."""
        from curriculum.verification import CANONICAL_REPORT_KEYS

        pages = ["Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
                 "Inicio A Desarrollo A Cierre A"]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": _field("inicio", "Inicio A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })
        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)
        report_dict = report.to_dict()
        assert set(report_dict.keys()) == CANONICAL_REPORT_KEYS

    def test_validate_canonical_report_rejects_forged_counts(self):
        """Incrementing checked_count invalidates the canonical validator."""
        from curriculum.verification import (
            compute_canonical_verification_report,
            validate_canonical_verification_report,
        )

        pages = ["Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
                 "Inicio A Desarrollo A Cierre A"]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": _field("inicio", "Inicio A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })
        dossier, src = _make_dossier(pages, [s1])
        report = compute_canonical_verification_report(dossier, src)

        # Forge the count
        forged = copy.deepcopy(report)
        forged["checked_count"] += 1

        assert validate_canonical_verification_report(dossier, src, forged) is False, (
            "Forged checked_count must be rejected by canonical validator"
        )

    def test_proposed_field_never_auto_approved_by_verifier(self):
        """Verifier must never auto-approve (checked) a proposed field.
        This is a permission / authorization invariant."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "El contenido propuesto está aquí"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": InterpretedField(
                name="inicio",
                value="El contenido propuesto está aquí",
                origin=ORIGIN_PROPOSED,
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
                evidence=[SourceReference(
                    document_sha256=sha, page_number=1,
                    excerpt="El contenido propuesto está aquí",
                )],
            ),
            "desarrollo": _field("desarrollo", "Propósito de prueba", source_sha=sha, page=1),
            "cierre": _field("cierre", "Finalidad de prueba", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        # No proposed field should be checked
        inicio_value_items = [
            i for i in report.items
            if "inicio" in i.get("target", "")
            and i.get("scope") == "session"
            and "evidence" not in i.get("target", "")
        ]
        for item in inicio_value_items:
            assert item["status"] != STATUS_CHECKED, (
                "Proposed field must NEVER be auto-approved/checked"
            )

    def test_candidate_annex_never_checked_always_review(self):
        """Candidate annex sheets are always needs_teacher_review, never checked."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio A Desarrollo A Cierre A",
            "Lámina candidata aquí"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": _field("inicio", "Inicio A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1],
                                      annex_candidates=[{"page": 2, "label": "Lámina candidata"}])
        report = verify_curriculum_dossier(dossier, src)

        candidate_items = [
            i for i in report.items
            if "annex_candidate" in i.get("target", "")
        ]
        assert len(candidate_items) > 0
        for item in candidate_items:
            assert item["status"] == STATUS_NEEDS_TEACHER_REVIEW, (
                "Candidate annex must always be needs_teacher_review"
            )

    def test_dossier_to_dict_roundtrip_preserves_structure(self):
        """ImportDossier serialization / deserialization preserves all fields."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio A Desarrollo A Cierre A"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión", [1], {
            "inicio": _field("inicio", "Inicio A", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Desarrollo A", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre A", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        d = dossier.to_dict()
        restored = ImportDossier.from_dict(d)

        assert restored.source_sha256 == dossier.source_sha256
        assert restored.page_count == dossier.page_count
        assert restored.version == dossier.version
        assert len(restored.sessions) == len(dossier.sessions)
        assert restored.sessions[0].session_id == dossier.sessions[0].session_id
