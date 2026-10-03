"""File-backed storage for new sprint documents, not a legacy dossier migration.

The caller supplies a trusted Django teacher ID after authentication, role and
CSRF checks. Approval records human confirmation but never publishes curriculum.
Use a dedicated database path. Existing Django data is never read or rewritten.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3


APPLICATION_ID = 0x41554C41
SCHEMA_VERSION = 1
EDITABLE = frozenset({"title", "objective", "materials", "steps", "assessment"})
INSUFFICIENT_SOURCE = "No hay suficiente fuente local"


class PersistenceError(Exception):
    def __init__(self, status, code, message, *, retryable=False):
        self.status, self.code, self.message = status, code, message
        self.retryable = retryable
        super().__init__(message)


def _invalid():
    return PersistenceError(422, "invalid_draft", "Revisa los datos del borrador.")


def _conflict():
    return PersistenceError(409, "revision_conflict", "El borrador cambió. Vuelve a cargarlo antes de guardar.")


def _owner(value):
    if type(value) is not int or value < 1:
        raise PersistenceError(403, "invalid_owner", "No tienes permiso para realizar esta acción.")
    return value


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise _invalid() from None


def _changes(value):
    if not isinstance(value, dict) or not value or not set(value) <= EDITABLE:
        raise _invalid()
    for key, item in value.items():
        if key in {"materials", "steps"}:
            if not isinstance(item, list) or not all(isinstance(text, str) for text in item):
                raise _invalid()
        elif not isinstance(item, str):
            raise _invalid()


def _initial(payload):
    payload = json.loads(_json(payload))
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] not in (1, 2):
        raise _invalid()
    if payload["schema_version"] == 2:
        from curriculum.interpretation_schema import InterpretationSchemaError, validate_interpretation

        try:
            validate_interpretation(payload)
        except InterpretationSchemaError:
            raise _invalid() from None
    identifier = payload.get("document_id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise _invalid()
    draft = payload.get("draft")
    if not isinstance(draft, dict) or not EDITABLE <= draft.keys():
        raise _invalid()
    _changes({key: draft[key] for key in EDITABLE})
    if type(draft.get("revision")) is not int or draft["revision"] != 1 or draft.get("approval_status") != "pending":
        raise _invalid()
    segments = payload.get("source_segments")
    fields = payload.get("fields")
    if not isinstance(segments, list) or not isinstance(fields, list):
        raise _invalid()
    segment_ids = set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise _invalid()
        sid = segment.get("id")
        if (not isinstance(sid, str) or not sid.strip() or sid in segment_ids
                or not isinstance(segment.get("text"), str) or not segment["text"].strip()
                or type(segment.get("page")) is not int or segment["page"] < 1):
            raise _invalid()
        segment_ids.add(sid)

    def references(items):
        if (not isinstance(items, list) or not all(isinstance(item, str) for item in items)
                or len(set(items)) != len(items) or not set(items) <= segment_ids):
            raise _invalid()

    references(draft.get("source_ids"))
    for field in fields:
        if not isinstance(field, dict) or field.get("status") not in ("extracted", "suggested", "unknown"):
            raise _invalid()
        references(field.get("evidence_ids"))
        if field["status"] == "extracted" and not field["evidence_ids"]:
            raise _invalid()
    draft["id"] = identifier
    draft["status"] = _draft_status(draft)
    return payload


def _draft_status(draft):
    enough = draft["source_ids"] and draft["objective"].strip() and any(step.strip() for step in draft["steps"])
    return "needs_review" if enough else INSUFFICIENT_SOURCE


class SQLiteRepository:
    """One connection per operation; transactions arbitrate concurrent revisions."""

    def __init__(self, path, *, initialize=True):
        if not path or str(path) == ":memory:":
            raise PersistenceError(503, "storage_unconfigured", "Falta configurar el almacenamiento.")
        self.path = Path(path).resolve()
        with self._connection(write=True, initialize=initialize) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            application = db.execute("PRAGMA application_id").fetchone()[0]
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if initialize and not tables and version == 0 and application == 0:
                db.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, initial_json TEXT NOT NULL, source BLOB NOT NULL, source_sha256 TEXT NOT NULL, filename TEXT NOT NULL, created_at TEXT NOT NULL)")
                db.execute("CREATE TABLE revisions (document_id TEXT NOT NULL REFERENCES documents(id), revision INTEGER NOT NULL CHECK(revision > 0), draft_json TEXT NOT NULL, action TEXT NOT NULL CHECK(action IN ('created','edited','approved')), actor_id INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(document_id, revision))")
                db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION or application != APPLICATION_ID:
                raise PersistenceError(503, "incompatible_storage", "El almacenamiento requiere revisión técnica.")

    @contextmanager
    def _connection(self, *, write=False, initialize=False):
        db = None
        try:
            if initialize:
                try:
                    descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError:
                    pass
                else:
                    os.close(descriptor)
            # mode=rw avoids silently replacing a database removed during service use.
            db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except (sqlite3.Error, OSError):
            if db is not None:
                db.rollback()
            raise PersistenceError(503, "storage_unavailable", "No se pudo guardar o leer el borrador. Inténtalo más tarde.", retryable=True) from None
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _document(db, owner_id, identifier):
        owner_id = _owner(owner_id)
        row = db.execute("SELECT * FROM documents WHERE id=? AND owner_id=?", (identifier, owner_id)).fetchone()
        if row is None:
            raise PersistenceError(404, "not_found", "No se encontró el recurso solicitado.")
        if hashlib.sha256(row["source"]).hexdigest() != row["source_sha256"]:
            raise PersistenceError(409, "source_changed", "La fuente cambió. Requiere revisión técnica.")
        return row

    @staticmethod
    def _draft(db, identifier):
        row = db.execute("SELECT draft_json FROM revisions WHERE document_id=? ORDER BY revision DESC LIMIT 1", (identifier,)).fetchone()
        return json.loads(row["draft_json"])

    @staticmethod
    def _record(db, identifier, draft, action, owner_id):
        db.execute("INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?)",
                   (identifier, draft["revision"], _json(draft), action, owner_id, datetime.now(timezone.utc).isoformat()))

    def create_interpretation(self, owner_id, payload, *, source_bytes, filename):
        owner_id = _owner(owner_id)
        payload = _initial(payload)
        if not isinstance(source_bytes, bytes) or not source_bytes or not isinstance(filename, str) or not filename:
            raise _invalid()
        identifier = payload["document_id"]
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        with self._connection(write=True) as db:
            existing = db.execute("SELECT * FROM documents WHERE id=?", (identifier,)).fetchone()
            if existing is not None:
                self._document(db, owner_id, identifier)
                if (existing["initial_json"] != _json(payload) or existing["source_sha256"] != source_hash
                        or existing["filename"] != filename):
                    raise _conflict()
                result = json.loads(existing["initial_json"])
                result["draft"] = self._draft(db, identifier)
                return result
            db.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (identifier, owner_id, _json(payload), source_bytes, source_hash, filename, datetime.now(timezone.utc).isoformat()))
            self._record(db, identifier, payload["draft"], "created", owner_id)
        return payload

    def get_interpretation(self, owner_id, document_id):
        with self._connection() as db:
            row = self._document(db, owner_id, document_id)
            payload = json.loads(row["initial_json"])
            payload["draft"] = self._draft(db, document_id)
            return payload

    def list_interpretations(self, owner_id):
        with self._connection() as db:
            rows = db.execute("SELECT id, created_at FROM documents WHERE owner_id=? ORDER BY created_at DESC LIMIT 200", (_owner(owner_id),)).fetchall()
            result = []
            for row in rows:
                # Listing approval is subject to the same source-integrity check
                # as detail, download and history, within this read transaction.
                self._document(db, owner_id, row["id"])
                result.append({"document_id": row["id"], "created_at": row["created_at"],
                               "draft": self._draft(db, row["id"])})
            return result

    def get_draft(self, owner_id, draft_id):
        return self.get_interpretation(owner_id, draft_id)["draft"]

    def update_draft(self, owner_id, draft_id, expected_revision, changes):
        _changes(changes)
        changes = json.loads(_json(changes))
        with self._connection(write=True) as db:
            self._document(db, owner_id, draft_id)
            draft = self._draft(db, draft_id)
            self._check_revision(draft, expected_revision)
            draft.update(changes)
            draft.update(revision=draft["revision"] + 1, approval_status="pending")
            draft["status"] = _draft_status(draft)
            self._record(db, draft_id, draft, "edited", owner_id)
            return draft

    @staticmethod
    def _check_revision(draft, expected_revision):
        if type(expected_revision) is not int or expected_revision < 1:
            raise _invalid()
        if draft["revision"] != expected_revision:
            raise _conflict()

    def approve_draft(self, owner_id, draft_id, expected_revision, *, confirm):
        if confirm is not True:
            raise PersistenceError(422, "confirmation_required", "Confirma la revisión antes de aprobar.")
        with self._connection(write=True) as db:
            self._document(db, owner_id, draft_id)
            draft = self._draft(db, draft_id)
            self._check_revision(draft, expected_revision)
            if _draft_status(draft) == INSUFFICIENT_SOURCE:
                raise PersistenceError(422, "insufficient_source", INSUFFICIENT_SOURCE)
            if draft["approval_status"] != "approved":
                draft.update(revision=draft["revision"] + 1, approval_status="approved")
                self._record(db, draft_id, draft, "approved", owner_id)
            return draft

    def get_history(self, owner_id, draft_id):
        with self._connection() as db:
            self._document(db, owner_id, draft_id)
            rows = db.execute("SELECT * FROM revisions WHERE document_id=? ORDER BY revision", (draft_id,)).fetchall()
            return [{"draft": json.loads(row["draft_json"]), "action": row["action"],
                     "actor_id": row["actor_id"], "created_at": row["created_at"]} for row in rows]

    def get_source(self, owner_id, document_id):
        with self._connection() as db:
            row = self._document(db, owner_id, document_id)
            return {"content": bytes(row["source"]), "filename": row["filename"], "sha256": row["source_sha256"]}

    def backup(self, destination):
        """Create a new private backup; never overwrite a prior database or backup."""
        destination = Path(destination).resolve()
        try:
            descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError:
            raise PersistenceError(409, "backup_exists", "El respaldo ya existe. Elige otra ruta.") from None
        except OSError:
            raise PersistenceError(503, "backup_unavailable", "No se pudo crear el respaldo.") from None
        with self._connection() as db:
            target = sqlite3.connect(destination)
            try:
                db.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise PersistenceError(503, "backup_invalid", "No se pudo verificar el respaldo.")
            finally:
                target.close()
        return destination


def get_repository():
    from django.conf import settings

    path = getattr(settings, "SPRINT_PERSISTENCE_PATH", None)
    if not path:
        raise PersistenceError(503, "storage_unconfigured", "Falta configurar el almacenamiento.")
    django_path = settings.DATABASES.get("default", {}).get("NAME")
    if django_path and Path(path).resolve() == Path(django_path).resolve():
        raise PersistenceError(503, "incompatible_storage", "Usa un almacenamiento separado para los borradores.")
    return SQLiteRepository(path, initialize=False)
