"""AulaLista V0 Curriculum Source Interpreter.

Provides verifiable, traceable interpretation of curriculum planning PDFs
without fabricated claims, precached mock data, or automatic publication.
Preserves physical source page provenance, exact text excerpts, and
multidimensional uncertainty (origin, status, review).
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PyPdfError

from curriculum.verification import normalize_text_for_evidence_check
from curriculum.vocabulary import CANONICAL_CAMPOS
from curriculum.overview_fields import extract_overview_spans
from curriculum.source_segments import (
    scan_session_segments, match_session_segment, anchor_matches,
    clean_page_prefix, is_structural_barrier, phase_project_context, phase_review_scope,
)

logger = logging.getLogger(__name__)


class CurriculumInterpretationError(ValueError):
    """Base exception for curriculum interpretation failures."""
    pass


class SourcePdfReadError(CurriculumInterpretationError):
    """Raised when the source PDF file/stream is corrupt, truncated, or unreadable."""
    pass


class SelectionError(CurriculumInterpretationError):
    """Raised when the requested session_id or pages selection is invalid or inconsistent."""
    pass


class InterpretationCancelledError(CurriculumInterpretationError):
    """Raised when curriculum source interpretation is cooperatively cancelled."""
    pass


class InterpretationTimeoutError(TimeoutError, CurriculumInterpretationError):
    """Raised when curriculum source interpretation exceeds allowed duration."""
    pass


ORIGIN_EXTRACTED = "extracted"
ORIGIN_PROPOSED = "proposed"
ORIGIN_TEACHER_ENTERED = "teacher_entered"

STATUS_SUPPORTED = "supported"
STATUS_MISSING = "missing"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_CONFLICTING = "conflicting"

REVIEW_PENDING = "pending"
REVIEW_CONFIRMED = "confirmed"
REVIEW_CORRECTED = "corrected"

def _normalized_page_with_source_spans(text: str) -> tuple[str, list[tuple[int, int, int, int]]]:
    """Index normalized tokens while retaining their original physical spans.

    Offsets in normalized Unicode cannot be used to slice the source: NFD,
    ligatures and whitespace all change lengths. Token spans also preserve
    surrounding punctuation in the exact excerpt. Internal punctuation remains
    significant, using the same normalization as the mechanical verifier.
    """
    normalized_tokens = []
    spans = []
    cursor = 0
    for token in re.finditer(r"[^\s\u00a0\u2000-\u200b]+", text):
        normalized = normalize_text_for_evidence_check(token.group())
        if not normalized:
            continue
        if normalized_tokens:
            cursor += 1
        spans.append((cursor, cursor + len(normalized), token.start(), token.end()))
        normalized_tokens.append(normalized)
        cursor += len(normalized)
    return " ".join(normalized_tokens), spans


def _canonical_campo_mentions(pages: list[str], sha256: str) -> dict[str, SourceReference]:
    """First page-local literal mention per canonical name; never join pages."""
    mentions = {}
    for page_number, page in enumerate(pages, start=1):
        normalized_page, spans = _normalized_page_with_source_spans(page)
        for canonical in CANONICAL_CAMPOS:
            if canonical in mentions:
                continue
            needle = normalize_text_for_evidence_check(canonical)
            match = re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", normalized_page)
            if not match:
                continue
            covered = [span for span in spans if span[0] < match.end() and span[1] > match.start()]
            excerpt = page[covered[0][2]:covered[-1][3]]
            # Fail closed if a normalization edge case cannot be traced back.
            if not re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", normalize_text_for_evidence_check(excerpt)):
                continue
            mentions[canonical] = SourceReference(
                document_sha256=sha256, page_number=page_number, excerpt=excerpt,
            )
    return mentions


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SourceReference:
    """Explicit provenance anchor to an immutable source document."""

    document_sha256: str
    page_number: int  # 1-indexed physical PDF page
    printed_label: str = ""
    excerpt: str = ""
    region: dict[str, Any] | None = None
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_sha256": self.document_sha256,
            "page_number": int(self.page_number),
            "printed_label": self.printed_label,
            "excerpt": self.excerpt,
            "region": self.region,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceReference:
        return cls(
            document_sha256=str(data.get("document_sha256", "")),
            page_number=int(data.get("page_number", 1)),
            printed_label=str(data.get("printed_label", "")),
            excerpt=str(data.get("excerpt", "")),
            region=data.get("region"),
            role=str(data.get("role", "")),
        )


@dataclass
class MalformedEvidenceMarker:
    raw_value: Any

    def to_dict(self) -> Any:
        return self.raw_value


def _is_empty_value(val: Any) -> bool:
    """Check if value is considered empty for editorial purposes."""
    if val is None:
        return True
    if isinstance(val, str):
        return len(val.strip()) == 0
    if isinstance(val, (list, tuple, set, dict)):
        return len(val) == 0
    return False


def parse_canonical_positive_int(val: Any) -> int:
    """Parse and validate a strictly canonical positive integer (1, 2, ...).

    Accepts:
      - Python int > 0, strictly excluding bool (isinstance(val, bool) is False).
      - Strict canonical decimal string matching ^[1-9][0-9]*$ without leading zeros,
        signs, decimals, exponents, or whitespace.

    Rejects:
      - bool (True, False).
      - float (1.0, 1.5).
      - String with whitespace (' 1 '), signs ('+1', '-1'), leading zeros ('01'),
        decimals ('1.0'), exponent ('1e0'), or non-numeric characters.
      - Integers <= 0.
      - Any non-int, non-string type.
    """
    if isinstance(val, bool):
        raise ValueError(f"Valor booleano no permitido como entero: {val!r}")
    if isinstance(val, float):
        raise ValueError(f"Valor flotante no permitido como entero: {val!r}")
    if isinstance(val, int):
        if val <= 0:
            raise ValueError(f"El entero debe ser estrictamente positivo (>0): {val!r}")
        return val
    if isinstance(val, str):
        if not re.match(r"^[1-9]\d*$", val):
            raise ValueError(f"Formato no canónico de entero positivo: {val!r}")
        return int(val)
    raise ValueError(f"Tipo no convertible a entero positivo: {type(val).__name__} ({val!r})")


HISTORY_SCHEMA_VERSION = 1


@dataclass
class HistoryDelta:
    """Versioned schema for a discrete field or annex delta."""

    scope: str  # "general" | "session" | "annex"
    field: str
    change_type: str  # "modified" | "confirmed" | "cleared" | "added" | "removed" | "manual_association" | "disassociated" | "ambiguous_identity"
    before: Any | None
    after: Any | None
    stable_id: str = ""
    session_id: str | None = None
    reason: str = ""
    confidence: str = ""
    schema_version: int = HISTORY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        res = {
            "scope": self.scope,
            "field": self.field,
            "stable_id": self.stable_id or self.field,
            "session_id": self.session_id,
            "change_type": self.change_type,
            "before": copy.deepcopy(self.before),
            "after": copy.deepcopy(self.after),
            "schema_version": self.schema_version,
        }
        if self.reason:
            res["reason"] = self.reason
        if self.confidence:
            res["confidence"] = self.confidence
        return res

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryDelta:
        if not isinstance(data, dict):
            raise ValueError(f"Delta data must be a dict, got {type(data).__name__}")
        scope = str(data.get("scope", "")).strip()
        field_name = str(data.get("field", "")).strip()
        change_type = str(data.get("change_type", "")).strip()
        if scope not in ("general", "session", "annex") or not field_name or not change_type:
            raise ValueError(f"Incomplete or invalid delta keys: scope={scope!r}, field={field_name!r}, change_type={change_type!r}")

        before = data.get("before")
        after = data.get("after")
        if change_type == "ambiguous_identity":
            if before is not None and not isinstance(before, (dict, list)):
                raise ValueError(f"Delta 'ambiguous_identity' before must be dict, list, or None, got {type(before).__name__}")
            if after is not None and not isinstance(after, (dict, list)):
                raise ValueError(f"Delta 'ambiguous_identity' after must be dict, list, or None, got {type(after).__name__}")
        else:
            if before is not None and not isinstance(before, dict):
                raise ValueError(f"Delta before must be dict or None, got {type(before).__name__}")
            if after is not None and not isinstance(after, dict):
                raise ValueError(f"Delta after must be dict or None, got {type(after).__name__}")

        raw_schema = data.get("schema_version", HISTORY_SCHEMA_VERSION)
        try:
            if isinstance(raw_schema, (dict, list)):
                schema_ver = HISTORY_SCHEMA_VERSION
            else:
                schema_ver = int(raw_schema)
        except (ValueError, TypeError):
            schema_ver = HISTORY_SCHEMA_VERSION

        reason_val = str(data.get("reason", "")) if not isinstance(data.get("reason"), (dict, list)) else ""
        conf_val = str(data.get("confidence", "")) if not isinstance(data.get("confidence"), (dict, list)) else ""
        sess_id_val = str(data.get("session_id")) if data.get("session_id") is not None and not isinstance(data.get("session_id"), (dict, list)) else None

        return cls(
            scope=scope,
            field=field_name,
            change_type=change_type,
            before=before,
            after=after,
            stable_id=str(data.get("stable_id") or field_name),
            session_id=sess_id_val,
            reason=reason_val,
            confidence=conf_val,
            schema_version=schema_ver,
        )


@dataclass
class HistoryEntry:
    """Versioned audit trail history entry."""

    version: int
    action: str
    actor: str
    timestamp: str
    summary: str = ""
    changes: list[str] = field(default_factory=list)
    deltas: list[dict[str, Any]] = field(default_factory=list)
    selection_reset: bool = False
    retry_after_cancel: bool = False
    schema_version: int = HISTORY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": int(self.version),
            "action": self.action,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "changes": list(self.changes),
            "deltas": [
                d.to_dict() if isinstance(d, HistoryDelta) else d
                for d in self.deltas
            ],
            "selection_reset": self.selection_reset,
            "retry_after_cancel": self.retry_after_cancel,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Any) -> HistoryEntry:
        if not isinstance(data, dict):
            return cls(
                version=0,
                action="legacy_raw",
                actor="system",
                timestamp="",
                summary=str(data)[:500],
                changes=[],
                deltas=[],
                schema_version=0,
            )
        raw_ver = data.get("version", 0)
        try:
            if isinstance(raw_ver, (dict, list)):
                ver = 0
            else:
                ver = int(raw_ver)
        except (ValueError, TypeError):
            ver = 0

        raw_schema = data.get("schema_version", HISTORY_SCHEMA_VERSION)
        try:
            if isinstance(raw_schema, (dict, list)):
                schema_ver = HISTORY_SCHEMA_VERSION
            else:
                schema_ver = int(raw_schema)
        except (ValueError, TypeError):
            schema_ver = HISTORY_SCHEMA_VERSION

        raw_deltas = data.get("deltas")
        clean_deltas = []
        has_invalid_deltas = False
        if isinstance(raw_deltas, list):
            for d in raw_deltas:
                if isinstance(d, HistoryDelta):
                    clean_deltas.append(d.to_dict())
                elif isinstance(d, dict):
                    try:
                        clean_deltas.append(HistoryDelta.from_dict(d).to_dict())
                    except ValueError:
                        has_invalid_deltas = True
                else:
                    has_invalid_deltas = True
        else:
            has_invalid_deltas = (raw_deltas is not None)

        action_str = str(data.get("action") or "unknown")
        if has_invalid_deltas and not clean_deltas and action_str in ("unknown", ""):
            action_str = "legacy_malformed"

        raw_actor = data.get("actor")
        actor_str = str(raw_actor or "Sistema") if not isinstance(raw_actor, (dict, list)) else "Sistema"

        raw_ts = data.get("timestamp")
        ts_str = str(raw_ts or "") if not isinstance(raw_ts, (dict, list)) else ""

        raw_summary = data.get("summary")
        summary_str = str(raw_summary or "") if not isinstance(raw_summary, (dict, list)) else ""

        raw_changes = data.get("changes")
        if isinstance(raw_changes, list):
            changes_list = [str(c) for c in raw_changes if c is not None and not isinstance(c, (dict, list))]
        else:
            changes_list = []

        return cls(
            version=ver,
            action=action_str,
            actor=actor_str,
            timestamp=ts_str,
            summary=summary_str,
            changes=changes_list,
            deltas=clean_deltas,
            selection_reset=bool(data.get("selection_reset", False)),
            retry_after_cancel=bool(data.get("retry_after_cancel", False)),
            schema_version=schema_ver,
        )


def _make_history_delta(
    scope: str,
    field: str,
    change_type: str,
    before: Any | None,
    after: Any | None,
    session_id: str | None = None,
    stable_id: str = "",
    reason: str = "",
    confidence: str = "",
) -> dict[str, Any]:
    return HistoryDelta(
        scope=scope,
        field=field,
        change_type=change_type,
        before=before,
        after=after,
        session_id=session_id,
        stable_id=stable_id or field,
        reason=reason,
        confidence=confidence,
    ).to_dict()


def derive_field_operational_state(field: "InterpretedField") -> tuple[str, str]:
    """Derive (operational_state, current_action) for an InterpretedField.
    operational_state:
      - 'requires_resolution': conflict or missing required content (red)
      - 'needs_review': unconfirmed data, ambiguous/proposal pending review (yellow)
      - 'resolved': explicitly confirmed or corrected by teacher (green)
    current_action:
      - Empty string if resolved.
      - Clear human-readable Spanish instructions if action is pending.
    """
    if field.status == STATUS_CONFLICTING:
        return ("requires_resolution", "Conflicto en la fuente: requiere desambiguación y corrección docente.")
    if field.review in (REVIEW_CONFIRMED, REVIEW_CORRECTED) and not _is_empty_value(field.value):
        return ("resolved", "")
    if field.status == STATUS_MISSING or _is_empty_value(field.value):
        return ("requires_resolution", "Requiere captura de contenido pedagógico por el docente.")
    if field.status == STATUS_AMBIGUOUS:
        return ("needs_review", "Interpretación ambigua o propuesta; requiere verificación docente.")
    if field.origin == ORIGIN_PROPOSED or field.review == REVIEW_PENDING:
        return ("needs_review", "Dato fundamentado en la fuente; pendiente de confirmación docente.")
    return ("needs_review", "Pendiente de revisión docente.")


def derive_annex_operational_state(
    ref: "AnnexReference",
    source_sha: str = "",
    page_count: int = 0,
) -> tuple[str, str]:
    """Derive (operational_state, current_action) for an AnnexReference."""
    has_valid_page = (
        ref.confirmed_page is not None
        and isinstance(ref.confirmed_page, int)
        and ref.confirmed_page > 0
        and (page_count <= 0 or ref.confirmed_page <= page_count)
    )
    if has_valid_page and ref.review in (REVIEW_CONFIRMED, REVIEW_CORRECTED):
        # Must have coherent evidence for the confirmed page + source SHA
        has_coherent_evidence = False
        for ev in (ref.evidence or []):
            if ev.page_number == ref.confirmed_page:
                ev_sha = getattr(ev, "document_sha256", None) or ""
                if (
                    source_sha
                    and ev_sha
                    and ev_sha == source_sha
                    and getattr(ev, "role", "") in (
                        "teacher_selected_source_page",
                        "annex_source",
                        "extracted_annex",
                        "evidence",
                        "",
                    )
                ):
                    has_coherent_evidence = True
                    break
        if has_coherent_evidence:
            return ("resolved", "")
        if ref.candidate_pages:
            return (
                "needs_review",
                "Lámina confirmada sin evidencia coherente en la fuente. Requiere verificar o seleccionar lámina.",
            )
        return (
            "requires_resolution",
            "Lámina confirmada sin evidencia de lámina física en la fuente. Requiere asociar una página física válida.",
        )

    if not ref.candidate_pages:
        return (
            "requires_resolution",
            "Sin lámina candidata detectada automáticamente. Requiere asociar una página física del PDF manualmente.",
        )
    return ("needs_review", "Lámina candidata detectada; pendiente de confirmación docente.")


def _snapshot_field_for_delta(f: "InterpretedField") -> dict[str, Any]:
    return copy.deepcopy(f.to_dict())


def _snapshot_annex_for_delta(r: "AnnexReference") -> dict[str, Any]:
    return copy.deepcopy(r.to_dict())


@dataclass
class InterpretedField:
    """An interpreted domain field with multidimensional uncertainty and review."""

    name: str
    value: Any
    origin: str = ORIGIN_EXTRACTED
    status: str = STATUS_SUPPORTED
    review: str = REVIEW_PENDING
    reason: str = ""
    action_required: str = ""
    evidence: list[Any] = field(default_factory=list)
    original_value: Any = None
    original_reason: str | None = None
    current_action: str = ""
    missing_schema_keys: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if _is_empty_value(self.value):
            if self.review in (REVIEW_CONFIRMED, REVIEW_CORRECTED):
                self.review = REVIEW_PENDING
            if self.status == STATUS_SUPPORTED:
                self.status = STATUS_MISSING
        state, act = derive_field_operational_state(self)
        self.current_action = act
        self.action_required = act

    @property
    def operational_state(self) -> str:
        state, _ = derive_field_operational_state(self)
        return state

    def to_dict(self) -> dict[str, Any]:
        res = {
            "name": self.name,
            "value": copy.deepcopy(self.value),
            "origin": self.origin,
            "status": self.status,
            "review": self.review,
            "reason": self.reason,
            "original_reason": self.original_reason,
            "action_required": self.action_required,
            "current_action": self.current_action,
            "evidence": [ev.to_dict() if hasattr(ev, "to_dict") else ev for ev in self.evidence],
            "original_value": copy.deepcopy(self.original_value),
            "operational_state": self.operational_state,
        }
        if self.missing_schema_keys:
            for k in self.missing_schema_keys:
                res.pop(k, None)
        return res

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterpretedField:
        missing_keys = []
        if isinstance(data, dict):
            REQUIRED_KEYS = {"name", "value", "status", "origin", "review", "evidence"}
            missing_keys = sorted(REQUIRED_KEYS - set(data.keys()))

        raw_evidence = data.get("evidence", []) if isinstance(data, dict) else []
        evidence = []
        if isinstance(raw_evidence, list):
            for ev in raw_evidence:
                if isinstance(ev, SourceReference):
                    evidence.append(ev)
                elif isinstance(ev, dict):
                    evidence.append(SourceReference.from_dict(ev))
                else:
                    # Do NOT silently drop scalar or malformed evidence!
                    evidence.append(MalformedEvidenceMarker(raw_value=ev))
        elif raw_evidence:
            evidence.append(MalformedEvidenceMarker(raw_value=raw_evidence))

        reason_val = str(data.get("reason", ""))
        orig_reason = data.get("original_reason")
        if orig_reason is not None:
            orig_reason = str(orig_reason)
        val = data.get("value")
        stat = str(data.get("status", STATUS_SUPPORTED))
        rev = str(data.get("review", REVIEW_PENDING))
        if _is_empty_value(val):
            if rev in (REVIEW_CONFIRMED, REVIEW_CORRECTED):
                rev = REVIEW_PENDING
            if stat == STATUS_SUPPORTED:
                stat = STATUS_MISSING
        return cls(
            name=str(data.get("name", "")),
            value=val,
            origin=str(data.get("origin", ORIGIN_EXTRACTED)),
            status=stat,
            review=rev,
            reason=reason_val,
            action_required="",
            evidence=evidence,
            original_value=data.get("original_value"),
            original_reason=orig_reason,
            current_action="",
            missing_schema_keys=missing_keys,
        )


@dataclass
class AnnexReference:
    """Relation between an in-session mention and candidate source annex sheets."""

    annex_number: str
    raw_mention: str
    source_pages: list[int] = field(default_factory=list)
    candidate_pages: list[int] = field(default_factory=list)
    status: str = STATUS_SUPPORTED
    review: str = REVIEW_PENDING
    reason: str = ""
    action_required: str = ""
    evidence: list[SourceReference] = field(default_factory=list)
    confirmed_page: int | None = None  # None until explicitly confirmed by teacher
    origin: str = ORIGIN_EXTRACTED
    original_reason: str | None = None
    current_action: str = ""
    reference_id: str = ""
    legacy_reference_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        state, act = derive_annex_operational_state(self)
        self.current_action = act
        self.action_required = act

    @property
    def operational_state(self) -> str:
        state, _ = derive_annex_operational_state(self)
        return state

    def to_dict(self) -> dict[str, Any]:
        res = {
            "reference_id": self.reference_id,
            "annex_number": self.annex_number,
            "raw_mention": self.raw_mention,
            "source_pages": list(self.source_pages),
            "candidate_pages": list(self.candidate_pages),
            "status": self.status,
            "review": self.review,
            "reason": self.reason,
            "original_reason": self.original_reason,
            "action_required": self.action_required,
            "current_action": self.current_action,
            "evidence": [ev.to_dict() if hasattr(ev, "to_dict") else ev for ev in self.evidence],
            "confirmed_page": self.confirmed_page,
            "origin": self.origin,
            "operational_state": self.operational_state,
        }
        if self.legacy_reference_ids:
            res["legacy_reference_ids"] = list(self.legacy_reference_ids)
        return res

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnnexReference:
        raw_evidence = data.get("evidence", []) if isinstance(data, dict) else []
        evidence = []
        if isinstance(raw_evidence, list):
            for ev in raw_evidence:
                if isinstance(ev, SourceReference):
                    evidence.append(ev)
                elif isinstance(ev, dict):
                    evidence.append(SourceReference.from_dict(ev))
                else:
                    evidence.append(MalformedEvidenceMarker(raw_value=ev))
        elif raw_evidence:
            evidence.append(MalformedEvidenceMarker(raw_value=raw_evidence))

        reason_val = str(data.get("reason", ""))
        orig_reason = data.get("original_reason")
        if orig_reason is not None:
            orig_reason = str(orig_reason)
        raw_leg = data.get("legacy_reference_ids", []) or []
        legacy_ids = [str(x) for x in raw_leg if isinstance(x, (str, int))]
        return cls(
            annex_number=str(data.get("annex_number", "")),
            raw_mention=str(data.get("raw_mention", "")),
            source_pages=[int(p) for p in data.get("source_pages", [])],
            candidate_pages=[int(p) for p in data.get("candidate_pages", [])],
            status=str(data.get("status", STATUS_SUPPORTED)),
            review=str(data.get("review", REVIEW_PENDING)),
            reason=reason_val,
            action_required="",
            evidence=evidence,
            confirmed_page=(
                int(data["confirmed_page"])
                if data.get("confirmed_page") is not None
                else None
            ),
            origin=str(data.get("origin", ORIGIN_EXTRACTED)),
            original_reason=orig_reason,
            current_action="",
            reference_id=str(data.get("reference_id", "")),
            legacy_reference_ids=legacy_ids,
        )


CANONICAL_REF_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _ensure_session_annex_ids(session_id: str, annexes: list[AnnexReference]) -> None:
    """Ensure every AnnexReference in a session has a unique, deterministic, HTML-safe reference_id.
    Validates canonical format (^[a-zA-Z0-9_-]+$). Regenerates deterministic, page-independent
    IDs (ref_a{clean_num}_{idx}) when empty, invalid, or duplicate, ensuring round-trip stability
    and annex continuity across session page moves.
    Tracks legacy/aliased reference IDs in `legacy_reference_ids` for complete provenance.
    """
    seen: set[str] = set()
    counts: dict[str, int] = {}
    for r in annexes:
        eid = getattr(r, "reference_id", None)
        if isinstance(eid, str) and eid:
            counts[eid] = counts.get(eid, 0) + 1

    for idx, ref in enumerate(annexes, start=1):
        if not hasattr(ref, "annex_number"):
            continue
        clean_num = re.sub(r"[^a-zA-Z0-9_-]", "_", str(ref.annex_number or "ref")).strip("_") or "ref"
        existing = getattr(ref, "reference_id", None)
        if not hasattr(ref, "legacy_reference_ids") or ref.legacy_reference_ids is None:
            ref.legacy_reference_ids = []

        is_canonical = isinstance(existing, str) and bool(existing) and bool(CANONICAL_REF_ID_PATTERN.match(existing))
        is_duplicate = is_canonical and counts.get(existing, 0) > 1

        if is_duplicate and existing not in ref.legacy_reference_ids:
            ref.legacy_reference_ids.append(existing)

        if is_canonical and existing not in seen:
            ref.reference_id = existing
            seen.add(existing)
        else:
            candidate = f"ref_a{clean_num}_{idx}"
            cur_idx = idx
            while candidate in seen:
                cur_idx += 1
                candidate = f"ref_a{clean_num}_{cur_idx}"
            if existing and isinstance(existing, str) and existing not in ref.legacy_reference_ids:
                ref.legacy_reference_ids.append(existing)
            ref.reference_id = candidate
            seen.add(candidate)


def _find_single_annex_ref(matching_session: "SessionPlan | None", annex_key: str) -> "AnnexReference":
    """Find exactly one AnnexReference in matching_session matching annex_key.
    Matches against both reference_id and legacy annex_number.
    Raises ValueError if 0 matches or if ambiguous (>1 match).
    """
    if matching_session is None:
        raise ValueError(f"No hay sesión seleccionada para buscar el Anexo '{annex_key}'.")
    key_str = str(annex_key)
    matches_by_id = [r for r in matching_session.annex_references if getattr(r, "reference_id", None) == key_str]
    matches_by_num = [r for r in matching_session.annex_references if str(r.annex_number) == key_str]

    matched_dict: dict[int, AnnexReference] = {}
    for r in (matches_by_id + matches_by_num):
        matched_dict[id(r)] = r
    all_matched = list(matched_dict.values())

    if len(all_matched) == 0:
        raise ValueError(f"El Anexo '{annex_key}' no existe en la sesión {matching_session.session_id}.")
    if len(all_matched) > 1:
        raise ValueError(
            f"Referencia de anexo ambigua para '{annex_key}'; colisiona con múltiples anexos en la sesión {matching_session.session_id}."
        )
    return all_matched[0]



@dataclass
class SessionActivity:
    """An identifiable activity within a session/class.

    Represents activities explicitly indicated by the source document.
    A class may have 1-2 complex activities or 5+ brief ones —
    no assumptions about cardinality, duration, or weekly structure.
    """

    activity_id: str
    title: str = ""
    description: str = ""
    order: int = 0
    annex_ids: list[str] = field(default_factory=list)
    evidence: list[SourceReference] = field(default_factory=list)
    annex_evidence: dict[str, list[SourceReference]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "title": self.title,
            "description": self.description,
            "order": self.order,
            "annex_ids": list(self.annex_ids),
            "evidence": [e.to_dict() if hasattr(e, "to_dict") else e for e in self.evidence],
            "annex_evidence": {
                k: [e.to_dict() if hasattr(e, "to_dict") else e for e in v]
                for k, v in self.annex_evidence.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionActivity":
        raw_ev = data.get("evidence", []) or []
        ev_list = [
            e if isinstance(e, SourceReference) else SourceReference.from_dict(e)
            for e in raw_ev if isinstance(e, (dict, SourceReference))
        ]
        raw_aev = data.get("annex_evidence", {}) or {}
        aev_dict = {}
        if isinstance(raw_aev, dict):
            for k, v in raw_aev.items():
                aev_dict[k] = [
                    e if isinstance(e, SourceReference) else SourceReference.from_dict(e)
                    for e in (v or []) if isinstance(e, (dict, SourceReference))
                ]
        return cls(
            activity_id=str(data.get("activity_id", "")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            order=int(data.get("order", 0)),
            annex_ids=list(data.get("annex_ids", [])),
            evidence=ev_list,
            annex_evidence=aev_dict,
        )


@dataclass
class SessionPlan:
    """Interpreted session plan with verified moments and annex relationships."""

    session_id: str
    session_number: int
    title: str
    project_title: str = ""
    day_of_week: str = ""
    pages: list[int] = field(default_factory=list)
    continues_on: list[int] = field(default_factory=list)
    layout_fidelity: str = "linearized_heuristics"
    layout_notes: str = (
        "Extracción lineal vía pypdf con reconstrucción heurística de momentos pedagógicos. "
        "No garantiza preservación de columnas ni tablas complejas."
    )
    fields: dict[str, InterpretedField] = field(default_factory=dict)
    annex_references: list[AnnexReference] = field(default_factory=list)
    activities: list[SessionActivity] = field(default_factory=list)
    status: str = STATUS_SUPPORTED
    review: str = REVIEW_PENDING
    # Optional additive metadata. Preserve malformed inputs verbatim so the
    # source verifier can reject them, rather than coercing bool/strings to ints.
    project_context: dict[str, Any] | None = None
    header_anchor: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        _ensure_session_annex_ids(self.session_id, self.annex_references)
        return {
            "session_id": self.session_id,
            "session_number": self.session_number,
            "title": self.title,
            "project_title": self.project_title,
            "project_context": copy.deepcopy(self.project_context),
            "header_anchor": copy.deepcopy(self.header_anchor),
            "day_of_week": self.day_of_week,
            "pages": list(self.pages),
            "continues_on": list(self.continues_on),
            "layout_fidelity": self.layout_fidelity,
            "layout_notes": self.layout_notes,
            "fields": {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in self.fields.items()},
            "annex_references": [ref.to_dict() if hasattr(ref, "to_dict") else ref for ref in self.annex_references],
            "activities": [a.to_dict() if hasattr(a, "to_dict") else a for a in self.activities],
            "status": self.status,
            "review": self.review,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionPlan:
        s_num = int(data.get("session_number", 1))
        p_list = [int(p) for p in data.get("pages", [])]
        first_page = p_list[0] if p_list else 1
        session_id = str(data.get("session_id") or f"p{first_page}_s{s_num}")
        raw_fields = data.get("fields", {}) or {}
        fields = {
            k: v if isinstance(v, InterpretedField) else (InterpretedField.from_dict(v) if isinstance(v, dict) else v)
            for k, v in raw_fields.items()
        } if isinstance(raw_fields, dict) else raw_fields
        raw_annexes = data.get("annex_references", []) or []
        annex_references = [
            a if isinstance(a, AnnexReference) else (AnnexReference.from_dict(a) if isinstance(a, dict) else a)
            for a in raw_annexes
        ] if isinstance(raw_annexes, list) else raw_annexes
        if isinstance(annex_references, list):
            _ensure_session_annex_ids(session_id, annex_references)
        raw_activities = data.get("activities", []) or []
        activities = [
            act if isinstance(act, SessionActivity) else (SessionActivity.from_dict(act) if isinstance(act, dict) else act)
            for act in raw_activities
        ] if isinstance(raw_activities, list) else []
        return cls(
            session_id=session_id,
            session_number=s_num,
            title=str(data.get("title", "")),
            project_title=str(data.get("project_title", "")),
            project_context=copy.deepcopy(data.get("project_context")),
            header_anchor=copy.deepcopy(data.get("header_anchor")),
            day_of_week=str(data.get("day_of_week", "")),
            pages=p_list,
            continues_on=[int(p) for p in data.get("continues_on", [])],
            layout_fidelity=str(data.get("layout_fidelity", "linearized_heuristics")),
            layout_notes=str(
                data.get(
                    "layout_notes",
                    "Extracción lineal vía pypdf con reconstrucción heurística de momentos pedagógicos.",
                )
            ),
            fields=fields,
            annex_references=annex_references,
            activities=activities,
            status=str(data.get("status", STATUS_SUPPORTED)),
            review=str(data.get("review", REVIEW_PENDING)),
        )


@dataclass
class ImportDossier:
    """Versioned staging dossier containing interpreted planning and audit trail."""

    source_sha256: str
    source_name: str
    page_count: int
    version: int = 1
    status: str = "active"  # "active" | "invalidated_source_tampered"
    selection: dict[str, Any] = field(default_factory=dict)
    general_fields: dict[str, InterpretedField] = field(default_factory=dict)
    sessions: list[SessionPlan] = field(default_factory=list)
    annex_candidates: list[dict[str, Any]] = field(default_factory=list)
    page_warnings: dict[int, str] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    verification_report: dict[str, Any] | None = None
    created_at: str = field(default_factory=_utc_iso_now)
    updated_at: str = field(default_factory=_utc_iso_now)

    def to_dict(self) -> dict[str, Any]:
        res = {
            "source_sha256": self.source_sha256,
            "source_name": self.source_name,
            "page_count": self.page_count,
            "version": self.version,
            "status": self.status,
            "selection": copy.deepcopy(self.selection),
            "general_fields": {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in self.general_fields.items()} if isinstance(self.general_fields, dict) else self.general_fields,
            "sessions": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.sessions] if isinstance(self.sessions, list) else self.sessions,
            "annex_candidates": copy.deepcopy(self.annex_candidates),
            "page_warnings": {str(k): v for k, v in self.page_warnings.items()} if isinstance(self.page_warnings, dict) else {},
            "history": [
                h.to_dict() if isinstance(h, HistoryEntry)
                else (HistoryEntry.from_dict(h).to_dict() if isinstance(h, dict) else h)
                for h in self.history
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.verification_report:
            res["verification_report"] = copy.deepcopy(self.verification_report)
        else:
            res["verification_report"] = None
        return res

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImportDossier:
        raw_general = data.get("general_fields", {}) or {}
        general_fields = {
            k: v if isinstance(v, InterpretedField) else (InterpretedField.from_dict(v) if isinstance(v, dict) else v)
            for k, v in raw_general.items()
        } if isinstance(raw_general, dict) else raw_general
        raw_sessions = data.get("sessions", []) or []
        sessions = [
            s if isinstance(s, SessionPlan) else (SessionPlan.from_dict(s) if isinstance(s, dict) else s)
            for s in raw_sessions
        ] if isinstance(raw_sessions, list) else raw_sessions
        raw_warnings = data.get("page_warnings", {}) or {}
        page_warnings = {int(k): str(v) for k, v in raw_warnings.items()} if isinstance(raw_warnings, dict) else {}
        raw_history_data = data.get("history")
        clean_history = []
        if isinstance(raw_history_data, list):
            for h in raw_history_data:
                entry = HistoryEntry.from_dict(h)
                clean_history.append(entry.to_dict())

        raw_report = data.get("verification_report")
        verification_report = copy.deepcopy(raw_report) if isinstance(raw_report, dict) else None

        return cls(
            source_sha256=str(data.get("source_sha256", "")),
            source_name=str(data.get("source_name", "")),
            page_count=int(data.get("page_count", 0)),
            version=int(data.get("version", 1)),
            status=str(data.get("status", "active")),
            selection=dict(data.get("selection", {}) or {}),
            general_fields=general_fields,
            sessions=sessions,
            annex_candidates=list(data.get("annex_candidates", []) or []),
            page_warnings=page_warnings,
            history=clean_history,
            verification_report=verification_report,
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )

    def get_session(self, identifier: str | int) -> SessionPlan | None:
        """Find session by session_id or session_number."""
        ident_str = str(identifier)
        for s in self.sessions:
            if s.session_id == ident_str:
                return s
        if ident_str.isdigit():
            s_num = int(ident_str)
            for s in self.sessions:
                if s.session_number == s_num:
                    return s
        return None

    def get_session_by_number(self, num: int) -> SessionPlan | None:
        """Find first session matching session_number."""
        for s in self.sessions:
            if s.session_number == num:
                return s
        return None


# ==============================================================================
# AulaLista V0 Fase B - F7: Cola Operativa de Revisión por Prioridades
# ==============================================================================

PRIORITY_REQUIRES_RESOLUTION = "requires_resolution"  # Rojo / Red
PRIORITY_PENDING_REVIEW = "pending_review"            # Amarillo / Yellow
PRIORITY_POSTPONED = "postponed"                      # Aplazado / Azul o Neutral
PRIORITY_NOT_SPECIFIED = "not_specified"              # Neutral / Gris
PRIORITY_REVIEWED = "reviewed"                        # Verde

PRIORITY_ORDER: dict[str, int] = {
    PRIORITY_REQUIRES_RESOLUTION: 0,
    PRIORITY_PENDING_REVIEW: 1,
    PRIORITY_POSTPONED: 2,
    PRIORITY_NOT_SPECIFIED: 3,
    PRIORITY_REVIEWED: 4,
}

PRIORITY_HUMAN_LABELS: dict[str, str] = {
    PRIORITY_REQUIRES_RESOLUTION: "Requiere resolver",
    PRIORITY_PENDING_REVIEW: "Por revisar",
    PRIORITY_POSTPONED: "Aplazado",
    PRIORITY_NOT_SPECIFIED: "No especificado",
    PRIORITY_REVIEWED: "Revisado",
}


REQUIRED_GENERAL_FIELDS = {"proyecto", "campos_formativos", "proposito", "finalidad"}
OPTIONAL_GENERAL_FIELDS = {"metodologia", "escenario_proyecto", "grado"}

REQUIRED_SESSION_FIELDS = {"inicio", "desarrollo", "cierre"}
OPTIONAL_SESSION_FIELDS = {"materiales", "evaluacion", "contexto_ejecucion"}

GENERAL_FIELD_DISPLAY_ORDER = [
    "proyecto",
    "campos_formativos",
    "proposito",
    "finalidad",
    "metodologia",
    "escenario_proyecto",
    "grado",
]

SESSION_FIELD_DISPLAY_ORDER = [
    "inicio",
    "desarrollo",
    "cierre",
    "materiales",
    "evaluacion",
    "contexto_ejecucion",
]

HUMAN_FIELD_NAMES: dict[str, str] = {
    "proyecto": "Nombre del Proyecto",
    "campos_formativos": "Campos Formativos",
    "proposito": "Propósito para el Alumno",
    "finalidad": "Finalidad e Intención Docente",
    "metodologia": "Metodología de Proyecto",
    "escenario_proyecto": "Escenario del Proyecto",
    "grado": "Grado Escolar",
    "duracion_proyecto": "Duración Sugerida del Proyecto",
    "inicio": "Momento 1: Inicio",
    "desarrollo": "Momento 2: Desarrollo",
    "cierre": "Momento 3: Cierre",
    "materiales": "Materiales y Recursos",
    "evaluacion": "Evaluación Formativa",
    "contexto_ejecucion": "Lugar y Contexto de Ejecución",
}

INPUT_TYPE_MAP: dict[str, str] = {
    "proyecto": "text",
    "campos_formativos": "checkboxes",
    "proposito": "textarea",
    "finalidad": "textarea",
    "metodologia": "text",
    "escenario_proyecto": "text",
    "grado": "text",
    "duracion_proyecto": "text",
    "inicio": "textarea",
    "desarrollo": "textarea",
    "cierre": "textarea",
    "materiales": "textarea",
    "evaluacion": "textarea",
    "contexto_ejecucion": "text",
}


def _generate_opaque_item_id(
    scope: str,
    session_id: str | None,
    field_or_ref: str,
    occurrence: int = 0,
) -> str:
    """Generate an opaque, HTML-safe, unique and deterministic item ID (128-bit digest)."""
    token = f"{scope}|{session_id or ''}|{field_or_ref}|{occurrence}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
    return f"op_{digest}"


def _generate_canonical_target_id(
    target_type: str,
    session_id: str | None,
    field_or_ref: str,
) -> str:
    """Generate an opaque, canonical target_id from unambiguous structured serialization (JSON array)."""
    payload = [target_type, session_id or "", field_or_ref]
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:32]
    return f"tgt_{digest}"


@dataclass
class OperationalItem:
    """A single actionable item in the operational review queue."""

    item_id: str
    stable_key: str
    scope: str  # "general" | "session" | "annex"
    session_id: str | None
    session_number: int | None
    project_title: str
    field_name: str
    reference_id: str | None
    human_label: str
    priority_state: str  # requires_resolution | pending_review | not_specified | reviewed
    problem_summary: str
    blocks_action: str
    requiredness: str  # "conversion" | "annex_use" | "optional"
    is_required: bool
    current_value: Any
    original_value: Any
    operational_state: str
    current_action: str
    original_reason: str
    target_id: str = ""
    required_for: list[str] = field(default_factory=list)
    blocking_codes: list[str] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    page_number: int | None = None
    annex_number: str = ""
    raw_mention: str = ""
    candidate_pages: list[int] = field(default_factory=list)
    confirmed_page: int | None = None
    input_type: str = "text"

    @property
    def priority_label(self) -> str:
        return PRIORITY_HUMAN_LABELS.get(self.priority_state, self.priority_state)

    @property
    def priority_icon(self) -> str:
        if self.priority_state == PRIORITY_REQUIRES_RESOLUTION:
            return "🔴"
        elif self.priority_state == PRIORITY_PENDING_REVIEW:
            return "🟡"
        elif self.priority_state == PRIORITY_POSTPONED:
            return "⏸️"
        elif self.priority_state == PRIORITY_REVIEWED:
            return "✅"
        return "⚪"


@dataclass
class OperationalQueue:
    """Collection of operational items with consistent counts and scoped filtering."""

    items: list[OperationalItem]
    requires_resolution_count: int
    pending_review_count: int
    reviewed_count: int
    not_specified_count: int
    actionable_count: int
    total_count: int
    scope: str
    scope_label: str
    session_filter: str | None
    all_items_count: int
    is_completed: bool
    first_pending_key: str | None
    postponed_count: int = 0

    @property
    def items_requires_resolution(self) -> list[OperationalItem]:
        return [it for it in self.items if it.priority_state == PRIORITY_REQUIRES_RESOLUTION]

    @property
    def items_pending_review(self) -> list[OperationalItem]:
        return [it for it in self.items if it.priority_state == PRIORITY_PENDING_REVIEW]

    @property
    def items_postponed(self) -> list[OperationalItem]:
        return [it for it in self.items if it.priority_state == PRIORITY_POSTPONED]

    @property
    def items_not_specified(self) -> list[OperationalItem]:
        return [it for it in self.items if it.priority_state == PRIORITY_NOT_SPECIFIED]

    @property
    def items_reviewed(self) -> list[OperationalItem]:
        return [it for it in self.items if it.priority_state == PRIORITY_REVIEWED]


    @property
    def progress_percent(self) -> int:
        if self.actionable_count == 0:
            return 100
        return int((self.reviewed_count / self.actionable_count) * 100)

    @property
    def total_items(self) -> int:
        return self.total_count


def _item_sort_key(item: OperationalItem) -> tuple:
    # Strict priority: conflicts/blockers -> missing -> ambiguous/proposed -> resto
    if item.priority_state == PRIORITY_REQUIRES_RESOLUTION:
        prob_lower = (item.problem_summary or "").lower()
        if (
            "CONFLICT_RESOLUTION" in item.blocking_codes
            or "conflicto" in prob_lower
            or "contradictoria" in prob_lower
            or item.operational_state == "conflict"
        ):
            p_rank = 0  # conflicts / hard blockers
        else:
            p_rank = 1  # missing required
    elif item.priority_state == PRIORITY_PENDING_REVIEW:
        prob_lower = (item.problem_summary or "").lower()
        if "ambigua" in prob_lower or "ambiguo" in prob_lower or item.operational_state == "ambiguous":
            p_rank = 2  # ambiguous
        elif "propuesta" in prob_lower or "inferida" in prob_lower or item.operational_state == "proposed":
            p_rank = 3  # proposed
        else:
            p_rank = 4  # other pending review
    elif item.priority_state == PRIORITY_NOT_SPECIFIED:
        p_rank = 5
    elif item.priority_state == PRIORITY_REVIEWED:
        p_rank = 6
    else:
        p_rank = 99

    s_rank = 0 if item.scope == "general" else (1 if item.scope == "session" else 2)
    sess_num = item.session_number if item.session_number is not None else -1
    if item.scope == "general":
        try:
            f_rank = GENERAL_FIELD_DISPLAY_ORDER.index(item.field_name)
        except ValueError:
            f_rank = 50
    elif item.scope == "session":
        try:
            f_rank = SESSION_FIELD_DISPLAY_ORDER.index(item.field_name)
        except ValueError:
            f_rank = 50
    else:
        try:
            f_rank = int(item.annex_number)
        except ValueError:
            f_rank = 50
    return (p_rank, sess_num, s_rank, f_rank, item.item_id)


def _build_field_operational_item(
    field: InterpretedField,
    scope: str,
    session_id: str | None = None,
    session_number: int | None = None,
    project_title: str = "",
    occurrence: int = 0,
) -> OperationalItem:
    f_name = field.name
    is_required = (
        f_name in REQUIRED_GENERAL_FIELDS if scope == "general" else f_name in REQUIRED_SESSION_FIELDS
    )
    requiredness = "conversion" if is_required else "optional"
    human_label = HUMAN_FIELD_NAMES.get(f_name, f_name.replace("_", " ").capitalize())
    input_type = INPUT_TYPE_MAP.get(f_name, "text")
    item_id = _generate_opaque_item_id(scope, session_id, f_name, occurrence)
    stable_key = item_id
    if scope == "general":
        target_id = _generate_canonical_target_id("general", "", f_name)
    else:
        target_id = _generate_canonical_target_id("session", session_id, f_name)

    op_state, curr_act = derive_field_operational_state(field)

    # B5 Precedence:
    # 1. Conflicting is ALWAYS requires_resolution (rojo), even if review is confirmed/corrected!
    if field.status == STATUS_CONFLICTING:
        priority_state = PRIORITY_REQUIRES_RESOLUTION
        problem_summary = (
            "Conflicto en la fuente: la información detectada es contradictoria o colisiona con otra sección."
        )
        blocks_action = (
            "Bloquea fundamentación y conversión de la planeación."
            if scope == "general"
            else "Bloquea estructuración pedagógica y conversión de la sesión."
        )
    # 2. Empty or missing is NEVER reviewed!
    elif _is_empty_value(field.value) or field.status == STATUS_MISSING:
        if is_required:
            priority_state = PRIORITY_REQUIRES_RESOLUTION
            problem_summary = "Campo requerido ausente en el documento original."
            blocks_action = (
                "Bloquea fundamentación y conversión de la planeación."
                if scope == "general"
                else "Bloquea estructuración pedagógica y conversión de la sesión."
            )
        else:
            priority_state = PRIORITY_NOT_SPECIFIED
            problem_summary = "No especificado en la planeación (campo complementario opcional)."
            blocks_action = ""
    # 3. Confirmed / Corrected is ONLY reviewed if non-empty and not conflicting
    elif field.review in (REVIEW_CONFIRMED, REVIEW_CORRECTED):
        priority_state = PRIORITY_REVIEWED
        problem_summary = (
            "Dato confirmado por el docente."
            if field.review == REVIEW_CONFIRMED
            else "Dato corregido y confirmado por el docente."
        )
        blocks_action = ""
    # 3.5. Postponed review
    elif field.review == "postponed":
        priority_state = PRIORITY_POSTPONED
        problem_summary = "Revisión aplazada por el docente."
        blocks_action = ""
    # 4. Pending review
    else:
        priority_state = PRIORITY_PENDING_REVIEW

        if field.status == STATUS_AMBIGUOUS:
            problem_summary = "Interpretación ambigua en la fuente: requiere verificación o corrección del texto."
        elif field.origin == ORIGIN_PROPOSED:
            problem_summary = "Propuesta inferida por el asistente: requiere confirmación docente."
        else:
            problem_summary = "Dato extraído del PDF; requiere verificación y confirmación del docente."
        blocks_action = (
            "Requiere confirmación docente antes de aprobar la planeación."
            if is_required
            else "Pendiente de revisión docente (opcional)."
        )

    required_for = (
        ["conversión", "fundamentación"]
        if (scope == "general" and is_required)
        else (["conversión", "estructuración_pedagógica"] if is_required else [])
    )
    blocking_codes = []
    if priority_state == PRIORITY_REQUIRES_RESOLUTION:
        blocking_codes.append("BLOCKS_CONVERSION")
        if field.status == STATUS_CONFLICTING:
            blocking_codes.append("CONFLICT_RESOLUTION")
        if _is_empty_value(field.value) or field.status == STATUS_MISSING:
            blocking_codes.append("MISSING_REQUIRED")
    elif priority_state == PRIORITY_PENDING_REVIEW:
        blocking_codes.append("PENDING_TEACHER_CONFIRMATION")

    source_refs = [ref.to_dict() for ref in field.evidence]
    page_number = field.evidence[0].page_number if field.evidence else None

    return OperationalItem(
        item_id=item_id,
        stable_key=stable_key,
        scope=scope,
        session_id=session_id,
        session_number=session_number,
        project_title=project_title,
        field_name=f_name,
        reference_id=None,
        human_label=human_label,
        priority_state=priority_state,
        problem_summary=problem_summary,
        blocks_action=blocks_action,
        requiredness=requiredness,
        is_required=is_required,
        current_value=copy.deepcopy(field.value),
        original_value=copy.deepcopy(field.original_value if field.original_value is not None else field.value),
        operational_state=op_state,
        current_action=curr_act,
        original_reason=field.original_reason or field.reason or "",
        target_id=target_id,
        required_for=required_for,
        blocking_codes=blocking_codes,
        source_refs=source_refs,
        page_number=page_number,
        input_type=input_type,
    )


def _build_annex_operational_item(
    ref: AnnexReference,
    session: SessionPlan,
    occurrence: int = 0,
    page_count: int = 1,
    source_sha: str = "",
) -> OperationalItem:
    ref_id = ref.reference_id or f"annex_{ref.annex_number}"
    item_id = _generate_opaque_item_id("annex", session.session_id, ref_id, occurrence)
    stable_key = item_id
    target_id = _generate_canonical_target_id("annex", session.session_id, ref_id)
    human_label = f"Anexo {ref.annex_number}" + (f": {ref.raw_mention[:40]}" if ref.raw_mention else "")
    op_state, curr_act = derive_annex_operational_state(ref, source_sha=source_sha, page_count=page_count)

    # B5: Annex is ONLY reviewed if derive_annex_operational_state returns resolved
    if ref.review == "postponed":
        priority_state = PRIORITY_POSTPONED
        problem_summary = "Revisión de anexo aplazada por el docente."
        blocks_action = ""
    elif op_state == "resolved":
        priority_state = PRIORITY_REVIEWED
        p_num = ref.confirmed_page
        problem_summary = f"Lámina confirmada en la página física {p_num} del PDF."
        blocks_action = ""
    elif op_state == "requires_resolution":
        priority_state = PRIORITY_REQUIRES_RESOLUTION
        problem_summary = curr_act
        blocks_action = "Bloquea vinculación y uso del anexo en la sesión."
    else:
        priority_state = PRIORITY_PENDING_REVIEW
        problem_summary = curr_act
        blocks_action = "Requiere confirmación docente de la página física del anexo."


    required_for = ["conversión", "asociación_materiales"]
    blocking_codes = []
    if priority_state == PRIORITY_REQUIRES_RESOLUTION:
        blocking_codes.extend(["BLOCKS_CONVERSION", "ANNEX_UNLINKED"])
    elif priority_state == PRIORITY_PENDING_REVIEW:
        blocking_codes.append("PENDING_TEACHER_CONFIRMATION")

    source_refs = [ev.to_dict() for ev in ref.evidence if getattr(ev, "page_number", None) == ref.confirmed_page]
    if not source_refs:
        source_refs = [{"page_number": p, "document_sha256": source_sha} for p in (ref.source_pages or ref.candidate_pages)]
    primary_page = ref.confirmed_page if ref.confirmed_page else (ref.source_pages[0] if ref.source_pages else (session.pages[0] if session.pages else None))

    return OperationalItem(
        item_id=item_id,
        stable_key=stable_key,
        scope="annex",
        session_id=session.session_id,
        session_number=session.session_number,
        project_title=session.project_title,
        field_name=ref_id,
        reference_id=ref.reference_id,
        human_label=human_label,
        priority_state=priority_state,
        problem_summary=problem_summary,
        blocks_action=blocks_action,
        requiredness="annex_use",
        is_required=True,
        current_value=ref.confirmed_page,
        original_value=ref.candidate_pages[0] if ref.candidate_pages else None,
        operational_state=op_state,
        current_action=curr_act,
        original_reason=ref.raw_mention or "",
        target_id=target_id,
        required_for=required_for,
        blocking_codes=blocking_codes,
        source_refs=source_refs,
        page_number=primary_page,
        annex_number=ref.annex_number,
        raw_mention=ref.raw_mention,
        candidate_pages=list(ref.candidate_pages),
        confirmed_page=ref.confirmed_page,
        input_type="annex",
    )


def derive_operational_queue(
    dossier: ImportDossier,
    session_filter: str | None = None,
) -> OperationalQueue:
    """Pure backend deriver of operational review queue from an ImportDossier.
    Centralizes all operational items across general fields, session fields, and annexes.
    Produces deterministic priority ordering and exact counts from the identical collection.
    """
    all_items: list[OperationalItem] = []
    seen_item_ids: set[str] = set()
    seen_target_ids: set[str] = set()

    # 0. Fail-closed validation of dossier identity across the ENTIRE dossier (all scopes)
    seen_session_ids: set[str] = set()
    for s in dossier.sessions:
        if s.session_id in seen_session_ids:
            raise SelectionError(
                f"Conflicto de identidad: existen múltiples sesiones persistidas con el mismo session_id '{s.session_id}'. "
                "Requiere reextracción segura o corrección de datos."
            )
        seen_session_ids.add(s.session_id)

        # Check target uniqueness in session fields
        seen_session_fields: set[str] = set()
        for f_name in s.fields.keys():
            if f_name in seen_session_fields:
                raise SelectionError(
                    f"Conflicto de identidad: campo duplicado '{f_name}' en sesión '{s.session_id}'."
                )
            seen_session_fields.add(f_name)

        # Combined namespace validation per session across all AnnexReferences:
        # reference_id, annex_number, and legacy_reference_ids
        token_to_ref_idx: dict[str, int] = {}
        for ref_idx, annex_ref in enumerate(s.annex_references):
            if not isinstance(annex_ref, AnnexReference) and not hasattr(annex_ref, "annex_number"):
                raise SelectionError(
                    f"Elemento de anexo malformado en sesión '{s.session_id}' índice {ref_idx}: {annex_ref!r}"
                )
            ref_tokens: set[str] = set()
            if annex_ref.reference_id:
                tok_ref = str(annex_ref.reference_id).strip()
                if tok_ref:
                    ref_tokens.add(tok_ref)
            if annex_ref.annex_number is not None:
                tok_num = str(annex_ref.annex_number).strip()
                if tok_num:
                    ref_tokens.add(tok_num)
            for leg_id in getattr(annex_ref, "legacy_reference_ids", []) or []:
                if leg_id:
                    tok_leg = str(leg_id).strip()
                    if tok_leg:
                        ref_tokens.add(tok_leg)

            for tok in ref_tokens:
                if tok in token_to_ref_idx and token_to_ref_idx[tok] != ref_idx:
                    raise SelectionError(
                        f"Conflicto de identidad: token de anexo ambiguo o duplicado '{tok}' "
                        f"asociado a múltiples referencias en la sesión '{s.session_id}'. "
                        "Requiere reextracción o revisión."
                    )
                token_to_ref_idx[tok] = ref_idx

    proj_title = ""
    if "proyecto" in dossier.general_fields:
        p_val = dossier.general_fields["proyecto"].value
        if isinstance(p_val, str):
            proj_title = p_val.strip()

    # 1. General fields (once per document / project)
    for g_idx, f_name in enumerate(GENERAL_FIELD_DISPLAY_ORDER):
        if f_name in dossier.general_fields:
            field_obj = dossier.general_fields[f_name]
        else:
            field_obj = InterpretedField(
                name=f_name,
                value="",
                origin=ORIGIN_EXTRACTED,
                status=STATUS_MISSING,
                review=REVIEW_PENDING,
            )
        it = _build_field_operational_item(
            field=field_obj,
            scope="general",
            session_id=None,
            session_number=None,
            project_title=proj_title,
            occurrence=g_idx,
        )
        if it.target_id in seen_target_ids:
            raise SelectionError(
                f"Conflicto de identidad: colisión de target_id duplicado '{it.target_id}' en cola operativa. "
                "Requiere revisión o corrección de datos."
            )
        seen_target_ids.add(it.target_id)
        if it.item_id in seen_item_ids:
            raise SelectionError(
                f"Conflicto de identidad: colisión de item_id duplicado '{it.item_id}' en cola operativa."
            )
        seen_item_ids.add(it.item_id)
        all_items.append(it)

    # 2. Sessions (fields and annexes)
    for s_idx, session in enumerate(dossier.sessions):
        s_proj = session.project_title  # Missing local context must not inherit the global title.
        for f_idx, f_name in enumerate(SESSION_FIELD_DISPLAY_ORDER):
            if f_name in session.fields:
                s_field = session.fields[f_name]
            else:
                s_field = InterpretedField(
                    name=f_name,
                    value="",
                    origin=ORIGIN_EXTRACTED,
                    status=STATUS_MISSING,
                    review=REVIEW_PENDING,
                )
            it = _build_field_operational_item(
                field=s_field,
                scope="session",
                session_id=session.session_id,
                session_number=session.session_number,
                project_title=s_proj,
                occurrence=(s_idx * 100) + f_idx,
            )
            if it.target_id in seen_target_ids:
                raise SelectionError(
                    f"Conflicto de identidad: colisión de target_id duplicado '{it.target_id}' en cola operativa. "
                    "Requiere revisión o corrección de datos."
                )
            seen_target_ids.add(it.target_id)
            if it.item_id in seen_item_ids:
                raise SelectionError(
                    f"Conflicto de identidad: colisión de item_id duplicado '{it.item_id}' en cola operativa."
                )
            seen_item_ids.add(it.item_id)
            all_items.append(it)

        for a_idx, annex_ref in enumerate(session.annex_references):
            if not isinstance(annex_ref, AnnexReference) and not hasattr(annex_ref, "annex_number"):
                raise SelectionError(
                    f"Elemento de anexo malformado en sesión '{session.session_id}' índice {a_idx}: {annex_ref!r}"
                )
            it = _build_annex_operational_item(
                ref=annex_ref,
                session=session,
                occurrence=(s_idx * 1000) + a_idx,
                page_count=dossier.page_count,
                source_sha=dossier.source_sha256,
            )
            if it.target_id in seen_target_ids:
                raise SelectionError(
                    f"Conflicto de identidad: colisión de target_id duplicado '{it.target_id}' en cola operativa. "
                    "Requiere revisión o corrección de datos."
                )
            seen_target_ids.add(it.target_id)
            if it.item_id in seen_item_ids:
                raise SelectionError(
                    f"Conflicto de identidad: colisión de item_id duplicado '{it.item_id}' en cola operativa."
                )
            seen_item_ids.add(it.item_id)
            all_items.append(it)

    scope_str = "document"
    scope_label_str = f"Documento completo ({len(dossier.sessions)} sesiones)"
    effective_session_filter: str | None = None
    filtered_items = all_items

    if session_filter and session_filter not in ("all", "document"):
        if session_filter == "general":
            filtered_items = [it for it in all_items if it.scope == "general"]
            scope_str = "general"
            scope_label_str = "Datos generales del documento"
            effective_session_filter = "general"
        else:
            # 1. Exact session_id match
            matching_s = [s for s in dossier.sessions if s.session_id == session_filter]
            if len(matching_s) == 1:
                target_s = matching_s[0]
            elif len(matching_s) > 1:
                raise SelectionError(f"Filtro de sesión ambiguo: existen múltiples sesiones con ID '{session_filter}'.")
            else:
                # 2. Canonical positive integer fallback ONLY if single match
                try:
                    s_num = parse_canonical_positive_int(session_filter)
                except ValueError:
                    raise SelectionError(f"Sesión no encontrada con ID '{session_filter}'.")

                num_matches = [s for s in dossier.sessions if s.session_number == s_num]
                if len(num_matches) == 1:
                    target_s = num_matches[0]
                elif len(num_matches) > 1:
                    raise SelectionError(
                        f"Filtro de sesión ambiguo: existen {len(num_matches)} sesiones con número {s_num}. "
                        "Especifique session_id para desambiguar."
                    )
                else:
                    raise SelectionError(f"Sesión no encontrada con número o ID '{session_filter}'.")

            filtered_items = [it for it in all_items if it.session_id == target_s.session_id]
            scope_str = target_s.session_id
            scope_label_str = f"Sesión {target_s.session_number} ({target_s.title})"
            effective_session_filter = target_s.session_id

    sorted_items = sorted(filtered_items, key=_item_sort_key)

    req_res_count = sum(1 for it in sorted_items if it.priority_state == PRIORITY_REQUIRES_RESOLUTION)
    pend_rev_count = sum(1 for it in sorted_items if it.priority_state == PRIORITY_PENDING_REVIEW)
    post_count = sum(1 for it in sorted_items if it.priority_state == PRIORITY_POSTPONED)
    rev_count = sum(1 for it in sorted_items if it.priority_state == PRIORITY_REVIEWED)
    not_spec_count = sum(1 for it in sorted_items if it.priority_state == PRIORITY_NOT_SPECIFIED)
    tot_count = len(sorted_items)
    actionable_count = req_res_count + pend_rev_count + rev_count

    is_completed = (req_res_count == 0 and pend_rev_count == 0)

    first_pending_key = None
    for it in sorted_items:
        if it.priority_state in (PRIORITY_REQUIRES_RESOLUTION, PRIORITY_PENDING_REVIEW):
            first_pending_key = it.item_id
            break

    return OperationalQueue(
        items=sorted_items,
        requires_resolution_count=req_res_count,
        pending_review_count=pend_rev_count,
        reviewed_count=rev_count,
        not_specified_count=not_spec_count,
        actionable_count=actionable_count,
        total_count=tot_count,
        scope=scope_str,
        scope_label=scope_label_str,
        session_filter=effective_session_filter,
        all_items_count=len(all_items),
        is_completed=is_completed,
        first_pending_key=first_pending_key,
        postponed_count=post_count,
    )



# Contracts for future V1 capabilities (as outlined in HANDOFF.md)
@dataclass
class DailyGuide:
    session_title: str
    target_date: str
    allocated_minutes: int
    materials: list[str]
    objectives: list[str]
    inicio_steps: list[str]
    desarrollo_steps: list[str]
    cierre_steps: list[str]
    pending_items: list[str]
    confirmed: bool = False


@dataclass
class ActivityVariant:
    objective: str
    original_instruction: str
    variant_instruction: str
    source_reference: SourceReference
    requires_human_review: bool = True


@dataclass
class PrintableBundle:
    pages: list[int]
    annex_labels: list[str]
    document_sha256: str
    output_path: str = ""


def build_daily_guide(
    confirmed_session: SessionPlan,
    constraints: dict[str, Any],
    context: Any = None,
) -> DailyGuide:
    """Stub contract for V1 daily guide synthesis (Phase V1)."""
    raise NotImplementedError(
        "build_daily_guide es una capacidad de Fase V1 (HANDOFF.md). No disponible en V0."
    )


def propose_activity_variant(
    confirmed_session: SessionPlan,
    teacher_need: str,
    source_excerpts: list[SourceReference],
) -> ActivityVariant:
    """Stub contract for V1 activity variation (Phase V1)."""
    raise NotImplementedError(
        "propose_activity_variant es una capacidad de Fase V1 (HANDOFF.md). No disponible en V0."
    )


def export_annexes(confirmed_annexes: list[AnnexReference]) -> PrintableBundle:
    """Stub contract for V1 annex export (Phase V1)."""
    raise NotImplementedError(
        "export_annexes es una capacidad de Fase V1 (HANDOFF.md). No disponible en V0."
    )


class CurriculumSourceInterpreter:
    """Extractor and interpreter of curriculum planning documents."""

    @classmethod
    def read_pdf_bytes_and_sha(cls, source: Any) -> tuple[bytes, str, str]:
        """Extract raw bytes, SHA-256 and original name from various source types."""
        if hasattr(source, "pdf") and getattr(source.pdf, "name", None):
            with source.pdf.open("rb") as stream:
                content = stream.read()
            name = Path(source.pdf.name).name
        elif isinstance(source, (str, Path)):
            path = Path(source)
            content = path.read_bytes()
            name = path.name
        elif hasattr(source, "read"):
            content = source.read()
            name = getattr(source, "name", "document.pdf")
            if isinstance(name, str):
                name = Path(name).name
        elif isinstance(source, (bytes, bytearray)):
            content = bytes(source)
            name = "document.pdf"
        else:
            raise TypeError(f"Unsupported source type: {type(source)}")

        digest = hashlib.sha256(content).hexdigest()
        return content, digest, name

    @classmethod
    def prepare(
        cls,
        source: Any,
        selection: dict[str, Any] | None = None,
        job: Any = None,
        timeout_seconds: float | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> ImportDossier:
        """Parse source PDF and build an initial provisional ImportDossier."""
        start_time = time.monotonic()
        content, sha256, source_name = cls.read_pdf_bytes_and_sha(source)
        try:
            reader = PdfReader(io.BytesIO(content))
            page_count = len(reader.pages)
            if page_count == 0:
                raise SourcePdfReadError("El archivo PDF no contiene páginas legibles.")
        except SourcePdfReadError:
            raise
        except (PyPdfError, OSError, ValueError, TypeError, Exception) as exc:
            raise SourcePdfReadError(f"No se pudo leer el archivo PDF: {exc}") from exc

        # Model job stage lifecycle: start stage cleanly
        if job and hasattr(job, "pk"):
            from django.utils import timezone
            job.progress_stage = "reading_pdf"
            job.progress_started_at = timezone.now()
            job.progress_finished_at = None
            job.progress_done = 0
            job.progress_total = page_count
            job.save(
                update_fields=[
                    "progress_stage",
                    "progress_started_at",
                    "progress_finished_at",
                    "progress_done",
                    "progress_total",
                    "updated_at",
                ]
            )

        # Connect cooperative cancellation to job if job provided
        effective_cancelled = is_cancelled
        if effective_cancelled is None and job and hasattr(job, "pk"):
            from curriculum.models import CurriculumImportJob
            effective_cancelled = lambda: CurriculumImportJob.objects.filter(
                pk=job.pk, cancel_requested=True
            ).exists()

        pages_text: list[str] = []
        page_warnings: dict[int, str] = {}

        try:
            for idx, p in enumerate(reader.pages):
                if effective_cancelled and effective_cancelled():
                    if job and hasattr(job, "pk"):
                        from curriculum.interpretation_commands import finish_cancelled_stage

                        finish_cancelled_stage(job)
                    raise InterpretationCancelledError("Extracción de PDF cancelada cooperativamente.")

                if timeout_seconds and (time.monotonic() - start_time) > timeout_seconds:
                    if job and hasattr(job, "pk"):
                        from curriculum.interpretation_commands import record_direct_timeout

                        record_direct_timeout(
                            job,
                            error_message=f"Tiempo de extracción excedido ({timeout_seconds}s).",
                        )
                    raise InterpretationTimeoutError(f"Tiempo de extracción excedido ({timeout_seconds}s).")

                try:
                    txt = p.extract_text() or ""
                    if not txt.strip():
                        page_warnings[idx + 1] = (
                            f"Página {idx + 1} no contiene texto digital legible (posible imagen o escaneo)."
                        )
                    pages_text.append(txt)
                except (PdfReadError, OSError, ValueError) as exc:
                    logger.warning("Error extrayendo texto en página %s: %s", idx + 1, exc)
                    page_warnings[idx + 1] = f"Fallo de lectura en página {idx + 1}: {exc}"
                    pages_text.append("")

                # Update live page counter in job if provided
                if job and hasattr(job, "pk"):
                    job.progress_done = idx + 1
                    job.save(update_fields=["progress_done", "updated_at"])

            # 1. Scan for annex sheet candidates across all pages
            annex_candidates = cls._scan_annex_sheet_candidates(pages_text)

            # 2. Extract general fields from initial overview pages with accurate physical page numbers
            general_fields = cls._extract_general_fields(pages_text, sha256, page_warnings)

            # 3. Detect sessions across the document
            detected_sessions = cls._detect_sessions(pages_text, sha256, annex_candidates, page_warnings)

            # 4. Strictly validate selection (Sol Item 1: No silent fallback!)
            active_selection: dict[str, Any] = {}
            target_session: SessionPlan | None = None

            if selection:
                req_pages = selection.get("pages")
                if req_pages:
                    invalid_pages = [
                        p for p in req_pages if not (isinstance(p, int) and 1 <= p <= page_count)
                    ]
                    if invalid_pages:
                        raise SelectionError(
                            f"Páginas seleccionadas fuera de rango: {invalid_pages} "
                            f"(el documento contiene {page_count} páginas)."
                        )

                req_s_id = selection.get("session_id")
                req_s_num = selection.get("session_number") or selection.get("session")

                if req_s_id:
                    for s in detected_sessions:
                        if s.session_id == str(req_s_id):
                            target_session = s
                            break
                    if target_session is None:
                        raise SelectionError(f"La sesión con ID '{req_s_id}' no existe en el documento.")
                elif req_s_num is not None:
                    try:
                        s_num_int = int(req_s_num)
                    except (ValueError, TypeError):
                        raise SelectionError(f"Número de sesión inválido: '{req_s_num}'.")

                    matching = [s for s in detected_sessions if s.session_number == s_num_int]
                    if len(matching) == 0:
                        raise SelectionError(f"La sesión número {s_num_int} no existe en el documento.")
                    elif len(matching) > 1:
                        # Sol Item 1: In C02, sessions repeat across projects. Ambiguous without project or session_id!
                        req_proj = selection.get("project_title")
                        if req_proj:
                            matching = [
                                s for s in matching if req_proj.lower() in s.project_title.lower()
                            ]
                        if len(matching) != 1:
                            raise SelectionError(
                                f"Selección ambigua: existen {len(matching)} sesiones con número {s_num_int} "
                                "en distintos proyectos. Debe especificar 'session_id' o 'project_title' y páginas."
                            )
                        target_session = matching[0]
                    else:
                        target_session = matching[0]
                elif req_pages:
                    exact_matching = [s for s in detected_sessions if set(s.pages) == set(req_pages)]
                    if len(exact_matching) == 1:
                        target_session = exact_matching[0]
                    elif len(exact_matching) > 1:
                        raise SelectionError(
                            f"Selección por páginas ambigua: existen {len(exact_matching)} sesiones con las páginas {req_pages}. "
                            "Especifique 'session_id' para desambiguar."
                        )
                    else:
                        overlapping = [
                            s for s in detected_sessions
                            if set(req_pages).issubset(set(s.pages)) or any(p in s.pages for p in req_pages)
                        ]
                        if len(overlapping) == 0:
                            raise SelectionError(f"Ninguna sesión detectada abarca las páginas {req_pages}.")
                        elif len(overlapping) > 1:
                            raise SelectionError(
                                f"Selección por páginas ambigua: las páginas {req_pages} coinciden con múltiples sesiones "
                                f"({[s.session_id for s in overlapping]}). Especifique 'session_id' para desambiguar."
                            )
                        cand = overlapping[0]
                        if any(p not in cand.pages for p in req_pages):
                            raise SelectionError(
                                f"Las páginas {req_pages} no coinciden de forma consistente con la sesión '{cand.session_id}' ({cand.pages})."
                            )
                        target_session = cand

                if target_session and req_pages:
                    if any(p not in target_session.pages for p in req_pages) or set(req_pages) != set(target_session.pages):
                        raise SelectionError(
                            f"Las páginas {req_pages} son inconsistentes con la sesión seleccionada '{target_session.session_id}' "
                            f"(páginas de la sesión: {target_session.pages})."
                        )
            else:
                # Default initial visit: first detected session
                target_session = detected_sessions[0] if detected_sessions else None

            if target_session:
                active_selection["session_id"] = target_session.session_id
                active_selection["session_number"] = target_session.session_number
                active_selection["pages"] = list(target_session.pages)
                active_selection["project_title"] = target_session.project_title

            now_str = _utc_iso_now()
            dossier = ImportDossier(
                source_sha256=sha256,
                source_name=source_name,
                page_count=page_count,
                version=1,
                status="active",
                selection=active_selection,
                general_fields=general_fields,
                sessions=detected_sessions,
                annex_candidates=annex_candidates,
                page_warnings=page_warnings,
                history=[
                    HistoryEntry(
                        version=1,
                        action="prepare",
                        actor="CurriculumSourceInterpreter",
                        timestamp=now_str,
                        summary=(
                            f"Extracción inicial: {page_count} páginas, "
                            f"{len(detected_sessions)} sesiones detectadas, "
                            f"{len(annex_candidates)} anexos candidatos, "
                            f"{len(page_warnings)} advertencias de página."
                        ),
                    ).to_dict()
                ],
                created_at=now_str,
                updated_at=now_str,
            )

            # Deterministic mechanical verification against physical PDF
            from curriculum.verification import verify_curriculum_dossier
            report = verify_curriculum_dossier(dossier, io.BytesIO(content))
            dossier.verification_report = report.to_dict()

            # Mark stage finished successfully on job
            if job and hasattr(job, "pk"):
                from django.utils import timezone
                now_dt = timezone.now()
                job.progress_stage = ""
                job.progress_finished_at = now_dt
                job.progress_done = page_count
                job.progress_total = page_count
                job.page_count = page_count
                job.save(
                    update_fields=[
                        "progress_stage",
                        "progress_finished_at",
                        "progress_done",
                        "progress_total",
                        "page_count",
                        "updated_at",
                    ]
                )
            return dossier
        except Exception:
            # On any failure/cancellation, clean progress_stage and preserve existing valid dossier
            if job and hasattr(job, "pk"):
                from django.utils import timezone
                now_dt = timezone.now()
                job.progress_stage = ""
                if not job.progress_finished_at:
                    job.progress_finished_at = now_dt
                job.save(
                    update_fields=[
                        "progress_stage",
                        "progress_finished_at",
                        "updated_at",
                    ]
                )
            raise

    @classmethod
    def _scan_annex_sheet_candidates(cls, pages_text: list[str]) -> list[dict[str, Any]]:
        """Identify pages that represent individual annex sheets."""
        candidates = []
        for idx, text in enumerate(pages_text, start=1):
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for line in lines[:6]:
                m = re.match(
                    r"^ANEXO\s*(?:#|No\.?|N°)?\s*0*(\d+)(?:\s*[-–—:]\s*(.*))?$",
                    line,
                    re.IGNORECASE,
                )
                if m:
                    num = str(int(m.group(1)))
                    extra_title = m.group(2) or ""
                    candidates.append({
                        "number": num,
                        "page": idx,
                        "label": line,
                        "title": extra_title.strip(),
                    })
                    break
        return candidates

    @classmethod
    def _extract_general_fields(
        cls, pages_text: list[str], sha256: str, page_warnings: dict[int, str]
    ) -> dict[str, InterpretedField]:
        """Extract overview fields with physical page provenance and deduplication."""
        fields_dict: dict[str, InterpretedField] = {}
        overview_pages = pages_text[:3]
        overview_text = "\n".join(overview_pages)
        overview_spans = extract_overview_spans(
            overview_pages, has_later_pages=len(pages_text) > len(overview_pages),
        )

        def _explicit_field(name: str, action: str, *, preserve_lines: bool = False) -> InterpretedField:
            span = overview_spans[name]
            value = span.excerpt if preserve_lines else re.sub(r"\s+", " ", span.excerpt).strip()
            uncertain = span.ambiguous
            if name == "proyecto" and span.termination != "quoted_title":
                uncertain = uncertain or bool(
                    re.match(r"^[sS]\b|^[eE]je\b|^\W", value)
                    or len(value) < 3
                    or value.lower().startswith("eje seleccionado")
                )
            warned = span.page_number in page_warnings
            if not value:
                status, origin = STATUS_MISSING, ORIGIN_PROPOSED
                reason = "La etiqueta explícita no tiene valor antes del siguiente límite estructural."
            elif uncertain:
                status, origin = STATUS_AMBIGUOUS, ORIGIN_PROPOSED
                reason = (
                    "Texto localizado en una sola página, pero el límite del campo requiere revisión; "
                    "no se completó ni unió texto de otra página."
                )
            else:
                status, origin = (STATUS_AMBIGUOUS if warned else STATUS_SUPPORTED), ORIGIN_EXTRACTED
                reason = (
                    f"Advertencia en página fuente {span.page_number}."
                    if warned else "Campo explícito delimitado con evidencia literal de su página física."
                )
            return InterpretedField(
                name=name, value=value, origin=origin, status=status,
                reason=reason, action_required=action,
                evidence=[SourceReference(
                    document_sha256=sha256, page_number=span.page_number,
                    excerpt=span.excerpt,
                )] if value else [],
            )

        def _find_page(needle_or_match: str) -> int:
            """Determine which 1-indexed physical page contains the matched text."""
            for p_idx, p_txt in enumerate(overview_pages, start=1):
                if needle_or_match[:40] in p_txt:
                    return p_idx
            return 1

        # 1. Project names keep their physical source and uncertain continuations.
        if "proyecto" in overview_spans:
            fields_dict["proyecto"] = _explicit_field(
                "proyecto", "Verificar o ingresar el nombre inequívoco del proyecto.",
            )
        else:
            fields_dict["proyecto"] = InterpretedField(
                name="proyecto", value="", origin=ORIGIN_PROPOSED, status=STATUS_MISSING,
                reason="No se encontró una etiqueta explícita e inequívoca del proyecto en la portada.",
                action_required="Ingresar título del proyecto manualmente.",
            )

        # 2. Canonical names with page-local, literal evidence. Orthographic
        # normalization must not invent a quotation or stitch two pages together.
        campo_mentions = _canonical_campo_mentions(overview_pages, sha256)
        found_canonical = [name for name in CANONICAL_CAMPOS if name in campo_mentions]

        campos_match = re.search(
            r"Campo[s]?(?:\s+Formativo[s]?)?:?\s*([^\n\r]+?)(?=(?:\s+Temporalidad|\s+Ejes|\s+Contenido|\n|\Z))",
            overview_text,
            re.IGNORECASE,
        )
        matched_page = _find_page(campos_match.group(0)) if campos_match else 1
        is_warned = matched_page in page_warnings

        if found_canonical:
            is_warned = any(campo_mentions[name].page_number in page_warnings for name in found_canonical)
            fields_dict["campos_formativos"] = InterpretedField(
                name="campos_formativos",
                value=found_canonical,
                origin=ORIGIN_EXTRACTED,
                status=STATUS_AMBIGUOUS if is_warned else STATUS_SUPPORTED,
                reason="Campos formativos oficiales identificados sin fragmentación sintáctica.",
                action_required="Confirmar campos formativos aplicables.",
                evidence=[campo_mentions[name] for name in found_canonical],
            )
        elif campos_match:
            # Non-canonical match (e.g. table header column like 'Proyectos Eje y Libro' in C04)
            raw_val = campos_match.group(1).strip()
            clean_val = re.sub(
                r"\s*(?:Temporalidad|Ejes|Contenido|Fase|Proyectos).*$", "", raw_val, flags=re.IGNORECASE
            ).strip()
            # Sol Item 9: Do NOT mark non-canonical heuristics as supported!
            fields_dict["campos_formativos"] = InterpretedField(
                name="campos_formativos",
                value=[clean_val] if clean_val else [],
                origin=ORIGIN_PROPOSED,
                status=STATUS_AMBIGUOUS,
                reason="Extracción heurística no concluyente desde tabla o formato no estándar.",
                action_required="Seleccionar los campos formativos pertinentes.",
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=matched_page,
                        excerpt=campos_match.group(0).strip(),
                    )
                ],
            )
        else:
            fields_dict["campos_formativos"] = InterpretedField(
                name="campos_formativos",
                value=[],
                origin=ORIGIN_PROPOSED,
                status=STATUS_MISSING,
                reason="No se detectó campo formativo explícito.",
                action_required="Seleccionar los campos formativos pertinentes.",
            )

        # 3. Explicit purpose; mentions in prose do not create labelled fields.
        if "proposito" in overview_spans:
            fields_dict["proposito"] = _explicit_field(
                "proposito", "Validar concordancia con PDA.",
            )
        else:
            fields_dict["proposito"] = InterpretedField(
                name="proposito", value="", origin=ORIGIN_PROPOSED, status=STATUS_MISSING,
                reason="No se localizó sección de propósito explícito.",
                action_required="Redactar el propósito para el alumno.",
            )

        # 4. Explicit finality uses the same page-local boundaries. The implicit
        # finality path below retains its separate inference/review contract.
        if "finalidad" in overview_spans:
            fields_dict["finalidad"] = _explicit_field(
                "finalidad", "Revisar adecuación a la intención pedagógica.", preserve_lines=True,
            )
        else:
            # Candidate detection for implicit finalidad on overview page (physical page 1)
            implicit_candidate = None
            candidate_excerpt = ""
            candidate_page = 1

            p1_text = overview_pages[0] if overview_pages else ""

            # 1. Delimit starting position: only after real "Proyecto [Titulo]" header line if present
            # Avoid cutting on mid-sentence occurrences of the word "proyecto" or prose starting with "Proyecto Comunitario..."
            proj_header_re = re.compile(
                r"(?:^|\n)\s*(?:"
                r"(?i:(?:Nombre\s+del\s+)?Proyecto\s*:)|"
                r"(?i:(?:Nombre\s+del\s+)?Proyecto\b[^\n\r]*\bEscenario\b)|"
                r"(?i:Nombre\s+del\s+Proyecto\b)"
                r")[^\n\r]*(?:\n|\Z)"
            )
            proj_match = proj_header_re.search(p1_text)
            if proj_match:
                p1_sub = p1_text[proj_match.end():]
            else:
                p1_sub = p1_text

            # 2. Delimit ending boundary: strictly by real structure of headers and table column headers.
            # Handles single-line and multiline table columns ('Campos formativos', 'Contenidos', etc.).
            structural_boundary = re.search(
                r"(?:\n|\A)\s*(?:"
                r"Campos?(?:\s+formativos?)?\b\s*(?:[:\n\r]|\s+(?:Contenidos?|Proceso|PDA)\b|\Z)|"
                r"Contenidos?\b\s*(?:[:\n\r]|\s+del\b|\s+sint[eé]tico|\s+Proceso|\s+PDA|\Z)|"
                r"Procesos?\s+de\s+desarrollo(?:\s+de\s+aprendizaje[s]?)?\b|"
                r"PDA\b|"
                r"Ejes?(?:\s+articuladores?)?\b\s*(?:[:\n\r]|\Z)|"
                r"Metodolog[ií]a\b\s*(?:[:\n\r]|\s+(?:Aprendizaje|de\s+proyecto)\b|\Z)|"
                r"Tiempo\s+de\s+aplicaci[oó]n\b|"
                r"Temporalidad\b\s*(?:[:\n\r]|\Z)|"
                r"DESARROLLO\s+DEL\s+PROYECTO\b|"
                r"Fase\s*#?\s*\d+\b\s*[:.]|"
                r"SESI[OÓ]N\b|"
                r"Ajustes(?:\s+razonables)?\b|"
                r"Materiales(?:\s+(?:educativos|did[aá]cticos))?\b|"
                r"Recursos(?:\s+(?:did[aá]cticos|y\s+materiales))?\b|"
                r"Evaluaci[oó]n(?:\s+formativa)?\b|"
                r"Instrumentos?(?:\s+de\s+evaluaci[oó]n)?\b|"
                r"Productos?(?:\s+esperados?)?\b|"
                r"Observaciones\b|"
                r"Notas?(?:\s+al\s+docente)?\b|"
                r"Visto\s+Bueno\b|Vo\.?\s*Bo\.?\b"
                r")",
                p1_sub,
                re.IGNORECASE,
            )
            candidate_area = p1_sub[:structural_boundary.start()] if structural_boundary else p1_sub

            # 3. Regular expressions for filtering out generic preambles vs identifying real project candidates
            generic_intro_re = re.compile(
                r"^(?:"
                r"El\s+enfoque\b|"
                r"(?:En\s+la\s+|La\s+)?Nueva\s+Escuela\s+Mexicana\b|"
                r"El\s+plan\s+de\s+estudio[s]?\b|"
                r"Propuesta\s+(?:did[aá]ctica|pedag[oó]gica|de\s+trabajo)\b|"
                r"Orientaciones\s+(?:did[aá]cticas|pedag[oó]gicas|generales)\b|"
                r"Estrategia\s+nacional\b|"
                r"(?:El|La)\s+presente\s+(?:documento|planeaci[oó]n|proyecto)\s+(?:busca|tiene|pretende|promueve)\b|"
                r"Las\s+actividades\s+(?:propuestas\s+)?promueven\b|"
                r"El\s+trabajo\s+por\s+proyectos\s+promueve\b|"
                r"La\s+educaci[oó]n\s+primaria\b|"
                r"En\s+este\s+ciclo\s+escolar\b|"
                r"Ciclo\s+escolar\b|"
                r"Escuela\s+(?:primaria|b[aá]sica|urbana|rural)\b|"
                r"Zona\s+escolar\b|"
                r"Sector\b|"
                r"Turno\b|"
                r"Docente\s+titular\b"
                r")",
                re.IGNORECASE,
            )

            card_metadata_re = re.compile(
                r"^(?:"
                r"P[aá]ginas\s+(?:de\s+la\s+)?\d+|"
                r"Escenario\b|"
                r"Grado\s*:?\s*\d+|"
                r"Fase\s+\d+|"
                r"Libro\s+de\s+texto"
                r")",
                re.IGNORECASE,
            )

            pedagogical_verbs_pattern = (
                r"Conocer|Identificar|Elaborar|Desarrollar|Reconocer|Explorar|Escribir|"
                r"Reflexionar|Comprender|Investigar|Diseñar|Crear|Aprender|Analizar|Construir|"
                r"Participar|Organizar|Promover|Descubrir|Valorar|Realizar|Sensibilizar|"
                r"Propiciar|Fomentar|Indagar|Recopilar|Difundir|Examinar|Documentar|"
                r"Implementar|Socializar|Festejar|Fortalecer|Favorecer|Impulsar|"
                r"Generar|Proponer|Explicar|Compartir|Cuidar|Proteger|Expresar|Comunicar|"
                r"Practicar|Integrar|Lograr|Establecer|Involucrar|Consolidar|Potenciar|"
                r"Abordar|Distinguir|Ejercitar|Experimentar|Demostrar|Interpretar|Evaluar|"
                r"Resolver|Transformar|Rescatar|Vincular|Afianzar"
            )
            pedagogical_verbs_re = re.compile(
                rf"\b(?:{pedagogical_verbs_pattern})\b",
                re.IGNORECASE,
            )

            # Action verbs in infinitive after finalistic connectors, explicitly excluding non-verb words (tercer, primer, escolar, etc.)
            finalistic_verb_pattern = (
                rf"(?:{pedagogical_verbs_pattern}|"
                r"(?!(?:primer|tercer|cuart|quint|sext|escolar|familiar|particular|regular|popular|similar|lugar|hogar|solar|militar|celular|nuclear|taller|l[ií]der|mujer|ayer|mar|par|bar|sin|con)\b)"
                r"[a-záéíóúñ]{4,}(?:ar|er|ir))"
            )
            subjunctive_forms = set()
            irregular_subjunctives = {
                "conocer": ("conozca", "conozcan"),
                "reconocer": ("reconozca", "reconozcan"),
                "resolver": ("resuelva", "resuelvan"),
                "proponer": ("proponga", "propongan"),
                "distinguir": ("distinga", "distingan"),
            }
            for infinitive in pedagogical_verbs_pattern.lower().split("|"):
                if infinitive in irregular_subjunctives:
                    subjunctive_forms.update(irregular_subjunctives[infinitive])
                elif infinitive.endswith("uir"):
                    root = infinitive[:-3]
                    subjunctive_forms.update((root + "uya", root + "uyan"))
                elif infinitive.endswith("ar"):
                    root = infinitive[:-2]
                    if infinitive.endswith("car"):
                        root = root[:-1] + "qu"
                    elif infinitive.endswith("gar"):
                        root = root[:-1] + "gu"
                    elif infinitive.endswith("zar"):
                        root = root[:-1] + "c"
                    subjunctive_forms.update((root + "e", root + "en"))
                elif infinitive.endswith(("er", "ir")):
                    if infinitive.endswith("cer"):
                        root = infinitive[:-3]
                        subjunctive_forms.update((root + "zca", root + "zcan"))
                    else:
                        root = infinitive[:-2]
                        subjunctive_forms.update((root + "a", root + "an"))
            finalistic_subjunctive_pattern = "|".join(sorted(subjunctive_forms, key=len, reverse=True))

            objective_start_re = re.compile(
                r"^(?:"
                # 1. Action verb at line start (optionally with bullet / list number)
                rf"(?:[•\-*]|\d+[\.\)])?\s*(?:{pedagogical_verbs_pattern})\b|"
                # 2. Finalistic connectors at line start must be followed by an action verb.
                rf"Para\s+(?:{finalistic_verb_pattern}\b|que\s+[^\n.]*?\b(?:{finalistic_subjunctive_pattern})\b)|"
                rf"(?:Con\s+la\s+finalidad\s+de|Tiene\s+como\s+finalidad|Tiene\s+por\s+objetivo|Tiene\s+por\s+objeto|"
                rf"Con\s+el\s+prop[oó]sito\s+de|Tiene\s+como\s+prop[oó]sito|El\s+prop[oó]sito\s+(?:es|consiste\s+en)|"
                rf"El\s+objetivo\s+(?:es|consiste\s+en)|La\s+finalidad\s+(?:es|consiste\s+en))\s+{finalistic_verb_pattern}\b|"
                # 3. Explicit subject / project context at line start
                rf"(?:En\s+este\s+proyecto\b[^\n.]*?|Las\s+y\s+los\s+alumnos\b[^\n.]*?|El\s+alumnado\b[^\n.]*?|"
                rf"Los\s+estudiantes\b[^\n.]*?|La\s+comunidad\s+escolar\b[^\n.]*?|Docentes\s+y\s+estudiantes\b[^\n.]*?)\s*"
                rf"(?:[,\-:]\s*)?(?:para\s+)?(?:{pedagogical_verbs_pattern})\b|"
                # 4. Project description / prose starting with Proyecto ... requiring verifiable finalistic intention
                rf"Proyecto\b[^\n.]*?\s+(?:"
                rf"para\s+(?:que\s+[^\n.]*?\b{finalistic_verb_pattern}\b|{finalistic_verb_pattern}\b)|"
                rf"(?:enfocado\s+en|orientado\s+a|con\s+la\s+finalidad\s+de|con\s+el\s+prop[oó]sito\s+de|destinado\s+a|busca|pretende)\s*(?:[,\-:]\s*)?{finalistic_verb_pattern}\b|"
                rf"\b{finalistic_verb_pattern}\b"
                rf")"
                r")",
                re.IGNORECASE,
            )

            post_objective_labels_re = re.compile(
                r"^(?:"
                r"Materiales(?:\s+(?:educativos|did[aá]cticos))?\b|"
                r"Recursos(?:\s+(?:did[aá]cticos|y\s+materiales|e\s+implicaciones))?\b|"
                r"Evaluaci[oó]n(?:\s+formativa)?\b|"
                r"Instrumentos?(?:\s+de\s+evaluaci[oó]n)?\b|"
                r"Productos?(?:\s+(?:esperados?|y\s+evidencias))?\b|"
                r"Evidencias?(?:\s+de\s+aprendizaje)?\b|"
                r"Observaciones(?:\s+generales)?\b|"
                r"Notas?(?:\s+(?:al\s+docente|para\s+padres|pedag[oó]gica))?\b|"
                r"Ajustes(?:\s+razonables)?\b|"
                r"razonables\b|"
                r"Estrategias?(?:\s+did[aá]cticas?)?\b|"
                r"Organizaci[oó]n(?:\s+del\s+grupo)?\b|"
                r"Actividades(?:\s+(?:permanentes|previas))?\b|"
                r"Sugerencias\b|"
                r"Visto(?:\s+Bueno)?\b|"
                r"Vo\.?\s*Bo\.?\b|"
                r"Firma\b|"
                r"(?:Texto\s+ajeno|Comentarios?(?:\s+adicionales)?)\b"
                r")\s*:?",
                re.IGNORECASE,
            )

            list_marker_re = re.compile(r"^(?:[•\-\*]|\d+[\.\)])\s+", re.IGNORECASE)

            # 4. Extract candidate lines: skip generic pedagogical/admin intros, start on syntactic objective trigger,
            # delimit by paragraph structure (stopping on blank lines) and post-objective boundaries.
            raw_lines = candidate_area.splitlines()
            captured_lines: list[str] = []
            capturing = False

            for raw_line in raw_lines:
                line = raw_line.strip()
                if not line:
                    if capturing:
                        # Paragraph ended: do not absorb subsequent independent paragraphs
                        break
                    continue

                if not capturing:
                    if card_metadata_re.search(line):
                        continue
                    if generic_intro_re.search(line):
                        continue
                    if objective_start_re.search(line):
                        capturing = True
                        captured_lines.append(line)
                else:
                    # While capturing, stop before metadata, post-objective labels, list markers, or table headers
                    if (
                        card_metadata_re.search(line)
                        or post_objective_labels_re.search(line)
                        or list_marker_re.search(line)
                        or generic_intro_re.search(line)
                    ):
                        break
                    captured_lines.append(line)

            if captured_lines:
                cand_full = " ".join(captured_lines).strip()
                cand_full = re.sub(r"\s+", " ", cand_full)
                if len(cand_full) > 30 and (pedagogical_verbs_re.search(cand_full) or objective_start_re.search(cand_full)):
                    first_line = captured_lines[0]
                    pos = p1_text.find(first_line)
                    if pos != -1:
                        raw_slice = p1_text[pos : pos + min(200, len(first_line))]
                        candidate_excerpt = raw_slice
                    else:
                        candidate_excerpt = first_line[:200]
                    implicit_candidate = cand_full

            if implicit_candidate:
                fields_dict["finalidad"] = InterpretedField(
                    name="finalidad",
                    value=implicit_candidate,
                    origin=ORIGIN_PROPOSED,
                    status=STATUS_AMBIGUOUS,
                    review=REVIEW_PENDING,
                    reason=(
                        "Párrafo de objetivo/finalidad identificado de forma inferida en portada sin encabezado explícito; "
                        "requiere revisión docente."
                    ),
                    action_required="Confirmar si este párrafo corresponde a la finalidad e intención didáctica del proyecto.",
                    evidence=[
                        SourceReference(
                            document_sha256=sha256,
                            page_number=candidate_page,
                            excerpt=candidate_excerpt,
                        )
                    ],
                )
            else:
                fields_dict["finalidad"] = InterpretedField(
                    name="finalidad",
                    value="",
                    origin=ORIGIN_PROPOSED,
                    status=STATUS_MISSING,
                    reason="No se localizó sección de finalidad explícita ni un candidato de objetivo delimitado en portada.",
                    action_required="Redactar la finalidad o intención didáctica docente.",
                )

        # 5. Metodología
        # Table headers can place "Tiempo de aplicación" immediately after the
        # methodology on the same line, with its value continuing on page 2.
        # Capture only the physical line that supplies the method; a citation
        # assembled across pages cannot pass the source verifier.
        table_method = re.search(
            r"Metodolog[ií]a\s*:?[ \t]*([^\n\r]*?)(?=[ \t]+Tiempo\s+de\b)",
            overview_pages[0] if overview_pages else "",
            re.IGNORECASE,
        )
        met_match = re.search(
            r"Metodolog[ií]a:?\s*(.+?)(?=(?:\s{2,}|\n\s*)(?:Campos|Contenidos|Escenario|Ejes|Prop[oó]sito|Finalidad|Temporalidad|[-•–])|\Z)",
            overview_text,
            re.DOTALL | re.IGNORECASE,
        )
        if table_method or met_match:
            source_match = table_method or met_match
            val = re.sub(r"\s+", " ", source_match.group(1)).strip().rstrip(".")
            matched_page = 1 if table_method else _find_page(source_match.group(0))
            is_warned = matched_page in page_warnings
            # If methodology ends with preposition, partial words, or is too long/runaway
            is_partial = val.endswith(("de", "en", "para", "con", "por", "a")) or len(val) > 150
            status = STATUS_AMBIGUOUS if (is_warned or is_partial) else STATUS_SUPPORTED
            fields_dict["metodologia"] = InterpretedField(
                name="metodologia",
                value=val[:150],
                origin=ORIGIN_EXTRACTED if not is_partial else ORIGIN_PROPOSED,
                status=status,
                reason="Metodología de proyecto identificada en el documento."
                if not is_partial
                else "Texto de metodología detectado de forma parcial o heurística.",
                action_required="Confirmar metodología pedagógica.",
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=matched_page,
                        excerpt=val[:150],
                    )
                ],
            )
        else:
            fields_dict["metodologia"] = InterpretedField(
                name="metodologia",
                value="",
                origin=ORIGIN_PROPOSED,
                status=STATUS_MISSING,
                reason="No se encontró mención de metodología en la fuente.",
                action_required="Definir la metodología a emplear.",
            )

        # 6. Escenario del proyecto
        esc_match = re.search(
            r"Escenario:?\s*([^\n\r]+?)(?=(?:\s{2,}|\n|\s+Metodología|\s+Propósito|\s+Ejes|\Z))",
            overview_text,
            re.IGNORECASE,
        )
        if esc_match:
            val = esc_match.group(1).strip()
            matched_page = _find_page(esc_match.group(0))
            is_warned = matched_page in page_warnings
            fields_dict["escenario_proyecto"] = InterpretedField(
                name="escenario_proyecto",
                value=val,
                origin=ORIGIN_EXTRACTED,
                status=STATUS_AMBIGUOUS if is_warned else STATUS_SUPPORTED,
                reason="Escenario general del proyecto delimitado en la fuente.",
                action_required="Distinguir del lugar de ejecución específico de cada momento.",
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=matched_page,
                        excerpt=esc_match.group(0).strip(),
                    )
                ],
            )
        # 7. Grado escolar
        words_to_num = {
            "1": 1, "primer": 1, "primero": 1,
            "2": 2, "segundo": 2,
            "3": 3, "tercer": 3, "tercero": 3,
            "4": 4, "cuarto": 4,
            "5": 5, "quinto": 5,
            "6": 6, "sexto": 6,
        }
        grado_regex = re.compile(
            r"(?:Grado\s*:\s*|(?<=\b))([1-6][º°]|Primer[oa]?|Segundo|Tercer[oa]?|Cuarto|Quinto|Sexto)(?:\s*Grado)?\b",
            re.IGNORECASE,
        )
        # Prefer an explicit grade label in the header. Otherwise prose such as
        # "lo primero" on a later page can be mistaken for primero grado.
        grado_match = re.search(
            r"\bGrado\s*:?\s*([1-6])\s*[º°]?\b",
            overview_text,
            re.IGNORECASE,
        ) or grado_regex.search(overview_text)
        if grado_match:
            raw_matched = grado_match.group(1).lower().rstrip("º°")
            g_num = words_to_num.get(raw_matched)
            matched_page = _find_page(grado_match.group(0))
            is_warned = matched_page in page_warnings
            if g_num:
                fields_dict["grado"] = InterpretedField(
                    name="grado",
                    value=str(g_num),
                    origin=ORIGIN_EXTRACTED,
                    status=STATUS_AMBIGUOUS if is_warned else STATUS_SUPPORTED,
                    reason=f"Grado escolar identificado en la página {matched_page}.",
                    action_required="Verificar grado escolar.",
                    evidence=[
                        SourceReference(
                            document_sha256=sha256,
                            page_number=matched_page,
                            excerpt=grado_match.group(0).strip(),
                        )
                    ],
                )
            else:
                fields_dict["grado"] = InterpretedField(
                    name="grado",
                    value="",
                    origin=ORIGIN_PROPOSED,
                    status=STATUS_AMBIGUOUS,
                    reason="Mención ambigua de grado en el documento.",
                    action_required="Indicar grado escolar correspondiente.",
                )
        else:
            fields_dict["grado"] = InterpretedField(
                name="grado",
                value="",
                origin=ORIGIN_PROPOSED,
                status=STATUS_MISSING,
                reason="No se detectó mención explícita de grado escolar en las páginas de portada/encabezado.",
                action_required="Especificar el grado escolar de la planeación.",
            )
        # 8. Duración global del proyecto (Tiempo de aplicación / Temporalidad)
        dur_val = ""
        dur_evidence: list[SourceReference] = []
        dur_status = STATUS_SUPPORTED
        dur_origin = ORIGIN_EXTRACTED
        dur_reason = ""

        # A. Check for cross-page split between page 1 and page 2
        if len(overview_pages) >= 2:
            m_t1 = re.search(r"Tiempo\s+de\s+(?:aplicaci[oó]n\s*:?\s*)?([^\n\r]+)", overview_pages[0], re.IGNORECASE)
            # A split label must resume with a plausible duration value in the
            # page header region, not an unrelated later mention of "aplicación".
            duration_quantity = r"(?:\d{1,3}|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte)"
            duration_unit = r"(?:d[ií]as?|semanas?|mes(?:es)?|bimestres?|trimestres?|cuatrimestres?|semestres?|a[nñ]os?|ciclos?)"
            m_t2 = re.search(
                rf"aplicaci[oó]n\s+((?:(?:se\s+sugiere|aproximadamente|de)\s+)?(?:{duration_quantity}\s+)?{duration_unit}\b[^\n\r]*?)(?=\s*\n\s*(?:DESARROLLO|Fase|Metodolog[ií]a|Campo)|\Z)",
                overview_pages[1],
                re.IGNORECASE,
            )
            if m_t2:
                prefix = overview_pages[1][:m_t2.start()]
                if prefix.count("\n") > 2 or len(prefix) > 256:
                    m_t2 = None
            if m_t1 and m_t2:
                p1_time = m_t1.group(1).strip()
                p2_time = m_t2.group(1).strip()
                combined = re.sub(r"\s+", " ", f"{p1_time} {p2_time}").strip()
                ex1 = m_t1.group(0).strip()
                ex2 = m_t2.group(0).strip()
                norm_ex1 = normalize_text_for_evidence_check(ex1)
                norm_p1 = normalize_text_for_evidence_check(overview_pages[0])
                norm_ex2 = normalize_text_for_evidence_check(ex2)
                norm_p2 = normalize_text_for_evidence_check(overview_pages[1])
                if norm_ex1 and norm_ex1 in norm_p1 and norm_ex2 and norm_ex2 in norm_p2:
                    dur_val = combined
                    dur_origin = ORIGIN_PROPOSED
                    dur_status = STATUS_AMBIGUOUS
                    dur_reason = (
                        "Sugerencia de temporalidad global del proyecto identificada a través del salto de páginas 1 y 2; "
                        "no define sesiones ni horario."
                    )
                    dur_evidence = [
                        SourceReference(document_sha256=sha256, page_number=1, excerpt=ex1),
                        SourceReference(document_sha256=sha256, page_number=2, excerpt=ex2),
                    ]

        # B. Check for single-page match if not resolved cross-page
        if not dur_val:
            single_m = re.search(
                r"(?:Tiempo\s+de(?:\s+aplicaci[oó]n)?|Duraci[oó]n\s+del\s+proyecto)\s*:?\s*([^\n\r]+?)(?=(?:\s{2,}|\n|\s+Metodolog[ií]a|\s+Fase|\Z))",
                overview_text,
                re.IGNORECASE,
            )
            if single_m:
                raw_dur = single_m.group(1).strip()
                clean_dur = re.sub(r"\s+", " ", raw_dur).strip()
                if clean_dur and len(clean_dur) > 2 and not clean_dur.lower().startswith("de aplicación"):
                    m_page = _find_page(single_m.group(0))
                    ex = single_m.group(0).strip()[:200]
                    norm_ex = normalize_text_for_evidence_check(ex)
                    norm_p = normalize_text_for_evidence_check(overview_pages[m_page - 1]) if 0 <= m_page - 1 < len(overview_pages) else ""
                    if norm_ex and norm_ex in norm_p:
                        dur_val = clean_dur
                        dur_origin = ORIGIN_EXTRACTED if not ("sugiere" in clean_dur.lower()) else ORIGIN_PROPOSED
                        dur_status = STATUS_AMBIGUOUS if (m_page in page_warnings or "sugiere" in clean_dur.lower()) else STATUS_SUPPORTED
                        dur_reason = f"Duración global del proyecto identificada en página {m_page}."
                        dur_evidence = [SourceReference(document_sha256=sha256, page_number=m_page, excerpt=ex)]
                    else:
                        dur_val = clean_dur
                        dur_origin = ORIGIN_PROPOSED
                        dur_status = STATUS_AMBIGUOUS
                        dur_reason = "Duración sugerida detectada pero no se pudo cotejar cita contigua unívoca en una sola página."
                        dur_evidence = []

        if dur_val:
            fields_dict["duracion_proyecto"] = InterpretedField(
                name="duracion_proyecto",
                value=dur_val,
                origin=dur_origin,
                status=dur_status,
                review=REVIEW_PENDING,
                reason=dur_reason,
                action_required="Revisar y definir la temporalidad o duración real del proyecto.",
                evidence=dur_evidence,
            )

        return fields_dict

    @classmethod
    def _detect_sessions(
        cls,
        pages_text: list[str],
        sha256: str,
        annex_candidates: list[dict[str, Any]],
        page_warnings: dict[int, str],
    ) -> list[SessionPlan]:
        """Detect individual sessions across documents with honest provenance and layouts."""
        source_segments = scan_session_segments(pages_text, sha256)

        # Some project plans have phases but no lesson/session divisions. Keep
        # one explicitly ambiguous review unit for the project; do not infer a
        # number of lessons or turn methodological phases into sessions.
        if not source_segments:
            project_start = next(
                (i for i, text in enumerate(pages_text, start=1)
                 if re.search(r"(?:^|\n)\s*DESARROLLO\s+DEL\s+PROYECTO\b", text, re.IGNORECASE)
                 and re.search(r"(?:^|\n)\s*Fase\s*#?\s*1\b", text, re.IGNORECASE)),
                None,
            )
            if project_start is not None:
                phase_segments, unassigned_segments = phase_review_scope(pages_text, sha256, project_start)
                project_pages = [number for number, _ in phase_segments]

                activities: list[SessionActivity] = []
                act_pattern = re.compile(
                    r"(?:^|\n)\s*(?:(Actividad\b(?:\s+\d+\s*[:.-]|\s+[A-Za-z]\s*[:.-])?\s*[^\n\r]+)|"
                    r"[•\-\*]\s*([^\n\r]+(?:\n(?!\s*(?:[•\-\*]|\d+[.)]|Fase\b|DESARROLLO\b|Productos\b|ANEXO\b|Recursos\b|implicaciones\b))[^\n\r]+)*)|"
                    r"\d+[.)]\s*([^\n\r]+(?:\n(?!\s*(?:[•\-\*]|\d+[.)]|Fase\b|DESARROLLO\b|Productos\b|ANEXO\b|Recursos\b|implicaciones\b))[^\n\r]+)*))",
                    re.IGNORECASE,
                )
                order = 0
                for p_num, p_text in phase_segments:
                    boundary = re.search(
                        r"(?im)^\s*(?:Recursos|Materiales|Evaluaci[oó]n|Productos(?:\s+y\s+evidencias)?|Implicaciones|Anexos?)\b",
                        p_text,
                    )
                    # Some exported plans place a resources/implications label
                    # before their activity list. Treat it as a cutoff only
                    # after at least one activity has started on this page.
                    activity_text = p_text
                    if boundary and act_pattern.search(p_text[:boundary.start()]):
                        activity_text = p_text[:boundary.start()]
                    for m in act_pattern.finditer(activity_text):
                        raw_desc = (m.group(1) or m.group(2) or m.group(3) or "").strip()
                        raw_desc = re.sub(r"^[•\-\*]\s*", "", raw_desc).strip()
                        clean_desc = re.sub(r"\s+", " ", raw_desc)
                        if not clean_desc or len(clean_desc) < 5:
                            continue
                        if re.match(r"^(?:Recursos\b|implicaciones\b|Evaluaci[oó]n\b|Fase\b|DESARROLLO\b|Aspectos\s+a\s+evaluar)", clean_desc, re.IGNORECASE):
                            continue
                        order += 1
                        act_title = f"Actividad {order}: {clean_desc[:40].rstrip('.')}"
                        excerpt = clean_desc[:120].strip()
                        norm_ex = normalize_text_for_evidence_check(excerpt)
                        norm_p = normalize_text_for_evidence_check(p_text)
                        if not (norm_ex and norm_ex in norm_p):
                            first_line = clean_desc.split(".")[0].strip()[:60]
                            if normalize_text_for_evidence_check(first_line) in norm_p:
                                excerpt = first_line
                            else:
                                excerpt = m.group(0).strip()[:60].strip()

                        activities.append(
                            SessionActivity(
                                activity_id=f"p{project_start}_act_{order}",
                                title=act_title,
                                description=clean_desc,
                                order=order,
                                evidence=[
                                    SourceReference(
                                        document_sha256=sha256,
                                        page_number=p_num,
                                        excerpt=excerpt,
                                    )
                                ],
                            )
                        )

                fields: dict[str, InterpretedField] = {}
                if activities:
                    act_1 = activities[0]
                    fields["inicio"] = InterpretedField(
                        name="inicio",
                        value=act_1.description,
                        origin=ORIGIN_PROPOSED,
                        status=STATUS_AMBIGUOUS,
                        review=REVIEW_PENDING,
                        reason=(
                            "Propuesta pedagógica inicial: se sugiere la primera actividad del proyecto "
                            "como momento de inicio; requiere validación docente."
                        ),
                        action_required="Revisar la asignación y adecuación de la actividad de inicio.",
                        evidence=list(act_1.evidence),
                    )
                    if len(activities) == 2:
                        act_2 = activities[1]
                        fields["desarrollo"] = InterpretedField(
                            name="desarrollo",
                            value=act_2.description,
                            origin=ORIGIN_PROPOSED,
                            status=STATUS_AMBIGUOUS,
                            review=REVIEW_PENDING,
                            reason="Propuesta pedagógica de actividades para el momento de desarrollo del proyecto.",
                            action_required="Verificar secuencia y materiales requeridos.",
                            evidence=list(act_2.evidence),
                        )
                        fields["cierre"] = InterpretedField(
                            name="cierre",
                            value="",
                            origin=ORIGIN_PROPOSED,
                            status=STATUS_MISSING,
                            reason="No se asignó actividad de cierre en la propuesta inicial de fases.",
                            action_required="Definir dinámica de cierre o síntesis del proyecto.",
                        )
                    elif len(activities) >= 3:
                        mid_acts = activities[1:-1]
                        last_act = activities[-1]
                        mid_text = "\n\n".join(a.description for a in mid_acts)
                        mid_ev = [ev for a in mid_acts for ev in a.evidence]
                        fields["desarrollo"] = InterpretedField(
                            name="desarrollo",
                            value=mid_text,
                            origin=ORIGIN_PROPOSED,
                            status=STATUS_AMBIGUOUS,
                            review=REVIEW_PENDING,
                            reason="Propuesta pedagógica de actividades para el momento de desarrollo del proyecto.",
                            action_required="Verificar secuencia y materiales requeridos.",
                            evidence=mid_ev[:5],
                        )
                        fields["cierre"] = InterpretedField(
                            name="cierre",
                            value=last_act.description,
                            origin=ORIGIN_PROPOSED,
                            status=STATUS_AMBIGUOUS,
                            review=REVIEW_PENDING,
                            reason="Propuesta pedagógica de actividad para el momento de cierre del proyecto.",
                            action_required="Revisar dinámica de cierre y evaluación formativa.",
                            evidence=list(last_act.evidence),
                        )
                    else:
                        fields["desarrollo"] = InterpretedField(
                            name="desarrollo",
                            value="",
                            origin=ORIGIN_PROPOSED,
                            status=STATUS_MISSING,
                            reason="No se identificaron actividades suficientes para desarrollo en la propuesta inicial.",
                            action_required="Redactar actividades de desarrollo.",
                        )
                        fields["cierre"] = InterpretedField(
                            name="cierre",
                            value="",
                            origin=ORIGIN_PROPOSED,
                            status=STATUS_MISSING,
                            reason="No se identificaron actividades de cierre en la propuesta inicial.",
                            action_required="Redactar actividad de cierre.",
                        )
                else:
                    fields["inicio"] = InterpretedField(
                        name="inicio",
                        value="",
                        origin=ORIGIN_PROPOSED,
                        status=STATUS_MISSING,
                        reason="La fuente no delimita sesiones ni un inicio de sesión.",
                        action_required="Revisar la organización del proyecto antes de planear sesiones.",
                    )
                    fields["desarrollo"] = InterpretedField(
                        name="desarrollo",
                        value="",
                        origin=ORIGIN_PROPOSED,
                        status=STATUS_MISSING,
                        reason="No se identificaron actividades para desarrollo.",
                        action_required="Redactar actividades de desarrollo.",
                    )
                    fields["cierre"] = InterpretedField(
                        name="cierre",
                        value="",
                        origin=ORIGIN_PROPOSED,
                        status=STATUS_MISSING,
                        reason="No se identificaron actividades de cierre.",
                        action_required="Redactar actividad de cierre.",
                    )

                fields["duracion"] = InterpretedField(
                    name="duracion",
                    value="",
                    origin=ORIGIN_PROPOSED,
                    status=STATUS_MISSING,
                    reason="La fuente organiza el trabajo por fases y no declara duración de clases en minutos ni horario.",
                    action_required="Definir horario y duración de clases al acordar el calendario real con la docente.",
                )

                phase_context = phase_project_context(pages_text, sha256, project_start)
                phase_notes = (
                    "La fuente organiza el trabajo por fases del proyecto y no declara sesiones. "
                    "Esta unidad agrupa páginas para revisión docente; propone una organización inicial "
                    "por momentos (inicio/desarrollo/cierre) sin fijar duración ni cantidad de sesiones."
                )
                if unassigned_segments:
                    phase_notes += "\n\nCorte de seguridad ante un límite de secuencia no resuelto; requiere revisión."
                    for number, raw in unassigned_segments:
                        phase_notes += f"\n\nTramo sin asignar, página física {number}:\n{raw}"
                return [SessionPlan(
                    session_id=f"p{project_start}_project_review",
                    session_number=1,
                    title="Proyecto sin sesiones explícitas",
                    project_title=phase_context["title"],
                    project_context=phase_context,
                    pages=project_pages,
                    layout_fidelity="linearized_heuristics",
                    layout_notes=phase_notes,
                    fields=fields,
                    activities=activities,
                    status=STATUS_AMBIGUOUS,
                    review=REVIEW_PENDING,
                )]

        sessions: list[SessionPlan] = []
        for segment in source_segments:
            pages_spanned = [p for p, _ in segment.page_segments]
            display_title = (
                f"{segment.day_of_week} - Sesión {segment.session_number}: {segment.title}".strip(" -:")
                if segment.day_of_week
                else f"Sesión {segment.session_number}: {segment.title}".strip(" -:")
            )
            notes = (
                "Extracción lineal vía pypdf con reconstrucción heurística y límites por ocurrencia de Proyecto/SESIÓN "
                "o reinicio compuesto de planeación. "
                "Disposición de columnas y tablas no garantizada estructuralmente."
            )
            if len(pages_spanned) > 1:
                notes += f" Continuación estructural en página {pages_spanned[1]} detectada por encabezados de momento."
            plan = cls._parse_session_block(
                session_id=segment.session_id,
                session_number=segment.session_number,
                title=display_title,
                project_title=segment.project_context["title"],
                day_of_week=segment.day_of_week,
                pages=pages_spanned,
                continues_on=pages_spanned[1:],
                layout_fidelity="linearized_heuristics",
                layout_notes=notes,
                block_text="\n".join(text for _, text in segment.page_segments),
                sha256=sha256,
                annex_candidates=annex_candidates,
                page_warnings=page_warnings,
                pages_text=pages_text,
                page_segments=segment.page_segments,
            )
            if segment.unassigned_segments:
                reason = (
                    "Corte de seguridad ante un límite de secuencia no resuelto; "
                    "el contenido puede estar incompleto y requiere revisión. "
                    "El tramo literal sin asignar se conserva en las notas de segmentación."
                )
                plan.status = STATUS_AMBIGUOUS
                plan.layout_notes += "\n\n" + reason
                for number, raw in segment.unassigned_segments:
                    plan.layout_notes += f"\n\nTramo sin asignar, página física {number}:\n{raw}"
                for field_obj in plan.fields.values():
                    if not _is_empty_value(field_obj.value):
                        field_obj.origin = ORIGIN_PROPOSED
                        field_obj.status = STATUS_AMBIGUOUS
                        field_obj.reason = reason
                        field_obj.original_reason = reason
                        field_obj.current_action = field_obj.action_required = derive_field_operational_state(field_obj)[1]
            plan.project_context = copy.deepcopy(segment.project_context)
            plan.header_anchor = copy.deepcopy(segment.header_anchor)
            sessions.append(plan)
        return sessions

    @classmethod
    def _is_structural_barrier(cls, text: str) -> bool:
        return is_structural_barrier(text)

    @classmethod
    def _clean_page_prefix(cls, text: str) -> str:
        return clean_page_prefix(text)

    @classmethod
    def _parse_session_block(
        cls,
        session_id: str,
        session_number: int,
        title: str,
        project_title: str,
        day_of_week: str,
        pages: list[int],
        continues_on: list[int],
        layout_fidelity: str,
        layout_notes: str,
        block_text: str,
        sha256: str,
        annex_candidates: list[dict[str, Any]],
        page_warnings: dict[int, str],
        pages_text: list[str] | None = None,
        page_segments: list[tuple[int, str]] | None = None,
    ) -> SessionPlan:
        """Parse moments, resources, evaluation, execution context, and annexes from session text."""
        fields: dict[str, InterpretedField] = {}
        primary_page = pages[0] if pages else 1
        is_warned = any(p in page_warnings for p in pages)

        def _find_chunk_page(chunk: str, default_page: int) -> int:
            if not chunk or not pages_text:
                return default_page
            lines = [l.strip() for l in chunk.splitlines() if len(l.strip()) > 10]
            needle = lines[0] if lines else chunk.strip()[:40]
            if not needle:
                return default_page
            for p in pages:
                if 1 <= p <= len(pages_text):
                    if needle in pages_text[p - 1]:
                        return p
            needle_lower = needle.lower()
            for p in pages:
                if 1 <= p <= len(pages_text):
                    if needle_lower in pages_text[p - 1].lower():
                        return p
            return default_page

        moment_pattern = re.compile(
            r"(?:^|\n|(?<=[.!?])\s+)\s*(?:[•\-*]\s*)?(Inicio|Desarrollo|Cierre|Evaluación|Recursos(?:\s+didácticos)?)\s*(?::|\n|\s{2,})",
            re.IGNORECASE,
        )

        matches = list(moment_pattern.finditer(block_text))
        sections: dict[str, str] = {}
        for m_idx, m in enumerate(matches):
            raw_key = m.group(1).lower()
            key = (
                "recursos"
                if "recurso" in raw_key
                else "evaluacion"
                if "evalua" in raw_key
                else raw_key
            )
            start = m.end()
            end = matches[m_idx + 1].start() if (m_idx + 1) < len(matches) else len(block_text)
            content = block_text[start:end].strip()
            if key not in sections:
                sections[key] = content

        inicio_text = sections.get("inicio", "")
        desarrollo_text = sections.get("desarrollo", "")
        cierre_full = sections.get("cierre", "")
        evaluacion_text = sections.get("evaluacion", "")
        recursos_direct = sections.get("recursos", "")

        cierre_action = cierre_full
        if cierre_full:
            # Clean evaluation and summary rubric if appended
            cierre_clean_parts = re.split(
                r"(?:\n|\s{2,})(?:Producto\s+del\s+proyecto|Evidencias\s+de\s+aprendizaje|Aspectos\s+a\s+evaluar|Adecuaciones\s+curriculares)",
                cierre_full,
                flags=re.IGNORECASE,
            )
            cierre_action = cierre_clean_parts[0].strip()

        recursos_from_cierre = ""
        cierre_parts = re.split(
            r"\n\s*\n(?=•\s*(?:Fichas|Tarjetas|Cuaderno|Material|Lápiz|Libro|Cuadernillo))",
            cierre_action,
            flags=re.IGNORECASE,
        )
        if len(cierre_parts) > 1:
            cierre_action = cierre_parts[0].strip()
            recursos_from_cierre = "\n".join(cierre_parts[1:]).strip()

        final_recursos = recursos_from_cierre or recursos_direct

        if evaluacion_text:
            eval_clean_parts = re.split(
                r"(?:\n|\s{2,})(?:Desarrollo\s+de\s+actividades|PROYECTO(?:\s+de\s+diagn[oó]stico)?:|R[uú]brica(?:\s+de\s+evaluaci[oó]n)?|Vo\.\s*Bo\.|Firma\s+del\s+docente)",
                evaluacion_text,
                flags=re.IGNORECASE,
            )
            evaluacion_text = eval_clean_parts[0].strip()

        # 1. Inicio field
        if inicio_text:
            inicio_page = _find_chunk_page(inicio_text, primary_page)
            fields["inicio"] = InterpretedField(
                name="inicio",
                value=inicio_text,
                origin=ORIGIN_EXTRACTED,
                status=STATUS_AMBIGUOUS if (inicio_page in page_warnings or is_warned) else STATUS_SUPPORTED,
                reason="Momento de inicio extraído de la sesión.",
                action_required="Revisar consignas y dinámicas de apertura.",
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=inicio_page,
                        excerpt=inicio_text[:200],
                    )
                ],
            )
        else:
            fields["inicio"] = InterpretedField(
                name="inicio",
                value="",
                origin=ORIGIN_PROPOSED,
                status=STATUS_MISSING,
                reason="No se detectó instrucción explícita de inicio.",
                action_required="Redactar actividad de apertura.",
            )

        # 2. Desarrollo field
        if desarrollo_text:
            desarrollo_page = _find_chunk_page(desarrollo_text, primary_page)
            fields["desarrollo"] = InterpretedField(
                name="desarrollo",
                value=desarrollo_text,
                origin=ORIGIN_EXTRACTED,
                status=STATUS_AMBIGUOUS if (desarrollo_page in page_warnings or is_warned) else STATUS_SUPPORTED,
                reason="Momento central de desarrollo extraído de la sesión.",
                action_required="Verificar secuencia y materiales requeridos.",
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=desarrollo_page,
                        excerpt=desarrollo_text[:200],
                    )
                ],
            )
        else:
            fields["desarrollo"] = InterpretedField(
                name="desarrollo",
                value="",
                origin=ORIGIN_PROPOSED,
                status=STATUS_MISSING,
                reason="No se detectó instrucción explícita de desarrollo.",
                action_required="Redactar actividad central.",
            )

        # 3. Cierre field
        if cierre_action:
            cierre_page = _find_chunk_page(cierre_action, pages[-1] if pages else primary_page)
            cierre_warned = cierre_page in page_warnings or is_warned
            fields["cierre"] = InterpretedField(
                name="cierre",
                value=cierre_action,
                origin=ORIGIN_EXTRACTED,
                status=STATUS_AMBIGUOUS if cierre_warned else STATUS_SUPPORTED,
                reason="Momento de cierre extraído de la sesión.",
                action_required="Confirmar consigna de conclusión y entrega.",
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=cierre_page,
                        excerpt=cierre_action[:200],
                    )
                ],
            )
        else:
            fields["cierre"] = InterpretedField(
                name="cierre",
                value="",
                origin=ORIGIN_PROPOSED,
                status=STATUS_MISSING,
                reason="No se detectó momento de cierre explícito.",
                action_required="Redactar cierre o síntesis de sesión.",
            )

        # 4. Materiales / Recursos field
        if final_recursos:
            recursos_page = _find_chunk_page(final_recursos, primary_page)
            fields["materiales"] = InterpretedField(
                name="materiales",
                value=final_recursos,
                origin=ORIGIN_EXTRACTED,
                status=STATUS_AMBIGUOUS if (recursos_page in page_warnings or is_warned) else STATUS_SUPPORTED,
                reason="Recursos y materiales requeridos extraídos de la sesión.",
                action_required="Comprobar disponibilidad física en el aula.",
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=recursos_page,
                        excerpt=final_recursos[:200],
                    )
                ],
            )
        else:
            fields["materiales"] = InterpretedField(
                name="materiales",
                value="",
                origin=ORIGIN_PROPOSED,
                status=STATUS_MISSING,
                reason="No se explicitó columna de recursos en la sesión.",
                action_required="Especificar materiales necesarios.",
            )

        # 5. Evaluación field
        if evaluacion_text:
            eval_page = _find_chunk_page(evaluacion_text, primary_page)
            fields["evaluacion"] = InterpretedField(
                name="evaluacion",
                value=evaluacion_text,
                origin=ORIGIN_EXTRACTED,
                status=STATUS_AMBIGUOUS if (eval_page in page_warnings or is_warned) else STATUS_SUPPORTED,
                reason="Criterios e instrumentos de evaluación formativa extraídos de la sesión.",
                action_required="Validar criterios formativos.",
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=eval_page,
                        excerpt=evaluacion_text[:200],
                    )
                ],
            )
        else:
            fields["evaluacion"] = InterpretedField(
                name="evaluacion",
                value="",
                origin=ORIGIN_PROPOSED,
                status=STATUS_MISSING,
                reason="No se explicitó evaluación formativa en el bloque.",
                action_required="Definir cómo se valorará el avance.",
            )

        # 6. Contexto de ejecución (Sol Advanced Audit: distinct from project scenario; no false 'Aula' extractions)
        has_home_task = bool(
            re.search(
                r"(?:tarea\s+(?:para\s+(?:la\s+)?)?casa|en\s+casa|llevar\s+de\s+tarea|de\s+tarea\b|domicili|familiar\b)",
                cierre_action or block_text,
                re.IGNORECASE,
            )
        )
        if has_home_task:
            ctx_page = _find_chunk_page(cierre_action or block_text, primary_page)
            fields["contexto_ejecucion"] = InterpretedField(
                name="contexto_ejecucion",
                value="Aula (Inicio/Desarrollo) con entrega o tarea en Casa (Cierre)",
                origin=ORIGIN_PROPOSED,
                status=STATUS_AMBIGUOUS,
                reason=(
                    "El escenario general o contexto presencial se combina con actividad domiciliaria "
                    "detectada en la sesión. Resumen compuesto propuesto, no extracción literal."
                ),
                action_required=(
                    "Confirmar si la sesión se concluye enteramente en el salón o incluye "
                    "trabajo extraescolar en casa con apoyo familiar."
                ),
                evidence=[
                    SourceReference(
                        document_sha256=sha256,
                        page_number=ctx_page,
                        excerpt=cierre_action[:200] if cierre_action else block_text[:200],
                    )
                ],
            )
        else:
            explicit_loc_match = re.search(
                r"\b(?:lugar(?:\s+de\s+ejecución)?\s*[:\-]\s*([^\n\.,;]+)|(?:se\s+llevará\s+a\s+cabo\s+en|actividades\s+a\s+desarrollar\s+en|en)\s+(el\s+aula|el\s+salón|el\s+patio|la\s+biblioteca|el\s+laboratorio|la\s+cancha))\b",
                block_text,
                re.IGNORECASE,
            )
            if explicit_loc_match:
                raw_loc = explicit_loc_match.group(1) or explicit_loc_match.group(2)
                loc_val = raw_loc.strip().capitalize()
                start_idx = max(0, explicit_loc_match.start() - 20)
                end_idx = min(len(block_text), explicit_loc_match.end() + 60)
                loc_page = _find_chunk_page(block_text[start_idx:end_idx], primary_page)
                fields["contexto_ejecucion"] = InterpretedField(
                    name="contexto_ejecucion",
                    value=loc_val,
                    origin=ORIGIN_EXTRACTED,
                    status=STATUS_AMBIGUOUS if (loc_page in page_warnings or is_warned) else STATUS_SUPPORTED,
                    reason=f"Lugar de ejecución literal extraído del texto de la sesión ('{loc_val}').",
                    action_required="Confirmar disponibilidad del espacio escolar.",
                    evidence=[
                        SourceReference(
                            document_sha256=sha256,
                            page_number=loc_page,
                            excerpt=block_text[start_idx:end_idx].strip(),
                        )
                    ],
                )
            else:
                fields["contexto_ejecucion"] = InterpretedField(
                    name="contexto_ejecucion",
                    value="",
                    origin=ORIGIN_PROPOSED,
                    status=STATUS_MISSING,
                    reason=(
                        "No se explicitó un lugar de ejecución en el texto de la sesión "
                        "(el escenario general del proyecto no equivale a lugar de ejecución de la sesión)."
                    ),
                    action_required="Definir el espacio de trabajo específico (aula, patio, biblioteca u otro).",
                    evidence=[],
                )

        # 7. Annex references
        annex_refs = cls._detect_annex_references_in_session(
            session_text=block_text,
            session_pages=pages,
            sha256=sha256,
            annex_candidates=annex_candidates,
            page_segments=page_segments,
            pages_text=pages_text,
        )
        _ensure_session_annex_ids(session_id, annex_refs)

        # 8. Activities
        activities = cls._detect_activities_in_session(
            session_id=session_id,
            session_text=block_text,
            session_pages=pages,
            sha256=sha256,
            annex_refs=annex_refs,
            page_segments=page_segments,
        )

        return SessionPlan(
            session_id=session_id,
            session_number=session_number,
            title=title,
            project_title=project_title,
            day_of_week=day_of_week,
            pages=list(pages),
            continues_on=list(continues_on),
            layout_fidelity=layout_fidelity,
            layout_notes=layout_notes,
            fields=fields,
            annex_references=annex_refs,
            activities=activities,
            status=STATUS_SUPPORTED,
            review=REVIEW_PENDING,
        )

    @classmethod
    def _detect_annex_references_in_session(
        cls,
        session_text: str,
        session_pages: list[int],
        sha256: str,
        annex_candidates: list[dict[str, Any]],
        page_segments: list[tuple[int, str]] | None = None,
        pages_text: list[str] | None = None,
    ) -> list[AnnexReference]:
        """Detect annex mentions in session text and match candidate sheets with exact page provenance."""
        detected_numbers: set[str] = set()
        mentions: list[dict[str, Any]] = []

        pattern = re.compile(
            r"(?:anexos?|cuadernillo\s+de\s+actividades\s+anexos?)\s*(\d+(?:\s*(?:,|y)\s*\d+)*)",
            re.IGNORECASE,
        )

        if page_segments:
            for seg_page, seg_text in page_segments:
                for match in pattern.finditer(seg_text):
                    raw_mention = match.group(0)
                    numbers_part = match.group(1)
                    found_nums = re.findall(r"\d+", numbers_part)
                    for num in found_nums:
                        norm_num = str(int(num))
                        detected_numbers.add(norm_num)
                        mentions.append({
                            "number": norm_num,
                            "raw": raw_mention,
                            "page": seg_page,
                        })
        else:
            for match in pattern.finditer(session_text):
                raw_mention = match.group(0)
                numbers_part = match.group(1)
                found_nums = re.findall(r"\d+", numbers_part)

                mention_page = session_pages[0] if session_pages else 1
                if pages_text and len(session_pages) > 1:
                    raw_lower = raw_mention.lower()
                    for p in session_pages:
                        if 1 <= p <= len(pages_text):
                            if raw_lower in pages_text[p - 1].lower():
                                mention_page = p
                                break

                for num in found_nums:
                    norm_num = str(int(num))
                    detected_numbers.add(norm_num)
                    mentions.append({
                        "number": norm_num,
                        "raw": raw_mention,
                        "page": mention_page,
                    })

        annex_references: list[AnnexReference] = []
        for num in sorted(detected_numbers, key=lambda x: int(x)):
            matching_sheets = [
                c for c in annex_candidates if str(int(c["number"])) == num
            ]
            candidate_pages = [c["page"] for c in matching_sheets]

            num_mentions = [m for m in mentions if m["number"] == num]
            mention_pages = sorted(list({m["page"] for m in num_mentions}))
            source_pages = mention_pages if mention_pages else (list(session_pages) if session_pages else [1])

            raw_rep = num_mentions[0]["raw"] if num_mentions else f"Anexo {num}"

            # Evidence for mention: cites exact mention page(s)
            evidence: list[SourceReference] = []
            for p in source_pages:
                p_mentions = [m["raw"] for m in num_mentions if m["page"] == p]
                rep_for_page = p_mentions[0] if p_mentions else raw_rep
                evidence.append(
                    SourceReference(
                        document_sha256=sha256,
                        page_number=p,
                        excerpt=rep_for_page,
                    )
                )

            # Evidence for candidate sheet(s): cites candidate page(s)
            if candidate_pages:
                for c in matching_sheets:
                    evidence.append(
                        SourceReference(
                            document_sha256=sha256,
                            page_number=c["page"],
                            printed_label=c.get("label", f"ANEXO {num}"),
                            excerpt=c.get("label", f"ANEXO {num}"),
                        )
                    )
                status = STATUS_SUPPORTED
                pages_desc = f"pág. {source_pages[0]}" if len(source_pages) == 1 else f"págs. {', '.join(str(p) for p in source_pages)}"
                reason = (
                    f"Anexo {num} referenciado en sesión ({pages_desc}); "
                    f"lámina candidata identificada en pág. {candidate_pages[0]}."
                )
                action_required = (
                    f"Abrir y revisar la lámina en la página {candidate_pages[0]} "
                    "para confirmar su adecuación antes de vincular o imprimir."
                )
            else:
                status = STATUS_MISSING
                pages_desc = f"pág. {source_pages[0]}" if len(source_pages) == 1 else f"págs. {', '.join(str(p) for p in source_pages)}"
                reason = (
                    f"Anexo {num} mencionado en la sesión ({pages_desc}) pero no se detectó "
                    "lámina con encabezado 'ANEXO' en el documento PDF."
                )
                action_required = "Localizar la lámina en otro documento o digitalizar el material."

            # P0-3: NEVER auto-confirm candidates. confirmed_page MUST start as None.
            annex_references.append(
                AnnexReference(
                    annex_number=num,
                    raw_mention=raw_rep,
                    source_pages=source_pages,
                    candidate_pages=candidate_pages,
                    status=status,
                    review=REVIEW_PENDING,
                    reason=reason,
                    original_reason=reason,
                    action_required=action_required,
                    evidence=evidence,
                    confirmed_page=None,
                )
            )

        return annex_references

    @classmethod
    def _detect_activities_in_session(
        cls,
        session_id: str,
        session_text: str,
        session_pages: list[int],
        sha256: str,
        annex_refs: list[AnnexReference],
        page_segments: list[tuple[int, str]] | None = None,
    ) -> list[SessionActivity]:
        """Detect activities within a session indicated by the source, with evidence and annex relations."""
        activities: list[SessionActivity] = []
        segments = page_segments or [(session_pages[0] if session_pages else 1, session_text)]

        act_pattern = re.compile(
            r"(?:^|\n)\s*Actividad\s*(\d+|[A-Za-z])?\s*[:.-]?\s*([^\n\r]+)",
            re.IGNORECASE,
        )

        order = 0
        for seg_page, seg_text in segments:
            for match in act_pattern.finditer(seg_text):
                num_group = match.group(1)
                text_group = (match.group(2) or "").strip()
                if not text_group or len(text_group) < 3:
                    continue
                order += 1
                matched_text = match.group(0).strip()
                title = f"Actividad {num_group}: {text_group[:40]}" if num_group else f"Actividad {order}: {text_group[:40]}"
                description = text_group
                excerpt = matched_text[:80].strip()

                linked_annex_ids: list[str] = []
                annex_ev_map: dict[str, list[SourceReference]] = {}

                for ar in (annex_refs or []):
                    ref_id = getattr(ar, "reference_id", "")
                    annex_num = str(getattr(ar, "annex_number", ""))
                    raw_mention = getattr(ar, "raw_mention", "")
                    is_linked = False
                    if annex_num and re.search(rf"\banexos?\s*.*?\b{re.escape(annex_num)}\b", matched_text, re.IGNORECASE):
                        is_linked = True
                    elif raw_mention and raw_mention.lower() in matched_text.lower():
                        is_linked = True
                    elif ref_id and ref_id in matched_text:
                        is_linked = True

                    if is_linked and ref_id:
                        if ref_id not in linked_annex_ids:
                            linked_annex_ids.append(ref_id)
                        annex_ev_map[ref_id] = [
                            SourceReference(
                                document_sha256=sha256,
                                page_number=seg_page,
                                excerpt=excerpt,
                            )
                        ]

                ev = [
                    SourceReference(
                        document_sha256=sha256,
                        page_number=seg_page,
                        excerpt=excerpt,
                    )
                ]

                activities.append(
                    SessionActivity(
                        activity_id=f"{session_id}_act_{order}",
                        title=title,
                        description=description,
                        order=order,
                        annex_ids=linked_annex_ids,
                        evidence=ev,
                        annex_evidence=annex_ev_map,
                    )
                )

        return activities



def _recompute_session_review(session: SessionPlan) -> None:
    """Derive SessionPlan.review strictly from its constituent fields and annexes (Sol Item 3)."""
    all_fields_ok = all(
        f.review in (REVIEW_CONFIRMED, REVIEW_CORRECTED) and f.status == STATUS_SUPPORTED
        for f in session.fields.values()
    )
    all_annexes_ok = all(
        ar.confirmed_page is not None and ar.review == REVIEW_CONFIRMED
        for ar in session.annex_references
    )
    if all_fields_ok and all_annexes_ok:
        session.review = REVIEW_CONFIRMED
    else:
        session.review = REVIEW_PENDING


def normalize_campos_formativos(val: Any) -> list[str]:
    """Normalize campos_formativos from either string (legacy) or list into a clean list of strings.
    Atomic: a single string is NOT split by commas/semicolons/newlines.
    """
    if val is None:
        return []
    if isinstance(val, str):
        s = val.strip()
        return [s] if s else []
    if isinstance(val, (list, tuple, set)):
        res: list[str] = []
        for item in val:
            if isinstance(item, str):
                s = item.strip()
                if s and s not in res:
                    res.append(s)
            elif isinstance(item, (list, tuple, set)):
                for sub in item:
                    if isinstance(sub, str):
                        s = sub.strip()
                        if s and s not in res:
                            res.append(s)
        return res
    return []


def derive_campos_formativos_options(raw_val: Any) -> list[dict[str, Any]]:
    """Derive list of options with exact selection state for campos_formativos.
    - Canonical options are always included in order.
    - If raw_val contains legacy non-canonical strings, they are included as intact options.
    - If raw_val is str: selected strictly by exact equality (opt == raw_val.strip()), NO substring matching.
    - If raw_val is list/tuple: selected strictly by element equality.
    """
    options_order = list(CANONICAL_CAMPOS)
    normalized = normalize_campos_formativos(raw_val)
    for c in normalized:
        if c and c not in options_order:
            options_order.append(c)

    result = []
    if isinstance(raw_val, str):
        target = raw_val.strip()
        for opt in options_order:
            result.append({
                "value": opt,
                "selected": opt == target if target else False,
            })
    elif isinstance(raw_val, (list, tuple, set)):
        targets = {str(x).strip() for x in raw_val if str(x).strip()}
        for opt in options_order:
            result.append({
                "value": opt,
                "selected": opt in targets,
            })
    else:
        for opt in options_order:
            result.append({
                "value": opt,
                "selected": False,
            })
    return result


def _normalize_value(val: Any) -> Any:
    """Normalize whitespace and linebreaks (CRLF/CR -> LF) for comparison and persistence."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(val, (list, tuple)):
        return [_normalize_value(x) for x in val if x is not None]
    return val


