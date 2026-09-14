import pytest
import hashlib
from curriculum.source_interpreter import (
    ORIGIN_EXTRACTED, REVIEW_PENDING, STATUS_SUPPORTED,
    ImportDossier, InterpretedField, SessionPlan, SourceReference,
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
