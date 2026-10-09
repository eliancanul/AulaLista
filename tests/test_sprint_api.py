"""HTTP contract tests. Fixture responses are not provider experiments."""

import pytest

__import__("fastapi")
from pydantic import ValidationError

from api.schemas import ApprovalRequest, DraftPatch, ChatRequest


@pytest.mark.parametrize("payload", [
    {"expected_revision": True, "changes": {"title": "Texto"}},
    {"expected_revision": "1", "changes": {"title": "Texto"}},
    {"expected_revision": 0, "changes": {"title": "Texto"}},
    {"expected_revision": 1, "changes": {}},
    {"expected_revision": 1, "changes": {"title": None}},
    {"expected_revision": 1, "changes": {"approval_status": "approved"}},
    {"expected_revision": 1, "changes": {"source_ids": ["inventada"]}},
    {"expected_revision": 1, "changes": {"title": "Texto"}, "owner_id": 2},
])
def test_patch_rejects_unsafe_or_ambiguous_updates(payload):
    with pytest.raises(ValidationError):
        DraftPatch.model_validate(payload)


def test_patch_keeps_teacher_edits_and_empty_material_list():
    patch = DraftPatch.model_validate({
        "expected_revision": 3,
        "changes": {"title": "Actividad revisada por la docente", "materials": []},
    })
    assert patch.changes.model_dump(exclude_unset=True) == {
        "title": "Actividad revisada por la docente", "materials": [],
    }


@pytest.mark.parametrize("confirmation", [False, 1, "true", None])
def test_approval_requires_explicit_boolean_confirmation(confirmation):
    with pytest.raises(ValidationError):
        ApprovalRequest(expected_revision=1, confirm=confirmation)


def test_chat_rejects_blank_message():
    with pytest.raises(ValidationError):
        ChatRequest(interpretation_id="document", message="   ")


@pytest.fixture
def http_contract():
    from copy import deepcopy
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from api.main import create_app
    from api.routes import APIError, current_teacher

    class FixtureRepository:
        """An isolated contract double, never a production storage fallback."""
        def __init__(self):
            self.document = {
                "schema_version": 1, "document_id": "fixture-document",
                "source_segments": [{"id": "s1", "text": "Materiales: hojas y lápices.", "page": 1}],
                "fields": [], "missing_questions": [],
                "draft": {"id": "fixture-document", "title": "Por revisar", "objective": "Leer",
                          "materials": ["hojas"], "steps": ["Leer"], "assessment": "Observar",
                          "source_ids": ["s1"], "revision": 1, "approval_status": "pending", "status": "needs_review"},
            }
            self.writes = 0

        def get_interpretation(self, owner, identifier):
            if owner != 7 or identifier != "fixture-document":
                raise APIError(404, "not_found", "No se encontró el recurso solicitado.")
            return deepcopy(self.document)

        def update_draft(self, owner, identifier, revision, changes):
            self.get_interpretation(owner, identifier)
            if revision != self.document["draft"]["revision"]:
                raise APIError(409, "revision_conflict", "El borrador cambió. Vuelve a cargarlo antes de guardar.")
            self.document["draft"].update(changes)
            self.document["draft"]["revision"] += 1
            self.document["draft"]["approval_status"] = "pending"
            self.writes += 1
            return deepcopy(self.document["draft"])

        def approve_draft(self, owner, identifier, revision, *, confirm):
            assert confirm is True
            self.get_interpretation(owner, identifier)
            if revision != self.document["draft"]["revision"]:
                raise APIError(409, "revision_conflict", "El borrador cambió. Vuelve a cargarlo antes de guardar.")
            self.document["draft"]["approval_status"] = "approved"
            self.document["draft"]["revision"] += 1
            self.writes += 1
            return deepcopy(self.document["draft"])

    app = create_app()
    store = FixtureRepository()
    app.state.repository = store
    app.dependency_overrides[current_teacher] = lambda: SimpleNamespace(pk=7)
    with TestClient(app) as client:
        yield client, app, store