def _values_are_semantically_equal(v1: Any, v2: Any) -> bool:
    """Check semantic equivalence between current dossier value and submitted value."""
    if _is_empty_value(v1) and _is_empty_value(v2):
        return True
    norm1 = _normalize_value(v1)
    norm2 = _normalize_value(v2)
    if isinstance(norm1, str) and isinstance(norm2, str):
        return norm1.strip() == norm2.strip()
    if isinstance(norm1, list) and isinstance(norm2, list):
        return [str(x).strip() for x in norm1 if str(x).strip()] == [str(x).strip() for x in norm2 if str(x).strip()]
    if isinstance(norm1, str) and isinstance(norm2, list):
        return [norm1.strip()] == [str(x).strip() for x in norm2 if str(x).strip()]
    if isinstance(norm1, list) and isinstance(norm2, str):
        return [str(x).strip() for x in norm1 if str(x).strip()] == [norm2.strip()]
    return norm1 == norm2



def _session_content_fingerprint(s: SessionPlan) -> str:
    """Compute a deterministic hash of the pedagogical content of a session."""
    parts = []
    for k in sorted(s.fields.keys()):
        f = s.fields[k]
        val_str = json.dumps(f.value, sort_keys=True, default=str) if f.value is not None else ""
        parts.append(f"{k}:{val_str}")
    for r in sorted(s.annex_references, key=lambda a: (str(a.annex_number), str(a.raw_mention))):
        parts.append(f"annex:{r.annex_number}:{r.raw_mention}")
    content_repr = "|".join(parts)
    return hashlib.sha256(content_repr.encode("utf-8")).hexdigest()[:16]


