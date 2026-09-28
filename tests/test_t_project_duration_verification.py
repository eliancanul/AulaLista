"""Tests for project duration verification in canonical physical verification (Slice F).

Verifies:
1. Canonical membership: `duracion_proyecto` is in `CANONICAL_GENERAL_FIELDS`.
2. Cross-page proposed duration (pages 1 and 2):
   - Physical evidence is verified page by page (both citations matched=True).
   - Verification status remains `NEEDS_TEACHER_REVIEW` (never `CHECKED` as semantic truth).
   - Dossier validation passes (`blocked_count == 0`, `is_valid is True`).
3. Physical contradiction:
   - Evidence citing text not on the indicated page (or across swapped pages) triggers `BLOCKED`.
   - Hard blocks cause `is_valid is False` and `blocked_count >= 1`.
4. Absence / missing handling:
   - When `duracion_proyecto` is omitted from `general_fields`, a missing canonical item is emitted
     with `NEEDS_TEACHER_REVIEW`, leaving `is_valid is True` without blocking.
   - Only the canonical `duracion_proyecto` key satisfies presence; a generic legacy
     `duracion` does not mask the missing project-level field.
   - Empty/missing value field in `general_fields` results in `NEEDS_TEACHER_REVIEW`.
"""

from __future__ import annotations

import hashlib
import pytest

from curriculum.source_interpreter import (
    ORIGIN_EXTRACTED,
    ORIGIN_PROPOSED,
    REVIEW_PENDING,
    STATUS_AMBIGUOUS,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    ImportDossier,
    InterpretedField,
    SessionPlan,
    SourceReference,
)
from curriculum.verification import (
    CANONICAL_GENERAL_FIELDS,
    STATUS_BLOCKED,
    STATUS_CHECKED,
    STATUS_NEEDS_TEACHER_REVIEW,
    verify_curriculum_dossier,
)
from test_t15_curriculum_import import make_minimal_pdf


def _make_two_page_pdf(p1_text: str, p2_text: str) -> tuple[bytes, str]:
    pdf_bytes = make_minimal_pdf([p1_text, p2_text])
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    return pdf_bytes, sha256


def _base_dossier(sha256: str, general_fields: dict[str, InterpretedField] | None = None) -> ImportDossier:
    base_fields: dict[str, InterpretedField] = {
        "proyecto": InterpretedField(
            name="proyecto",
            value="Proyecto Comunitario del Agua",
            origin=ORIGIN_EXTRACTED,
            status=STATUS_SUPPORTED,
            evidence=[
                SourceReference(
                    document_sha256=sha256,
                    page_number=1,
                    excerpt="Proyecto Comunitario del Agua",
                )
            ],
        ),
        "campos_formativos": InterpretedField(
            name="campos_formativos",
            value="Lenguajes",
            origin=ORIGIN_EXTRACTED,
            status=STATUS_SUPPORTED,
            evidence=[
                SourceReference(
                    document_sha256=sha256,
                    page_number=1,
                    excerpt="Campo Lenguajes",
                )
            ],
        ),
        "proposito": InterpretedField(
            name="proposito",
            value="Conocer el ciclo del agua",
            origin=ORIGIN_PROPOSED,
            status=STATUS_AMBIGUOUS,
            evidence=[],
        ),
        "finalidad": InterpretedField(
            name="finalidad",
            value="Sensibilizar a la comunidad sobre el uso responsable del agua",
            origin=ORIGIN_PROPOSED,
            status=STATUS_AMBIGUOUS,
            evidence=[
                SourceReference(
                    document_sha256=sha256,
                    page_number=1,
                    excerpt="Sensibilizar a la comunidad sobre el uso responsable del agua",
                )
            ],
        ),
    }
    if general_fields:
        base_fields.update(general_fields)

    base_session = SessionPlan(
        session_id="s1",
        session_number=1,
        title="Sesion 1",
        project_title="Proyecto Comunitario del Agua",
        pages=[2],
        layout_fidelity="verbatim_blocks",
        layout_notes="",
        fields={
            "inicio": InterpretedField(
                name="inicio",
                value="Actividad de apertura",
                origin=ORIGIN_EXTRACTED,
                status=STATUS_SUPPORTED,
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=2,
                        excerpt="Actividad de apertura",
                    )
                ],
            ),
            "desarrollo": InterpretedField(
                name="desarrollo",
                value="Actividad de desarrollo",
                origin=ORIGIN_EXTRACTED,
                status=STATUS_SUPPORTED,
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=2,
                        excerpt="Actividad de desarrollo",
                    )
                ],
            ),
            "cierre": InterpretedField(
                name="cierre",
                value="Actividad de cierre",
                origin=ORIGIN_EXTRACTED,
                status=STATUS_SUPPORTED,
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=2,
                        excerpt="Actividad de cierre",
                    )
                ],
            ),
        },
        activities=[],
        status=STATUS_SUPPORTED,
        review=REVIEW_PENDING,
    )

    return ImportDossier(
        source_sha256=sha256,
        source_name="planeacion_sintetica.pdf",
        page_count=2,
        general_fields=base_fields,
        sessions=[base_session],
    )