def test_http_edit_reopen_stale_write_and_explicit_approval(http_contract):
    client, _, store = http_contract
    response = client.patch("/api/v1/drafts/fixture-document", json={
        "expected_revision": 1, "changes": {"title": "Mi actividad revisada"},
    })
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert client.get("/api/v1/interpretations/fixture-document").json()["draft"]["title"] == "Mi actividad revisada"
    stale = client.patch("/api/v1/drafts/fixture-document", json={
        "expected_revision": 1, "changes": {"title": "Cambio viejo"},
    })
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"
    assert client.post("/api/v1/drafts/fixture-document/approve", json={"expected_revision": 2, "confirm": False}).status_code == 422
    assert store.writes == 1
    approved = client.post("/api/v1/drafts/fixture-document/approve", json={"expected_revision": 2, "confirm": True})
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "approved"
    assert approved.json()["revision"] == 3
    stale_after_approval = client.patch("/api/v1/drafts/fixture-document", json={"expected_revision": 2, "changes": {"title": "Edición anterior a la aprobación"}})
    assert stale_after_approval.status_code == 409
    assert store.writes == 2
    edited = client.patch("/api/v1/drafts/fixture-document", json={"expected_revision": 3, "changes": {"title": "Nueva edición"}})
    assert edited.status_code == 200
    assert edited.json()["approval_status"] == "pending"
    assert edited.json()["revision"] == 4


def test_chat_cites_source_without_mutating_draft(http_contract):
    client, _, store = http_contract
    response = client.post("/api/v1/chat", json={"interpretation_id": "fixture-document", "message": "¿Qué materiales necesito?"})
    assert response.status_code == 200
    assert response.json()["source_ids"] == ["s1"]
    assert "hojas y lápices" in response.json()["message"]
    assert response.json()["mode"] == "source_lookup"
    assert response.json()["applies_changes"] is False
    assert response.json()["proposals"] == []
    assert store.writes == 0


def test_unknown_chat_question_does_not_invent_an_answer(http_contract):
    client, _, _ = http_contract
    response = client.post("/api/v1/chat", json={"interpretation_id": "fixture-document", "message": "¿Qué grado escolar corresponde?"})
    assert response.json()["source_ids"] == []
    assert response.json()["message"].startswith("No encontré un fragmento")


def test_errors_do_not_echo_input_and_responses_are_private(http_contract):
    client, _, _ = http_contract
    response = client.patch("/api/v1/drafts/fixture-document", json={"expected_revision": "private-secret", "changes": {"title": "private-source"}})
    assert response.status_code == 422
    assert "private-secret" not in response.text
    assert "private-source" not in response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["error"]["fields"] == ["body.expected_revision"]


def test_fixture_owner_error_propagates_in_read_edit_approve_chat_and_cancel(http_contract):
    from types import SimpleNamespace
    from api.routes import current_teacher
    client, app, store = http_contract
    app.dependency_overrides[current_teacher] = lambda: SimpleNamespace(pk=8)
    responses = [
        client.get("/api/v1/interpretations/fixture-document"),
        client.patch("/api/v1/drafts/fixture-document", json={"expected_revision": 1, "changes": {"title": "foreign"}}),
        client.post("/api/v1/drafts/fixture-document/approve", json={"expected_revision": 1, "confirm": True}),
        client.post("/api/v1/chat", json={"interpretation_id": "fixture-document", "message": "materiales"}),
        client.post("/api/v1/interpretations/fixture-document/cancel"),
    ]
    assert [response.status_code for response in responses] == [404] * 5
    assert store.writes == 0


def test_cancel_finished_interpretation_preserves_saved_work(http_contract):
    client, _, store = http_contract
    response = client.post("/api/v1/interpretations/fixture-document/cancel")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "interpretation_finished"
    assert store.writes == 0


def test_missing_auth_integration_fails_closed():
    from fastapi.testclient import TestClient
    from api.main import create_app
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/interpretations/private-document")
    assert response.status_code in (401, 503)
    assert "private-document" not in response.text


def test_upload_rejects_invalid_pdf_and_multiple_files(http_contract):
    client, _, store = http_contract
    invalid = client.post("/api/v1/interpretations", files={"file": ("source.pdf", b"not a PDF", "application/pdf")})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_pdf"
    duplicate = client.post("/api/v1/interpretations", files=[
        ("file", ("one.pdf", b"one")), ("file", ("two.pdf", b"two")),
    ])
    assert duplicate.status_code == 400
    assert store.writes == 0