def preserve_reextract_decisions(old: ImportDossier | None, fresh: ImportDossier, pdf_source: Any) -> list[dict[str, Any]]:
    """Reapply human work only inside a proven, unchanged source occurrence.

    Raw extraction changes and these decision snapshots are retained separately
    in reextract history. No title joins, no cross-SHA transfers, and no new
    extracted value inherits a confirmation from a different baseline.
    """
    if old is None:
        return []
    from curriculum.verification import read_physical_pdf_source

    _, source_sha, pages = read_physical_pdf_source(pdf_source)
    same_source = old.source_sha256 == fresh.source_sha256 == source_sha
    segments = scan_session_segments(pages, source_sha)
    deltas = []

    def human_field(f: InterpretedField) -> bool:
        return f.origin == ORIGIN_TEACHER_ENTERED or f.review in (REVIEW_CONFIRMED, REVIEW_CORRECTED, "postponed")

    def record(scope, sid, name, before, after, change, reason):
        deltas.append(_make_history_delta(
            scope=scope, session_id=sid, field=name, before=before, after=after,
            change_type=change, reason=reason,
        ))

    def merge_fields(previous, current, scope, sid, safe, source_uncertain=False):
        for name, previous_field in previous.items():
            if not isinstance(previous_field, InterpretedField) or not human_field(previous_field):
                continue
            extracted = current.get(name) if current is not None else None
            before = previous_field.to_dict()
            if not safe:
                record(scope, sid, name, before, extracted.to_dict() if extracted else None,
                       "decision_not_reapplied", "Decisión conservada en historial; fuente u ocurrencia sin correspondencia unívoca.")
                continue
            baseline = previous_field.original_value if previous_field.origin == ORIGIN_TEACHER_ENTERED else previous_field.value
            old_evidence = before["evidence"]
            unchanged = not source_uncertain and extracted is not None and _values_are_semantically_equal(baseline, extracted.value) and old_evidence == extracted.to_dict()["evidence"]
            if unchanged:
                current[name] = copy.deepcopy(previous_field)
                record(scope, sid, name, before, current[name].to_dict(), "retained_decision",
                       "Decisión humana preservada en la misma fuente y ocurrencia; extracción de base sin cambios.")
            elif previous_field.origin == ORIGIN_TEACHER_ENTERED:
                # Retain the author's value/provenance, never bless a newly
                # segmented interpretation on the strength of an old decision.
                retained = copy.deepcopy(previous_field)
                retained.review = REVIEW_PENDING
                retained.reason = "La reextracción cambió la base de esta decisión docente; se conserva su valor y procedencia y requiere revisión."
                retained.current_action = retained.action_required = derive_field_operational_state(retained)[1]
                current[name] = retained
                record(scope, sid, name, before, retained.to_dict(), "decision_requires_review", retained.reason)
            else:
                if extracted:
                    extracted.review = REVIEW_PENDING
                    extracted.reason += " La decisión anterior se conserva en historial y no se aplica al contenido cambiado por reextracción."
                    extracted.current_action = extracted.action_required = derive_field_operational_state(extracted)[1]
                record(scope, sid, name, before, extracted.to_dict() if extracted else None,
                       "decision_requires_review", "La nueva extracción no hereda la confirmación o el aplazamiento de un valor distinto.")

    merge_fields(old.general_fields, fresh.general_fields, "general", None, same_source)
    old_ids = [s.session_id for s in old.sessions]
    new_ids = [s.session_id for s in fresh.sessions]
    for previous in old.sessions:
        sid = previous.session_id
        current = next((s for s in fresh.sessions if s.session_id == sid), None)
        match = match_session_segment(previous.to_dict(), segments)
        safe = bool(same_source and current and old_ids.count(sid) == new_ids.count(sid) == 1 and match)
        if safe and previous.header_anchor is not None:
            safe = anchor_matches(previous.header_anchor, match.header_anchor) and anchor_matches(current.header_anchor, match.header_anchor)
        elif safe:
            # Legacy canonical IDs by themselves do not disambiguate repeated
            # numbers; there must be only one source occurrence on this page.
            safe = len([s for s in segments if s.session_number == previous.session_number and s.header_anchor["page_number"] == previous.pages[0]]) == 1
            if safe:
                bounded = {p: normalize_text_for_evidence_check(text) for p, text in match.page_segments}
                safe = all(
                    isinstance(ev, SourceReference) and ev.document_sha256 == source_sha
                    and normalize_text_for_evidence_check(ev.excerpt) in bounded.get(ev.page_number, "")
                    for f in previous.fields.values() for ev in f.evidence
                )
        merge_fields(previous.fields, current.fields if current else None, "session", sid, safe, bool(match and match.unassigned_segments))
        for ref in previous.annex_references:
            if ref.review not in (REVIEW_CONFIRMED, REVIEW_CORRECTED, "postponed") and ref.confirmed_page is None:
                continue
            candidates = [r for r in current.annex_references if r.reference_id == ref.reference_id] if current else []
            same_reference = len(candidates) == 1 and ref.raw_mention == candidates[0].raw_mention and ref.source_pages == candidates[0].source_pages
            old_ev = [e.to_dict() for e in ref.evidence if isinstance(e, SourceReference) and e.role != "teacher_selected_source_page"]
            if safe and same_reference and old_ev == [e.to_dict() for e in candidates[0].evidence]:
                current.annex_references[current.annex_references.index(candidates[0])] = copy.deepcopy(ref)
                record("annex", sid, ref.reference_id, ref.to_dict(), ref.to_dict(), "retained_decision", "Asociación humana conservada para la misma referencia física.")
            else:
                record("annex", sid, ref.reference_id, ref.to_dict(), candidates[0].to_dict() if len(candidates) == 1 else None,
                       "decision_not_reapplied", "Asociación previa conservada en historial; no se traslada a otra ocurrencia.")
        if current:
            _recompute_session_review(current)
    return deltas