# ==============================================================================
# 1. CANONICAL MEMBERSHIP
# ==============================================================================

def test_duracion_proyecto_is_canonical_general_field():
    """`duracion_proyecto` must be registered in CANONICAL_GENERAL_FIELDS."""
    assert "duracion_proyecto" in CANONICAL_GENERAL_FIELDS


# ==============================================================================
# 2. CROSS-PAGE PROPOSED DURATION VERIFICATION (NEEDS_TEACHER_REVIEW, NOT CHECKED)
# ==============================================================================

def test_proposed_duration_cross_page_verified_page_by_page_remains_needs_review_not_checked():
    """Two-page proposed duration is mechanically matched page-by-page and stays NEEDS_TEACHER_REVIEW."""
    p1 = (
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Campo Lenguajes\n"
        "Proyecto Comunitario del Agua\n"
        "Sensibilizar a la comunidad sobre el uso responsable del agua\n"
        "Tiempo de aplicacion: Se sugiere"
    )
    p2 = (
        "dos semanas lectivas para su desarrollo\n"
        "SESION 1: Sesion 1\n"
        "Actividad de apertura\n"
        "Actividad de desarrollo\n"
        "Actividad de cierre"
    )
    pdf_bytes, sha = _make_two_page_pdf(p1, p2)

    dur_field = InterpretedField(
        name="duracion_proyecto",
        value="Se sugiere dos semanas lectivas",
        origin=ORIGIN_PROPOSED,
        status=STATUS_AMBIGUOUS,
        review=REVIEW_PENDING,
        reason="Sugerencia de temporalidad global identificada entre paginas 1 y 2.",
        evidence=[
            SourceReference(document_sha256=sha, page_number=1, excerpt="Tiempo de aplicacion: Se sugiere"),
            SourceReference(document_sha256=sha, page_number=2, excerpt="dos semanas lectivas para su desarrollo"),
        ],
    )

    dossier = _base_dossier(sha, {"duracion_proyecto": dur_field})
    report = verify_curriculum_dossier(dossier, pdf_bytes)

    # Must be valid without blocking
    assert report.is_valid is True
    assert report.blocked_count == 0

    # Locate the verification item for duracion_proyecto
    dur_item = next(it for it in report.items if it["target"] == "general.duracion_proyecto")

    # Invariant: Must remain NEEDS_TEACHER_REVIEW, never CHECKED as semantic truth
    assert dur_item["status"] == STATUS_NEEDS_TEACHER_REVIEW
    assert dur_item["status"] != STATUS_CHECKED

    # Invariant: Evidence citations are verified mechanically page by page
    citations = dur_item["details"].get("evidence_citations", [])
    assert len(citations) == 2
    assert citations[0]["page_number"] == 1
    assert citations[0]["matched"] is True
    assert citations[1]["page_number"] == 2
    assert citations[1]["matched"] is True

    # First matched page/excerpt metadata points to page 1 primary citation
    assert dur_item["page_number"] == 1
    assert "Tiempo de aplicacion" in dur_item["excerpt"]


