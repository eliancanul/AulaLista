"""Real Django identity, SQLite and local PDF interpreter through HTTP.

Run against an assembly containing the published S06/S08/S09 modules.
No provider calls or test replacements of service boundaries are used.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

__import__("fastapi")
__import__("api.auth")
__import__("api.persistence")
__import__("curriculum.interpretation_service")

from django.contrib.auth import get_user_model
from django.test import Client
from fastapi.testclient import TestClient

from api.main import create_app
from api.persistence import SQLiteRepository
from test_t15_curriculum_import import make_minimal_pdf

pytestmark = pytest.mark.django_db(transaction=True)
PDF_NAME = 'synthetic-reading.pdf'
PDF_BYTES = make_minimal_pdf(['Proyecto: La lectura\nPropósito: Reconocer vocales y la letra M.\nMateriales: Papel\nGrado: 3ro'])


@pytest.fixture
def service(settings, tmp_path):
    settings.SPRINT_PERSISTENCE_PATH = str(tmp_path / "drafts.sqlite3")
    store = SQLiteRepository(settings.SPRINT_PERSISTENCE_PATH)
    app = create_app()
    users = []
    clients = []
    for name in ("s07-owner", "s07-other"):
        user = get_user_model().objects.create_user(username=name, is_staff=True)
        django_client = Client(enforce_csrf_checks=True)
        django_client.force_login(user)
        django_client.get("/cms/login/")
        client = TestClient(app)
        client.cookies.update({key: value.value for key, value in django_client.cookies.items()})
        client.headers["X-CSRFToken"] = django_client.cookies[settings.CSRF_COOKIE_NAME].value
        users.append(user)
        clients.append(client)
    yield app, store, users, clients
    for client in clients:
        client.close()


def upload(client):
    response = client.post("/api/v1/interpretations", files={
        "file": (PDF_NAME, PDF_BYTES, "application/pdf"),
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_real_upload_reopen_edit_approve_and_history(service):
    _, store, users, clients = service
    client = clients[0]
    result = upload(client)
    identifier = result["document_id"]
    assert result["schema_version"] == 2
    assert result["draft"]["id"] == identifier
    assert result["draft"]["approval_status"] == "pending"
    assert result["source_segments"]
    assert next(f for f in result["fields"] if f["key"] == "nivel_educativo")["value"] is None
    assert store.get_source(users[0].pk, identifier)["content"] == PDF_BYTES
    assert store.get_source(users[0].pk, identifier)["filename"] == PDF_NAME
    assert store.get_interpretation(users[0].pk, identifier) == result
    assert client.get(f"/api/v1/interpretations/{identifier}").json() == result
    assert result["draft"]["steps"] == []
    rejected = client.post(f"/api/v1/drafts/{identifier}/approve", json={
        "expected_revision": 1, "confirm": True,
    })
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "insufficient_source"
    assert store.get_interpretation(users[0].pk, identifier) == result
    assert len(store.get_history(users[0].pk, identifier)) == 1
    title = "  Actividad revisada por la maestra\nÁrboles y comunidad  "
    steps = ["Identificar las vocales y la letra M en el fragmento revisado."]
    edited = client.patch(f"/api/v1/drafts/{identifier}", json={
        # The conservative role check may leave source purpose unknown. The
        # teacher supplies an objective explicitly before human approval.
        "expected_revision": 1, "changes": {"title": title, "steps": steps,
                                            "objective": "Reconocer vocales y la letra M."},
    })
    assert edited.status_code == 200
    assert edited.json()["title"] == title
    assert edited.json()["steps"] == steps
    assert edited.json()["revision"] == 2
    assert client.post(f"/api/v1/drafts/{identifier}/approve", json={
        "expected_revision": 2, "confirm": False,
    }).status_code == 422
    approved = client.post(f"/api/v1/drafts/{identifier}/approve", json={
        "expected_revision": 2, "confirm": True,
    })
    assert approved.status_code == 200, approved.text
    assert approved.json()["revision"] == 3
    assert approved.json()["approval_status"] == "approved"
    assert client.patch(f"/api/v1/drafts/{identifier}", json={
        "expected_revision": 2, "changes": {"title": "Texto anterior"},
    }).status_code == 409
    edited_again = client.patch(f"/api/v1/drafts/{identifier}", json={
        "expected_revision": 3, "changes": {"title": title + " nueva"},
    })
    assert edited_again.status_code == 200
    assert edited_again.json()["approval_status"] == "pending"
    assert len(store.get_history(users[0].pk, identifier)) == 4
    reopened = subprocess.run([
        sys.executable, "-c",
        "import json,sys; from api.persistence import SQLiteRepository; "
        "print(json.dumps(SQLiteRepository(sys.argv[1],initialize=False).get_interpretation(int(sys.argv[2]),sys.argv[3])))",
        str(store.path), str(users[0].pk), identifier,
    ], capture_output=True, text=True, check=True)
    persisted = json.loads(reopened.stdout)
    assert persisted["draft"]["title"] == title + " nueva"
    assert persisted["draft"]["revision"] == 4
    assert persisted["draft"]["steps"] == steps
    assert {k: v for k, v in persisted.items() if k != "draft"} == {
        k: v for k, v in result.items() if k != "draft"
    }


def test_real_owner_isolation_chat_and_completed_cancel(service):
    _, store, users, clients = service
    owner, other = clients
    result = upload(owner)
    identifier = result["document_id"]
    responses = [
        other.get(f"/api/v1/interpretations/{identifier}"),
        other.patch(f"/api/v1/drafts/{identifier}", json={"expected_revision": 1, "changes": {"title": "Ajeno"}}),
        other.post(f"/api/v1/drafts/{identifier}/approve", json={"expected_revision": 1, "confirm": True}),
        other.post("/api/v1/chat", json={"interpretation_id": identifier, "message": "materiales"}),
        other.post(f"/api/v1/interpretations/{identifier}/cancel"),
    ]
    missing = other.get("/api/v1/interpretations/missing")
    assert [r.status_code for r in responses] == [404] * 5
    assert all(r.json() == missing.json() for r in responses)
    chat = owner.post("/api/v1/chat", json={"interpretation_id": identifier, "message": "materiales"})
    assert chat.status_code == 200
    assert chat.json()["applies_changes"] is False
    assert chat.json()["proposals"] == []
    assert set(chat.json()["source_ids"]) <= {s["id"] for s in result["source_segments"]}
    cancelled = owner.post(f"/api/v1/interpretations/{identifier}/cancel")
    assert cancelled.status_code == 409
    assert cancelled.json()["error"]["code"] == "interpretation_finished"
    assert store.get_interpretation(users[0].pk, identifier) == result
    assert len(store.get_history(users[0].pk, identifier)) == 1


def test_real_session_csrf_and_revocation(service):
    app, _, users, clients = service
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/v1/interpretations/missing").status_code == 401
        assert anonymous.post("/api/v1/interpretations", content=b"private").status_code == 401
    client = clients[0]
    token = client.headers.pop("X-CSRFToken")
    responses = [
        client.post("/api/v1/interpretations", content=b"private"),
        client.patch("/api/v1/drafts/missing", json={"expected_revision": 1, "changes": {"title": "Texto"}}),
        client.post("/api/v1/drafts/missing/approve", json={"expected_revision": 1, "confirm": True}),
        client.post("/api/v1/chat", json={"interpretation_id": "missing", "message": "materiales"}),
        client.post("/api/v1/interpretations/missing/cancel"),
    ]
    assert [r.status_code for r in responses] == [403] * 5
    assert all(r.json()["error"]["code"] == "csrf_failed" for r in responses)
    client.headers["X-CSRFToken"] = token
    client.headers["Origin"] = "https://untrusted.example"
    assert client.post("/api/v1/interpretations", content=b"private").status_code == 403
    client.headers.pop("Origin")
    users[0].is_staff = False
    users[0].save(update_fields=["is_staff"])
    assert client.get("/api/v1/interpretations/missing").status_code == 403
    users[0].is_active = False
    users[0].save(update_fields=["is_active"])
    assert client.get("/api/v1/interpretations/missing").status_code == 401


def test_real_http_edit_and_approval_race(service):
    app, store, users, clients = service
    result = upload(clients[0])
    identifier = result["document_id"]
    prepared = clients[0].patch(f"/api/v1/drafts/{identifier}", json={
        "expected_revision": 1,
        "changes": {"steps": ["Identificar las vocales y la letra M en el fragmento revisado."],
                    "objective": "Reconocer vocales y la letra M."},
    })
    assert prepared.status_code == 200
    assert prepared.json()["revision"] == 2
    assert prepared.json()["approval_status"] == "pending"

    def write(action):
        with TestClient(app, cookies=dict(clients[0].cookies), headers={"X-CSRFToken": clients[0].headers["X-CSRFToken"]}) as client:
            if action == "edit":
                return client.patch(f"/api/v1/drafts/{identifier}", json={
                    "expected_revision": 2, "changes": {"title": "Cambio concurrente"},
                })
            return client.post(f"/api/v1/drafts/{identifier}/approve", json={
                "expected_revision": 2, "confirm": True,
            })

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(write, ("edit", "approve")))
    assert sorted(r.status_code for r in responses) == [200, 409]
    history = store.get_history(users[0].pk, identifier)
    assert len(history) == 3
    draft = store.get_draft(users[0].pk, identifier)
    assert draft["revision"] == 3
    if draft["approval_status"] == "approved":
        assert draft["title"] == result["draft"]["title"]
    else:
        assert draft["title"] == "Cambio concurrente"