def compute_reextract_diff(old_d: ImportDossier | None, new_d: ImportDossier) -> list[dict[str, Any]]:
    """Compute structured delta diff between old dossier and newly re-extracted dossier.
    Matches sessions by content fingerprint within semantic groups (project+title+session_number)
    with fallbacks to deterministic 1-to-1 matching, session_id and unique session_number.
    Detects page moves as 'modified' session_id with complete SessionPlan before/after snapshots.
    Preserves annex continuity across session page moves.
    """
    deltas: list[dict[str, Any]] = []
    if old_d is None:
        return deltas

    # 1. General fields
    all_gen_keys = sorted(set(old_d.general_fields.keys()) | set(new_d.general_fields.keys()))
    for k in all_gen_keys:
        old_f = old_d.general_fields.get(k)
        new_f = new_d.general_fields.get(k)
        if old_f is None and new_f is not None:
            deltas.append(_make_history_delta(
                scope="general",
                field=k,
                change_type="added",
                before=None,
                after=_snapshot_field_for_delta(new_f),
            ))
        elif old_f is not None and new_f is None:
            deltas.append(_make_history_delta(
                scope="general",
                field=k,
                change_type="removed",
                before=_snapshot_field_for_delta(old_f),
                after=None,
            ))
        elif old_f is not None and new_f is not None:
            if (
                not _values_are_semantically_equal(old_f.value, new_f.value)
                or old_f.status != new_f.status
                or old_f.review != new_f.review
                or old_f.origin != new_f.origin
                or old_f.reason != new_f.reason
                or old_f.current_action != new_f.current_action
            ):
                deltas.append(_make_history_delta(
                    scope="general",
                    field=k,
                    change_type="modified",
                    before=_snapshot_field_for_delta(old_f),
                    after=_snapshot_field_for_delta(new_f),
                ))

    # 2. Session matching and diff
    matched_pairs: list[tuple[SessionPlan, SessionPlan, str]] = []
    unmatched_new = list(new_d.sessions)
    unmatched_old: list[SessionPlan] = []

    def _header_key(s: SessionPlan) -> tuple[str, str, int]:
        return (
            (s.project_title or "").strip().lower(),
            (s.title or "").strip().lower(),
            int(s.session_number),
        )

    old_groups: dict[tuple[str, str, int], list[SessionPlan]] = {}
    for s in old_d.sessions:
        hk = _header_key(s)
        old_groups.setdefault(hk, []).append(s)

    for hk, old_group in old_groups.items():
        new_candidates = [s for s in unmatched_new if _header_key(s) == hk]

        # Pass 1a: match by content fingerprint
        still_unmatched_in_group: list[SessionPlan] = []
        for old_s in old_group:
            old_fp = _session_content_fingerprint(old_s)
            found_idx = next(
                (i for i, ns in enumerate(new_candidates) if _session_content_fingerprint(ns) == old_fp),
                None,
            )
            if found_idx is not None:
                new_s = new_candidates.pop(found_idx)
                unmatched_new.remove(new_s)
                sem_key = f"{hk[0]}|{hk[1]}|{hk[2]}|fp_{old_fp}"
                matched_pairs.append((old_s, new_s, sem_key))
            else:
                still_unmatched_in_group.append(old_s)

        # Pass 1b: evaluate remaining in group
        if len(still_unmatched_in_group) == 1 and len(new_candidates) == 1:
            old_s = still_unmatched_in_group.pop(0)
            new_s = new_candidates.pop(0)
            unmatched_new.remove(new_s)
            sem_key = f"{hk[0]}|{hk[1]}|{hk[2]}|modified"
            matched_pairs.append((old_s, new_s, sem_key))
        elif len(still_unmatched_in_group) > 0 and len(new_candidates) > 0:
            # Multiple sessions remain without fingerprint match in same semantic group.
            # Do NOT pair them 1-to-1 in order (no false A->B').
            # Emit explicit group delta with change_type="ambiguous_identity".
            ambig_delta = _make_history_delta(
                scope="session",
                field="sessions",
                change_type="ambiguous_identity",
                before=[copy.deepcopy(s.to_dict()) for s in still_unmatched_in_group],
                after=[copy.deepcopy(s.to_dict()) for s in new_candidates],
                stable_id=f"{hk[0]}|{hk[1]}|{hk[2]}|ambiguous",
                reason="Imposibilidad de determinar continuidad unívoca: múltiples sesiones con idéntico encabezado modificaron su contenido simultáneamente.",
                confidence="ambiguous",
            )
            deltas.append(ambig_delta)
            for ns in new_candidates:
                unmatched_new.remove(ns)
            still_unmatched_in_group.clear()
            new_candidates.clear()
        else:
            for old_s in still_unmatched_in_group:
                unmatched_old.append(old_s)

    # Fallback 1: match by session_id among remaining
    still_unmatched_old: list[SessionPlan] = []
    for old_s in unmatched_old:
        found_idx = next((i for i, ns in enumerate(unmatched_new) if ns.session_id == old_s.session_id), None)
        if found_idx is not None:
            new_s = unmatched_new.pop(found_idx)
            matched_pairs.append((old_s, new_s, old_s.session_id))
        else:
            still_unmatched_old.append(old_s)

    # Fallback 2: match by unique session_number if unambiguous among remaining
    truly_unmatched_old: list[SessionPlan] = []
    for old_s in still_unmatched_old:
        cands = [i for i, ns in enumerate(unmatched_new) if ns.session_number == old_s.session_number]
        if len(cands) == 1:
            new_s = unmatched_new.pop(cands[0])
            matched_pairs.append((old_s, new_s, f"s_num_{old_s.session_number}"))
        else:
            truly_unmatched_old.append(old_s)

    # Process matched sessions
    for old_s, new_s, sem_key in matched_pairs:
        # Check if session moved physical page / session_id
        if old_s.session_id != new_s.session_id or old_s.pages != new_s.pages:
            sid_delta = _make_history_delta(
                scope="session",
                field="session_id",
                change_type="modified",
                before=copy.deepcopy(old_s.to_dict()),
                after=copy.deepcopy(new_s.to_dict()),
                session_id=new_s.session_id,
                stable_id=sem_key,
            )
            sid_delta["previous_session_id"] = old_s.session_id
            sid_delta["current_session_id"] = new_s.session_id
            deltas.append(sid_delta)

        # Compare session fields
        all_s_keys = sorted(set(old_s.fields.keys()) | set(new_s.fields.keys()))
        for sf_name in all_s_keys:
            old_sf = old_s.fields.get(sf_name)
            new_sf = new_s.fields.get(sf_name)
            if old_sf is None and new_sf is not None:
                deltas.append(_make_history_delta(
                    scope="session",
                    session_id=new_s.session_id,
                    field=sf_name,
                    change_type="added",
                    before=None,
                    after=_snapshot_field_for_delta(new_sf),
                    stable_id=f"{sem_key}.{sf_name}",
                ))
            elif old_sf is not None and new_sf is None:
                deltas.append(_make_history_delta(
                    scope="session",
                    session_id=new_s.session_id,
                    field=sf_name,
                    change_type="removed",
                    before=_snapshot_field_for_delta(old_sf),
                    after=None,
                    stable_id=f"{sem_key}.{sf_name}",
                ))
            elif old_sf is not None and new_sf is not None:
                if (
                    not _values_are_semantically_equal(old_sf.value, new_sf.value)
                    or old_sf.status != new_sf.status
                    or old_sf.review != new_sf.review
                    or old_sf.origin != new_sf.origin
                    or old_sf.reason != new_sf.reason
                    or old_sf.current_action != new_sf.current_action
                ):
                    deltas.append(_make_history_delta(
                        scope="session",
                        session_id=new_s.session_id,
                        field=sf_name,
                        change_type="modified",
                        before=_snapshot_field_for_delta(old_sf),
                        after=_snapshot_field_for_delta(new_sf),
                        stable_id=f"{sem_key}.{sf_name}",
                    ))

        # Annexes comparison (first by reference_id, then fallback by annex_number)
        matched_annex_pairs: list[tuple[AnnexReference, AnnexReference, str]] = []
        unmatched_new_refs = list(new_s.annex_references)
        unmatched_old_refs: list[AnnexReference] = []

        # Pass 1: exact reference_id match
        for old_r in old_s.annex_references:
            found_idx = next(
                (i for i, nr in enumerate(unmatched_new_refs) if nr.reference_id and nr.reference_id == old_r.reference_id),
                None,
            )
            if found_idx is not None:
                new_r = unmatched_new_refs.pop(found_idx)
                matched_annex_pairs.append((old_r, new_r, old_r.reference_id))
            else:
                unmatched_old_refs.append(old_r)

        # Pass 2: fallback match by annex_number
        still_unmatched_old_refs: list[AnnexReference] = []
        for old_r in unmatched_old_refs:
            found_idx = next(
                (i for i, nr in enumerate(unmatched_new_refs) if str(nr.annex_number) == str(old_r.annex_number)),
                None,
            )
            if found_idx is not None:
                new_r = unmatched_new_refs.pop(found_idx)
                matched_annex_pairs.append((old_r, new_r, old_r.reference_id or new_r.reference_id or f"annex_{old_r.annex_number}"))
            else:
                still_unmatched_old_refs.append(old_r)

        for old_r, new_r, a_stable_id in matched_annex_pairs:
            old_snap = _snapshot_annex_for_delta(old_r)
            new_snap = _snapshot_annex_for_delta(new_r)
            if old_snap != new_snap:
                deltas.append(_make_history_delta(
                    scope="annex",
                    session_id=new_s.session_id,
                    field=new_r.reference_id or a_stable_id,
                    change_type="modified",
                    before=old_snap,
                    after=new_snap,
                    stable_id=a_stable_id,
                ))

        for old_r in still_unmatched_old_refs:
            deltas.append(_make_history_delta(
                scope="annex",
                session_id=new_s.session_id,
                field=old_r.reference_id or f"annex_{old_r.annex_number}",
                change_type="removed",
                before=_snapshot_annex_for_delta(old_r),
                after=None,
                stable_id=old_r.reference_id or f"annex_{old_r.annex_number}",
            ))

        for new_r in unmatched_new_refs:
            deltas.append(_make_history_delta(
                scope="annex",
                session_id=new_s.session_id,
                field=new_r.reference_id or f"annex_{new_r.annex_number}",
                change_type="added",
                before=None,
                after=_snapshot_annex_for_delta(new_r),
                stable_id=new_r.reference_id or f"annex_{new_r.annex_number}",
            ))

    # Truly removed sessions
    for old_s in truly_unmatched_old:
        deltas.append(_make_history_delta(
            scope="session",
            session_id=old_s.session_id,
            field="session",
            change_type="removed",
            before=copy.deepcopy(old_s.to_dict()),
            after=None,
            stable_id=old_s.session_id,
        ))

    # Truly added sessions
    for new_s in unmatched_new:
        deltas.append(_make_history_delta(
            scope="session",
            session_id=new_s.session_id,
            field="session",
            change_type="added",
            before=None,
            after=copy.deepcopy(new_s.to_dict()),
            stable_id=new_s.session_id,
        ))

    return deltas