def test_upload_rejects_wrong_format_and_bounds_chunked_body(http_contract, settings):
    client, _, store = http_contract
    wrong_type = client.post("/api/v1/interpretations", json={"file": "private-document"})
    assert wrong_type.status_code == 415
    settings.CURRICULUM_MAX_UPLOAD_SIZE_BYTES = 10
    oversized = client.post("/api/v1/interpretations", files={"file": ("source.pdf", b"x" * 11)})
    assert oversized.status_code == 413
    streamed = client.post(
        "/api/v1/interpretations",
        content=iter([b"x" * 65536, b"x" * 11]),
        headers={"Content-Type": "multipart/form-data; boundary=example"},
    )
    assert streamed.status_code == 413
    assert store.writes == 0


def test_upload_calls_interpreter_and_persists_only_completed_result(http_contract, monkeypatch):
    from copy import deepcopy
    from helpers import MINIMAL_VALID_PDF_BYTES
    from api import routes
    client, _, store = http_contract
    calls = []

    def interpret_fixture(source, *, document_id):
        assert source.read() == MINIMAL_VALID_PDF_BYTES
        result = deepcopy(store.document)
        result["document_id"] = document_id
        result["draft"]["id"] = document_id
        calls.append(document_id)
        return result

    def create_fixture(owner, result, *, source_bytes, filename):
        assert source_bytes == MINIMAL_VALID_PDF_BYTES
        assert filename == "source.pdf"
        assert owner == 7
        assert result["document_id"] == calls[0]
        store.writes += 1
        return result

    monkeypatch.setattr(routes, "interpret", interpret_fixture)
    monkeypatch.setattr(store, "create_interpretation", create_fixture, raising=False)
    response = client.post("/api/v1/interpretations", files={"file": ("source.pdf", MINIMAL_VALID_PDF_BYTES, "application/pdf")})
    assert response.status_code == 201
    assert response.json()["document_id"] == calls[0]
    assert response.json()["draft"]["approval_status"] == "pending"
    assert store.writes == 1


