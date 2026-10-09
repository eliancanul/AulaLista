"""Real disposable SQLite checks; interpretation payloads are synthetic fixtures."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Barrier

import pytest

from api.persistence import PersistenceError, SQLiteRepository


PDF = b"%PDF-1.4\nsynthetic source fixture\n%%EOF\n"


@pytest.fixture(params=[1, 2], ids=["v1", "v2"])
def payload(request):
    return _payload(request.param)


def _payload(version):
    result = {
        "schema_version": 1, "document_id": "doc-one",
        "source_segments": [{"id": "p1", "text": "1ro. Leer y conversar.", "page": 1}],
        "fields": [{"key": "grado", "value": "1ro", "status": "extracted", "evidence_ids": ["p1"]},
                   {"key": "nivel_educativo", "value": None, "status": "unknown", "evidence_ids": []}],
        "missing_questions": ["¿A qué nivel educativo corresponde?"], "diagnostics": {},
        "draft": {"title": "Lectura", "objective": "Leer y conversar.", "materials": ["Texto"],
                  "steps": ["Leer", "Conversar"], "assessment": "Escuchar las ideas.",
                  "source_ids": ["p1"], "revision": 1, "approval_status": "pending", "status": "needs_review"},
    }
    if version == 2:
        from curriculum.interpretation_schema import FIELD_QUESTIONS
        from curriculum.source_segments import extracted_page_segments

        text = result["source_segments"][0]["text"]
        result["schema_version"] = 2
        result["draft"]["title"] = "Actividad por revisar"
        result["source_segments"] = extracted_page_segments(text, "fixture-source", 1)
        refs = [s["id"] for s in result["source_segments"]]
        result["draft"]["source_ids"] = refs
        result["fields"][0].update(evidence_ids=refs, reason="Fuente sintética.")
        result["fields"][1]["reason"] = "Falta confirmar."
        result["fields"].extend(
            {"key": key, "value": None, "status": "unknown", "evidence_ids": [], "reason": "Falta confirmar."}
            for key in FIELD_QUESTIONS if key not in {"grado", "nivel_educativo"}
        )
        result["missing_questions"] = [FIELD_QUESTIONS[f["key"]] for f in result["fields"] if f["status"] == "unknown"]
        result["diagnostics"] = {
            "method": "local_source_interpreter", "provider_status": "not_requested",
            "attempts": 0, "errors": [], "model_winner": None, "source_page_count": 1,
            "source_warnings": [], "source_extraction": {
                "document_id": "fixture-source", "status": "complete", "page_count": 1,
                "requires_review": True, "warnings": [], "pages": [{
                    "page": 1, "text": text, "raw_text": text, "status": "extracted",
                    "method": "pypdf-layout", "warnings": [],
                }],
            },
        }
    return result


@pytest.fixture
def store(tmp_path, payload):
    repo = SQLiteRepository(tmp_path / "drafts.sqlite3")
    repo.create_interpretation(7, payload, source_bytes=PDF, filename="planeación.pdf")
    return repo


def test_reopen_in_fresh_process_preserves_upload_and_exact_teacher_text(store, payload):
    text = "  Mi título docente\nñ y acentos á  "
    store.update_draft(7, "doc-one", 1, {"title": text})
    script = '''
import json, sys
from api.persistence import SQLiteRepository
repo = SQLiteRepository(sys.argv[1])
print(json.dumps({"document": repo.get_interpretation(7, "doc-one"), "source": repo.get_source(7, "doc-one")["content"].hex()}))
'''
    result = subprocess.run([sys.executable, "-c", script, str(store.path)], check=True, capture_output=True, text=True)
    saved = json.loads(result.stdout)
    assert saved["document"]["draft"]["title"] == text
    assert saved["document"]["draft"]["revision"] == 2
    assert saved["document"]["fields"][1]["value"] is None
    assert {k: v for k, v in saved["document"].items() if k != "draft"} == {
        k: v for k, v in payload.items() if k != "draft"
    }
    assert bytes.fromhex(saved["source"]) == PDF
    assert store.get_source(7, "doc-one")["filename"] == "planeación.pdf"
    assert store.get_source(7, "doc-one")["sha256"] == hashlib.sha256(PDF).hexdigest()


def test_approval_history_survives_edit_and_second_approval(store):
    approved = store.approve_draft(7, "doc-one", 1, confirm=True)
    assert (approved["revision"], approved["approval_status"]) == (2, "approved")
    assert store.approve_draft(7, "doc-one", 2, confirm=True) == approved
    edited = store.update_draft(7, "doc-one", 2, {"steps": ["La docente cambia el paso"]})
    assert (edited["revision"], edited["approval_status"]) == (3, "pending")
    store.approve_draft(7, "doc-one", 3, confirm=True)
    history = SQLiteRepository(store.path).get_history(7, "doc-one")
    assert [row["action"] for row in history] == ["created", "approved", "edited", "approved"]
    assert history[1]["draft"]["steps"] == ["Leer", "Conversar"]
    assert history[3]["draft"]["steps"] == ["La docente cambia el paso"]
    assert {row["actor_id"] for row in history} == {7}
    history[1]["draft"]["steps"].append("mutación externa")
    assert store.get_history(7, "doc-one")[1]["draft"]["steps"] == ["Leer", "Conversar"]


@pytest.mark.parametrize("operation", [
    lambda s, owner, key: s.get_interpretation(owner, key),
    lambda s, owner, key: s.get_draft(owner, key),
    lambda s, owner, key: s.get_source(owner, key),
    lambda s, owner, key: s.get_history(owner, key),
    lambda s, owner, key: s.update_draft(owner, key, 1, {"title": "Intrusión"}),
    lambda s, owner, key: s.approve_draft(owner, key, 1, confirm=True),
])
def test_other_teacher_and_absent_document_are_indistinguishable(store, operation):
    errors = []
    for owner, key in [(8, "doc-one"), (7, "absent")]:
        with pytest.raises(PersistenceError) as caught:
            operation(store, owner, key)
        errors.append((caught.value.status, caught.value.code, caught.value.message))
    assert errors[0] == errors[1]
    assert errors[0][0] == 404
    assert len(store.get_history(7, "doc-one")) == 1


def test_concurrent_connections_cannot_lose_an_edit(store):
    barrier = Barrier(2)

    def edit(title):
        repo = SQLiteRepository(store.path)
        barrier.wait(timeout=5)
        try:
            return repo.update_draft(7, "doc-one", 1, {"title": title})
        except PersistenceError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["Primer cambio", "Segundo cambio"]))
    winners = [result for result in results if isinstance(result, dict)]
    failures = [result for result in results if isinstance(result, PersistenceError)]
    assert len(winners) == len(failures) == 1
    assert failures[0].code == "revision_conflict"
    assert store.get_draft(7, "doc-one")["title"] == winners[0]["title"]
    assert len(store.get_history(7, "doc-one")) == 2


def test_approval_cannot_approve_stale_revision(store):
    store.update_draft(7, "doc-one", 1, {"title": "Revisión humana"})
    with pytest.raises(PersistenceError, match="El borrador cambió"):
        store.approve_draft(7, "doc-one", 1, confirm=True)
    assert store.get_draft(7, "doc-one")["approval_status"] == "pending"


@pytest.mark.parametrize("changes", [{}, {"owner_id": 8}, {"revision": 8}, {"source_ids": []},
                                      {"approval_status": "approved"}, {"title": None}, {"steps": "texto"},
                                      {"materials": [1]}, {"title": "válido", "unknown": 1}])
def test_invalid_edits_leave_saved_draft_unchanged(store, changes):
    before = store.get_interpretation(7, "doc-one")
    with pytest.raises(PersistenceError) as caught:
        store.update_draft(7, "doc-one", 1, changes)
    assert caught.value.status == 422
    assert store.get_interpretation(7, "doc-one") == before
    assert len(store.get_history(7, "doc-one")) == 1


@pytest.mark.parametrize("confirm", [False, None, 1, "true"])
def test_confirmation_is_explicit_boolean(store, confirm):
    with pytest.raises(PersistenceError) as caught:
        store.approve_draft(7, "doc-one", 1, confirm=confirm)
    assert caught.value.code == "confirmation_required"
    assert store.get_draft(7, "doc-one")["approval_status"] == "pending"


def test_insufficient_source_cannot_be_approved(tmp_path, payload):
    payload["draft"]["source_ids"] = []
    payload["draft"].update(objective="", materials=[], steps=[], assessment="",
                            status="No hay suficiente fuente local")
    store = SQLiteRepository(tmp_path / "empty-source.sqlite3")
    store.create_interpretation(7, payload, source_bytes=PDF, filename="source.pdf")
    with pytest.raises(PersistenceError) as caught:
        store.approve_draft(7, "doc-one", 1, confirm=True)
    assert caught.value.message == "No hay suficiente fuente local"


def test_retry_create_preserves_teacher_edit_and_rejects_different_content(store, payload):
    store.update_draft(7, "doc-one", 1, {"title": "Título docente"})
    retry = store.create_interpretation(7, payload, source_bytes=PDF, filename="planeación.pdf")
    assert retry["draft"]["title"] == "Título docente"
    assert retry["draft"]["revision"] == 2
    changed = copy.deepcopy(payload)
    changed["draft"]["objective"] = "Nueva extracción"
    with pytest.raises(PersistenceError) as caught:
        store.create_interpretation(7, changed, source_bytes=PDF, filename="planeación.pdf")
    assert caught.value.status == 409
    with pytest.raises(PersistenceError) as caught:
        store.create_interpretation(8, payload, source_bytes=PDF, filename="planeación.pdf")
    assert caught.value.status == 404
    assert len(store.get_history(7, "doc-one")) == 2


def test_backup_restore_keeps_source_owner_and_approved_history(store, tmp_path):
    store.approve_draft(7, "doc-one", 1, confirm=True)
    store.update_draft(7, "doc-one", 2, {"title": "Trabajo posterior"})
    backup = store.backup(tmp_path / "backup.sqlite3")
    restored = SQLiteRepository(backup)
    assert restored.get_interpretation(7, "doc-one") == store.get_interpretation(7, "doc-one")
    assert restored.get_history(7, "doc-one") == store.get_history(7, "doc-one")
    assert restored.get_source(7, "doc-one")["content"] == PDF
    with pytest.raises(PersistenceError) as caught:
        restored.get_draft(8, "doc-one")
    assert caught.value.status == 404
    with pytest.raises(PersistenceError) as caught:
        store.backup(backup)
    assert caught.value.code == "backup_exists"
    restored.update_draft(7, "doc-one", 3, {"title": "Sólo restaurado"})
    assert store.get_draft(7, "doc-one")["title"] == "Trabajo posterior"
    assert os.stat(backup).st_mode & 0o777 == 0o600


def test_failure_during_create_rolls_back_source_and_document(store, payload):
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON revisions BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END")
    payload["document_id"] = "failed-document"
    with pytest.raises(PersistenceError) as caught:
        store.create_interpretation(7, payload, source_bytes=PDF, filename="source.pdf")
    assert caught.value.status == 503
    with pytest.raises(PersistenceError) as caught:
        store.get_interpretation(7, "failed-document")
    assert caught.value.status == 404
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 1


def test_foreign_database_and_future_schema_are_not_modified(tmp_path):
    path = tmp_path / "foreign.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE auth_user (id INTEGER)")
        db.execute("INSERT INTO auth_user VALUES (7)")
    before = path.read_bytes()
    with pytest.raises(PersistenceError) as caught:
        SQLiteRepository(path)
    assert caught.value.code == "incompatible_storage"
    assert path.read_bytes() == before
    future = SQLiteRepository(tmp_path / "future.sqlite3")
    with sqlite3.connect(future.path) as db:
        db.execute("PRAGMA user_version=2")
    before = future.path.read_bytes()
    with pytest.raises(PersistenceError):
        SQLiteRepository(future.path)
    assert future.path.read_bytes() == before


def test_corrupt_source_cannot_be_approved_or_downloaded(store):
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE documents SET source=? WHERE id='doc-one'", (b"tampered",))
    for operation in [lambda: store.approve_draft(7, "doc-one", 1, confirm=True),
                      lambda: store.get_source(7, "doc-one")]:
        with pytest.raises(PersistenceError) as caught:
            operation()
        assert caught.value.code == "source_changed"


@pytest.mark.parametrize("mutation", [
    lambda p: p["draft"].update(source_ids=["missing"]),
    lambda p: p["draft"].update(approval_status="approved"),
    lambda p: p.update(schema_version=3),
    lambda p: p["source_segments"].append(p["source_segments"][0]),
    lambda p: p["fields"][0].update(evidence_ids=["missing"]),
])
def test_invalid_initial_payload_is_not_stored(tmp_path, payload, mutation):
    mutation(payload)
    store = SQLiteRepository(tmp_path / "invalid.sqlite3")
    with pytest.raises(PersistenceError) as caught:
        store.create_interpretation(7, payload, source_bytes=PDF, filename="source.pdf")
    assert caught.value.status == 422
    with pytest.raises(PersistenceError) as caught:
        store.get_draft(7, "doc-one")
    assert caught.value.status == 404


@pytest.mark.parametrize("revision", [True, "1", 0, None])
def test_revision_is_a_positive_integer(store, revision):
    with pytest.raises(PersistenceError) as caught:
        store.update_draft(7, "doc-one", revision, {"title": "Cambio"})
    assert caught.value.status == 422


def test_removed_database_is_not_silently_recreated(store):
    store.path.unlink()
    with pytest.raises(PersistenceError) as caught:
        store.get_draft(7, "doc-one")
    assert caught.value.status == 503
    assert not store.path.exists()


def test_configuration_requires_provisioned_separate_database(settings, tmp_path):
    from api.persistence import get_repository

    settings.SPRINT_PERSISTENCE_PATH = None
    with pytest.raises(PersistenceError) as caught:
        get_repository()
    assert caught.value.code == "storage_unconfigured"
    settings.SPRINT_PERSISTENCE_PATH = str(tmp_path / "not-provisioned.sqlite3")
    with pytest.raises(PersistenceError) as caught:
        get_repository()
    assert caught.value.code == "storage_unavailable"
    assert not Path(settings.SPRINT_PERSISTENCE_PATH).exists()
    SQLiteRepository(settings.SPRINT_PERSISTENCE_PATH)
    assert get_repository().path == Path(settings.SPRINT_PERSISTENCE_PATH)
    settings.SPRINT_PERSISTENCE_PATH = settings.DATABASES["default"]["NAME"]
    with pytest.raises(PersistenceError) as caught:
        get_repository()
    assert caught.value.code == "incompatible_storage"


def test_retry_is_independent_of_json_key_order(store, payload):
    reordered = dict(reversed(list(payload.items())))
    reordered["draft"] = dict(reversed(list(payload["draft"].items())))
    assert store.create_interpretation(7, reordered, source_bytes=PDF, filename="planeación.pdf")["draft"]["revision"] == 1
    assert len(store.get_history(7, "doc-one")) == 1


def test_read_approved_draft_fails_closed_when_source_is_corrupt(store):
    store.approve_draft(7, "doc-one", 1, confirm=True)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE documents SET source=? WHERE id='doc-one'", (b"changed",))
    with pytest.raises(PersistenceError) as caught:
        store.get_draft(7, "doc-one")
    assert caught.value.code == "source_changed"
    with pytest.raises(PersistenceError) as caught:
        store.get_draft(8, "doc-one")
    assert caught.value.code == "not_found"


def test_failed_edit_preserves_current_approval_and_history(store):
    store.approve_draft(7, "doc-one", 1, confirm=True)
    before = store.get_history(7, "doc-one")
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TRIGGER fail_edit BEFORE INSERT ON revisions BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END")
    with pytest.raises(PersistenceError) as caught:
        store.update_draft(7, "doc-one", 2, {"title": "No se guarda"})
    assert caught.value.code == "storage_unavailable"
    assert store.get_history(7, "doc-one") == before
    assert store.get_draft(7, "doc-one")["approval_status"] == "approved"


def test_concurrent_edit_and_approval_never_approve_unseen_text(store):
    initial_title = store.get_draft(7, "doc-one")["title"]
    barrier = Barrier(2)

    def write(action):
        repo = SQLiteRepository(store.path)
        barrier.wait(timeout=5)
        try:
            if action == "approve":
                return repo.approve_draft(7, "doc-one", 1, confirm=True)
            return repo.update_draft(7, "doc-one", 1, {"title": "Texto no revisado"})
        except PersistenceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["edit", "approve"]))
    assert results.count("revision_conflict") == 1
    saved = store.get_draft(7, "doc-one")
    assert (saved["title"], saved["approval_status"]) in {
        ("Texto no revisado", "pending"), (initial_title, "approved"),
    }
    assert len(store.get_history(7, "doc-one")) == 2


@pytest.mark.parametrize("path,value", [
    (("schema_version",), True),
    (("schema_version",), "2"),
    (("schema_version",), 0),
    (("source_segments", 0, "kind"), "invented"),
    (("source_segments", 0, "text_start"), True),
    (("source_segments", 0, "text_start"), -1),
    (("source_segments", 0, "text_end"), 0),
    (("source_segments", 0, "text_end"), 999),
    (("source_segments", 0, "page"), 2),
    (("source_segments", 0, "text"), "Texto inventado"),
    (("source_segments", 0, "id"), "invented"),
    (("diagnostics", "source_extraction"), None),
    (("diagnostics", "source_extraction", "page_count"), 2),
    (("diagnostics", "source_extraction", "requires_review"), False),
    (("diagnostics", "source_extraction", "status"), "partial"),
    (("diagnostics", "source_extraction", "pages"), []),
    (("diagnostics", "source_extraction", "pages", 0, "text"), "Otro texto"),
    (("diagnostics", "source_extraction", "pages", 0, "method"), "invented"),
    (("diagnostics", "source_extraction", "pages", 0, "status"), "failed"),
])
def test_malformed_v2_is_rejected_before_any_write(tmp_path, path, value):
    repo = SQLiteRepository(tmp_path / "malformed.sqlite3")
    payload = _payload(2)
    node = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    before = repo.path.read_bytes()
    with pytest.raises(PersistenceError) as caught:
        repo.create_interpretation(7, payload, source_bytes=PDF, filename="source.pdf")
    assert (caught.value.status, caught.value.code) == (422, "invalid_draft")
    assert repo.path.read_bytes() == before
    with sqlite3.connect(repo.path) as db:
        assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM revisions").fetchone()[0] == 0


@pytest.mark.parametrize("missing", ["kind", "text_start", "text_end"])
def test_v2_cannot_use_incomplete_segment_shape(tmp_path, missing):
    payload = _payload(2)
    del payload["source_segments"][0][missing]
    repo = SQLiteRepository(tmp_path / "missing.sqlite3")
    with pytest.raises(PersistenceError) as caught:
        repo.create_interpretation(7, payload, source_bytes=PDF, filename="source.pdf")
    assert caught.value.code == "invalid_draft"


def test_real_interpreter_v2_and_existing_v1_coexist_and_reopen(tmp_path):
    from curriculum.interpretation_service import interpret_source
    from test_t15_curriculum_import import make_minimal_pdf

    repo = SQLiteRepository(tmp_path / "mixed.sqlite3")
    legacy = _payload(1)
    repo.create_interpretation(7, legacy, source_bytes=PDF, filename="legacy.pdf")
    approved = repo.approve_draft(7, "doc-one", 1, confirm=True)
    repo.update_draft(7, "doc-one", 2, {"title": "  Edición v1 conservada\n"})
    legacy_saved = repo.get_interpretation(7, "doc-one")
    legacy_history = repo.get_history(7, "doc-one")
    content = make_minimal_pdf(["Proyecto: El patio", "", "Grado: 3ro"])
    payload = interpret_source(content)
    original = copy.deepcopy(payload)
    assert payload["schema_version"] == 2
    assert payload["diagnostics"]["source_extraction"]["status"] == "partial"
    assert [s["page"] for s in payload["source_segments"]] == [1, 3]
    saved = repo.create_interpretation(7, payload, source_bytes=content, filename="partial.pdf")
    assert payload == original
    expected = copy.deepcopy(original)
    expected["draft"]["id"] = payload["document_id"]
    assert saved == expected
    script = '''
import json, sys
from api.persistence import SQLiteRepository
repo = SQLiteRepository(sys.argv[1], initialize=False)
print(json.dumps(repo.get_interpretation(7, sys.argv[2])))
'''
    result = subprocess.run([sys.executable, "-c", script, str(repo.path), payload["document_id"]],
                            check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == expected
    reopened = SQLiteRepository(repo.path, initialize=False)
    assert reopened.get_source(7, payload["document_id"])["content"] == content
    assert reopened.get_interpretation(7, "doc-one") == legacy_saved
    assert reopened.get_history(7, "doc-one") == legacy_history
    assert legacy_history[1]["draft"] == approved
    with sqlite3.connect(repo.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