def resolve(
    dossier: ImportDossier,
    corrections: dict[str, Any],
    actor: str = "Docente",
    pdf_source: Any = None,
) -> ImportDossier:
    """Apply human editorial corrections, versioning the dossier and keeping evidence intact."""
    changes: list[str] = []
    deltas: list[dict[str, Any]] = []
    # B1: resolve accepts exclusively explicit pdf_source argument; corrections/payload cannot supply or override it.

    # B3: Normalize any legacy empty fields so empty fields never remain confirmed or corrected
    for g_f in dossier.general_fields.values():
        if _is_empty_value(g_f.value):
            if g_f.review in (REVIEW_CONFIRMED, REVIEW_CORRECTED):
                g_f.review = REVIEW_PENDING
            if g_f.status == STATUS_SUPPORTED:
                g_f.status = STATUS_MISSING
            _, act = derive_field_operational_state(g_f)
            g_f.current_action = act
            g_f.action_required = act
    for sess in dossier.sessions:
        for sf in sess.fields.values():
            if _is_empty_value(sf.value):
                if sf.review in (REVIEW_CONFIRMED, REVIEW_CORRECTED):
                    sf.review = REVIEW_PENDING
                if sf.status == STATUS_SUPPORTED:
                    sf.status = STATUS_MISSING
                _, act = derive_field_operational_state(sf)
                sf.current_action = act
                sf.action_required = act

    # 1. Identify target session by session_id or session_number (Sol Item 2 & Gate Final: strict validation, no fallback)
    matching_session = None
    target_id = corrections.get("session_id")
    target_s_num = None

    # B4: If session_number is supplied (even ''), validate its canonical form before any mutation
    if "session_number" in corrections:
        raw_s_num = corrections["session_number"]
        try:
            target_s_num = parse_canonical_positive_int(raw_s_num)
        except ValueError:
            raise SelectionError(f"Número de sesión no canónico o inválido en 'session_number': {raw_s_num!r}")

    if target_id is not None and str(target_id).strip() != "":
        target_id_str = str(target_id).strip()
        matching_session = dossier.get_session(target_id_str)
        if matching_session is None:
            raise SelectionError(f"La sesión con ID '{target_id_str}' no existe en el documento.")
        if target_s_num is not None and matching_session.session_number != target_s_num:
            raise SelectionError(
                f"Inconsistencia entre session_id '{target_id_str}' (sesión {matching_session.session_number}) "
                f"y session_number {target_s_num}."
            )
    elif target_s_num is not None:
        matching = [s for s in dossier.sessions if s.session_number == target_s_num]
        if len(matching) == 0:
            raise SelectionError(f"La sesión número {target_s_num} no existe en el documento.")
        elif len(matching) > 1:
            raise SelectionError(
                f"Selección ambigua: existen {len(matching)} sesiones con número {target_s_num}. "
                "Especifique session_id para desambiguar."
            )
        matching_session = matching[0]
    else:
        if corrections.get("session_fields") or corrections.get("annex_confirmations"):
            if dossier.selection.get("session_id"):
                matching_session = dossier.get_session(dossier.selection["session_id"])
            if matching_session is None:
                if len(dossier.sessions) == 1:
                    matching_session = dossier.sessions[0]
                elif len(dossier.sessions) > 1:
                    raise SelectionError(
                        "Se requieren correcciones de sesión pero no se especificó session_id."
                    )

    # Sol Item 2 & F6: Validate all annex confirmations BEFORE mutating or bumping version
    annex_confirmations = corrections.get("annex_confirmations", {}) or {}
    manual_annex_confirmations = corrections.get("manual_annex_confirmations", {}) or {}
    validated_annex_actions = []
    if matching_session is not None and annex_confirmations:
        for annex_key, page_choice in annex_confirmations.items():
            ref = _find_single_annex_ref(matching_session, annex_key)
            if page_choice is None or page_choice == "":
                validated_annex_actions.append((ref, annex_key, None, False))
            else:
                try:
                    p_int = parse_canonical_positive_int(page_choice)
                except ValueError:
                    raise ValueError(
                        f"Número de página inválido '{page_choice}' para Anexo {annex_key} "
                        f"(fuera de rango o formato no canónico; debe ser entero entre 1 y {dossier.page_count})."
                    )
                # F6 strict range validation: 1 <= page <= page_count
                if p_int < 1 or p_int > dossier.page_count:
                    raise ValueError(
                        f"Página {p_int} fuera de rango. El documento tiene {dossier.page_count} páginas."
                    )

                is_manual = False
                if (
                    annex_key in manual_annex_confirmations
                    or str(annex_key) in manual_annex_confirmations
                    or ref.reference_id in manual_annex_confirmations
                    or str(ref.annex_number) in manual_annex_confirmations
                ):
                    is_manual = True
                elif not ref.candidate_pages:
                    is_manual = True
                elif p_int in ref.candidate_pages:
                    is_manual = False
                else:
                    raise ValueError(
                        f"Página {p_int} no es una lámina candidata válida para el Anexo {annex_key}. "
                        f"Candidatos válidos: {ref.candidate_pages}."
                    )
                validated_annex_actions.append((ref, annex_key, p_int, is_manual))

    # Apply general fields corrections (only changed fields are updated; CRLF normalized; no false confirmations)
    general_corrections = corrections.get("general_fields")
    if general_corrections is not None and isinstance(general_corrections, dict):
        for field_name, new_val in general_corrections.items():
            if field_name == "campos_formativos":
                normalized_val = normalize_campos_formativos(new_val)
                if field_name in dossier.general_fields:
                    item = dossier.general_fields[field_name]
                    if not _values_are_semantically_equal(item.value, normalized_val):
                        before_snap = _snapshot_field_for_delta(item)
                        if item.original_value is None:
                            item.original_value = copy.deepcopy(item.value)
                        item.value = normalized_val
                        item.origin = ORIGIN_TEACHER_ENTERED
                        if _is_empty_value(normalized_val):
                            item.status = STATUS_MISSING
                            item.review = REVIEW_PENDING
                            state, act = derive_field_operational_state(item)
                            item.current_action = act
                            item.action_required = act
                            change_type = "cleared"
                        else:
                            item.status = STATUS_SUPPORTED
                            item.review = REVIEW_CORRECTED
                            state, act = derive_field_operational_state(item)
                            item.current_action = act
                            item.action_required = act
                            change_type = "modified"
                        after_snap = _snapshot_field_for_delta(item)
                        changes.append(f"Campo general '{field_name}' corregido por docente.")
                        deltas.append(_make_history_delta(
                            scope="general",
                            field=field_name,
                            change_type=change_type,
                            before=before_snap,
                            after=after_snap,
                        ))
                else:
                    if not _is_empty_value(normalized_val):
                        new_f = InterpretedField(
                            name=field_name,
                            value=normalized_val,
                            origin=ORIGIN_TEACHER_ENTERED,
                            status=STATUS_SUPPORTED,
                            review=REVIEW_CORRECTED,
                            reason="Ingresado manualmente por el docente durante la revisión.",
                            original_reason="Ingresado manualmente por el docente durante la revisión.",
                            action_required="",
                            current_action="",
                        )
                        dossier.general_fields[field_name] = new_f
                        after_snap = _snapshot_field_for_delta(new_f)
                        changes.append(f"Campo general '{field_name}' agregado por docente.")
                        deltas.append(_make_history_delta(
                            scope="general",
                            field=field_name,
                            change_type="added",
                            before=None,
                            after=after_snap,
                        ))
            elif field_name in dossier.general_fields:
                item = dossier.general_fields[field_name]
                if not _values_are_semantically_equal(item.value, new_val):
                    before_snap = _snapshot_field_for_delta(item)
                    persisted_val = _normalize_value(new_val)
                    if isinstance(persisted_val, str):
                        persisted_val = persisted_val.strip()
                    if item.original_value is None:
                        item.original_value = copy.deepcopy(item.value)
                    item.value = persisted_val
                    item.origin = ORIGIN_TEACHER_ENTERED
                    if _is_empty_value(persisted_val):
                        item.status = STATUS_MISSING
                        item.review = REVIEW_PENDING
                        state, act = derive_field_operational_state(item)
                        item.current_action = act
                        item.action_required = act
                        change_type = "cleared"
                    else:
                        item.status = STATUS_SUPPORTED
                        item.review = REVIEW_CORRECTED
                        state, act = derive_field_operational_state(item)
                        item.current_action = act
                        item.action_required = act
                        change_type = "modified"
                    after_snap = _snapshot_field_for_delta(item)
                    changes.append(f"Campo general '{field_name}' corregido por docente.")
                    deltas.append(_make_history_delta(
                        scope="general",
                        field=field_name,
                        change_type=change_type,
                        before=before_snap,
                        after=after_snap,
                    ))
            else:
                persisted_val = _normalize_value(new_val)
                if isinstance(persisted_val, str):
                    persisted_val = persisted_val.strip()
                if not _is_empty_value(persisted_val):
                    new_f = InterpretedField(
                        name=field_name,
                        value=persisted_val,
                        origin=ORIGIN_TEACHER_ENTERED,
                        status=STATUS_SUPPORTED,
                        review=REVIEW_CORRECTED,
                        reason="Ingresado manualmente por el docente durante la revisión.",
                        original_reason="Ingresado manualmente por el docente durante la revisión.",
                        action_required="",
                        current_action="",
                    )
                    dossier.general_fields[field_name] = new_f
                    after_snap = _snapshot_field_for_delta(new_f)
                    changes.append(f"Campo general '{field_name}' agregado por docente.")
                    deltas.append(_make_history_delta(
                        scope="general",
                        field=field_name,
                        change_type="added",
                        before=None,
                        after=after_snap,
                    ))

    # Apply session fields corrections (only changed fields are updated; CRLF normalized; no false confirmations)
    session_changed = False
    session_corrections = corrections.get("session_fields")
    if matching_session is not None and session_corrections is not None and isinstance(session_corrections, dict):
        for s_field_name, new_val in session_corrections.items():
            if s_field_name in matching_session.fields:
                field_obj = matching_session.fields[s_field_name]
                if not _values_are_semantically_equal(field_obj.value, new_val):
                    before_snap = _snapshot_field_for_delta(field_obj)
                    persisted_val = _normalize_value(new_val)
                    if isinstance(persisted_val, str):
                        persisted_val = persisted_val.strip()
                    if field_obj.original_value is None:
                        field_obj.original_value = copy.deepcopy(field_obj.value)
                    field_obj.value = persisted_val
                    field_obj.origin = ORIGIN_TEACHER_ENTERED
                    if _is_empty_value(persisted_val):
                        field_obj.status = STATUS_MISSING
                        field_obj.review = REVIEW_PENDING
                        state, act = derive_field_operational_state(field_obj)
                        field_obj.current_action = act
                        field_obj.action_required = act
                        change_type = "cleared"
                    else:
                        field_obj.status = STATUS_SUPPORTED
                        field_obj.review = REVIEW_CORRECTED
                        state, act = derive_field_operational_state(field_obj)
                        field_obj.current_action = act
                        field_obj.action_required = act
                        change_type = "modified"
                    after_snap = _snapshot_field_for_delta(field_obj)
                    changes.append(
                        f"Sesión {matching_session.session_number} '{s_field_name}' corregido por docente."
                    )
                    deltas.append(_make_history_delta(
                        scope="session",
                        session_id=matching_session.session_id,
                        field=s_field_name,
                        change_type=change_type,
                        before=before_snap,
                        after=after_snap,
                        stable_id=s_field_name,
                    ))
                    session_changed = True
            else:
                persisted_val = _normalize_value(new_val)
                if isinstance(persisted_val, str):
                    persisted_val = persisted_val.strip()
                if not _is_empty_value(persisted_val):
                    new_sf = InterpretedField(
                        name=s_field_name,
                        value=persisted_val,
                        origin=ORIGIN_TEACHER_ENTERED,
                        status=STATUS_SUPPORTED,
                        review=REVIEW_CORRECTED,
                        reason="Ingresado manualmente por el docente.",
                        original_reason="Ingresado manualmente por el docente.",
                        action_required="",
                        current_action="",
                    )
                    matching_session.fields[s_field_name] = new_sf
                    after_snap = _snapshot_field_for_delta(new_sf)
                    changes.append(f"Sesión {matching_session.session_number} '{s_field_name}' agregado.")
                    deltas.append(_make_history_delta(
                        scope="session",
                        session_id=matching_session.session_id,
                        field=s_field_name,
                        change_type="added",
                        before=None,
                        after=after_snap,
                        stable_id=s_field_name,
                    ))
                    session_changed = True

    # Apply validated annex confirmations (radio left empty or unchanged does NOT record a decision)
    from curriculum.verification import normalize_text_for_evidence_check, _read_pdf_source

    for ref, annex_key, p_int, is_manual in validated_annex_actions:
        annex_stable_id = ref.reference_id or f"annex_{ref.annex_number}"
        if p_int is not None:
            coherent_excerpt = ""
            target_excerpt = ""

            # 1. Physical text extraction from explicit authorized pdf_source
            norm_page_text = ""
            if pdf_source is not None:
                try:
                    _, actual_sha, pages_text = _read_pdf_source(pdf_source)
                    # Physical bounds and SHA ownership integrity:
                    if actual_sha.lower() == dossier.source_sha256.lower() and 1 <= p_int <= len(pages_text):
                        raw_page_text = pages_text[p_int - 1]
                        norm_page_text = normalize_text_for_evidence_check(raw_page_text)
                except Exception as exc:
                    logger.warning("Error leyendo pdf_source en resolve() para página %s: %s", p_int, exc)
                    norm_page_text = ""

            # 2. Excerpt matching: only against contiguous normalized substring in physical page text
            if norm_page_text:
                # A. Prior coherent evidence
                for ev in (ref.evidence or []):
                    if getattr(ev, "page_number", None) == p_int:
                        ev_sha = getattr(ev, "document_sha256", "") or ""
                        if ev_sha.lower() == dossier.source_sha256.lower():
                            ev_ex = getattr(ev, "excerpt", "")
                            norm_ex = normalize_text_for_evidence_check(ev_ex)
                            if norm_ex and norm_ex in norm_page_text:
                                coherent_excerpt = ev_ex
                                break

                # B. Candidate label
                if not coherent_excerpt and dossier.annex_candidates:
                    for cand in dossier.annex_candidates:
                        if cand.get("page") == p_int and cand.get("label"):
                            cand_label = str(cand.get("label", "")).strip()
                            norm_label = normalize_text_for_evidence_check(cand_label)
                            if norm_label and norm_label in norm_page_text:
                                coherent_excerpt = cand_label
                                break

            # 3. Determine target review state
            # If coherent physical excerpt exists, confirm with mechanical/extracted evidence.
            # If no physical source, page has no text (scanned), or text doesn't match:
            # Keep as honest pending review, NOT confirmed, NO fake evidence.
            if coherent_excerpt:
                target_review = REVIEW_CONFIRMED
                target_status = STATUS_SUPPORTED
                target_excerpt = coherent_excerpt
                printed_label = f"Página {p_int} asociada manualmente por el docente" if is_manual else f"Lámina {p_int} confirmada por el docente"
                action_text = ""
            else:
                target_review = REVIEW_PENDING
                target_status = STATUS_SUPPORTED
                target_excerpt = ""
                printed_label = f"Página {p_int} seleccionada por el docente (pendiente de cotejo)"
                action_text = f"Lámina seleccionada en página {p_int} requiere verificación docente visual (sin evidencia física cotejable)."

            teacher_evs = [ev for ev in ref.evidence if getattr(ev, "role", "") == "teacher_selected_source_page"]
            is_already_confirmed = (
                ref.confirmed_page == p_int
                and ref.review == target_review
                and (len(teacher_evs) == 1 if target_review == REVIEW_CONFIRMED else len(teacher_evs) == 0)
                and (teacher_evs[0].excerpt == target_excerpt if target_review == REVIEW_CONFIRMED else True)
            )
            if not is_already_confirmed:
                before_snap = _snapshot_annex_for_delta(ref)
                ref.confirmed_page = p_int
                ref.review = target_review
                ref.status = target_status
                ref.origin = "teacher_selected_source_page" if is_manual else ORIGIN_EXTRACTED
                ref.current_action = action_text
                ref.action_required = action_text

                # Preserve all extracted/source evidence (excluding any existing teacher_selected_source_page)
                preserved_evidence = [ev for ev in ref.evidence if getattr(ev, "role", "") != "teacher_selected_source_page"]
                if target_review == REVIEW_CONFIRMED and target_excerpt:
                    # ONLY confirmed creates ref with exact excerpt present!
                    decision_ev = SourceReference(
                        document_sha256=dossier.source_sha256,
                        page_number=p_int,
                        printed_label=printed_label,
                        excerpt=target_excerpt,
                        region=None,
                        role="teacher_selected_source_page",
                    )
                    preserved_evidence.append(decision_ev)
                ref.evidence = preserved_evidence

                after_snap = _snapshot_annex_for_delta(ref)
                desc = f"página manual pág. {p_int}" if is_manual else f"lámina candidata pág. {p_int}"
                changes.append(
                    f"Anexo {ref.annex_number} confirmado en {desc}."
                    if target_review == REVIEW_CONFIRMED
                    else f"Anexo {ref.annex_number} seleccionado en {desc} (pendiente de cotejo)."
                )
                deltas.append(_make_history_delta(
                    scope="annex",
                    session_id=matching_session.session_id,
                    field=annex_stable_id,
                    change_type="manual_association" if is_manual else "confirmed",
                    before=before_snap,
                    after=after_snap,
                    stable_id=annex_stable_id,
                ))
                session_changed = True
        else:
            # Clean disassociation - remove teacher_selected_source_page references
            teacher_evs = [ev for ev in ref.evidence if getattr(ev, "role", "") == "teacher_selected_source_page"]
            if ref.confirmed_page is not None or len(teacher_evs) > 0:
                before_snap = _snapshot_annex_for_delta(ref)
                ref.confirmed_page = None
                ref.review = REVIEW_PENDING
                ref.origin = ORIGIN_EXTRACTED
                # Remove only teacher_selected_source_page, preserve extracted evidence
                ref.evidence = [ev for ev in ref.evidence if getattr(ev, "role", "") != "teacher_selected_source_page"]
                state, act = derive_annex_operational_state(ref, source_sha=dossier.source_sha256, page_count=dossier.page_count)
                ref.current_action = act
                ref.action_required = act
                after_snap = _snapshot_annex_for_delta(ref)
                changes.append(f"Anexo {ref.annex_number} desmarcado / marcado como pendiente.")
                deltas.append(_make_history_delta(
                    scope="annex",
                    session_id=matching_session.session_id,
                    field=annex_stable_id,
                    change_type="disassociated",
                    before=before_snap,
                    after=after_snap,
                    stable_id=annex_stable_id,
                ))
                session_changed = True

    # Bulk confirm_all: Sol Item 3 & Luna B3:
    # 1) Targets ONLY the selected session (matching_session) and general fields
    # 2) Confirms ONLY supported fields; does not confirm ambiguous/missing or empty fields
    # 3) Leaves unconfirmed annexes pending
    reviews_override = corrections.get("reviews", {}) or {}
    if reviews_override.get("__all__") == "confirmed":
        for g_f in dossier.general_fields.values():
            if _is_empty_value(g_f.value):
                g_f.review = REVIEW_PENDING
                if g_f.status == STATUS_SUPPORTED:
                    g_f.status = STATUS_MISSING
                state, act = derive_field_operational_state(g_f)
                g_f.current_action = act
                g_f.action_required = act
                continue
            if g_f.status == STATUS_SUPPORTED and g_f.review != REVIEW_CORRECTED and g_f.review != REVIEW_CONFIRMED:
                before_snap = _snapshot_field_for_delta(g_f)
                g_f.review = REVIEW_CONFIRMED
                state, act = derive_field_operational_state(g_f)
                g_f.current_action = act
                g_f.action_required = act
                after_snap = _snapshot_field_for_delta(g_f)
                changes.append(f"Campo general '{g_f.name}' confirmado.")
                deltas.append(_make_history_delta(
                    scope="general",
                    field=g_f.name,
                    change_type="confirmed",
                    before=before_snap,
                    after=after_snap,
                ))
        if matching_session is not None:
            for sf in matching_session.fields.values():
                if _is_empty_value(sf.value):
                    sf.review = REVIEW_PENDING
                    if sf.status == STATUS_SUPPORTED:
                        sf.status = STATUS_MISSING
                    state, act = derive_field_operational_state(sf)
                    sf.current_action = act
                    sf.action_required = act
                    continue
                if sf.status == STATUS_SUPPORTED and sf.review != REVIEW_CORRECTED and sf.review != REVIEW_CONFIRMED:
                    before_snap = _snapshot_field_for_delta(sf)
                    sf.review = REVIEW_CONFIRMED
                    state, act = derive_field_operational_state(sf)
                    sf.current_action = act
                    sf.action_required = act
                    after_snap = _snapshot_field_for_delta(sf)
                    changes.append(f"Sesión {matching_session.session_number} '{sf.name}' confirmado.")
                    deltas.append(_make_history_delta(
                        scope="session",
                        session_id=matching_session.session_id,
                        field=sf.name,
                        change_type="confirmed",
                        before=before_snap,
                        after=after_snap,
                        stable_id=sf.name,
                    ))
                    session_changed = True
        if changes:
            changes.append("Confirmación docente de los campos debidamente fundamentados de la sesión seleccionada.")
    elif reviews_override:
        for f_name, r_val in reviews_override.items():
            if r_val == "confirmed":
                if f_name in dossier.general_fields:
                    g_f = dossier.general_fields[f_name]
                    if _is_empty_value(g_f.value):
                        g_f.review = REVIEW_PENDING
                        if g_f.status == STATUS_SUPPORTED:
                            g_f.status = STATUS_MISSING
                        state, act = derive_field_operational_state(g_f)
                        g_f.current_action = act
                        g_f.action_required = act
                        continue
                    if g_f.review != REVIEW_CONFIRMED:
                        before_snap = _snapshot_field_for_delta(g_f)
                        g_f.review = REVIEW_CONFIRMED
                        state, act = derive_field_operational_state(g_f)
                        g_f.current_action = act
                        g_f.action_required = act
                        after_snap = _snapshot_field_for_delta(g_f)
                        changes.append(f"Campo general '{f_name}' confirmado.")
                        deltas.append(_make_history_delta(
                            scope="general",
                            field=f_name,
                            change_type="confirmed",
                            before=before_snap,
                            after=after_snap,
                        ))
                elif matching_session is not None and f_name in matching_session.fields:
                    sf = matching_session.fields[f_name]
                    if _is_empty_value(sf.value):
                        sf.review = REVIEW_PENDING
                        if sf.status == STATUS_SUPPORTED:
                            sf.status = STATUS_MISSING
                        state, act = derive_field_operational_state(sf)
                        sf.current_action = act
                        sf.action_required = act
                        continue
                    if sf.review != REVIEW_CONFIRMED:
                        before_snap = _snapshot_field_for_delta(sf)
                        sf.review = REVIEW_CONFIRMED
                        state, act = derive_field_operational_state(sf)
                        sf.current_action = act
                        sf.action_required = act
                        after_snap = _snapshot_field_for_delta(sf)
                        changes.append(f"Sesión {matching_session.session_number} '{f_name}' confirmado.")
                        deltas.append(_make_history_delta(
                            scope="session",
                            session_id=matching_session.session_id,
                            field=f_name,
                            change_type="confirmed",
                            before=before_snap,
                            after=after_snap,
                            stable_id=f_name,
                        ))
                        session_changed = True
            elif r_val == "postponed":
                if f_name in dossier.general_fields:
                    g_f = dossier.general_fields[f_name]
                    if g_f.review != "postponed":
                        before_snap = _snapshot_field_for_delta(g_f)
                        g_f.review = "postponed"
                        state, act = derive_field_operational_state(g_f)
                        g_f.current_action = act
                        g_f.action_required = act
                        after_snap = _snapshot_field_for_delta(g_f)
                        changes.append(f"Campo general '{f_name}' aplazado.")
                        deltas.append(_make_history_delta(
                            scope="general",
                            field=f_name,
                            change_type="postponed",
                            before=before_snap,
                            after=after_snap,
                        ))
                elif matching_session is not None and f_name in matching_session.fields:
                    sf = matching_session.fields[f_name]
                    if sf.review != "postponed":
                        before_snap = _snapshot_field_for_delta(sf)
                        sf.review = "postponed"
                        state, act = derive_field_operational_state(sf)
                        sf.current_action = act
                        sf.action_required = act
                        after_snap = _snapshot_field_for_delta(sf)
                        changes.append(f"Sesión {matching_session.session_number} '{f_name}' aplazado.")
                        deltas.append(_make_history_delta(
                            scope="session",
                            session_id=matching_session.session_id,
                            field=f_name,
                            change_type="postponed",
                            before=before_snap,
                            after=after_snap,
                            stable_id=f_name,
                        ))
                        session_changed = True
                elif matching_session is not None:
                    try:
                        ref = _find_single_annex_ref(matching_session, f_name)
                        annex_stable_id = ref.reference_id or f"annex_{ref.annex_number}"
                        if ref.review != "postponed":
                            before_snap = _snapshot_annex_for_delta(ref)
                            ref.review = "postponed"
                            state, act = derive_annex_operational_state(ref, source_sha=dossier.source_sha256, page_count=dossier.page_count)
                            ref.current_action = act
                            ref.action_required = act
                            after_snap = _snapshot_annex_for_delta(ref)
                            changes.append(f"Anexo {ref.annex_number} aplazado.")
                            deltas.append(_make_history_delta(
                                scope="annex",
                                session_id=matching_session.session_id,
                                field=annex_stable_id,
                                change_type="postponed",
                                before=before_snap,
                                after=after_snap,
                                stable_id=annex_stable_id,
                            ))
                            session_changed = True
                    except ValueError:
                        pass


    # B2: Pure no-op if effective payload contains no decisions/changes.
    # Must return unchanged dossier WITHOUT mutating anything (including SessionPlan.review).
    if not changes:
        return dossier

    # Recompute aggregate session review strictly from its components ONLY when that session had effective changes
    if matching_session is not None and session_changed:
        _recompute_session_review(matching_session)

    new_version = dossier.version + 1
    now_str = _utc_iso_now()
    dossier.version = new_version
    dossier.updated_at = now_str
    entry = HistoryEntry(
        version=new_version,
        action="resolve",
        actor=actor,
        timestamp=now_str,
        changes=changes,
        deltas=deltas,
        summary=f"Resolución v{new_version}: {len(changes)} decisiones docentes registradas.",
    )
    dossier.history.append(entry.to_dict())
    return dossier