# ==============================================================================
# 3. CONTRADICTION / MISMATCH (BLOCKED)
# ==============================================================================

def test_duration_evidence_not_on_indicated_page_is_blocked():
    """An evidence excerpt citing text that does not exist on that physical page is BLOCKED."""
    p1 = (
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Campo Lenguajes\n"
        "Proyecto Comunitario del Agua\n"
        "Sensibilizar a la comunidad sobre el uso responsable del agua\n"
        "Tiempo de aplicacion: Se sugiere"
    )
    p2 = (
        "dos semanas lectivas para su desarrollo\n"
        "SESION 1: Sesion 1\n"
        "Actividad de apertura\n"
        "Actividad de desarrollo\n"
        "Actividad de cierre"
    )
    pdf_bytes, sha = _make_two_page_pdf(p1, p2)

    # Invert pages or provide text absent from page 1: cite page 2 text as page 1
    dur_field = InterpretedField(
        name="duracion_proyecto",
        value="Dos semanas lectivas",
        origin=ORIGIN_PROPOSED,
        status=STATUS_AMBIGUOUS,
        review=REVIEW_PENDING,
        evidence=[
            SourceReference(
                document_sha256=sha,
                page_number=1,
                excerpt="dos semanas lectivas para su desarrollo",  # Present on page 2, NOT on page 1!
            )
        ],
    )

    dossier = _base_dossier(sha, {"duracion_proyecto": dur_field})
    report = verify_curriculum_dossier(dossier, pdf_bytes)

    # Invariant: Physical mismatch causes hard failure
    assert report.is_valid is False
    assert report.blocked_count >= 1

    blocked_item = next(
        it for it in report.items
        if "duracion_proyecto" in it["target"] and it["status"] == STATUS_BLOCKED
    )
    assert blocked_item["page_number"] == 1
    assert "no se encuentra en la página física 1" in blocked_item["message"].lower()


def test_composite_duration_evidence_blocks_when_only_second_page_citation_is_wrong():
    """A valid primary citation cannot hide a contradictory second-page citation."""
    p1 = (
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Campo Lenguajes\n"
        "Proyecto Comunitario del Agua\n"
        "Tiempo de aplicacion: Se sugiere"
    )
    p2 = "dos semanas lectivas para su desarrollo\nDESARROLLO DEL PROYECTO"
    pdf_bytes, sha = _make_two_page_pdf(p1, p2)

    dur_field = InterpretedField(
        name="duracion_proyecto",
        value="Se sugiere dos semanas lectivas",
        origin=ORIGIN_PROPOSED,
        status=STATUS_AMBIGUOUS,
        review=REVIEW_PENDING,
        evidence=[
            SourceReference(document_sha256=sha, page_number=1, excerpt="Tiempo de aplicacion: Se sugiere"),
            SourceReference(document_sha256=sha, page_number=2, excerpt="texto que no aparece en la pagina"),
        ],
    )
    dossier = _base_dossier(sha, {"duracion_proyecto": dur_field})

    report = verify_curriculum_dossier(dossier, pdf_bytes)

    assert report.is_valid is False
    assert report.blocked_count >= 1
    blocked_item = next(
        it for it in report.items
        if it["target"] == "general.duracion_proyecto.evidence.1"
        and it["status"] == STATUS_BLOCKED
    )
    assert blocked_item["page_number"] == 2
    assert "no se encuentra en la página física 2" in blocked_item["message"].lower()


# ==============================================================================
# 4. ABSENCE AND CANONICAL INTEGRITY
# ==============================================================================

