import pytest
import hashlib
from curriculum.source_interpreter import (
    ORIGIN_EXTRACTED, REVIEW_PENDING, STATUS_SUPPORTED,
    ImportDossier, InterpretedField, SessionPlan, SourceReference, SessionActivity,
)
from curriculum.verification import (
    STATUS_BLOCKED, STATUS_CHECKED, STATUS_NEEDS_TEACHER_REVIEW,
    verify_curriculum_dossier, normalize_text_for_evidence_check,
)

pytestmark = pytest.mark.django_db

def _make_synthetic_pdf(pages_text):
    content = "\n---PAGE---\n".join(pages_text).encode("utf-8")
    sha = hashlib.sha256(content).hexdigest()
    return content, sha, pages_text

def _field(name, value, *, origin=ORIGIN_EXTRACTED, status=STATUS_SUPPORTED, review=REVIEW_PENDING, evidence=None, source_sha="", page=1):
    ev_list = evidence if evidence is not None else (
        [SourceReference(document_sha256=source_sha, page_number=page, excerpt=value)]
        if source_sha and value else []
    )
    return InterpretedField(name=name, value=value, origin=origin, status=status, review=review, evidence=ev_list)

def _session(sid, num, title, pages, fields):
    return SessionPlan(session_id=sid, session_number=num, title=title, pages=pages, fields=fields)

def _make_dossier(pages_text, sessions, general_fields=None):
    pdf_source = _make_synthetic_pdf(pages_text)
    sha = pdf_source[1]
    if general_fields is None:
        general_fields = {
            "proyecto": _field("proyecto", "Proyecto Sintético", source_sha=sha, page=1),
            "asignatura": _field("asignatura", "Lenguajes", source_sha=sha, page=1),
            "proposito": _field("proposito", "Propósito de prueba", source_sha=sha, page=1),
            "finalidad": _field("finalidad", "Finalidad de prueba", source_sha=sha, page=1),
        }
    dossier = ImportDossier(
        source_sha256=sha, page_count=len(pages_text),
        source_name="synthetic.pdf",
        sessions=sessions, general_fields=general_fields,
    )
    return dossier, pdf_source


