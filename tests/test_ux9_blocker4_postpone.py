"""tests/test_ux9_blocker4_postpone.py
B4 (#116 B): Aplazamiento persistente en la cola operativa.
Acción 'postpone_queue_item' persistida en el dossier:
- Estado del ítem: pendiente / aplazada / resuelta
- Historial mínimo: quién, cuándo
- Prueba causal HTTP: aplazar → recargar → sigue aplazada (y distinta de pendiente y de resuelta).
"""

import hashlib
import io
import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from pypdf import PdfWriter

from curriculum.models import CurriculumImportJob
from curriculum.source_interpreter import (
    CurriculumSourceInterpreter,
    ImportDossier,
    InterpretedField,
    SessionPlan,
    SourceReference,
    ORIGIN_EXTRACTED,
    STATUS_SUPPORTED,
    REVIEW_PENDING,
    derive_operational_queue,
)

pytestmark = pytest.mark.django_db


def _make_pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _setup_job():
    User = get_user_model()
    teacher = User.objects.create_user(username="b4-teacher", is_staff=True)
    pdf_bytes = _make_pdf_bytes()
    sha = hashlib.sha256(pdf_bytes).hexdigest()

    job = CurriculumImportJob.objects.create(
        status=CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
        created_by=teacher,
        source_text="Planeación de prueba",
        page_count=1,
    )
    job.pdf.save("test-b4.pdf", ContentFile(pdf_bytes), save=True)

    # Initial dossier
    general_fields = {
        "proyecto": InterpretedField(
            name="proyecto",
            value="Proyecto Sintético",
            origin=ORIGIN_EXTRACTED,
            status=STATUS_SUPPORTED,
            review=REVIEW_PENDING,
            evidence=[SourceReference(document_sha256=sha, page_number=1, excerpt="Proyecto Sintético")],
        ),
        "proposito": InterpretedField(
            name="proposito",
            value="Propósito inicial",
            origin=ORIGIN_EXTRACTED,
            status=STATUS_SUPPORTED,
            review=REVIEW_PENDING,
            evidence=[SourceReference(document_sha256=sha, page_number=1, excerpt="Propósito inicial")],
        ),
    }
    sessions = [
        SessionPlan(
            session_id="s1",
            session_number=1,
            title="Sesión 1",
            pages=[1],
            fields={
                "inicio": InterpretedField(
                    name="inicio",
                    value="Inicio clase 1",
                    origin=ORIGIN_EXTRACTED,
                    status=STATUS_SUPPORTED,
                    review=REVIEW_PENDING,
                    evidence=[SourceReference(document_sha256=sha, page_number=1, excerpt="Inicio clase 1")],
                ),
                "desarrollo": InterpretedField(
                    name="desarrollo",
                    value="Desarrollo clase 1",
                    origin=ORIGIN_EXTRACTED,
                    status=STATUS_SUPPORTED,
                    review=REVIEW_PENDING,
                    evidence=[SourceReference(document_sha256=sha, page_number=1, excerpt="Desarrollo clase 1")],
                ),
                "cierre": InterpretedField(
                    name="cierre",
                    value="Cierre clase 1",
                    origin=ORIGIN_EXTRACTED,
                    status=STATUS_SUPPORTED,
                    review=REVIEW_PENDING,
                    evidence=[SourceReference(document_sha256=sha, page_number=1, excerpt="Cierre clase 1")],
                ),
            },
        )
    ]
    dossier = ImportDossier(
        source_sha256=sha,
        source_name="test-b4.pdf",
        page_count=1,
        version=1,
        general_fields=general_fields,
        sessions=sessions,
    )
    job.save_interpretation_dossier(dossier)
    return teacher, job, dossier


@pytest.mark.usefixtures("legacy_import_routes")
def test_postpone_queue_item_causal_flow():
    """Causal HTTP test:
    1. Check initial state is pending_review (not postponed, not resolved).
    2. POST action='postpone_queue_item' with item_id.
    3. Reload via GET → verifies the item persists as postponed across reload,
       and is distinguishable from pending and from resolved.
    4. Verifies minimal history tracking (who, when).
    """
    teacher, job, dossier = _setup_job()
    client = Client()
    client.force_login(teacher)

    url = reverse("tutor-import-interpretation", args=[job.pk])

    # Initial GET
    response = client.get(url)
    assert response.status_code == 200
    queue = response.context["queue"]
    initial_pending = [it for it in queue.items if it.field_name == "proposito"]
    assert len(initial_pending) == 1
    target_item = initial_pending[0]
    assert target_item.priority_state == "pending_review"

    # POST action='postpone_queue_item'
    post_data = {
        "action": "postpone_queue_item",
        "expected_version": dossier.version,
        "item_id": target_item.item_id,
        "scope": "general",
    }
    post_resp = client.post(url, post_data)
    assert post_resp.status_code == 200

    # Reload via fresh GET
    reload_resp = client.get(url)
    assert reload_resp.status_code == 200
    reloaded_queue = reload_resp.context["queue"]
    reloaded_items = [it for it in reloaded_queue.items if it.field_name == "proposito"]
    assert len(reloaded_items) == 1
    reloaded_item = reloaded_items[0]

    # Must be postponed, NOT pending_review and NOT reviewed
    assert reloaded_item.priority_state == "postponed", (
        f"Expected priority_state 'postponed', got '{reloaded_item.priority_state}'"
    )
    assert reloaded_item.priority_state != "pending_review"
    assert reloaded_item.priority_state != "reviewed"

    reloaded_html = reload_resp.content.decode("utf-8")
    assert "Revisar después (1)" in reloaded_html
    assert "Aplazada" in reloaded_html
    assert "Volver a revisar" in reloaded_html

    # Verify history in persisted dossier
    job.refresh_from_db()
    persisted_dossier = job.get_interpretation_dossier()
    assert persisted_dossier.version > 1
    # Check history has who and when
    recent_history = persisted_dossier.history[-1]
    assert recent_history.get("actor") == "b4-teacher"
    assert bool(recent_history.get("timestamp"))
    assert any(d.get("change_type") == "postponed" for d in recent_history.get("deltas", []))


@pytest.mark.usefixtures("legacy_import_routes")
def test_postpone_queue_item_json_api():
    """Fetch/JSON API test: verify JsonResponse is returned when X-Requested-With header is present."""
    teacher, job, dossier = _setup_job()
    client = Client()
    client.force_login(teacher)

    url = reverse("tutor-import-interpretation", args=[job.pk])

    # Initial GET to find target
    response = client.get(url)
    queue = response.context["queue"]
    target_item = [it for it in queue.items if it.field_name == "proyecto"][0]

    post_data = {
        "action": "postpone_queue_item",
        "expected_version": dossier.version,
        "item_id": target_item.item_id,
        "scope": "general",
    }
    json_resp = client.post(url, post_data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert json_resp.status_code == 200
    assert json_resp["Content-Type"].startswith("application/json")
    data = json_resp.json()
    assert data.get("status") == "ok"
    assert data.get("priority_state") == "postponed"
    assert data.get("version") == dossier.version + 1
