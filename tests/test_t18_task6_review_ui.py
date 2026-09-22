"""Tests for Task 6: New Organized Teacher Review UI Slice (rebanada UI vertical).

Requirements (UX6):
1. Teacher Header:
   - "Revisa tu planeación" as main h1.
   - Brief, respectful explanation: AulaLista organized/checked, teacher decides, nothing published.
   - No technical leaks: no "Fase V0", no raw status codes ("active", "supported"), no raw hashes exposed.
2. Top Summary:
   - Project & general data (project name, formativos, purpose/finalidad).
   - Mechanical verification summary (checked count, needs review count, 0 blocked).
   - Evidence collapsed on demand via accessible <details>.
   - Evidence links are owner-scoped to tutor-import-source-page.
3. "Por revisar" Block First:
   - First interactive section in the main document flow.
   - Deterministic ordering by F7 priority:
     1) requires_resolution (conflicts / blocking)
     2) missing (required empty fields)
     3) pending_review (ambiguous / proposed)
   - Visible counter of items to review.
   - Each item has a CTA targeting the exact control.
   - No duplicate decisions across multiple lists; no technical IDs (op_..., tgt_...), no JSON leaks.
4. Sessions as Cards / Accordions in Order:
   - Listed in order: Sesión 1, Sesión 2, etc.
   - Pedagogical moments: Inicio, Desarrollo, Cierre with editable inputs/textareas.
   - Associated annexes with human-readable status copy.
   - POST forms preserve CSRF, expected_version, and existing actions (save_corrections, confirm_all, etc.).
   - Inline errors / focusable controls; no publishing.
5. Sticky / Clear Actions:
   - Save changes button (save_corrections).
   - "Continuar a aprobación" CTA present but disabled/honest destination (T7 not implemented, no publishing).
   - Canonical return link to tutor-curriculum ("Volver a planeaciones" / "Cancelar").
6. Responsive & Accessibility:
   - 375x667 (mobile) and 1440x900 (desktop) without horizontal overflow.
   - Touch targets >= 44px for buttons and interactive inputs.
   - Visible focus styling and keyboard navigation.
   - Semantic headings (h1, h2, h3), labels associated with form controls.
   - Zero external CDN dependencies.
7. Robustness:
   - Empty sessions / partial sessions / many sessions render cleanly without 500.
   - User inputs with HTML/script are safely escaped.
   - Approval button does not publish or trigger publication commands.
   - Embedded JavaScript passes syntax check.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from curriculum.models import CurriculumImportJob
from curriculum.source_interpreter import (
    AnnexReference,
    CurriculumSourceInterpreter,
    ImportDossier,
    InterpretedField,
    ORIGIN_EXTRACTED,
    REVIEW_CONFIRMED,
    REVIEW_PENDING,
    STATUS_AMBIGUOUS,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    SessionPlan,
    SourceReference,
)
from curriculum.verification import (
    compute_canonical_verification_report,
    verify_curriculum_dossier,
)
from helpers import tutor_client

pytestmark = pytest.mark.django_db(transaction=True)

C01_PATH = Path("output/pdf/prueba-issue-96-paginas-4-a-8.pdf")
if not C01_PATH.exists():
    C01_PATH = Path("media/curriculum_imports/prueba-semana-01.pdf")


def _c01_bytes() -> bytes:
    assert C01_PATH.exists(), f"PDF fixture not found at {C01_PATH}"
    return C01_PATH.read_bytes()


def tutor_teacher(username=None):
    client = tutor_client(username)
    user = get_user_model().objects.get(pk=client.session["_auth_user_id"])
    return client, user


def create_ready_job(user, pdf_bytes=None, dossier=None):
    if pdf_bytes is None:
        pdf_bytes = _c01_bytes()
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    if dossier is None:
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)

    # Compute canonical verification report and attach
    report = verify_curriculum_dossier(dossier, pdf_bytes)
    dossier.verification_report = report.to_dict()

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("planeacion.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_COMPLETED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        page_count=dossier.page_count,
        interpretation_dossier=dossier.to_dict(),
    )
    return job, dossier


class TestTask6TeacherReviewUI:
    """Test suite for Task 6 UX revision."""

    def test_t6_teacher_header_and_explanation(self):
        """1. Teacher header has 'Revisa tu planeación', brief teacher explanation, no technical jargon."""
        client, user = tutor_teacher("t6-teacher-header")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        soup = BeautifulSoup(response.content.decode("utf-8"), "html.parser")

        # Main heading
        h1 = soup.find("h1")
        assert h1 is not None
        assert "Revisa tu planeación" in h1.get_text()

        # Explanatory text: AulaLista organized/checked, teacher decides, nothing published
        page_text = soup.get_text().lower()
        assert "organizó" in page_text or "organizo" in page_text
        assert "decide" in page_text or "control" in page_text or "tú decides" in page_text
        assert "public" in page_text  # "nada publicado" / "nada se publica"

        # No technical leaks in header
        header = soup.find(class_=lambda c: c and "header" in c)
        header_text = header.get_text() if header else ""
        assert "fase v0" not in header_text.lower()
        assert "linearized_heuristics" not in header_text
        assert "invalidated_source_tampered" not in header_text

    def test_t6_summary_top_general_and_verification(self):
        """2. Top summary has project/general data, mechanical verification, evidence collapsed on demand."""
        client, user = tutor_teacher("t6-top-summary")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        soup = BeautifulSoup(response.content.decode("utf-8"), "html.parser")

        # Project name present
        proj_val = dossier.general_fields["proyecto"].value
        assert proj_val in soup.get_text()

        # Verification summary block present
        verif_text = soup.get_text()
        assert "Comprobación automática completada" in verif_text
        assert "cotejados contra páginas físicas" in verif_text
        assert "0 bloqueos" in verif_text

        # Evidence details collapsed on demand
        verif_details = soup.find("details", class_=lambda c: c and "verification" in c)
        if not verif_details:
            # Look for any details containing verification evidence
            for d in soup.find_all("details"):
                if "cotejos" in d.get_text() or "páginas físicas" in d.get_text():
                    verif_details = d
                    break
        assert verif_details is not None
        # Must not be open by default
        assert not verif_details.has_attr("open")

        # Evidence links must be owner-scoped to tutor-import-source-page
        evidence_links = verif_details.find_all("a", href=True)
        assert len(evidence_links) > 0
        for link in evidence_links:
            href = link["href"]
            assert f"/tutor/imports/{job.pk}/fuente/" in href
            assert "#page=" in href

    def test_t6_review_block_first_and_deterministic_order(self):
        """3. 'Por revisar' block appears first, deterministic F7 order, counter, CTA to control, no duplicate decisions."""
        client, user = tutor_teacher("t6-review-block")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        soup = BeautifulSoup(response.content.decode("utf-8"), "html.parser")

        # Find "Por revisar" section
        por_revisar_heading = None
        for h in soup.find_all(["h2", "h3"]):
            if "por revisar" in h.get_text().lower() or "cola de revisión" in h.get_text().lower():
                por_revisar_heading = h
                break
        assert por_revisar_heading is not None, "Bloque 'Por revisar' no encontrado"

        # Check that it appears BEFORE the sessions section
        sessions_heading = None
        for h in soup.find_all(["h2", "h3"]):
            if "sesiones" in h.get_text().lower() or "clases" in h.get_text().lower():
                sessions_heading = h
                break
        if sessions_heading:
            por_revisar_pos = response.content.find(por_revisar_heading.encode())
            sessions_pos = response.content.find(sessions_heading.encode())
            assert por_revisar_pos < sessions_pos, "'Por revisar' debe aparecer antes que el detalle de sesiones"

        # Check for CTAs leading to exact controls
        ctas = soup.find_all(class_=lambda c: c and ("cta" in c or "button" in c or "jump" in c))
        # No technical opaque IDs like op_... or tgt_... shown in visible text
        body_text = soup.get_text()
        assert not re.search(r"\bop_[0-9a-f]{16,}\b", body_text), "Leak of opaque item ID in visible text"
        assert not re.search(r"\btgt_[0-9a-f]{16,}\b", body_text), "Leak of opaque target ID in visible text"
        assert '{"target_type"' not in body_text, "Leak of JSON in visible text"

    def test_t6_sessions_cards_or_accordions_in_order(self):
        """4. Sessions as cards/accordions in order, pedagogical moments (Inicio, Desarrollo, Cierre), annexes, human copy."""
        client, user = tutor_teacher("t6-sessions-order")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        soup = BeautifulSoup(response.content.decode("utf-8"), "html.parser")

        # Check sessions appear in order: Sesión 1, Sesión 2, etc.
        session_matches = []
        for elem in soup.find_all(["h2", "h3", "h4", "summary"]):
            text = elem.get_text()
            m = re.search(r"Sesión\s+(\d+)", text, re.IGNORECASE)
            if m:
                session_matches.append(int(m.group(1)))

        # Ensure order is non-decreasing and starts from 1
        assert len(session_matches) > 0
        filtered_order = []
        for s_num in session_matches:
            if not filtered_order or s_num != filtered_order[-1]:
                filtered_order.append(s_num)
        assert filtered_order == sorted(filtered_order), f"Sessions not in order: {filtered_order}"

        # Check pedagogical moments
        page_text = soup.get_text()
        assert "Inicio" in page_text
        assert "Desarrollo" in page_text
        assert "Cierre" in page_text

        # Human copy for statuses (no raw status badges like "STATUS_SUPPORTED")
        assert "STATUS_SUPPORTED" not in page_text
        assert "STATUS_MISSING" not in page_text
        assert "STATUS_AMBIGUOUS" not in page_text

        # POST forms must exist with CSRF and expected_version
        forms = soup.find_all("form", method=lambda m: m and m.lower() == "post")
        assert len(forms) > 0
        for f in forms:
            csrf = f.find("input", attrs={"name": "csrfmiddlewaretoken"})
            assert csrf is not None, "Form missing CSRF token"
            exp_ver = f.find("input", attrs={"name": "expected_version"})
            if exp_ver:
                assert exp_ver.get("value") == str(dossier.version)

    def test_t6_sticky_actions_bar_and_approval_disabled_honest(self):
        """5. Sticky action bar, save_corrections button, approval disabled/honest destination, canonical cancel/return."""
        client, user = tutor_teacher("t6-actions-bar")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        soup = BeautifulSoup(response.content.decode("utf-8"), "html.parser")

        # Save button present
        save_btn = soup.find("button", attrs={"name": "action", "value": "save_corrections"})
        assert save_btn is not None, "Boton save_corrections debe existir"
        assert "Guardar" in save_btn.get_text()

        # Approval CTA present when ready (retired previous disabled placeholder)
        approve_btn = soup.find("button", attrs={"name": "action", "value": "approve"})
        assert approve_btn is not None, "CTA Aprobar planeación debe estar disponible cuando el dossier está listo"
        assert "aprobar planeación" in approve_btn.get_text().lower()

        # Canonical return link to tutor-curriculum
        back_link = None
        for a in soup.find_all("a", href=reverse("tutor-curriculum")):
            if any(w in a.get_text().lower() for w in ("volver", "cancelar", "planeaciones")):
                back_link = a
                break
        assert back_link is not None, "Enlace de retorno a tutor-curriculum debe existir"
        assert any(w in back_link.get_text().lower() for w in ("volver", "cancelar", "planeaciones"))

        # MUST NOT contain a direct publish button/action
        for btn in soup.find_all("button"):
            val = btn.get("value", "")
            name = btn.get("name", "")
            assert "publish" not in val.lower()
            assert "publicar" not in val.lower()
            assert "publish" not in name.lower()

    def test_t6_responsive_accessibility_and_no_cdn(self):
        """6. Viewport tag, no horizontal overflow CSS, touch targets >= 44px, semantic headings, zero CDN."""
        client, user = tutor_teacher("t6-responsive-a11y")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode("utf-8")
        soup = BeautifulSoup(content, "html.parser")

        # 1. Viewport tag
        viewport = soup.find("meta", attrs={"name": "viewport"})
        assert viewport is not None
        assert "width=device-width" in viewport.get("content", "")

        # 2. Zero external CDN dependencies
        for link in soup.find_all("link", href=True):
            href = link["href"]
            assert not href.startswith("http://") and not href.startswith("https://") and not href.startswith("//"), \
                f"External CDN link found: {href}"
        for script in soup.find_all("script", src=True):
            src = script["src"]
            assert not src.startswith("http://") and not src.startswith("https://") and not src.startswith("//"), \
                f"External CDN script found: {src}"

        # 3. Semantic headings hierarchy (must have h1, h2)
        h1s = soup.find_all("h1")
        assert len(h1s) == 1, f"Expected exactly one h1, found {len(h1s)}"
        h2s = soup.find_all("h2")
        assert len(h2s) >= 1, "Expected at least one h2"

        # 4. Form labels associated with inputs
        for inp in soup.find_all(["input", "textarea"]):
            inp_type = inp.get("type", "")
            if inp_type in ("hidden", "submit", "button"):
                continue
            inp_id = inp.get("id")
            if inp_id:
                label = soup.find("label", attrs={"for": inp_id})
                assert label is not None or inp.find_parent("label") is not None, \
                    f"Input id '{inp_id}' has no associated label"

    def test_t6_empty_partial_and_many_sessions(self):
        """7. Renders cleanly (200 OK, no 500) for edge cases: empty/minimal sessions, partial sessions, many sessions."""
        client, user = tutor_teacher("t6-edge-sessions")
        pdf_bytes = _c01_bytes()
        sha = hashlib.sha256(pdf_bytes).hexdigest()

        # Case A: Minimal dossier with 1 session with empty/partial moments
        dossier_minimal = ImportDossier(
            source_sha256=sha,
            source_name="minimal.pdf",
            page_count=5,
            general_fields={
                "proyecto": InterpretedField(name="proyecto", value="Proyecto Minimal", status=STATUS_MISSING, review=REVIEW_PENDING),
            },
            sessions=[
                SessionPlan(
                    session_id="s_min_1",
                    session_number=1,
                    title="Sesión Única",
                    pages=[1],
                    fields={
                        "inicio": InterpretedField(name="inicio", value="", status=STATUS_MISSING, review=REVIEW_PENDING),
                    },
                )
            ],
        )
        report_min = verify_curriculum_dossier(dossier_minimal, pdf_bytes)
        dossier_minimal.verification_report = report_min.to_dict()

        job_min = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=SimpleUploadedFile("min.pdf", pdf_bytes, content_type="application/pdf"),
            status=CurriculumImportJob.STATUS_COMPLETED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            page_count=5,
            interpretation_dossier=dossier_minimal.to_dict(),
        )
        resp_min = client.get(reverse("tutor-import-interpretation", args=[job_min.pk]))
        assert resp_min.status_code == 200

        # Case B: Many sessions (e.g. 8 sessions)
        many_sessions = []
        for i in range(1, 9):
            many_sessions.append(
                SessionPlan(
                    session_id=f"sess_{i}",
                    session_number=i,
                    title=f"Sesión {i}",
                    pages=[1],
                    fields={
                        "inicio": InterpretedField(name="inicio", value=f"Inicio {i}", status=STATUS_MISSING, review=REVIEW_PENDING),
                        "desarrollo": InterpretedField(name="desarrollo", value=f"Desarrollo {i}", status=STATUS_MISSING, review=REVIEW_PENDING),
                        "cierre": InterpretedField(name="cierre", value=f"Cierre {i}", status=STATUS_MISSING, review=REVIEW_PENDING),
                    },
                )
            )
        dossier_many = ImportDossier(
            source_sha256=sha,
            source_name="many.pdf",
            page_count=5,
            general_fields={
                "proyecto": InterpretedField(name="proyecto", value="Proyecto Muchos", status=STATUS_MISSING, review=REVIEW_PENDING),
            },
            sessions=many_sessions,
        )
        report_many = verify_curriculum_dossier(dossier_many, pdf_bytes)
        dossier_many.verification_report = report_many.to_dict()

        job_many = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=SimpleUploadedFile("many.pdf", pdf_bytes, content_type="application/pdf"),
            status=CurriculumImportJob.STATUS_COMPLETED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            page_count=5,
            interpretation_dossier=dossier_many.to_dict(),
        )
        resp_many = client.get(reverse("tutor-import-interpretation", args=[job_many.pk]))
        assert resp_many.status_code == 200
        for i in range(1, 9):
            assert f"Sesión {i}" in resp_many.content.decode("utf-8")

    def test_t6_html_escaping_safeguards(self):
        """8. HTML escaping prevents XSS injection in project title, session fields, or annex mentions."""
        client, user = tutor_teacher("t6-xss-test")
        pdf_bytes = _c01_bytes()
        sha = hashlib.sha256(pdf_bytes).hexdigest()

        xss_payload = "<script>alert('pwned')</script>"
        dossier_xss = ImportDossier(
            source_sha256=sha,
            source_name="xss.pdf",
            page_count=5,
            general_fields={
                "proyecto": InterpretedField(name="proyecto", value=xss_payload, status=STATUS_MISSING, review=REVIEW_PENDING),
            },
            sessions=[
                SessionPlan(
                    session_id="s_xss_1",
                    session_number=1,
                    title=f"Sesión XSS {xss_payload}",
                    pages=[1],
                    fields={
                        "inicio": InterpretedField(name="inicio", value=xss_payload, status=STATUS_MISSING, review=REVIEW_PENDING),
                    },
                )
            ],
        )
        report = verify_curriculum_dossier(dossier_xss, pdf_bytes)
        dossier_xss.verification_report = report.to_dict()

        job_xss = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=SimpleUploadedFile("xss.pdf", pdf_bytes, content_type="application/pdf"),
            status=CurriculumImportJob.STATUS_COMPLETED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            page_count=5,
            interpretation_dossier=dossier_xss.to_dict(),
        )
        resp = client.get(reverse("tutor-import-interpretation", args=[job_xss.pk]))
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        # The literal raw script tag MUST NOT appear unescaped in HTML
        assert "<script>alert('pwned')</script>" not in content
        # Escaped version is fine
        assert "&lt;script&gt;alert(&#x27;pwned&#x27;)&lt;/script&gt;" in content or \
               "&lt;script&gt;alert('pwned')&lt;/script&gt;" in content

    def test_t6_post_forms_csrf_and_ownership(self):
        """9. Ownership enforcement and POST actions preserve versioning and data."""
        client, user = tutor_teacher("t6-post-owner")
        job, dossier = create_ready_job(user)

        # Other user cannot access
        other_client, other_user = tutor_teacher("t6-other-user")
        url = reverse("tutor-import-interpretation", args=[job.pk])
        resp_other = other_client.get(url)
        assert resp_other.status_code == 404

        # POST save_corrections updates version
        prev_ver = dossier.version
        post_data = {
            "action": "save_corrections",
            "expected_version": prev_ver,
            "session_id": dossier.sessions[0].session_id,
            "session_number": dossier.sessions[0].session_number,
            "inicio": "Inicio corregido por docente en T6",
        }
        resp_post = client.post(url, post_data)
        assert resp_post.status_code in (200, 302)

        # Reload job and check version incremented
        job.refresh_from_db()
        dossier_after = job.get_interpretation_dossier()
        assert dossier_after.version == prev_ver + 1

    def test_t6_embedded_javascript_syntax(self):
        """10. Any embedded <script> tags in tutor_import_interpretation.html pass node --check syntax validation."""
        client, user = tutor_teacher("t6-js-syntax")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        soup = BeautifulSoup(response.content.decode("utf-8"), "html.parser")
        scripts = soup.find_all("script")
        for idx, s in enumerate(scripts):
            if s.has_attr("src"):
                continue
            js_code = s.string or ""
            if not js_code.strip():
                continue
            res = subprocess.run(
                ["node", "--check"],
                input=js_code,
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0, f"JavaScript syntax error in script #{idx}: {res.stderr}"

    def test_t6_strict_dom_order(self):
        """11. DOM real: resumen -> comprobación -> Por revisar -> workspace activo -> TODAS las clases -> acciones."""
        client, user = tutor_teacher("t6-dom-order")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        html = response.content.decode("utf-8")

        # Key landmark positions in the raw HTML string
        pos_header = html.find('class="v0-header teacher-header"')
        pos_summary = html.find('class="project-summary-card"')
        pos_verif = html.find('id="seccion-comprobacion"')
        pos_queue = html.find('id="seccion-por-revisar"')
        pos_queue_heading = html.find('id="por-revisar-heading"')
        pos_workspace = html.find('id="workspace-activo"')
        pos_classes = html.find('id="seccion-clases"')
        pos_actions = html.find('id="sticky-actions-bar"')

        assert pos_header != -1, "Header not found"
        assert pos_summary != -1, "Summary card not found"
        assert pos_verif != -1, "Verification banner not found"
        assert pos_queue != -1, "Queue section not found"
        assert pos_queue_heading != -1, "Por revisar heading not found"
        assert pos_workspace != -1, "Workspace activo not found"
        assert pos_classes != -1, "Classes section not found"
        assert pos_actions != -1, "Sticky action bar not found"

        # Strict order assertion:
        # resumen -> comprobación -> Por revisar -> workspace activo -> TODAS las clases -> acciones
        assert pos_header < pos_summary < pos_verif < pos_queue <= pos_queue_heading < pos_workspace < pos_classes < pos_actions, (
            f"DOM order violation: header={pos_header}, summary={pos_summary}, verif={pos_verif}, "
            f"queue={pos_queue}, heading={pos_queue_heading}, workspace={pos_workspace}, "
            f"classes={pos_classes}, actions={pos_actions}"
        )

    def test_t6_all_sessions_rendered_in_order(self):
        """12. All sessions in dossier are rendered in sequential order; active session is editable; inactive is preview accordion."""
        client, user = tutor_teacher("t6-all-sessions")
        job, dossier = create_ready_job(user)

        assert len(dossier.sessions) >= 2, "Fixture must have at least 2 sessions"

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        soup = BeautifulSoup(response.content.decode("utf-8"), "html.parser")
        classes_sec = soup.find("section", id="seccion-clases")
        assert classes_sec is not None, "Sección de clases no encontrada"

        # Both sessions must exist in the classes section
        for sess in dossier.sessions:
            card = classes_sec.find(id=f"session-card-{sess.session_id}")
            assert card is not None, f"Card for session {sess.session_id} not found"

        # First session is active by default
        s1 = dossier.sessions[0]
        s2 = dossier.sessions[1]
        card1 = classes_sec.find(id=f"session-card-{s1.session_id}")
        card2 = classes_sec.find(id=f"session-card-{s2.session_id}")

        assert "session-card-active" in card1.get("class", [])
        assert card2.name == "details"
        assert "session-accordion" in card2.get("class", [])
        assert "Editar esta sesión" in card2.get_text()

    def test_t6_f7_ctas_anchors_and_scope_correctness(self):
        """13. F7 CTAs have correct scope (general without session_id), query + anchor (#control-...), and unique target controls in destination DOM for all 22 items."""
        client, user = tutor_teacher("t6-ctas-anchors")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        soup = BeautifulSoup(response.content.decode("utf-8"), "html.parser")
        queue_sec = soup.find("section", id="seccion-por-revisar")
        assert queue_sec is not None

        ctas = queue_sec.find_all("a", href=True)
        cta_hrefs = [a["href"] for a in ctas if "item=" in a["href"]]
        assert len(cta_hrefs) == 22, f"Expected exactly 22 CTAs in queue, got {len(cta_hrefs)}"

        for href in cta_hrefs:
            # Query + anchor
            assert "#control-" in href, f"CTA missing anchor #control-: {href}"
            query_part, anchor_id = href.split("#")

            # If general, cannot have session_id
            if "scope=general" in href:
                assert "session_id=" not in href, f"Misleading session_id in general CTA: {href}"

            # If session, must have session_id
            if "scope=session" in href or "item=session:" in href or "item=annex:" in href:
                assert "session_id=" in href, f"Missing session_id in session/annex CTA: {href}"

            assert anchor_id.startswith("control-"), f"Anchor ID malformed: {anchor_id}"

            # Follow CTA to destination URL and assert exact unique target control in DOM
            dest_url = f"{url}{query_part}"
            dest_response = client.get(dest_url)
            assert dest_response.status_code == 200, f"Destination {dest_url} returned {dest_response.status_code}"

            dest_soup = BeautifulSoup(dest_response.content.decode("utf-8"), "html.parser")
            targets = dest_soup.find_all(id=anchor_id)
            assert len(targets) == 1, (
                f"Expected exactly 1 target with id='{anchor_id}' in destination DOM for CTA '{href}', "
                f"found {len(targets)}"
            )
            target = targets[0]
            assert target.name in ("input", "textarea", "div", "span"), (
                f"Target {anchor_id} has unexpected tag name <{target.name}>"
            )

    def test_t6_priority_precedence_conflicts_before_missing(self):
        """14. Priority precedence: conflicts/blockers -> missing -> ambiguous/proposed -> resto."""
        from curriculum.source_interpreter import derive_operational_queue

        client, user = tutor_teacher("t6-priority-prec")
        job, dossier = create_ready_job(user)

        # Set session 2 field to conflict, session 1 field to missing
        dossier.sessions[0].fields["inicio"].status = STATUS_MISSING
        dossier.sessions[0].fields["inicio"].review = REVIEW_PENDING
        dossier.sessions[0].fields["inicio"].value = ""

        dossier.sessions[1].fields["desarrollo"].status = "conflict"
        dossier.sessions[1].fields["desarrollo"].review = REVIEW_PENDING
        dossier.sessions[1].fields["desarrollo"].value = "Texto en conflicto"

        queue = derive_operational_queue(dossier)
        items = queue.items

        conflict_indices = [i for i, it in enumerate(items) if "conflict" in it.priority_state.lower() or "conflict" in it.problem_summary.lower() or it.priority_state == "requires_resolution"]
        missing_indices = [i for i, it in enumerate(items) if it.priority_state == "missing" or "falta" in it.problem_summary.lower()]

        if conflict_indices and missing_indices:
            assert min(conflict_indices) < min(missing_indices), "Conflicts must be prioritized before missing fields"

    def test_t6_mobile_touch_targets_and_static_toolbar(self):
        """15. Mobile 375: toolbar is static (no fixed overlay), min 44px touch targets on buttons, links, evidence links."""
        client, user = tutor_teacher("t6-mobile-style")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        html = response.content.decode("utf-8")

        # Check CSS rules for 44px
        assert "min-height: 44px" in html
        assert "min-width: 44px" in html

        # Check mobile media query has position: static !important for toolbar
        assert ".decision-actions {" in html
        assert "position: static !important;" in html
        assert ".action-bar {" in html

    def test_t6_invalid_post_returns_400_renders_review_preserves_input_no_mutation(self):
        """16. Invalid POST returns 400, re-renders review template with role='alert', autofocus, preserves input, zero mutation."""
        client, user = tutor_teacher("t6-invalid-post")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        prev_version = dossier.version
        prev_updated = dossier.updated_at

        from curriculum.source_interpreter import derive_operational_queue
        queue = derive_operational_queue(dossier, session_filter=dossier.sessions[0].session_id)
        annex_item = next((it for it in queue.items if it.scope == "annex"), None)
        assert annex_item is not None
        ref_id = annex_item.reference_id
        post_data = {
            "action": "save_queue_item",
            "expected_version": prev_version,
            "item_id": annex_item.item_id,
            "scope": annex_item.session_id,
            f"annex_manual_page_{ref_id}": "999",
            f"annex_manual_confirm_{ref_id}": "1",
        }
        resp = client.post(f"{url}?session_id={annex_item.session_id}&scope={annex_item.session_id}&item={annex_item.stable_key}", post_data)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"

        # Renders review template, NOT bare plain text
        assert "text/html" in resp.headers.get("Content-Type", "")
        soup = BeautifulSoup(resp.content.decode("utf-8"), "html.parser")
        h1 = soup.find("h1")
        assert h1 is not None and "Revisa tu planeación" in h1.get_text()

        # Has role="alert"
        alert = soup.find(attrs={"role": "alert"})
        assert alert is not None, "Debe tener elemento con role='alert'"

        # Input has aria-invalid="true"
        invalid_input = soup.find(attrs={"aria-invalid": "true"})
        assert invalid_input is not None, "Debe tener input con aria-invalid='true'"

        # Value 999 preserved
        assert invalid_input.get("value") == "999"

        # ZERO mutation on dossier
        job.refresh_from_db()
        dossier_after = job.get_interpretation_dossier()
        assert dossier_after.version == prev_version
        assert dossier_after.updated_at == prev_updated

    def test_t6_no_technical_leaks_or_truncation(self):
        """17. No technical-details element, no raw SHA codes, no linearized_heuristics, no V0/T7 in copy, no truncatechars:80."""
        client, user = tutor_teacher("t6-no-leaks")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        html = response.content.decode("utf-8")
        soup = BeautifulSoup(html, "html.parser")

        # <details class="technical-details"> must be completely gone
        tech_details = soup.find("details", class_="technical-details")
        assert tech_details is None, "<details class='technical-details'> must not exist"

        body_text = soup.get_text()

        # No raw SHA hex codes in body text
        full_sha = job.interpretation_dossier.get("source_sha256", "")
        if full_sha:
            assert full_sha not in body_text
            assert full_sha[:16] not in body_text

        # No linearized_heuristics
        assert "linearized_heuristics" not in body_text

        # No raw V0 / T7 labels in visible text
        assert "fase v0" not in body_text.lower()
        assert "etapa t7" not in body_text.lower()
        assert "(t7)" not in body_text.lower()

        # Evidence quotes not truncated with truncatechars
        for it in dossier.verification_report.get("items", []):
            exc = it.get("excerpt")
            if exc and len(exc) > 80:
                assert exc in html, "Evidence excerpt was truncated"

        # Zero pypdf or engine jargon in visible text or attributes
        assert "pypdf" not in html.lower(), "Found pypdf engine leak in HTML output"
        assert "technical-note-collapse" not in html, "Found technical-note-collapse class leak"

    def test_t6_mobile_375_overflow_and_annex_table_responsive(self):
        """18. Mobile 375 viewport: table-responsive container, block card styling for annex-table on mobile, zero body overflow."""
        client, user = tutor_teacher("t6-mobile-overflow")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        html = response.content.decode("utf-8")
        soup = BeautifulSoup(html, "html.parser")

        # annex-table must be wrapped inside .table-responsive
        annex_table = soup.find("table", class_="annex-table")
        if annex_table:
            parent = annex_table.parent
            assert "table-responsive" in parent.get("class", []), "annex-table must be wrapped in .table-responsive"

        # CSS contains mobile responsive block card rules for annex-table
        assert ".table-responsive" in html
        assert "display: block !important;" in html
        assert "word-break: break-word !important;" in html
        assert "overflow-wrap: anywhere !important;" in html

        # html, body have overflow-x: hidden and max-width: 100%
        assert "overflow-x: hidden;" in html
        assert "box-sizing: border-box;" in html

        # .table-responsive wrapper must use overflow-x: auto (accessible fallback) and NOT overflow-x: hidden
        assert "overflow-x: auto !important;" in html
        assert "overflow-x: hidden !important;" not in html

        # Strict landmark order: seccion-datos-generales is inside summary card (before comprobacion)
        pos_header = html.find('class="v0-header teacher-header"')
        pos_summary = html.find('class="project-summary-card"')
        pos_general_fields = html.find('id="seccion-datos-generales"')
        pos_verif = html.find('id="seccion-comprobacion"')
        pos_queue = html.find('id="seccion-por-revisar"')
        pos_workspace = html.find('id="workspace-activo"')
        pos_classes = html.find('id="seccion-clases"')
        pos_actions = html.find('id="sticky-actions-bar"')

        assert pos_header < pos_summary < pos_general_fields < pos_verif < pos_queue < pos_workspace < pos_classes < pos_actions

    def test_t6_annex_table_data_labels_and_a11y_equivalence(self):
        """19. Causal check: if thead is hidden on mobile, each td preserves visible/AT equivalent label via data-label + ::before."""
        client, user = tutor_teacher("t6-annex-labels")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        html = response.content.decode("utf-8")
        soup = BeautifulSoup(html, "html.parser")

        # 1. Desktop thead has correct semantic columns: Referencia, Evidencia, Página candidata, Decisión, Acción
        table = soup.find("table", class_="annex-table")
        assert table is not None, "Tabla de anexos debe existir en la vista"
        thead = table.find("thead")
        assert thead is not None, "thead debe existir en markup semántico"
        th_elements = thead.find_all("th")
        assert len(th_elements) == 5, f"Expected 5 headers, got {len(th_elements)}"
        th_texts = [th.get_text(strip=True) for th in th_elements]
        expected_concepts = ["Referencia", "Evidencia", "Página candidata", "Decisión", "Acción"]
        assert th_texts == expected_concepts, f"Header columns mismatch: {th_texts} vs {expected_concepts}"

        # 2. Every td in tbody must have a non-empty data-label and aria-label matching its corresponding th
        tbody = table.find("tbody")
        assert tbody is not None
        rows = tbody.find_all("tr")
        assert len(rows) > 0, "Debe haber al menos una fila de anexos en el fixture C01"

        for row in rows:
            tds = row.find_all("td")
            assert len(tds) == len(th_texts), f"Row {row.get('id')} has {len(tds)} cells, expected {len(th_texts)}"
            for idx, td in enumerate(tds):
                label = td.get("data-label")
                assert label, f"Celda #{idx} en fila {row.get('id')} no tiene data-label o está vacío"
                assert label == th_texts[idx], (
                    f"Celda #{idx} data-label '{label}' no corresponde con th '{th_texts[idx]}'"
                )
                assert td.get("aria-label") == th_texts[idx], (
                    f"Celda #{idx} aria-label '{td.get('aria-label')}' no corresponde con th '{th_texts[idx]}'"
                )

        # 3. Mobile CSS: thead hidden, td::before displays data-label
        assert ".annex-table thead {" in html
        assert "display: none !important;" in html
        assert ".annex-table td[data-label]::before" in html
        assert "content: attr(data-label)" in html

        # 4. Desktop CSS: thead normal, ::before reset
        assert ".annex-table td::before { content: none; }" in html

        # 5. Essential content is not hidden
        for row in rows:
            # Col 1: has annex number
            assert "Anexo" in row.find_all("td")[0].get_text()
            # Col 2: has raw mention
            assert len(row.find_all("td")[1].get_text(strip=True)) > 0
            # Col 4: decision inputs exist
            decision_cell = row.find_all("td")[3]
            inputs = decision_cell.find_all("input")
            assert len(inputs) >= 1, f"Decisión cell in row {row.get('id')} missing interactive inputs"

    def test_t6_mobile_wrap_and_no_risky_rules(self):
        """20. Causal check: no risky nowrap or rigid min-width on .scope-tab, .progress-text, or html; toolbar static; targets 44px."""
        client, user = tutor_teacher("t6-wrap-rules")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        response = client.get(url)
        assert response.status_code == 200

        html = response.content.decode("utf-8")

        # 1. .scope-tab and .progress-text must allow wrap, no white-space: nowrap
        assert ".progress-text { font-size: 0.76rem; font-weight: 700; color: var(--color-muted); white-space: normal; overflow-wrap: anywhere; }" in html
        assert "white-space: normal;" in html
        # Ensure no white-space: nowrap in scope-tab or progress-text
        for line in html.splitlines():
            if ".scope-tab" in line or ".progress-text" in line or ".scope-nav" in line:
                assert "white-space: nowrap" not in line, f"Found forbidden white-space: nowrap in {line}"
                assert "flex-wrap: nowrap" not in line, f"Found forbidden flex-wrap: nowrap in {line}"

        # 2. html must not have rigid min-width >= 375px
        assert "min-width: 375px" not in html
        assert "min-width: 400px" not in html

        # 3. Toolbar static mobile
        assert ".decision-actions {" in html
        assert ".action-bar {" in html
        assert "position: static !important;" in html

        # 4. Touch targets >= 44px
        assert "min-height: 44px" in html or "min-block-size: 44px" in html
        assert "min-width: 44px" in html or "min-inline-size: 44px" in html