class TestInventedValueNotChecked:
    def test_invented_value_with_real_excerpt_not_checked(self):
        """Astra probe: value='CONTENIDO INVENTADO', excerpt='Inicio' (exists on page)
        must NOT produce STATUS_CHECKED."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio Desarrollo Cierre"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]
        
        s1 = _session("s1", 1, "Sesión 1", [1], {
            "inicio": InterpretedField(
                name="inicio", value="CONTENIDO INVENTADO",
                origin=ORIGIN_EXTRACTED, status=STATUS_SUPPORTED, review=REVIEW_PENDING,
                evidence=[SourceReference(
                    document_sha256=sha, page_number=1,
                    excerpt="Inicio",  # This IS on the page
                )],
            ),
            "desarrollo": _field("desarrollo", "Desarrollo", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre", source_sha=sha, page=1),
        })
        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)
        
        # The 'inicio' field with value 'CONTENIDO INVENTADO' must NOT be checked
        inicio_checked = [
            i for i in report.items
            if i.get("status") == STATUS_CHECKED
            and "inicio" in i.get("details", {}).get("field_name", "")
            and "s1" in i.get("target", "")
        ]
        assert len(inicio_checked) == 0, (
            f"Invented value 'CONTENIDO INVENTADO' must NOT be checked; "
            f"found {len(inicio_checked)} checked items for 'inicio'"
        )


class TestDuplicateEvidenceNoInflation:
    def test_duplicate_evidence_does_not_inflate_counter(self):
        """Astra probe: duplicating the same evidence must not increment checked_count."""
        pages = [
            "Proyecto Sintético Lenguajes Propósito de prueba Finalidad de prueba "
            "Inicio real Desarrollo real Cierre real"
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]
        
        # Single evidence
        s1_single = _session("s1", 1, "Sesión 1", [1], {
            "inicio": InterpretedField(
                name="inicio", value="Inicio real",
                origin=ORIGIN_EXTRACTED, status=STATUS_SUPPORTED, review=REVIEW_PENDING,
                evidence=[SourceReference(document_sha256=sha, page_number=1, excerpt="Inicio real")],
            ),
            "desarrollo": _field("desarrollo", "Desarrollo real", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre real", source_sha=sha, page=1),
        })
        dossier_single, src_single = _make_dossier(pages, [s1_single])
        report_single = verify_curriculum_dossier(dossier_single, src_single)
        
        # Duplicate evidence (same excerpt repeated)
        s1_dup = _session("s1", 1, "Sesión 1", [1], {
            "inicio": InterpretedField(
                name="inicio", value="Inicio real",
                origin=ORIGIN_EXTRACTED, status=STATUS_SUPPORTED, review=REVIEW_PENDING,
                evidence=[
                    SourceReference(document_sha256=sha, page_number=1, excerpt="Inicio real"),
                    SourceReference(document_sha256=sha, page_number=1, excerpt="Inicio real"),  # duplicate!
                ],
            ),
            "desarrollo": _field("desarrollo", "Desarrollo real", source_sha=sha, page=1),
            "cierre": _field("cierre", "Cierre real", source_sha=sha, page=1),
        })
        dossier_dup, src_dup = _make_dossier(pages, [s1_dup])
        report_dup = verify_curriculum_dossier(dossier_dup, src_dup)
        
        assert report_dup.checked_count == report_single.checked_count, (
            f"Duplicate evidence inflated counter: single={report_single.checked_count}, "
            f"dup={report_dup.checked_count}"
        )


class TestCrossSessionBelongingVerification:
    def test_cross_session_content_assignment_not_checked_on_shared_page(self):
        """Review probe: Two sessions on page 1. 'Leer un cuento' belongs structurally
        only to session 1. Assigning it to s2.inicio must NOT produce checked, but
        needs_review/blocked with reason 'asociación estructural no demostrada'."""
        pages = [
            "Sesión 1: Lectura. Inicio: Leer un cuento. Desarrollo: Preguntas. Cierre: Dibujo.\n"
            "Sesión 2: Escritura. Inicio: Redactar texto. Desarrollo: Revisar. Cierre: Compartir."
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        s1 = _session("s1", 1, "Sesión 1: Lectura", [1], {
            "inicio": _field("inicio", "Leer un cuento", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Preguntas", source_sha=sha, page=1),
            "cierre": _field("cierre", "Dibujo", source_sha=sha, page=1),
        })
        # s2 incorrectly assigns s1 content 'Leer un cuento' to its inicio
        s2 = _session("s2", 2, "Sesión 2: Escritura", [1], {
            "inicio": _field("inicio", "Leer un cuento", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Revisar", source_sha=sha, page=1),
            "cierre": _field("cierre", "Compartir", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1, s2])
        report = verify_curriculum_dossier(dossier, src)

        # Session 1 inicio evidence should be checked
        s1_inicio_items = [
            it for it in report.items
            if it.get("target") == "session.s1.inicio.evidence.0"
        ]
        assert len(s1_inicio_items) == 1
        assert s1_inicio_items[0].get("status") == STATUS_CHECKED

        # Session 2 inicio evidence MUST NOT be checked
        s2_inicio_items = [
            it for it in report.items
            if it.get("target") == "session.s2.inicio.evidence.0"
        ]
        assert len(s2_inicio_items) == 1
        s2_item = s2_inicio_items[0]
        assert s2_item.get("status") in (STATUS_NEEDS_TEACHER_REVIEW, STATUS_BLOCKED), (
            f"Expected s2.inicio to be needs_review/blocked, got '{s2_item.get('status')}'"
        )
        msg_and_reason = (
            str(s2_item.get("message", "")) + " " +
            str(s2_item.get("details", {}).get("reason", ""))
        ).lower()
        assert "asociacion estructural no demostrada" in normalize_text_for_evidence_check(msg_and_reason), (
            f"Expected reason 'asociación estructural no demostrada' in {s2_item}"
        )

    def test_session_evidence_page_outside_declared_session_pages_not_checked(self):
        """Condition (a): evidence page must be within declared pages of that session."""
        pages = [
            "Sesión 1: Lectura. Inicio: Leer cuento. Desarrollo: Preguntas. Cierre: Dibujo.",
            "Sesión 2: Escritura. Inicio: Redactar. Desarrollo: Revisar. Cierre: Compartir.",
        ]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        # s1 declared on page 1, but cites evidence on page 2
        s1 = _session("s1", 1, "Sesión 1", [1], {
            "inicio": _field("inicio", "Redactar", source_sha=sha, page=2),
            "desarrollo": _field("desarrollo", "Preguntas", source_sha=sha, page=1),
            "cierre": _field("cierre", "Dibujo", source_sha=sha, page=1),
        })

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        s1_inicio_items = [
            it for it in report.items
            if it.get("target") == "session.s1.inicio.evidence.0"
        ]
        assert len(s1_inicio_items) == 1
        s1_item = s1_inicio_items[0]
        assert s1_item.get("status") in (STATUS_NEEDS_TEACHER_REVIEW, STATUS_BLOCKED)
        msg_and_reason = (
            str(s1_item.get("message", "")) + " " +
            str(s1_item.get("details", {}).get("reason", ""))
        ).lower()
        assert "asociacion estructural no demostrada" in normalize_text_for_evidence_check(msg_and_reason)


class TestSessionActivityContract:
    def test_activity_with_nonexistent_annex_id_is_blocked(self):
        """Review probe: invented activity with annex_ids=['anexo_inexistente']
        must produce BLOCKED (not zero blocks / silence)."""
        pages = ["Sesión 1: Prueba. Inicio: Algo. Desarrollo: Mas. Cierre: Fin."]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        act = SessionActivity(
            activity_id="act_1",
            title="Actividad con anexo falso",
            description="Hacer tarea con anexo inexistente",
            order=1,
            annex_ids=["anexo_inexistente"],
            evidence=[SourceReference(document_sha256=sha, page_number=1, excerpt="Inicio: Algo")],
        )
        s1 = _session("s1", 1, "Sesión 1", [1], {
            "inicio": _field("inicio", "Algo", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Mas", source_sha=sha, page=1),
            "cierre": _field("cierre", "Fin", source_sha=sha, page=1),
        })
        s1.activities = [act]

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        assert report.blocked_count > 0, "Activity with nonexistent annex_id must be BLOCKED, not 0 blocks"
        blocked_items = [
            it for it in report.items
            if it.get("status") == STATUS_BLOCKED and "anexo_inexistente" in str(it)
        ]
        assert len(blocked_items) >= 1

    def test_activity_without_evidence_is_needs_review(self):
        """Activity without evidence -> needs_review."""
        pages = ["Sesión 1: Prueba. Inicio: Algo. Desarrollo: Mas. Cierre: Fin."]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        act = SessionActivity(
            activity_id="act_1",
            title="Actividad sin evidencia",
            description="No hay citas en el PDF",
            order=1,
            annex_ids=[],
            evidence=[],  # No evidence
        )
        s1 = _session("s1", 1, "Sesión 1", [1], {
            "inicio": _field("inicio", "Algo", source_sha=sha, page=1),
            "desarrollo": _field("desarrollo", "Mas", source_sha=sha, page=1),
            "cierre": _field("cierre", "Fin", source_sha=sha, page=1),
        })
        s1.activities = [act]

        dossier, src = _make_dossier(pages, [s1])
        report = verify_curriculum_dossier(dossier, src)

        review_items = [
            it for it in report.items
            if it.get("status") == STATUS_NEEDS_TEACHER_REVIEW
            and "activity" in it.get("target", "")
        ]
        assert len(review_items) >= 1


class TestListTypeValueVerification:
    def test_list_type_field_value_checked_when_elements_present_in_page(self):
        """Hallazgo 5: Fields with list values (e.g. ['Lenguajes']) must NOT lose
        checked status due to str(val) producing bracketed repr string."""
        pages = ["Proyecto Sintético. Campos formativos: Lenguajes. Propósito: Aprender. Finalidad: Educar."]
        pdf_src = _make_synthetic_pdf(pages)
        sha = pdf_src[1]

        dossier, src = _make_dossier(pages, [])
        dossier.general_fields["campos_formativos"] = InterpretedField(
            name="campos_formativos",
            value=["Lenguajes"],
            origin=ORIGIN_EXTRACTED,
            status=STATUS_SUPPORTED,
            review=REVIEW_PENDING,
            evidence=[SourceReference(document_sha256=sha, page_number=1, excerpt="Lenguajes")],
        )

        report = verify_curriculum_dossier(dossier, src)
        cf_items = [it for it in report.items if it.get("target") == "general.campos_formativos.evidence.0"]
        assert len(cf_items) == 1
        assert cf_items[0].get("status") == STATUS_CHECKED, (
            f"Expected checked status for list-valued field, got {cf_items[0].get('status')}: {cf_items[0]}"
        )