def test_absence_of_duracion_proyecto_emits_needs_teacher_review_without_blocking():
    """When duracion_proyecto is missing from general_fields, it emits a missing item needing review."""
    p1 = (
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Campo Lenguajes\n"
        "Proyecto Comunitario del Agua\n"
        "Sensibilizar a la comunidad sobre el uso responsable del agua"
    )
    p2 = (
        "SESION 1: Sesion 1\n"
        "Actividad de apertura\n"
        "Actividad de desarrollo\n"
        "Actividad de cierre"
    )
    pdf_bytes, sha = _make_two_page_pdf(p1, p2)

    # Dossier without duracion_proyecto
    dossier = _base_dossier(sha)
    assert "duracion_proyecto" not in dossier.general_fields

    report = verify_curriculum_dossier(dossier, pdf_bytes)

    # Absence does not cause hard failure (not blocked)
    assert report.is_valid is True
    assert report.blocked_count == 0

    missing_item = next(
        it for it in report.items
        if it["target"] == "general.duracion_proyecto" and it["item_id"] == "gen_duracion_proyecto_missing"
    )
    assert missing_item["status"] == STATUS_NEEDS_TEACHER_REVIEW
    assert "no está presente en la planeación" in missing_item["message"]
    assert missing_item["details"]["present"] is False


def test_present_duracion_proyecto_does_not_emit_missing_item():
    """When duracion_proyecto is present, report does not flag it as missing."""
    p1 = (
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Campo Lenguajes\n"
        "Proyecto Comunitario del Agua\n"
        "Sensibilizar a la comunidad sobre el uso responsable del agua\n"
        "Tiempo de aplicacion: Dos semanas"
    )
    p2 = (
        "SESION 1: Sesion 1\n"
        "Actividad de apertura\n"
        "Actividad de desarrollo\n"
        "Actividad de cierre"
    )
    pdf_bytes, sha = _make_two_page_pdf(p1, p2)

    dur_field = InterpretedField(
        name="duracion_proyecto",
        value="Dos semanas",
        origin=ORIGIN_PROPOSED,
        status=STATUS_AMBIGUOUS,
        review=REVIEW_PENDING,
        evidence=[
            SourceReference(document_sha256=sha, page_number=1, excerpt="Tiempo de aplicacion: Dos semanas")
        ],
    )
    dossier = _base_dossier(sha, {"duracion_proyecto": dur_field})
    report = verify_curriculum_dossier(dossier, pdf_bytes)

    # Missing item must NOT be emitted
    missing_items = [it for it in report.items if it["item_id"] == "gen_duracion_proyecto_missing"]
    assert len(missing_items) == 0

    # Field item exists and is validated
    dur_items = [it for it in report.items if it["target"] == "general.duracion_proyecto"]
    assert len(dur_items) == 1
    assert dur_items[0]["status"] == STATUS_NEEDS_TEACHER_REVIEW


def test_legacy_duracion_does_not_hide_missing_project_duration():
    """A generic legacy duration must not stand in for project-level duration."""
    p1 = (
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Campo Lenguajes\n"
        "Proyecto Comunitario del Agua\n"
        "Sensibilizar a la comunidad sobre el uso responsable del agua\n"
        "Tiempo de aplicacion: Dos semanas"
    )
    p2 = (
        "SESION 1: Sesion 1\n"
        "Actividad de apertura\n"
        "Actividad de desarrollo\n"
        "Actividad de cierre"
    )
    pdf_bytes, sha = _make_two_page_pdf(p1, p2)

    dur_field = InterpretedField(
        name="duracion",
        value="Dos semanas",
        origin=ORIGIN_PROPOSED,
        status=STATUS_AMBIGUOUS,
        review=REVIEW_PENDING,
        evidence=[
            SourceReference(document_sha256=sha, page_number=1, excerpt="Tiempo de aplicacion: Dos semanas")
        ],
    )
    dossier = _base_dossier(sha, {"duracion": dur_field})
    report = verify_curriculum_dossier(dossier, pdf_bytes)

    missing_items = [it for it in report.items if it["item_id"] == "gen_duracion_proyecto_missing"]
    assert len(missing_items) == 1
    assert missing_items[0]["status"] == STATUS_NEEDS_TEACHER_REVIEW