def test_openapi_publishes_upload_patch_approval_and_chat_contract(http_contract):
    client, _, _ = http_contract
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert paths["/api/v1/interpretations"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]["required"] == ["file"]
    assert paths["/api/v1/drafts/{draft_id}"]["patch"]["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/DraftPatch")
    assert paths["/api/v1/chat"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/ChatResponse")


def test_unexpected_service_errors_do_not_expose_details(http_contract, monkeypatch):
    from fastapi.testclient import TestClient
    _, app, store = http_contract

    def fail(*args):
        raise RuntimeError("secret-path-and-provider-token")

    monkeypatch.setattr(store, "get_interpretation", fail)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/interpretations/fixture-document")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret-path" not in response.text


@pytest.mark.parametrize("payload", [
    {}, {"expected_revision": 1},
    *[{"expected_revision": 1, "confirm": value} for value in [False, 1, "true", None]],
    *[{"expected_revision": value, "confirm": True} for value in [True, 0, -1, "1", 1.5, None]],
])
def test_http_invalid_approval_never_reaches_repository(http_contract, payload):
    client, _, store = http_contract
    response = client.post("/api/v1/drafts/fixture-document/approve", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert store.writes == 0
    assert store.document["draft"]["approval_status"] == "pending"


def test_stale_approval_preserves_fixture_draft(http_contract):
    client, _, store = http_contract
    response = client.post("/api/v1/drafts/fixture-document/approve", json={"expected_revision": 2, "confirm": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "revision_conflict"
    assert store.writes == 0


@pytest.mark.parametrize("content_type, body", [
    ("multipart/form-data", b"private-document"),
    ("multipart/form-data; boundary=example", b"private-document"),
])
def test_malformed_upload_has_safe_client_error(http_contract, content_type, body):
    from fastapi.testclient import TestClient
    _, app, store = http_contract
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/interpretations", content=body, headers={"Content-Type": content_type})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "http_400"
    assert "private-document" not in response.text
    assert store.writes == 0


@pytest.mark.parametrize("module_name, class_name, status, code, message, retryable", [
    ("api.auth", "AuthenticationError", 401, "authentication_required", "Inicia sesión para continuar.", False),
    ("api.auth", "AuthenticationError", 403, "csrf_failed", "Recarga la página e inténtalo de nuevo.", False),
    ("api.persistence", "PersistenceError", 409, "revision_conflict", "El borrador cambió.", False),
    ("api.persistence", "PersistenceError", 503, "storage_unavailable", "No se pudo leer el borrador.", True),
])
def test_published_adapter_errors_keep_safe_contract(monkeypatch, module_name, class_name, status, code, message, retryable):
    import sys
    from types import ModuleType
    from fastapi.testclient import TestClient
    from api.main import create_app
    from api.routes import current_teacher

    class FixtureAdapterError(Exception):
        def __init__(self):
            self.status, self.code, self.message, self.retryable = status, code, message, retryable

    module = ModuleType(module_name)
    setattr(module, class_name, FixtureAdapterError)
    monkeypatch.setitem(sys.modules, module_name, module)
    app = create_app()

    def reject_fixture_request():
        raise FixtureAdapterError()

    app.dependency_overrides[current_teacher] = reject_fixture_request
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/interpretations/fixture-document")
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message, "retryable": retryable, "fields": []}}
    assert response.headers["cache-control"] == "private, no-store"


def test_http_v2_preserves_source_offsets_and_extraction_diagnostics(http_contract):
    from copy import deepcopy
    client, _, store = http_contract
    store.document["schema_version"] = 2
    store.document["source_segments"][0].update({
        "kind": "table_row_candidate", "text_start": 12, "text_end": 42,
    })
    store.document["diagnostics"] = {"source_extraction": {
        "status": "partial", "requires_review": True,
        "pages": [{"page": 1, "status": "extracted", "text": "Texto sintético"},
                  {"page": 2, "status": "empty", "text": ""}],
    }}
    expected = deepcopy(store.document)
    response = client.get("/api/v1/interpretations/fixture-document")
    assert response.status_code == 200
    assert response.json() == expected
    assert store.writes == 0


def test_openapi_distinguishes_v1_and_v2_sources(http_contract):
    client, _, _ = http_contract
    schema = client.get("/openapi.json").json()
    response = schema["paths"]["/api/v1/interpretations/{interpretation_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert response["discriminator"]["propertyName"] == "schema_version"
    assert set(response["discriminator"]["mapping"]) == {"1", "2"}
    assert {"kind", "text_start", "text_end"} <= set(schema["components"]["schemas"]["LayoutSourceSegment"]["required"])


def test_v2_response_rejects_missing_or_reversed_offsets(http_contract):
    from copy import deepcopy
    from pydantic import TypeAdapter
    from api.schemas import InterpretationResponse
    _, _, store = http_contract
    payload = deepcopy(store.document)
    payload["schema_version"] = 2
    adapter = TypeAdapter(InterpretationResponse)
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)
    payload["source_segments"][0].update({"kind": "text", "text_start": 20, "text_end": 10})
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)


@pytest.mark.parametrize("disconnect_call", [1, 2])
def test_disconnect_before_persistence_keeps_store_untouched(http_contract, monkeypatch, disconnect_call):
    from copy import deepcopy
    from starlette.requests import Request
    from helpers import MINIMAL_VALID_PDF_BYTES
    from api import routes
    client, _, store = http_contract
    calls = []

    async def disconnected(self):
        calls.append("check")
        return len(calls) == disconnect_call

    def local_fixture(source, *, document_id):
        result = deepcopy(store.document)
        result["document_id"] = document_id
        return result

    def unexpected_write(*args, **kwargs):
        pytest.fail("A detected disconnect must not persist a draft")

    monkeypatch.setattr(Request, "is_disconnected", disconnected)
    monkeypatch.setattr(routes, "interpret", local_fixture)
    monkeypatch.setattr(store, "create_interpretation", unexpected_write, raising=False)
    response = client.post("/api/v1/interpretations", files={
        "file": ("source.pdf", MINIMAL_VALID_PDF_BYTES, "application/pdf"),
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "request_cancelled"
    assert len(calls) == disconnect_call
    assert store.writes == 0
