"""curriculum.verification
-----------------------
Pure, deterministic verification module for curriculum dossiers against physical PDF source pages.

Enforces:
- Deterministic text normalization without token-bag false positives or empty matches.
- Full mechanical audit covering all scopes: dossier identity, general fields, session fields,
  annex references, candidate sheets, and F7 operational queue items.
- Strict categorization:
  - BLOCKED (hard failure): identity mismatch, wrong SHA, page out of bounds, malformed schema,
    missing evidence on extracted/supported fields, empty excerpt on declared evidence,
    conflicting data, physical contradiction with PDF text, structurally empty dossier.
  - NEEDS_TEACHER_REVIEW: empty/missing values, ambiguous data, proposed/inferred
    content (always review even if physically located), unconfirmed annexes, candidate annex sheets,
    scanned pages without digital text, pending operational queue items.
  - CHECKED: evidence mechanically located and verified on the referenced physical page
    for extracted/supported content with exact SHA, non-empty excerpt, and contiguous match;
    confirmed annex with verified physical evidence; resolved queue items.
- 100% deterministic JSON report tied directly to dossier.version and source_sha256 (no timestamps).
- Unique, collision-free item_id, path, and target across all verification items.
- Strictly non-authoritarian teacher copy: never "validado por SEP" nor "correcto pedagógicamente".
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PyPdfError

from curriculum.vocabulary import CANONICAL_CAMPOS
from curriculum.source_segments import (
    scan_session_segments, match_session_segment, anchor_matches,
    project_context_matches, phase_project_context, phase_review_segments, has_possible_session_structure,
)

logger = logging.getLogger(__name__)

VERIFICATION_SCHEMA_VERSION = 1

STATUS_CHECKED = "checked"
STATUS_NEEDS_TEACHER_REVIEW = "needs_teacher_review"
STATUS_BLOCKED = "blocked"

SCOPE_DOSSIER = "dossier"
SCOPE_GENERAL = "general"
SCOPE_SESSION = "session"
SCOPE_ANNEX = "annex"
SCOPE_QUEUE = "queue"

CANONICAL_REPORT_KEYS = {
    "schema_version",
    "dossier_version",
    "source_sha256",
    "is_valid",
    "checked_count",
    "needs_review_count",
    "blocked_count",
    "total_items",
    "items",
}

CANONICAL_GENERAL_FIELDS = [
    "proyecto",
    "campos_formativos",
    "proposito",
    "finalidad",
    "duracion_proyecto",
]

CANONICAL_SESSION_FIELDS = [
    "inicio",
    "desarrollo",
    "cierre",
]


def normalize_text_for_evidence_check(text: str | None) -> str:
    """Normalize text for deterministic physical evidence verification.

    Transformations:
    1. Rejects None, non-string, or empty whitespace.
    2. NFKC unicode normalization (unifies composite characters, ligatures, full-width glyphs).
    3. Case-folding (lower()).
    4. Decomposes combining marks (NFD) and strips non-spacing diacritics (Mn).
    5. Normalizes quotes (curly to ascii) and dashes (em/en to ascii hyphen).
    6. Collapses all consecutive whitespace (spaces, tabs, newlines, non-breaking spaces)
       into a single ASCII space and strips leading/trailing whitespace.

    Guarantees:
    - Strictly sequence-preserving: verification checks use contiguous substring matching,
      never token-bag or set intersections.
    - An empty string or whitespace-only string returns "", which never matches any page.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. NFKC normalization
    text = unicodedata.normalize("NFKC", text)
    # 2. Case-folding
    text = text.lower()
    # 3. Strip non-spacing diacritical marks (accents)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # 4. Normalize dashes and quotes
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)
    text = re.sub(r"[\u2018\u2019\u201a\u201b]", "'", text)
    text = re.sub(r"[\u201c\u201d\u201e\u201f«»]", '"', text)
    # 5. Collapse all whitespace / newlines
    text = re.sub(r"[\s\u00a0\u2000-\u200b]+", " ", text)
    return text.strip()


def _is_value_present(val: Any, target_text: str) -> bool:
    """Check if a field value (string, list, or scalar) is physically present in target_text."""
    if val is None or not target_text:
        return False
    if isinstance(val, list):
        clean_elems = [normalize_text_for_evidence_check(str(v)) for v in val if v is not None]
        clean_elems = [e for e in clean_elems if e]
        if not clean_elems:
            return False
        if all(elem in target_text for elem in clean_elems):
            return True
        joined = " ".join(clean_elems)
        return joined in target_text
    norm_v = normalize_text_for_evidence_check(str(val or ""))
    return bool(norm_v and norm_v in target_text)


def _contains_whole_literal(value: str, text: str) -> bool:
    return bool(value and re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text))


def _campos_cited_coverage(
    values: list[Any], evidence: list[Any], source_sha: str, normalized_pages: list[str],
) -> bool | None:
    """Cover each canonical name in a valid, page-local excerpt.

    None preserves legacy handling for non-canonical lists. Empty/malformed
    elements fail closed rather than silently disappearing from the denominator.
    This checks textual support only, never whether a field applies pedagogically.
    """
    if not values or any(not isinstance(v, str) or not v.strip() for v in values):
        return False
    if any(v not in CANONICAL_CAMPOS for v in values):
        return None
    remaining = {normalize_text_for_evidence_check(v) for v in values}
    for ev in evidence:
        if isinstance(ev, dict):
            page, sha, excerpt = ev.get("page_number"), ev.get("document_sha256"), ev.get("excerpt")
        elif hasattr(ev, "page_number"):
            page = getattr(ev, "page_number", None)
            sha = getattr(ev, "document_sha256", "")
            excerpt = getattr(ev, "excerpt", "")
        else:
            continue
        if (
            not isinstance(page, int) or isinstance(page, bool)
            or not 1 <= page <= len(normalized_pages)
            or str(sha or "").strip().lower() != source_sha.lower()
        ):
            continue
        norm_excerpt = normalize_text_for_evidence_check(excerpt)
        if not norm_excerpt or norm_excerpt not in normalized_pages[page - 1]:
            continue
        remaining = {v for v in remaining if not _contains_whole_literal(v, norm_excerpt)}
    return not remaining


@dataclass

class VerificationItem:
    """A discrete verified assertion anchored to a specific scope and physical page."""

    scope: str
    target: str
    status: str  # "checked" | "needs_teacher_review" | "blocked"
    message: str
    item_id: str = ""
    path: str = ""
    page_number: int | None = None
    excerpt: str = ""
    evidence_sha256: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "path": self.path,
            "scope": self.scope,
            "target": self.target,
            "status": self.status,
            "message": self.message,
            "page_number": self.page_number,
            "excerpt": self.excerpt,
            "evidence_sha256": self.evidence_sha256,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationItem:
        return cls(
            item_id=str(data.get("item_id", "")),
            path=str(data.get("path", "")),
            scope=str(data.get("scope", "")),
            target=str(data.get("target", "")),
            status=str(data.get("status", STATUS_NEEDS_TEACHER_REVIEW)),
            message=str(data.get("message", "")),
            page_number=data.get("page_number"),
            excerpt=str(data.get("excerpt", "")),
            evidence_sha256=str(data.get("evidence_sha256", "")),
            details=dict(data.get("details", {}) or {}),
        )


CANONICAL_REPORT_KEYS = {
    "schema_version",
    "dossier_version",
    "source_sha256",
    "is_valid",
    "checked_count",
    "needs_review_count",
    "blocked_count",
    "total_items",
    "items",
}


@dataclass
class VerificationReport:
    """100% deterministic versioned audit report of automatic mechanical verification."""

    schema_version: int = VERIFICATION_SCHEMA_VERSION
    dossier_version: int = 1
    source_sha256: str = ""
    is_valid: bool = False
    checked_count: int = 0
    needs_review_count: int = 0
    blocked_count: int = 0
    total_items: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "dossier_version": int(self.dossier_version),
            "source_sha256": self.source_sha256,
            "is_valid": bool(self.is_valid),
            "checked_count": int(self.checked_count),
            "needs_review_count": int(self.needs_review_count),
            "blocked_count": int(self.blocked_count),
            "total_items": int(self.total_items),
            "items": list(self.items),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationReport:
        items = data.get("items") or []
        return cls(
            schema_version=int(data.get("schema_version", VERIFICATION_SCHEMA_VERSION)),
            dossier_version=int(data.get("dossier_version", 1)),
            source_sha256=str(data.get("source_sha256", "")),
            is_valid=bool(data.get("is_valid", False)),
            checked_count=int(data.get("checked_count", 0)),
            needs_review_count=int(data.get("needs_review_count", 0)),
            blocked_count=int(data.get("blocked_count", 0)),
            total_items=int(data.get("total_items", 0)),
            items=list(items),
        )


def _read_pdf_source(pdf_source: Any) -> tuple[bytes, str, list[str]]:
    """Read physical PDF source and return (content_bytes, sha256_hex, pages_text_list).

    Reads file-like objects always from 0 and restores their exact original position
    in a finally block, handles at EOF included.
    """
    if isinstance(pdf_source, tuple) and len(pdf_source) == 3 and isinstance(pdf_source[0], bytes):
        return pdf_source  # Pre-cached (bytes, sha, pages_text)

    if pdf_source is None:
        raise ValueError("Fuente PDF física no especificada (None).")

    orig_pos = None
    content: bytes = b""

    if isinstance(pdf_source, (bytes, bytearray)):
        content = bytes(pdf_source)
    elif isinstance(pdf_source, (str, Path)):
        p = Path(pdf_source)
        if not p.exists():
            raise FileNotFoundError(f"El archivo PDF no existe: {p}")
        content = p.read_bytes()
    elif hasattr(pdf_source, "read"):
        # File-like object (BytesIO, File, open file handle, FieldFile with file, etc.)
        if hasattr(pdf_source, "tell"):
            try:
                orig_pos = pdf_source.tell()
            except Exception:
                orig_pos = None
        try:
            if hasattr(pdf_source, "seek"):
                try:
                    pdf_source.seek(0)
                except Exception:
                    pass
            content = pdf_source.read()
        finally:
            if orig_pos is not None and hasattr(pdf_source, "seek"):
                try:
                    pdf_source.seek(orig_pos)
                except Exception:
                    pass
    elif hasattr(pdf_source, "open"):
        with pdf_source.open("rb") as stream:
            content = stream.read()
    else:
        raise ValueError(f"Tipo de fuente PDF no soportado: {type(pdf_source).__name__}")

    sha256_hex = hashlib.sha256(content).hexdigest()
    reader = PdfReader(io.BytesIO(content))
    pages_text = [p.extract_text() or "" for p in reader.pages]
    return content, sha256_hex, pages_text


read_physical_pdf_source = _read_pdf_source


def _is_empty_value(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return len(val.strip()) == 0
    if isinstance(val, (list, tuple, set, dict)):
        return len(val) == 0
    return False


def _is_moment_consistent(field_name: str, norm_ex: str, s_segment: str) -> bool:
    """Check whether norm_ex falls in the structural section of field_name (inicio, desarrollo, cierre)."""
    m_inicio = re.search(r"\b(?:inicio|apertura)\b", s_segment)
    m_desarrollo = re.search(r"\b(?:desarrollo)\b", s_segment)
    m_cierre = re.search(r"\b(?:cierre)\b", s_segment)

    ex_pos = s_segment.find(norm_ex)
    if ex_pos == -1:
        return False

    pos_ini = m_inicio.start() if m_inicio else -1
    pos_des = m_desarrollo.start() if m_desarrollo else -1
    pos_cie = m_cierre.start() if m_cierre else -1

    if field_name == "inicio":
        if pos_des != -1 and ex_pos >= pos_des:
            return False
        if pos_cie != -1 and ex_pos >= pos_cie:
            return False
        return True
    elif field_name == "desarrollo":
        if pos_ini != -1 and ex_pos < pos_ini:
            return False
        if pos_cie != -1 and ex_pos >= pos_cie:
            return False
        return True
    elif field_name == "cierre":
        if pos_des != -1 and ex_pos < pos_des:
            return False
        if pos_ini != -1 and ex_pos < pos_ini:
            return False
        return True
    return True


def verify_curriculum_dossier(
    dossier: Any,
    pdf_source: Any,
) -> VerificationReport:
    """Mechanically verify a curriculum dossier against physical PDF source pages.

    Pure function: zero DB writes, zero network calls, zero LLM prompts.
    Emits a 100% deterministic VerificationReport tied to dossier.version and source_sha256.
    """
    # 1. Read PDF source
    try:
        content_bytes, actual_sha256, pages_text = _read_pdf_source(pdf_source)
    except Exception as exc:
        logger.warning("Fallo al leer la fuente PDF para verificación: %s", exc)
        d_ver = getattr(dossier, "version", 1) if not isinstance(dossier, dict) else dossier.get("version", 1)
        if not isinstance(d_ver, int) or isinstance(d_ver, bool) or d_ver < 1:
            d_ver = 1
        return VerificationReport(
            schema_version=VERIFICATION_SCHEMA_VERSION,
            dossier_version=d_ver,
            source_sha256="",
            is_valid=False,
            checked_count=0,
            needs_review_count=0,
            blocked_count=1,
            total_items=1,
            items=[
                VerificationItem(
                    item_id="dossier_source_pdf",
                    path="identity/pdf_source",
                    scope=SCOPE_DOSSIER,
                    target="source_pdf",
                    status=STATUS_BLOCKED,
                    message=f"No se pudo leer el archivo PDF de la planeación: {exc}",
                ).to_dict()
            ],
        )

    pdf_page_count = len(pages_text)
    norm_pages_text = [normalize_text_for_evidence_check(t) for t in pages_text]

    # 2. Extract dossier properties and validate root structure
    if hasattr(dossier, "to_dict"):
        dossier_dict = dossier.to_dict()
        dossier_obj = dossier
    elif isinstance(dossier, dict):
        dossier_dict = dossier
        try:
            from curriculum.source_interpreter import ImportDossier
            dossier_obj = ImportDossier.from_dict(dossier)
        except Exception:
            dossier_obj = None
    else:
        dossier_dict = {}
        dossier_obj = None

    dossier_version = dossier_dict.get("version")
    if not isinstance(dossier_version, int) or isinstance(dossier_version, bool) or dossier_version < 1:
        dossier_version = 1

    dossier_sha = str(dossier_dict.get("source_sha256") or "").strip().lower()
    dossier_status = str(dossier_dict.get("status") or "active")
    dossier_page_count = dossier_dict.get("page_count")

    items: list[VerificationItem] = []

    # A. Dossier Identity & Schema Checks
    if dossier_sha == actual_sha256.lower():
        items.append(
            VerificationItem(
                item_id="dossier_sha",
                path="identity/source_sha256",
                scope=SCOPE_DOSSIER,
                target="source_sha256",
                status=STATUS_CHECKED,
                message="Identidad SHA-256 del documento coincide con el archivo PDF en disco.",
                evidence_sha256=dossier_sha,
                details={"source_sha256": dossier_sha},
            )
        )
    else:
        items.append(
            VerificationItem(
                item_id="dossier_sha",
                path="identity/source_sha256",
                scope=SCOPE_DOSSIER,
                target="source_sha256",
                status=STATUS_BLOCKED,
                message=(
                    f"Inconsistencia de identidad: el SHA-256 del dossier ({dossier_sha[:16]}…) "
                    f"no coincide con el archivo PDF ({actual_sha256[:16]}…)."
                ),
                evidence_sha256=dossier_sha,
                details={"expected_sha": actual_sha256, "dossier_sha": dossier_sha},
            )
        )

    if isinstance(dossier_page_count, int) and not isinstance(dossier_page_count, bool) and dossier_page_count == pdf_page_count:
        items.append(
            VerificationItem(
                item_id="dossier_page_count",
                path="identity/page_count",
                scope=SCOPE_DOSSIER,
                target="page_count",
                status=STATUS_CHECKED,
                message=f"Total de {pdf_page_count} páginas coincide con el PDF físico.",
                details={"page_count": pdf_page_count},
            )
        )
    else:
        items.append(
            VerificationItem(
                item_id="dossier_page_count",
                path="identity/page_count",
                scope=SCOPE_DOSSIER,
                target="page_count",
                status=STATUS_BLOCKED,
                message=(
                    f"Total de páginas declarado ({dossier_page_count}) "
                    f"no coincide con las páginas reales del PDF ({pdf_page_count})."
                ),
                details={"dossier_page_count": dossier_page_count, "pdf_page_count": pdf_page_count},
            )
        )

    if dossier_status != "active":
        items.append(
            VerificationItem(
                item_id="dossier_status",
                path="identity/status",
                scope=SCOPE_DOSSIER,
                target="status",
                status=STATUS_BLOCKED,
                message=f"El dossier está marcado como '{dossier_status}', no apto para revisión.",
                details={"status": dossier_status},
            )
        )

    # B. Structural Emptiness Check
    raw_general = dossier_dict.get("general_fields")
    raw_sessions = dossier_dict.get("sessions")
    raw_cands = dossier_dict.get("annex_candidates")

    is_structurally_empty = False
    if not isinstance(raw_general, dict) or not raw_general:
        is_structurally_empty = True
    if not isinstance(raw_sessions, list) or not raw_sessions:
        is_structurally_empty = True

    if is_structurally_empty:
        items.append(
            VerificationItem(
                item_id="dossier_structure_empty",
                path="structure",
                scope=SCOPE_DOSSIER,
                target="structure",
                status=STATUS_BLOCKED,
                message="Dossier estructuralmente vacío o incompleto: debe contener campos generales y al menos una sesión.",
                details={
                    "has_general_fields": isinstance(raw_general, dict) and bool(raw_general),
                    "has_sessions": isinstance(raw_sessions, list) and bool(raw_sessions),
                },
            )
        )

    # Precompute session declared pages, page-to-session segments, and shared citations
    session_declared_pages: dict[str, set[int]] = {}
    sessions_by_page: dict[int, list[Any]] = {}
    shared_citations: dict[tuple[int, str], list[tuple[str, str, str, int]]] = {}

    for s in (raw_sessions or []):
        s_id = getattr(s, "session_id", None) if not isinstance(s, dict) else s.get("session_id")
        if not s_id:
            continue
        s_pages = getattr(s, "pages", []) if not isinstance(s, dict) else s.get("pages", [])
        s_cont = getattr(s, "continues_on", []) if not isinstance(s, dict) else s.get("continues_on", [])
        pages = {int(p) for p in (list(s_pages or []) + list(s_cont or [])) if isinstance(p, int) and not isinstance(p, bool)}
        session_declared_pages[str(s_id)] = pages
        for p in pages:
            sessions_by_page.setdefault(p, []).append(s)

        s_fields = getattr(s, "fields", {}) if not isinstance(s, dict) else s.get("fields", {})
        if isinstance(s_fields, dict):
            for fname, fdata in s_fields.items():
                ev_list = getattr(fdata, "evidence", []) if not isinstance(fdata, dict) else fdata.get("evidence", [])
                if isinstance(ev_list, list):
                    for eidx, ev in enumerate(ev_list):
                        ep = getattr(ev, "page_number", None) if not isinstance(ev, dict) else ev.get("page_number")
                        ex = getattr(ev, "excerpt", "") if not isinstance(ev, dict) else ev.get("excerpt", "")
                        norm_ex = normalize_text_for_evidence_check(ex)
                        if isinstance(ep, int) and not isinstance(ep, bool) and norm_ex:
                            shared_citations.setdefault((ep, norm_ex), []).append((SCOPE_SESSION, str(s_id), fname, eidx))

    if isinstance(raw_general, dict):
        for fname, fdata in raw_general.items():
            ev_list = getattr(fdata, "evidence", []) if not isinstance(fdata, dict) else fdata.get("evidence", [])
            if isinstance(ev_list, list):
                for eidx, ev in enumerate(ev_list):
                    ep = getattr(ev, "page_number", None) if not isinstance(ev, dict) else ev.get("page_number")
                    ex = getattr(ev, "excerpt", "") if not isinstance(ev, dict) else ev.get("excerpt", "")
                    norm_ex = normalize_text_for_evidence_check(ex)
                    if isinstance(ep, int) and not isinstance(ep, bool) and norm_ex:
                        shared_citations.setdefault((ep, norm_ex), []).append((SCOPE_GENERAL, "general", fname, eidx))

    # Source-derived boundaries are independent of dossier order/subsets, titles
    # and declared offsets. A legacy repeated number is never matched to the
    # first textual occurrence merely because it appears on the same page.
    source_segments = scan_session_segments(pages_text, actual_sha256)
    has_session_structure = bool(source_segments) or has_possible_session_structure(pages_text)
    page_session_segments: dict[int, dict[str, str]] = {}
    uncertain_session_ids: set[str] = set()
    for s_index, session in enumerate(raw_sessions if isinstance(raw_sessions, list) else []):
        if not isinstance(session, dict):
            continue
        sid = session.get("session_id")
        if not isinstance(sid, str) or not sid:
            continue
        matched = match_session_segment(session, source_segments)
        declared_pages = session_declared_pages.get(sid, set())
        for page_number in declared_pages:
            # No broad page fallback when the source has session structure,
            # even if an anchor was removed or other sessions were omitted.
            page_session_segments.setdefault(page_number, {})[sid] = (
                norm_pages_text[page_number - 1]
                if not has_session_structure and 1 <= page_number <= len(pages_text) else ""
            )
        if not has_session_structure and sid.endswith("_project_review"):
            physical_pages = session.get("pages", [])
            if isinstance(physical_pages, list) and physical_pages and type(physical_pages[0]) is int and 1 <= physical_pages[0] <= len(pages_text):
                for page_number in declared_pages:
                    page_session_segments.setdefault(page_number, {})[sid] = ""
                for page_number, text in phase_review_segments(pages_text, actual_sha256, physical_pages[0]):
                    page_session_segments.setdefault(page_number, {})[sid] = normalize_text_for_evidence_check(text)
        if matched:
            if matched.unassigned_segments:
                uncertain_session_ids.add(sid)
            for page_number, text in matched.page_segments:
                page_session_segments.setdefault(page_number, {})[sid] = normalize_text_for_evidence_check(text)

        for name in ("header_anchor", "project_context"):
            supplied = session.get(name)
            if supplied is None:  # Optional additive schema: legacy remains readable.
                continue
            expected = getattr(matched, name) if matched else None
            if name == "project_context" and matched is None and sid.endswith("_project_review"):
                pages = session.get("pages", [])
                if isinstance(pages, list) and pages and type(pages[0]) is int and 1 <= pages[0] <= len(pages_text):
                    expected = phase_project_context(pages_text, actual_sha256, pages[0])
            valid = expected is not None and (
                anchor_matches(supplied, expected) if name == "header_anchor"
                else project_context_matches(supplied, expected)
            )
            if name == "project_context" and valid and session.get("project_title", "") != expected["title"]:
                items.append(VerificationItem(
                    item_id=f"sess_{s_index}_{sid}_project_title",
                    path=f"sessions/{sid}/project_title", scope=SCOPE_SESSION,
                    target=f"session.{sid}.project_title", status=STATUS_BLOCKED,
                    message="El título visible del proyecto contradice su contexto físico recomputado.",
                    details={"session_id": sid, "reason": "project_projection_mismatch"},
                ))
            if not valid:
                items.append(VerificationItem(
                    item_id=f"sess_{s_index}_{sid}_{name}",
                    path=f"sessions/{sid}/{name}", scope=SCOPE_SESSION,
                    target=f"session.{sid}.{name}", status=STATUS_BLOCKED,
                    message="Ancla o contexto incompatible con los encabezados y límites recomputados desde la fuente física.",
                    details={"session_id": sid, "reason": "source_anchor_mismatch", "metadata": name},
                ))

    # Helper to check evidence list for a single field
    def _verify_field_evidence(
        scope: str,
        parent_id: str,
        field_name: str,
        field_data: Any,
    ) -> None:
        target_prefix = f"session.{parent_id}.{field_name}" if scope == SCOPE_SESSION else f"{scope}.{field_name}"
        path_prefix = f"sessions/{parent_id}/fields/{field_name}" if scope == SCOPE_SESSION else f"general_fields/{field_name}"
        id_prefix = f"sess_{parent_id}_{field_name}" if scope == SCOPE_SESSION else f"gen_{field_name}"

        # Schema validation for field data
        if not isinstance(field_data, dict) and not hasattr(field_data, "value"):
            items.append(
                VerificationItem(
                    item_id=f"{id_prefix}_malformed",
                    path=path_prefix,
                    scope=scope,
                    target=target_prefix,
                    status=STATUS_BLOCKED,
                    message=f"Campo '{field_name}' tiene una estructura de datos malformada (se esperaba mapa u objeto).",
                    details={"field_name": field_name, "raw_data": str(field_data)[:100]},
                )
            )
            return

        REQUIRED_FIELD_SCHEMA_KEYS = {"name", "value", "status", "origin", "review", "evidence"}
        missing_keys = set()
        if isinstance(field_data, dict):
            missing_keys = REQUIRED_FIELD_SCHEMA_KEYS - set(field_data.keys())
        elif hasattr(field_data, "missing_schema_keys") and field_data.missing_schema_keys:
            missing_keys = set(field_data.missing_schema_keys)

        if missing_keys:
            items.append(
                VerificationItem(
                    item_id=f"{id_prefix}_schema_missing_keys",
                    path=path_prefix,
                    scope=scope,
                    target=target_prefix,
                    status=STATUS_BLOCKED,
                    message=f"Campo '{field_name}' malformado: faltan claves de esquema requeridas ({', '.join(sorted(missing_keys))}).",
                    details={"field_name": field_name, "missing_keys": sorted(missing_keys)},
                )
            )
            return

        val = getattr(field_data, "value", None) if not isinstance(field_data, dict) else field_data.get("value")
        stat = getattr(field_data, "status", "") if not isinstance(field_data, dict) else field_data.get("status", "")
        origin = getattr(field_data, "origin", "") if not isinstance(field_data, dict) else field_data.get("origin", "")
        review = getattr(field_data, "review", "") if not isinstance(field_data, dict) else field_data.get("review", "")
        ev_list = getattr(field_data, "evidence", []) if not isinstance(field_data, dict) else field_data.get("evidence", [])

        norm_val = normalize_text_for_evidence_check(str(val or ""))

        # 1. Conflicting: hard failure (BLOCKED) - stop immediately, no second checked item!
        if stat == "conflicting":
            items.append(
                VerificationItem(
                    item_id=f"{id_prefix}_value",
                    path=f"{path_prefix}/value",
                    scope=scope,
                    target=target_prefix,
                    status=STATUS_BLOCKED,
                    message=f"Interpretación del campo '{field_name}' contiene una contradicción insalvable (status=conflicting).",
                    details={"field_name": field_name, "status": stat},
                )
            )
            return

        # 2. Missing or empty value
        if _is_empty_value(val) or stat == "missing":
            items.append(
                VerificationItem(
                    item_id=f"{id_prefix}_value",
                    path=f"{path_prefix}/value",
                    scope=scope,
                    target=target_prefix,
                    status=STATUS_NEEDS_TEACHER_REVIEW,
                    message=f"Campo '{field_name}' no contiene datos; requiere captura docente.",
                    details={"field_name": field_name, "status": stat},
                )
            )
            return

        # 3. Proposed / Inferred: produce EXACTLY ONE item teacher_review per field/target
        if origin in ("proposed", "inferred"):
            if not isinstance(ev_list, list):
                items.append(
                    VerificationItem(
                        item_id=f"{id_prefix}_ev_malformed",
                        path=f"{path_prefix}/evidence",
                        scope=scope,
                        target=f"{target_prefix}.evidence",
                        status=STATUS_BLOCKED,
                        message=f"La evidencia del campo '{field_name}' debe ser una lista.",
                        details={"field_name": field_name},
                    )
                )
                return

            has_contradiction = False
            first_matched_page = None
            first_matched_excerpt = ""
            first_matched_sha = ""
            ev_checked_meta = []

            for ev_idx, ev in enumerate(ev_list):
                if not isinstance(ev, dict) and not hasattr(ev, "page_number"):
                    items.append(
                        VerificationItem(
                            item_id=f"{id_prefix}_ev_{ev_idx}",
                            path=f"{path_prefix}/evidence/{ev_idx}",
                            scope=scope,
                            target=f"{target_prefix}.evidence.{ev_idx}",
                            status=STATUS_BLOCKED,
                            message=f"Evidencia {ev_idx} de '{field_name}' está malformada.",
                            details={"field_name": field_name, "evidence_index": ev_idx},
                        )
                    )
                    has_contradiction = True
                    continue

                ev_page = getattr(ev, "page_number", None) if not isinstance(ev, dict) else ev.get("page_number")
                ev_sha = getattr(ev, "document_sha256", "") if not isinstance(ev, dict) else ev.get("document_sha256", "")
                ev_excerpt = getattr(ev, "excerpt", "") if not isinstance(ev, dict) else ev.get("excerpt", "")

                # A. Bounds check
                if ev_page is None or not isinstance(ev_page, int) or isinstance(ev_page, bool) or ev_page < 1 or ev_page > pdf_page_count:
                    items.append(
                        VerificationItem(
                            item_id=f"{id_prefix}_ev_{ev_idx}",
                            path=f"{path_prefix}/evidence/{ev_idx}",
                            scope=scope,
                            target=f"{target_prefix}.evidence.{ev_idx}",
                            status=STATUS_BLOCKED,
                            page_number=ev_page if isinstance(ev_page, int) and not isinstance(ev_page, bool) else None,
                            message=f"Evidencia de '{field_name}' apunta a página {ev_page}, fuera de rango válido (1 a {pdf_page_count}).",
                            excerpt=str(ev_excerpt or ""),
                            evidence_sha256=str(ev_sha or ""),
                            details={"field_name": field_name, "page_number": ev_page},
                        )
                    )
                    has_contradiction = True
                    continue

                # B. Document SHA check
                if str(ev_sha or "").strip().lower() != actual_sha256.lower():
                    items.append(
                        VerificationItem(
                            item_id=f"{id_prefix}_ev_{ev_idx}",
                            path=f"{path_prefix}/evidence/{ev_idx}",
                            scope=scope,
                            target=f"{target_prefix}.evidence.{ev_idx}",
                            status=STATUS_BLOCKED,
                            page_number=ev_page,
                            message=(
                                f"Evidencia de '{field_name}' en página {ev_page} tiene un hash SHA-256 "
                                f"({str(ev_sha)[:12]}…) que no coincide con el archivo físico ({actual_sha256[:12]}…)."
                            ),
                            excerpt=str(ev_excerpt or ""),
                            evidence_sha256=str(ev_sha or ""),
                            details={"field_name": field_name, "expected_sha": actual_sha256, "ev_sha": ev_sha},
                        )
                    )
                    has_contradiction = True
                    continue

                # C. Excerpt non-empty check
                norm_ex = normalize_text_for_evidence_check(ev_excerpt)
                if not norm_ex:
                    items.append(
                        VerificationItem(
                            item_id=f"{id_prefix}_ev_{ev_idx}",
                            path=f"{path_prefix}/evidence/{ev_idx}",
                            scope=scope,
                            target=f"{target_prefix}.evidence.{ev_idx}",
                            status=STATUS_BLOCKED,
                            page_number=ev_page,
                            message=f"Evidencia declarada para '{field_name}' en página {ev_page} contiene un fragmento de texto vacío o en blanco.",
                            excerpt=str(ev_excerpt or ""),
                            evidence_sha256=str(ev_sha or ""),
                            details={"field_name": field_name, "page_number": ev_page},
                        )
                    )
                    has_contradiction = True
                    continue

                page_idx = ev_page - 1
                norm_page = norm_pages_text[page_idx] if 0 <= page_idx < len(norm_pages_text) else ""
                if norm_page and norm_ex not in norm_page:
                    items.append(
                        VerificationItem(
                            item_id=f"{id_prefix}_ev_{ev_idx}",
                            path=f"{path_prefix}/evidence/{ev_idx}",
                            scope=scope,
                            target=f"{target_prefix}.evidence.{ev_idx}",
                            status=STATUS_BLOCKED,
                            page_number=ev_page,
                            message=(
                                f"Contradicción física: El texto citado en la evidencia de '{field_name}' "
                                f"no se encuentra en la página física {ev_page}."
                            ),
                            excerpt=str(ev_excerpt or ""),
                            evidence_sha256=str(ev_sha or ""),
                            details={"field_name": field_name, "page_number": ev_page, "excerpt": str(ev_excerpt or "")},
                        )
                    )
                    has_contradiction = True
                    continue

                if first_matched_page is None:
                    first_matched_page = ev_page
                    first_matched_excerpt = str(ev_excerpt or "")
                    first_matched_sha = str(ev_sha or "")
                ev_checked_meta.append({
                    "page_number": ev_page,
                    "excerpt": str(ev_excerpt or ""),
                    "evidence_sha256": str(ev_sha or ""),
                    "matched": bool(norm_page and norm_ex in norm_page),
                })

            if not has_contradiction:
                msg = (
                    f"Campo '{field_name}' contiene un dato propuesto y ambiguo; requiere verificación docente."
                    if stat == "ambiguous"
                    else f"Campo '{field_name}' contiene un dato propuesto o inferido; requiere confirmación docente."
                )
                items.append(
                    VerificationItem(
                        item_id=f"{id_prefix}_value",
                        path=f"{path_prefix}/value",
                        scope=scope,
                        target=target_prefix,
                        status=STATUS_NEEDS_TEACHER_REVIEW,
                        page_number=first_matched_page,
                        excerpt=first_matched_excerpt,
                        evidence_sha256=first_matched_sha,
                        message=msg,
                        details={
                            "field_name": field_name,
                            "status": stat,
                            "origin": origin,
                            "review": review,
                            "evidence_citations": ev_checked_meta,
                        },
                    )
                )
            return

        # 4. Ambiguous (for extracted / non-proposed fields)
        if stat == "ambiguous":
            items.append(
                VerificationItem(
                    item_id=f"{id_prefix}_value",
                    path=f"{path_prefix}/value",
                    scope=scope,
                    target=target_prefix,
                    status=STATUS_NEEDS_TEACHER_REVIEW,
                    message=f"Interpretación del campo '{field_name}' es ambigua; requiere verificación docente.",
                    details={"field_name": field_name, "status": stat, "origin": origin, "review": review},
                )
            )

        # 5. Evidence list validation for extracted/supported fields
        if not isinstance(ev_list, list):
            items.append(
                VerificationItem(
                    item_id=f"{id_prefix}_ev_malformed",
                    path=f"{path_prefix}/evidence",
                    scope=scope,
                    target=f"{target_prefix}.evidence",
                    status=STATUS_BLOCKED,
                    message=f"La evidencia del campo '{field_name}' debe ser una lista.",
                    details={"field_name": field_name},
                )
            )
            return

        if not ev_list:
            if stat == "supported" or origin == "extracted":
                items.append(
                    VerificationItem(
                        item_id=f"{id_prefix}_evidence_missing",
                        path=f"{path_prefix}/evidence",
                        scope=scope,
                        target=f"{target_prefix}.evidence",
                        status=STATUS_BLOCKED,
                        message=f"Campo '{field_name}' está marcado como '{stat or origin}' pero carece de referencias de evidencia en el PDF.",
                        details={"field_name": field_name, "status": stat, "origin": origin},
                    )
                )
            else:
                items.append(
                    VerificationItem(
                        item_id=f"{id_prefix}_evidence_missing",
                        path=f"{path_prefix}/evidence",
                        scope=scope,
                        target=f"{target_prefix}.evidence",
                        status=STATUS_NEEDS_TEACHER_REVIEW,
                        message=f"Campo '{field_name}' carece de evidencia textual directa en el documento fuente.",
                        details={"field_name": field_name},
                    )
                )
            return

        # Canonical field lists may have one literal citation per physical page.
        # Every value must have valid cited support, not merely appear somewhere
        # in the union of source pages. Other fields retain their existing rules.
        campos_coverage = None
        if scope == SCOPE_GENERAL and field_name == "campos_formativos" and isinstance(val, list):
            campos_coverage = _campos_cited_coverage(val, ev_list, actual_sha256, norm_pages_text)

        # 6. Verify each evidence citation for extracted fields
        for ev_idx, ev in enumerate(ev_list):
            ev_item_id = f"{id_prefix}_ev_{ev_idx}"
            ev_path = f"{path_prefix}/evidence/{ev_idx}"
            ev_target = f"{target_prefix}.evidence.{ev_idx}"

            if not isinstance(ev, dict) and not hasattr(ev, "page_number"):
                items.append(
                    VerificationItem(
                        item_id=ev_item_id,
                        path=ev_path,
                        scope=scope,
                        target=ev_target,
                        status=STATUS_BLOCKED,
                        message=f"Evidencia {ev_idx} de '{field_name}' está malformada.",
                        details={"field_name": field_name, "evidence_index": ev_idx},
                    )
                )
                continue

            ev_page = getattr(ev, "page_number", None) if not isinstance(ev, dict) else ev.get("page_number")
            ev_sha = getattr(ev, "document_sha256", "") if not isinstance(ev, dict) else ev.get("document_sha256", "")
            ev_excerpt = getattr(ev, "excerpt", "") if not isinstance(ev, dict) else ev.get("excerpt", "")

            # A. Page range check
            if (
                ev_page is None
                or not isinstance(ev_page, int)
                or isinstance(ev_page, bool)
                or ev_page < 1
                or ev_page > pdf_page_count
            ):
                items.append(
                    VerificationItem(
                        item_id=ev_item_id,
                        path=ev_path,
                        scope=scope,
                        target=ev_target,
                        status=STATUS_BLOCKED,
                        page_number=ev_page if isinstance(ev_page, int) and not isinstance(ev_page, bool) else None,
                        message=f"Evidencia de '{field_name}' apunta a página {ev_page}, fuera de rango válido (1 a {pdf_page_count}).",
                        excerpt=str(ev_excerpt or ""),
                        evidence_sha256=str(ev_sha or ""),
                        details={"field_name": field_name, "page_number": ev_page},
                    )
                )
                continue

            # B. Document SHA coherence check
            if str(ev_sha or "").strip().lower() != actual_sha256.lower():
                items.append(
                    VerificationItem(
                        item_id=ev_item_id,
                        path=ev_path,
                        scope=scope,
                        target=ev_target,
                        status=STATUS_BLOCKED,
                        page_number=ev_page,
                        message=(
                            f"Evidencia de '{field_name}' en página {ev_page} tiene un hash SHA-256 "
                            f"({str(ev_sha)[:12]}…) que no coincide con el archivo físico ({actual_sha256[:12]}…)."
                        ),
                        excerpt=str(ev_excerpt or ""),
                        evidence_sha256=str(ev_sha or ""),
                        details={"field_name": field_name, "expected_sha": actual_sha256, "ev_sha": ev_sha},
                    )
                )
                continue

            # C. Excerpt non-empty check
            norm_ex = normalize_text_for_evidence_check(ev_excerpt)
            if not norm_ex:
                items.append(
                    VerificationItem(
                        item_id=ev_item_id,
                        path=ev_path,
                        scope=scope,
                        target=ev_target,
                        status=STATUS_BLOCKED,
                        page_number=ev_page,
                        message=f"Evidencia declarada para '{field_name}' en página {ev_page} contiene un fragmento de texto vacío o en blanco.",
                        excerpt=str(ev_excerpt or ""),
                        evidence_sha256=str(ev_sha or ""),
                        details={"field_name": field_name, "page_number": ev_page},
                    )
                )
                continue

            # D. Physical page text extraction check
            page_idx = ev_page - 1

            # Scope session structural consistency check: declared pages
            if scope == SCOPE_SESSION:
                decl_pages = session_declared_pages.get(str(parent_id), set())
                if decl_pages and ev_page not in decl_pages:
                    items.append(
                        VerificationItem(
                            item_id=ev_item_id,
                            path=ev_path,
                            scope=scope,
                            target=ev_target,
                            status=STATUS_NEEDS_TEACHER_REVIEW,
                            page_number=ev_page,
                            message=(
                                f"Asociación estructural no demostrada: la página física {ev_page} "
                                f"no pertenece a las páginas declaradas de la sesión '{parent_id}' ({sorted(decl_pages)})."
                            ),
                            excerpt=str(ev_excerpt or ""),
                            evidence_sha256=str(ev_sha or ""),
                            details={
                                "field_name": field_name,
                                "page_number": ev_page,
                                "reason": "asociación estructural no demostrada",
                            },
                        )
                    )
                    continue

            norm_page = norm_pages_text[page_idx] if 0 <= page_idx < len(norm_pages_text) else ""
            if not norm_page:
                items.append(
                    VerificationItem(
                        item_id=ev_item_id,
                        path=ev_path,
                        scope=scope,
                        target=ev_target,
                        status=STATUS_NEEDS_TEACHER_REVIEW,
                        page_number=ev_page,
                        message=f"Página física {ev_page} no contiene texto digital legible (posible imagen o escaneo); requiere verificación visual docente.",
                        excerpt=str(ev_excerpt or ""),
                        evidence_sha256=str(ev_sha or ""),
                        details={"field_name": field_name, "page_number": ev_page},
                    )
                )
                continue

            # E. Physical contiguous match check
            if norm_ex in norm_page:
                # Check if the actual field VALUE is also present
                value_present = _is_value_present(val, norm_page)
                if campos_coverage is not None:
                    value_present = campos_coverage and any(
                        _contains_whole_literal(normalize_text_for_evidence_check(v), norm_ex)
                        for v in val if isinstance(v, str)
                    )
                if value_present:
                    is_structurally_consistent = not (scope == SCOPE_SESSION and str(parent_id) in uncertain_session_ids)
                    inconsistent_reason = (
                        "Límite de sesión no resuelto: el corte de seguridad conserva un tramo sin asignar y requiere revisión docente."
                        if not is_structurally_consistent else ""
                    )

                    if scope == SCOPE_SESSION:
                        if ev_page in page_session_segments and str(parent_id) in page_session_segments[ev_page]:
                            s_segment = page_session_segments[ev_page][str(parent_id)]
                            if norm_ex not in s_segment:
                                is_structurally_consistent = False
                                inconsistent_reason = (
                                    f"Asociación estructural no demostrada: la evidencia de '{field_name}' "
                                    f"no pertenece al segmento de la sesión '{parent_id}' en la página física {ev_page}."
                                )
                            elif not _is_value_present(val, s_segment):
                                is_structurally_consistent = False
                                inconsistent_reason = (
                                    f"Asociación estructural no demostrada: el valor de '{field_name}' "
                                    f"no pertenece al segmento de la sesión '{parent_id}' en la página física {ev_page}."
                                )

                    if is_structurally_consistent and (ev_page, norm_ex) in shared_citations:
                        claims = shared_citations[(ev_page, norm_ex)]
                        if len(claims) > 1:
                            if scope == SCOPE_SESSION and field_name in ("inicio", "desarrollo", "cierre"):
                                s_segment = page_session_segments.get(ev_page, {}).get(str(parent_id), norm_page)
                                if not _is_moment_consistent(field_name, norm_ex, s_segment):
                                    is_structurally_consistent = False
                                    inconsistent_reason = (
                                        f"Asociación estructural no demostrada: fragmento compartido citado en "
                                        f"múltiples campos no corresponde estructuralmente al momento '{field_name}'."
                                    )

                    if is_structurally_consistent:
                        items.append(
                            VerificationItem(
                                item_id=ev_item_id,
                                path=ev_path,
                                scope=scope,
                                target=ev_target,
                                status=STATUS_CHECKED,
                                page_number=ev_page,
                                message=f"Dato de '{field_name}' comprobado textualmente en página física {ev_page}.",
                                excerpt=str(ev_excerpt or ""),
                                evidence_sha256=str(ev_sha or ""),
                                details={"field_name": field_name, "page_number": ev_page},
                            )
                        )
                    else:
                        items.append(
                            VerificationItem(
                                item_id=ev_item_id,
                                path=ev_path,
                                scope=scope,
                                target=ev_target,
                                status=STATUS_NEEDS_TEACHER_REVIEW,
                                page_number=ev_page,
                                message=inconsistent_reason,
                                excerpt=str(ev_excerpt or ""),
                                evidence_sha256=str(ev_sha or ""),
                                details={
                                    "field_name": field_name,
                                    "page_number": ev_page,
                                    "reason": "asociación estructural no demostrada",
                                },
                            )
                        )
                else:
                    items.append(
                        VerificationItem(
                            item_id=ev_item_id,
                            path=ev_path,
                            scope=scope,
                            target=ev_target,
                            status=STATUS_NEEDS_TEACHER_REVIEW,
                            page_number=ev_page,
                            message=(
                                f"Fuente de '{field_name}' localizada en página física {ev_page}, "
                                + (
                                    "pero falta cobertura textual de todos los valores en citas válidas, "
                                    "o esta cita no respalda ningún valor."
                                    if campos_coverage is not None
                                    else "pero el valor del campo no se encontró textualmente en la página."
                                )
                            ),
                            excerpt=str(ev_excerpt or ""),
                            evidence_sha256=str(ev_sha or ""),
                            details={"field_name": field_name, "page_number": ev_page, "reason": "source_located_value_missing"},
                        )
                    )
            else:
                items.append(
                    VerificationItem(
                        item_id=ev_item_id,
                        path=ev_path,
                        scope=scope,
                        target=ev_target,
                        status=STATUS_BLOCKED,
                        page_number=ev_page,
                        message=(
                            f"Contradicción física: El texto citado en la evidencia de '{field_name}' "
                            f"no se encuentra en la página física {ev_page}."
                        ),
                        excerpt=str(ev_excerpt or ""),
                        evidence_sha256=str(ev_sha or ""),
                        details={"field_name": field_name, "page_number": ev_page, "excerpt": str(ev_excerpt or "")},
                    )
                )

    # C. General Fields Traversal
    if isinstance(raw_general, dict):
        if not raw_general:
            items.append(
                VerificationItem(
                    item_id="general_fields_empty",
                    path="general_fields",
                    scope=SCOPE_GENERAL,
                    target="general_fields",
                    status=STATUS_BLOCKED,
                    message="Estructura vacía: general_fields no contiene ningún campo.",
                    details={"field_count": 0},
                )
            )
        for g_canon in CANONICAL_GENERAL_FIELDS:
            if g_canon not in raw_general:
                items.append(
                    VerificationItem(
                        item_id=f"gen_{g_canon}_missing",
                        path=f"general_fields/{g_canon}",
                        scope=SCOPE_GENERAL,
                        target=f"general.{g_canon}",
                        status=STATUS_NEEDS_TEACHER_REVIEW,
                        message=f"Campo canónico general '{g_canon}' no está presente en la planeación; pendiente de revisión docente.",
                        details={"field_name": g_canon, "present": False},
                    )
                )
        for g_name, g_field in raw_general.items():
            _verify_field_evidence(SCOPE_GENERAL, parent_id="general", field_name=g_name, field_data=g_field)
    elif raw_general is not None:
        items.append(
            VerificationItem(
                item_id="general_fields_malformed",
                path="general_fields",
                scope=SCOPE_GENERAL,
                target="general_fields",
                status=STATUS_BLOCKED,
                message="Estructura malformada: general_fields debe ser un diccionario/mapa.",
                details={"type": type(raw_general).__name__},
            )
        )

    # D. Sessions Traversal
    if isinstance(raw_sessions, list):
        if not raw_sessions:
            items.append(
                VerificationItem(
                    item_id="sessions_empty",
                    path="sessions",
                    scope=SCOPE_SESSION,
                    target="sessions",
                    status=STATUS_BLOCKED,
                    message="La planeación no contiene sesiones (lista vacía); se requiere al menos una sesión.",
                    details={"session_count": 0},
                )
            )
        seen_session_ids: dict[str, int] = {}
        for s_idx, s_item in enumerate(raw_sessions):
            if not isinstance(s_item, dict) and not hasattr(s_item, "session_id"):
                items.append(
                    VerificationItem(
                        item_id=f"sess_{s_idx}_malformed",
                        path=f"sessions/{s_idx}",
                        scope=SCOPE_SESSION,
                        target=f"session.{s_idx}",
                        status=STATUS_BLOCKED,
                        message=f"Estructura malformada en sesión índice {s_idx}.",
                        details={"index": s_idx},
                    )
                )
                continue

            raw_s_id = getattr(s_item, "session_id", None) if not isinstance(s_item, dict) else s_item.get("session_id")
            s_num = getattr(s_item, "session_number", None) if not isinstance(s_item, dict) else s_item.get("session_number")
            s_pages = getattr(s_item, "pages", []) if not isinstance(s_item, dict) else s_item.get("pages", [])
            s_cont = getattr(s_item, "continues_on", []) if not isinstance(s_item, dict) else s_item.get("continues_on", [])
            s_fields = getattr(s_item, "fields", {}) if not isinstance(s_item, dict) else s_item.get("fields", {})
            s_annexes = getattr(s_item, "annex_references", []) if not isinstance(s_item, dict) else s_item.get("annex_references", [])

            if not raw_s_id or not isinstance(raw_s_id, str):
                items.append(
                    VerificationItem(
                        item_id=f"sess_{s_idx}_id_invalid",
                        path=f"sessions/{s_idx}/session_id",
                        scope=SCOPE_SESSION,
                        target=f"session.{s_idx}.session_id",
                        status=STATUS_BLOCKED,
                        message=f"Identidad inválida de sesión en índice {s_idx}: session_id requerido.",
                        details={"session_id": raw_s_id},
                    )
                )
                s_id = f"s_{s_idx}"
            elif raw_s_id in seen_session_ids:
                items.append(
                    VerificationItem(
                        item_id=f"sess_{s_idx}_id_duplicate_{raw_s_id}",
                        path=f"sessions/{s_idx}/session_id",
                        scope=SCOPE_SESSION,
                        target=f"session.{s_idx}.session_id.{raw_s_id}",
                        status=STATUS_BLOCKED,
                        message=f"Conflicto de identidad: session_id '{raw_s_id}' duplicado en sesiones índices {seen_session_ids[raw_s_id]} y {s_idx}.",
                        details={"session_id": raw_s_id, "first_index": seen_session_ids[raw_s_id], "duplicate_index": s_idx},
                    )
                )
                s_id = f"{raw_s_id}_idx{s_idx}"
            else:
                seen_session_ids[raw_s_id] = s_idx
                s_id = raw_s_id

            if not isinstance(s_num, int) or isinstance(s_num, bool) or s_num < 1:
                items.append(
                    VerificationItem(
                        item_id=f"sess_{s_id}_number_invalid",
                        path=f"sessions/{s_id}/session_number",
                        scope=SCOPE_SESSION,
                        target=f"session.{s_id}.session_number",
                        status=STATUS_BLOCKED,
                        message=f"Número de sesión inválido para sesión '{s_id}': debe ser entero positivo.",
                        details={"session_number": s_num},
                    )
                )

            # Pages validation
            if not isinstance(s_pages, list) or not s_pages:
                items.append(
                    VerificationItem(
                        item_id=f"sess_{s_id}_pages_empty",
                        path=f"sessions/{s_id}/pages",
                        scope=SCOPE_SESSION,
                        target=f"session.{s_id}.pages",
                        status=STATUS_BLOCKED,
                        message=f"Sesión '{s_id}' carece de páginas asignadas.",
                        details={"pages": s_pages},
                    )
                )
            else:
                for p_idx, p in enumerate(s_pages):
                    if not isinstance(p, int) or isinstance(p, bool) or p < 1 or p > pdf_page_count:
                        items.append(
                            VerificationItem(
                                item_id=f"sess_{s_id}_page_{p_idx}",
                                path=f"sessions/{s_id}/pages/{p_idx}",
                                scope=SCOPE_SESSION,
                                target=f"session.{s_id}.pages.{p_idx}",
                                status=STATUS_BLOCKED,
                                page_number=p if isinstance(p, int) and not isinstance(p, bool) else None,
                                message=f"Sesión '{s_id}' declara página {p} fuera de rango físico (1 a {pdf_page_count}).",
                                details={"session_id": s_id, "page": p},
                            )
                        )
                    else:
                        items.append(
                            VerificationItem(
                                item_id=f"sess_{s_id}_page_{p_idx}",
                                path=f"sessions/{s_id}/pages/{p_idx}",
                                scope=SCOPE_SESSION,
                                target=f"session.{s_id}.pages.{p_idx}",
                                status=STATUS_CHECKED,
                                page_number=p,
                                message=f"Página física {p} de la sesión '{s_id}' está dentro del rango del documento.",
                                details={"session_id": s_id, "page": p},
                            )
                        )

            for cp_idx, cp in enumerate(s_cont or []):
                if not isinstance(cp, int) or isinstance(cp, bool) or cp < 1 or cp > pdf_page_count:
                    items.append(
                        VerificationItem(
                            item_id=f"sess_{s_id}_cont_{cp_idx}",
                            path=f"sessions/{s_id}/continues_on/{cp_idx}",
                            scope=SCOPE_SESSION,
                            target=f"session.{s_id}.continues_on.{cp_idx}",
                            status=STATUS_BLOCKED,
                            page_number=cp if isinstance(cp, int) and not isinstance(cp, bool) else None,
                            message=f"Sesión '{s_id}' declara continuación en página {cp} fuera de rango físico.",
                            details={"session_id": s_id, "page": cp},
                        )
                    )

            # Session moments / fields validation
            if isinstance(s_fields, dict):
                if not s_fields:
                    items.append(
                        VerificationItem(
                            item_id=f"sess_{s_id}_fields_empty",
                            path=f"sessions/{s_id}/fields",
                            scope=SCOPE_SESSION,
                            target=f"session.{s_id}.fields",
                            status=STATUS_BLOCKED,
                            message=f"Estructura vacía: fields en sesión '{s_id}' no contiene ningún campo.",
                            details={"session_id": s_id, "field_count": 0},
                        )
                    )
                for sf_canon in CANONICAL_SESSION_FIELDS:
                    if sf_canon not in s_fields:
                        items.append(
                            VerificationItem(
                                item_id=f"sess_{s_id}_{sf_canon}_missing",
                                path=f"sessions/{s_id}/fields/{sf_canon}",
                                scope=SCOPE_SESSION,
                                target=f"session.{s_id}.{sf_canon}",
                                status=STATUS_NEEDS_TEACHER_REVIEW,
                                message=f"Momento canónico '{sf_canon}' no presente en la sesión '{s_id}'; pendiente de revisión docente.",
                                details={"session_id": s_id, "field_name": sf_canon, "present": False},
                            )
                        )
                for sf_name, sf_field in s_fields.items():
                    _verify_field_evidence(SCOPE_SESSION, parent_id=s_id, field_name=sf_name, field_data=sf_field)
            else:
                items.append(
                    VerificationItem(
                        item_id=f"sess_{s_id}_fields_malformed",
                        path=f"sessions/{s_id}/fields",
                        scope=SCOPE_SESSION,
                        target=f"session.{s_id}.fields",
                        status=STATUS_BLOCKED,
                        message=f"Estructura malformada: fields en sesión '{s_id}' debe ser un diccionario.",
                        details={"session_id": s_id},
                    )
                )

            # Session annex references validation
            if isinstance(s_annexes, list):
                for a_idx, annex in enumerate(s_annexes):
                    if not isinstance(annex, dict) and not hasattr(annex, "annex_number"):
                        items.append(
                            VerificationItem(
                                item_id=f"annex_{s_id}_idx_{a_idx}_malformed",
                                path=f"sessions/{s_id}/annex_references/{a_idx}",
                                scope=SCOPE_ANNEX,
                                target=f"session.{s_id}.annex.{a_idx}",
                                status=STATUS_BLOCKED,
                                message=f"Elemento de anexo en índice {a_idx} de sesión '{s_id}' está malformado (escalar o tipo no soportado).",
                                details={"session_id": s_id, "annex_index": a_idx, "raw_value": str(annex)[:100]},
                            )
                        )
                        continue

                    ref_id = getattr(annex, "reference_id", None) if not isinstance(annex, dict) else annex.get("reference_id")
                    num_str = getattr(annex, "annex_number", "") if not isinstance(annex, dict) else annex.get("annex_number", "")
                    ref_token = str(ref_id or (f"num_{num_str}" if num_str else f"ref_{a_idx}"))
                    conf_page = getattr(annex, "confirmed_page", None) if not isinstance(annex, dict) else annex.get("confirmed_page")
                    cand_pages = getattr(annex, "candidate_pages", []) if not isinstance(annex, dict) else annex.get("candidate_pages", [])
                    annex_rev = getattr(annex, "review", "") if not isinstance(annex, dict) else annex.get("review", "")
                    annex_ev = getattr(annex, "evidence", []) if not isinstance(annex, dict) else annex.get("evidence", [])

                    # Candidate pages bounds check
                    for cp_idx, cp in enumerate(cand_pages or []):
                        if not isinstance(cp, int) or isinstance(cp, bool) or cp < 1 or cp > pdf_page_count:
                            items.append(
                                VerificationItem(
                                    item_id=f"annex_{s_id}_{ref_token}_cand_p{cp_idx}",
                                    path=f"sessions/{s_id}/annex_references/{ref_token}/candidate_pages/{cp_idx}",
                                    scope=SCOPE_ANNEX,
                                    target=f"session.{s_id}.annex.{ref_token}.candidate_page.{cp}",
                                    status=STATUS_BLOCKED,
                                    page_number=cp if isinstance(cp, int) and not isinstance(cp, bool) else None,
                                    message=f"Anexo {ref_token} tiene lámina candidata {cp} fuera de rango.",
                                    details={"session_id": s_id, "reference_id": ref_id, "candidate_page": cp},
                                )
                            )

                    # Confirmed page check
                    if conf_page is None or annex_rev != "confirmed":
                        items.append(
                            VerificationItem(
                                item_id=f"annex_{s_id}_{ref_token}_conf",
                                path=f"sessions/{s_id}/annex_references/{ref_token}/confirmed_page",
                                scope=SCOPE_ANNEX,
                                target=f"session.{s_id}.annex.{ref_token}.confirmed_page",
                                status=STATUS_NEEDS_TEACHER_REVIEW,
                                message=f"Anexo {ref_token} en sesión {s_id} está sin confirmar por el docente.",
                                details={"session_id": s_id, "reference_id": ref_id, "annex_number": num_str, "review": annex_rev},
                            )
                        )
                    elif not isinstance(conf_page, int) or isinstance(conf_page, bool) or conf_page < 1 or conf_page > pdf_page_count:
                        items.append(
                            VerificationItem(
                                item_id=f"annex_{s_id}_{ref_token}_conf",
                                path=f"sessions/{s_id}/annex_references/{ref_token}/confirmed_page",
                                scope=SCOPE_ANNEX,
                                target=f"session.{s_id}.annex.{ref_token}.confirmed_page",
                                status=STATUS_BLOCKED,
                                page_number=conf_page if isinstance(conf_page, int) and not isinstance(conf_page, bool) else None,
                                message=f"Anexo {ref_token} tiene lámina confirmada {conf_page} fuera de rango físico (1 a {pdf_page_count}).",
                                details={"session_id": s_id, "reference_id": ref_id, "confirmed_page": conf_page},
                            )
                        )
                    else:
                        # Confirmed annex requires coherent physical evidence on confirmed_page!
                        has_coherent_match = False
                        has_contradiction = False
                        for ev in (annex_ev or []):
                            ep = getattr(ev, "page_number", None) if not isinstance(ev, dict) else ev.get("page_number")
                            es = getattr(ev, "document_sha256", "") if not isinstance(ev, dict) else ev.get("document_sha256", "")
                            ex = getattr(ev, "excerpt", "") if not isinstance(ev, dict) else ev.get("excerpt", "")
                            if ep == conf_page and str(es or "").strip().lower() == actual_sha256.lower():
                                norm_ex = normalize_text_for_evidence_check(ex)
                                if norm_ex:
                                    p_idx = conf_page - 1
                                    norm_p = norm_pages_text[p_idx] if 0 <= p_idx < len(norm_pages_text) else ""
                                    if norm_p and norm_ex in norm_p:
                                        has_coherent_match = True
                                    elif norm_p and norm_ex not in norm_p:
                                        has_contradiction = True

                        if has_contradiction:
                            items.append(
                                VerificationItem(
                                    item_id=f"annex_{s_id}_{ref_token}_conf",
                                    path=f"sessions/{s_id}/annex_references/{ref_token}/confirmed_page",
                                    scope=SCOPE_ANNEX,
                                    target=f"session.{s_id}.annex.{ref_token}.confirmed_page",
                                    status=STATUS_BLOCKED,
                                    page_number=conf_page,
                                    message=f"Contradicción física: evidencia de anexo {ref_token} en página {conf_page} no concuerda con el texto físico.",
                                    details={"session_id": s_id, "reference_id": ref_id, "confirmed_page": conf_page},
                                )
                            )
                        elif has_coherent_match:
                            items.append(
                                VerificationItem(
                                    item_id=f"annex_{s_id}_{ref_token}_conf",
                                    path=f"sessions/{s_id}/annex_references/{ref_token}/confirmed_page",
                                    scope=SCOPE_ANNEX,
                                    target=f"session.{s_id}.annex.{ref_token}.confirmed_page",
                                    status=STATUS_CHECKED,
                                    page_number=conf_page,
                                    message=f"Anexo {ref_token} confirmado en lámina física {conf_page} con evidencia cotejada.",
                                    details={"session_id": s_id, "reference_id": ref_id, "confirmed_page": conf_page},
                                )
                            )
                        else:
                            items.append(
                                VerificationItem(
                                    item_id=f"annex_{s_id}_{ref_token}_conf",
                                    path=f"sessions/{s_id}/annex_references/{ref_token}/confirmed_page",
                                    scope=SCOPE_ANNEX,
                                    target=f"session.{s_id}.annex.{ref_token}.confirmed_page",
                                    status=STATUS_BLOCKED,
                                    page_number=conf_page,
                                    message=f"Anexo {ref_token} confirmado en página {conf_page} carece de evidencia física coherente cotejada mecánicamente.",
                                    details={"session_id": s_id, "reference_id": ref_id, "confirmed_page": conf_page},
                                )
                            )
            else:
                items.append(
                    VerificationItem(
                        item_id=f"sess_{s_id}_annexes_malformed",
                        path=f"sessions/{s_id}/annex_references",
                        scope=SCOPE_ANNEX,
                        target=f"session.{s_id}.annex_references",
                        status=STATUS_BLOCKED,
                        message=f"Estructura malformada: annex_references en sesión '{s_id}' debe ser una lista.",
                        details={"session_id": s_id},
                    )
                )

            # Session activities validation
            s_activities = getattr(s_item, "activities", []) if not isinstance(s_item, dict) else s_item.get("activities", [])
            if isinstance(s_activities, list):
                for act_idx, act in enumerate(s_activities):
                    if not isinstance(act, dict) and not hasattr(act, "activity_id"):
                        items.append(
                            VerificationItem(
                                item_id=f"sess_{s_id}_act_{act_idx}_malformed",
                                path=f"sessions/{s_id}/activities/{act_idx}",
                                scope=SCOPE_SESSION,
                                target=f"session.{s_id}.activity.{act_idx}",
                                status=STATUS_BLOCKED,
                                message=f"Estructura malformada en actividad índice {act_idx} de sesión '{s_id}'.",
                                details={"session_id": s_id, "activity_index": act_idx},
                            )
                        )
                        continue

                    raw_act_id = getattr(act, "activity_id", None) if not isinstance(act, dict) else act.get("activity_id")
                    act_id = str(raw_act_id or f"act_{act_idx}")
                    act_annex_ids = getattr(act, "annex_ids", []) if not isinstance(act, dict) else act.get("annex_ids", [])
                    act_evidence = getattr(act, "evidence", []) if not isinstance(act, dict) else act.get("evidence", [])
                    act_annex_ev = getattr(act, "annex_evidence", {}) if not isinstance(act, dict) else act.get("annex_evidence", {})

                    act_target_prefix = f"session.{s_id}.activity.{act_id}"
                    act_path_prefix = f"sessions/{s_id}/activities/{act_id}"
                    act_id_prefix = f"sess_{s_id}_act_{act_id}"

                    # 1. Validate annex_ids: each must exist in session annexes or dossier annexes
                    if isinstance(act_annex_ids, list):
                        for aid in act_annex_ids:
                            aid_str = str(aid).strip()
                            if not aid_str:
                                continue
                            matches = []
                            for r in (s_annexes if isinstance(s_annexes, list) else []):
                                r_id = str(getattr(r, "reference_id", None) if not isinstance(r, dict) else r.get("reference_id", "") or "").strip()
                                r_num = str(getattr(r, "annex_number", None) if not isinstance(r, dict) else r.get("annex_number", "") or "").strip()
                                r_leg = [str(x) for x in (getattr(r, "legacy_reference_ids", []) if not isinstance(r, dict) else r.get("legacy_reference_ids", []) or [])]
                                keys = {r_id.lower(), r_num.lower(), f"anexo_{r_num.lower()}", f"anexo{r_num.lower()}"} | {x.lower() for x in r_leg}
                                keys.discard("")
                                if aid_str.lower() in keys:
                                    matches.append(r)

                            if not matches:
                                for oth_s in (raw_sessions or []):
                                    if oth_s is s_item:
                                        continue
                                    oth_annexes = getattr(oth_s, "annex_references", []) if not isinstance(oth_s, dict) else oth_s.get("annex_references", [])
                                    for r in (oth_annexes if isinstance(oth_annexes, list) else []):
                                        r_id = str(getattr(r, "reference_id", None) if not isinstance(r, dict) else r.get("reference_id", "") or "").strip()
                                        r_num = str(getattr(r, "annex_number", None) if not isinstance(r, dict) else r.get("annex_number", "") or "").strip()
                                        r_leg = [str(x) for x in (getattr(r, "legacy_reference_ids", []) if not isinstance(r, dict) else r.get("legacy_reference_ids", []) or [])]
                                        keys = {r_id.lower(), r_num.lower(), f"anexo_{r_num.lower()}", f"anexo{r_num.lower()}"} | {x.lower() for x in r_leg}
                                        keys.discard("")
                                        if aid_str.lower() in keys:
                                            matches.append(r)

                            if not matches and isinstance(raw_cands, list):
                                for cand in raw_cands:
                                    c_name = str(getattr(cand, "name", "") if not isinstance(cand, dict) else cand.get("name", "")).strip().lower()
                                    if aid_str.lower() in c_name or c_name in aid_str.lower():
                                        matches.append(cand)

                            if len(matches) == 0:
                                items.append(
                                    VerificationItem(
                                        item_id=f"{act_id_prefix}_annex_{aid_str}_missing",
                                        path=f"{act_path_prefix}/annex_ids/{aid_str}",
                                        scope=SCOPE_SESSION,
                                        target=f"{act_target_prefix}.annex.{aid_str}",
                                        status=STATUS_BLOCKED,
                                        message=f"Actividad '{act_id}' en sesión '{s_id}' referencia anexo inexistente '{aid_str}'.",
                                        details={"session_id": s_id, "activity_id": act_id, "annex_id": aid_str, "anexo_inexistente": aid_str},
                                    )
                                )
                            elif len(matches) > 1:
                                items.append(
                                    VerificationItem(
                                        item_id=f"{act_id_prefix}_annex_{aid_str}_ambiguous",
                                        path=f"{act_path_prefix}/annex_ids/{aid_str}",
                                        scope=SCOPE_SESSION,
                                        target=f"{act_target_prefix}.annex.{aid_str}",
                                        status=STATUS_BLOCKED,
                                        message=f"Actividad '{act_id}' en sesión '{s_id}' referencia ambigua al anexo '{aid_str}' ({len(matches)} coincidencias).",
                                        details={"session_id": s_id, "activity_id": act_id, "annex_id": aid_str, "matches": len(matches)},
                                    )
                                )

                    # 2. Validate evidence: if empty -> needs_teacher_review, else verify citations
                    if not isinstance(act_evidence, list) or not act_evidence:
                        items.append(
                            VerificationItem(
                                item_id=f"{act_id_prefix}_evidence_missing",
                                path=f"{act_path_prefix}/evidence",
                                scope=SCOPE_SESSION,
                                target=f"{act_target_prefix}.evidence",
                                status=STATUS_NEEDS_TEACHER_REVIEW,
                                message=f"Actividad '{act_id}' en sesión '{s_id}' carece de citas de evidencia en el documento fuente.",
                                details={"session_id": s_id, "activity_id": act_id},
                            )
                        )
                    else:
                        decl_pages = session_declared_pages.get(str(s_id), set())
                        for ev_idx, ev in enumerate(act_evidence):
                            ev_item_id = f"{act_id_prefix}_ev_{ev_idx}"
                            ev_path = f"{act_path_prefix}/evidence/{ev_idx}"
                            ev_target = f"{act_target_prefix}.evidence.{ev_idx}"

                            ev_page = getattr(ev, "page_number", None) if not isinstance(ev, dict) else ev.get("page_number")
                            ev_sha = getattr(ev, "document_sha256", "") if not isinstance(ev, dict) else ev.get("document_sha256", "")
                            ev_excerpt = getattr(ev, "excerpt", "") if not isinstance(ev, dict) else ev.get("excerpt", "")

                            if ev_page is None or not isinstance(ev_page, int) or isinstance(ev_page, bool) or ev_page < 1 or ev_page > pdf_page_count:
                                items.append(
                                    VerificationItem(
                                        item_id=ev_item_id,
                                        path=ev_path,
                                        scope=SCOPE_SESSION,
                                        target=ev_target,
                                        status=STATUS_BLOCKED,
                                        page_number=ev_page if isinstance(ev_page, int) and not isinstance(ev_page, bool) else None,
                                        message=f"Evidencia de actividad '{act_id}' apunta a página {ev_page}, fuera de rango válido.",
                                        excerpt=str(ev_excerpt or ""),
                                        evidence_sha256=str(ev_sha or ""),
                                        details={"session_id": s_id, "activity_id": act_id, "page_number": ev_page},
                                    )
                                )
                                continue

                            if str(ev_sha or "").strip().lower() != actual_sha256.lower():
                                items.append(
                                    VerificationItem(
                                        item_id=ev_item_id,
                                        path=ev_path,
                                        scope=SCOPE_SESSION,
                                        target=ev_target,
                                        status=STATUS_BLOCKED,
                                        page_number=ev_page,
                                        message=f"Evidencia de actividad '{act_id}' tiene hash SHA-256 no coincidente.",
                                        excerpt=str(ev_excerpt or ""),
                                        evidence_sha256=str(ev_sha or ""),
                                        details={"session_id": s_id, "activity_id": act_id, "expected_sha": actual_sha256},
                                    )
                                )
                                continue

                            norm_ex = normalize_text_for_evidence_check(ev_excerpt)
                            if not norm_ex:
                                items.append(
                                    VerificationItem(
                                        item_id=ev_item_id,
                                        path=ev_path,
                                        scope=SCOPE_SESSION,
                                        target=ev_target,
                                        status=STATUS_BLOCKED,
                                        page_number=ev_page,
                                        message=f"Evidencia declarada para actividad '{act_id}' contiene fragmento vacío.",
                                        excerpt=str(ev_excerpt or ""),
                                        evidence_sha256=str(ev_sha or ""),
                                        details={"session_id": s_id, "activity_id": act_id, "page_number": ev_page},
                                    )
                                )
                                continue

                            if decl_pages and ev_page not in decl_pages:
                                items.append(
                                    VerificationItem(
                                        item_id=ev_item_id,
                                        path=ev_path,
                                        scope=SCOPE_SESSION,
                                        target=ev_target,
                                        status=STATUS_NEEDS_TEACHER_REVIEW,
                                        page_number=ev_page,
                                        message=f"Asociación estructural no demostrada: la página física {ev_page} no pertenece a las páginas declaradas de la sesión '{s_id}'.",
                                        excerpt=str(ev_excerpt or ""),
                                        evidence_sha256=str(ev_sha or ""),
                                        details={"session_id": s_id, "activity_id": act_id, "page_number": ev_page, "reason": "asociación estructural no demostrada"},
                                    )
                                )
                                continue

                            page_idx = ev_page - 1
                            norm_page = norm_pages_text[page_idx] if 0 <= page_idx < len(norm_pages_text) else ""
                            if not norm_page:
                                items.append(
                                    VerificationItem(
                                        item_id=ev_item_id,
                                        path=ev_path,
                                        scope=SCOPE_SESSION,
                                        target=ev_target,
                                        status=STATUS_NEEDS_TEACHER_REVIEW,
                                        page_number=ev_page,
                                        message=f"Página física {ev_page} no contiene texto digital legible.",
                                        excerpt=str(ev_excerpt or ""),
                                        evidence_sha256=str(ev_sha or ""),
                                        details={"session_id": s_id, "activity_id": act_id, "page_number": ev_page},
                                    )
                                )
                                continue

                            if norm_ex not in norm_page:
                                items.append(
                                    VerificationItem(
                                        item_id=ev_item_id,
                                        path=ev_path,
                                        scope=SCOPE_SESSION,
                                        target=ev_target,
                                        status=STATUS_BLOCKED,
                                        page_number=ev_page,
                                        message=f"Contradicción física: evidencia de actividad '{act_id}' no se encuentra en la página física {ev_page}.",
                                        excerpt=str(ev_excerpt or ""),
                                        evidence_sha256=str(ev_sha or ""),
                                        details={"session_id": s_id, "activity_id": act_id, "page_number": ev_page},
                                    )
                                )
                                continue

                            if ev_page in page_session_segments and str(s_id) in page_session_segments[ev_page]:
                                s_seg = page_session_segments[ev_page][str(s_id)]
                                if str(s_id) in uncertain_session_ids or norm_ex not in s_seg:
                                    items.append(
                                        VerificationItem(
                                            item_id=ev_item_id,
                                            path=ev_path,
                                            scope=SCOPE_SESSION,
                                            target=ev_target,
                                            status=STATUS_NEEDS_TEACHER_REVIEW,
                                            page_number=ev_page,
                                            message=f"Asociación estructural no demostrada: la evidencia de actividad '{act_id}' no pertenece al segmento de la sesión '{s_id}'.",
                                            excerpt=str(ev_excerpt or ""),
                                            evidence_sha256=str(ev_sha or ""),
                                            details={"session_id": s_id, "activity_id": act_id, "page_number": ev_page, "reason": "asociación estructural no demostrada"},
                                        )
                                    )
                                    continue

                            items.append(
                                VerificationItem(
                                    item_id=ev_item_id,
                                    path=ev_path,
                                    scope=SCOPE_SESSION,
                                    target=ev_target,
                                    status=STATUS_CHECKED,
                                    page_number=ev_page,
                                    message=f"Evidencia de actividad '{act_id}' comprobada textualmente en página física {ev_page}.",
                                    excerpt=str(ev_excerpt or ""),
                                    evidence_sha256=str(ev_sha or ""),
                                    details={"session_id": s_id, "activity_id": act_id, "page_number": ev_page},
                                )
                            )

                    # 3. Validate annex_evidence if present
                    if isinstance(act_annex_ev, dict):
                        for a_key, a_ev_list in act_annex_ev.items():
                            if not isinstance(a_ev_list, list):
                                continue
                            for a_ev_idx, a_ev in enumerate(a_ev_list):
                                a_ev_item_id = f"{act_id_prefix}_aev_{a_key}_{a_ev_idx}"
                                a_ev_path = f"{act_path_prefix}/annex_evidence/{a_key}/{a_ev_idx}"
                                a_ev_target = f"{act_target_prefix}.annex_evidence.{a_key}.{a_ev_idx}"

                                a_ev_page = getattr(a_ev, "page_number", None) if not isinstance(a_ev, dict) else a_ev.get("page_number")
                                a_ev_sha = getattr(a_ev, "document_sha256", "") if not isinstance(a_ev, dict) else a_ev.get("document_sha256", "")
                                a_ev_excerpt = getattr(a_ev, "excerpt", "") if not isinstance(a_ev, dict) else a_ev.get("excerpt", "")

                                if a_ev_page is None or not isinstance(a_ev_page, int) or isinstance(a_ev_page, bool) or a_ev_page < 1 or a_ev_page > pdf_page_count:
                                    items.append(
                                        VerificationItem(
                                            item_id=a_ev_item_id,
                                            path=a_ev_path,
                                            scope=SCOPE_SESSION,
                                            target=a_ev_target,
                                            status=STATUS_BLOCKED,
                                            page_number=a_ev_page if isinstance(a_ev_page, int) and not isinstance(a_ev_page, bool) else None,
                                            message=f"Evidencia de anexo '{a_key}' para actividad '{act_id}' apunta a página {a_ev_page}, fuera de rango válido.",
                                            excerpt=str(a_ev_excerpt or ""),
                                            evidence_sha256=str(a_ev_sha or ""),
                                            details={"session_id": s_id, "activity_id": act_id, "annex_key": a_key},
                                        )
                                    )
                                    continue

                                if str(a_ev_sha or "").strip().lower() != actual_sha256.lower():
                                    items.append(
                                        VerificationItem(
                                            item_id=a_ev_item_id,
                                            path=a_ev_path,
                                            scope=SCOPE_SESSION,
                                            target=a_ev_target,
                                            status=STATUS_BLOCKED,
                                            page_number=a_ev_page,
                                            message=f"Evidencia de anexo '{a_key}' para actividad '{act_id}' tiene hash SHA-256 no coincidente.",
                                            excerpt=str(a_ev_excerpt or ""),
                                            evidence_sha256=str(a_ev_sha or ""),
                                            details={"session_id": s_id, "activity_id": act_id, "annex_key": a_key},
                                        )
                                    )
                                    continue

                                a_norm_ex = normalize_text_for_evidence_check(a_ev_excerpt)
                                if not a_norm_ex:
                                    items.append(
                                        VerificationItem(
                                            item_id=a_ev_item_id,
                                            path=a_ev_path,
                                            scope=SCOPE_SESSION,
                                            target=a_ev_target,
                                            status=STATUS_BLOCKED,
                                            page_number=a_ev_page,
                                            message=f"Evidencia de anexo '{a_key}' para actividad '{act_id}' contiene fragmento vacío.",
                                            excerpt=str(a_ev_excerpt or ""),
                                            evidence_sha256=str(a_ev_sha or ""),
                                            details={"session_id": s_id, "activity_id": act_id, "annex_key": a_key},
                                        )
                                    )
                                    continue

                                a_page_idx = a_ev_page - 1
                                a_norm_page = norm_pages_text[a_page_idx] if 0 <= a_page_idx < len(norm_pages_text) else ""
                                if a_norm_page and a_norm_ex in a_norm_page:
                                    items.append(
                                        VerificationItem(
                                            item_id=a_ev_item_id,
                                            path=a_ev_path,
                                            scope=SCOPE_SESSION,
                                            target=a_ev_target,
                                            status=STATUS_CHECKED,
                                            page_number=a_ev_page,
                                            message=f"Evidencia de anexo '{a_key}' para actividad '{act_id}' comprobada en página física {a_ev_page}.",
                                            excerpt=str(a_ev_excerpt or ""),
                                            evidence_sha256=str(a_ev_sha or ""),
                                            details={"session_id": s_id, "activity_id": act_id, "annex_key": a_key},
                                        )
                                    )
                                else:
                                    items.append(
                                        VerificationItem(
                                            item_id=a_ev_item_id,
                                            path=a_ev_path,
                                            scope=SCOPE_SESSION,
                                            target=a_ev_target,
                                            status=STATUS_BLOCKED,
                                            page_number=a_ev_page,
                                            message=f"Evidencia de anexo '{a_key}' para actividad '{act_id}' no coincide con el texto físico en página {a_ev_page}.",
                                            excerpt=str(a_ev_excerpt or ""),
                                            evidence_sha256=str(a_ev_sha or ""),
                                            details={"session_id": s_id, "activity_id": act_id, "annex_key": a_key},
                                        )
                                    )
            elif s_activities is not None:
                items.append(
                    VerificationItem(
                        item_id=f"sess_{s_id}_activities_malformed",
                        path=f"sessions/{s_id}/activities",
                        scope=SCOPE_SESSION,
                        target=f"session.{s_id}.activities",
                        status=STATUS_BLOCKED,
                        message=f"Estructura malformada: activities en sesión '{s_id}' debe ser una lista.",
                        details={"session_id": s_id},
                    )
                )

    elif raw_sessions is not None:
        items.append(
            VerificationItem(
                item_id="sessions_malformed",
                path="sessions",
                scope=SCOPE_SESSION,
                target="sessions",
                status=STATUS_BLOCKED,
                message="Estructura malformada: sessions debe ser una lista.",
                details={"type": type(raw_sessions).__name__},
            )
        )

    # E. Annex Candidates Traversal
    if isinstance(raw_cands, list):
        for c_idx, cand in enumerate(raw_cands):
            if not isinstance(cand, dict) and not hasattr(cand, "page"):
                items.append(
                    VerificationItem(
                        item_id=f"annex_cand_{c_idx}",
                        path=f"annex_candidates/{c_idx}",
                        scope=SCOPE_ANNEX,
                        target=f"annex_candidate.{c_idx}",
                        status=STATUS_BLOCKED,
                        message="Lámina candidata de anexo malformada.",
                        details={"index": c_idx},
                    )
                )
                continue
            p_cand = cand.get("page") if isinstance(cand, dict) else getattr(cand, "page", None)
            lbl = cand.get("label", "") if isinstance(cand, dict) else getattr(cand, "label", "")
            if p_cand is None or not isinstance(p_cand, int) or isinstance(p_cand, bool):
                items.append(
                    VerificationItem(
                        item_id=f"annex_cand_{c_idx}",
                        path=f"annex_candidates/{c_idx}",
                        scope=SCOPE_ANNEX,
                        target=f"annex_candidate.{c_idx}",
                        status=STATUS_BLOCKED,
                        message=f"Lámina candidata '{lbl}' carece de número de página física válido.",
                        details={"index": c_idx, "page": p_cand, "label": lbl},
                    )
                )
            elif p_cand < 1 or p_cand > pdf_page_count:
                items.append(
                    VerificationItem(
                        item_id=f"annex_cand_{c_idx}",
                        path=f"annex_candidates/{c_idx}",
                        scope=SCOPE_ANNEX,
                        target=f"annex_candidate.{c_idx}",
                        status=STATUS_BLOCKED,
                        page_number=p_cand,
                        message=f"Lámina candidata '{lbl}' apunta a página {p_cand} fuera de rango físico (1 a {pdf_page_count}).",
                        details={"index": c_idx, "page": p_cand, "label": lbl},
                    )
                )
            else:
                # Candidate sheet within range: NEVER checked, always needs_teacher_review!
                items.append(
                    VerificationItem(
                        item_id=f"annex_cand_{c_idx}",
                        path=f"annex_candidates/{c_idx}",
                        scope=SCOPE_ANNEX,
                        target=f"annex_candidate.{c_idx}",
                        status=STATUS_NEEDS_TEACHER_REVIEW,
                        page_number=p_cand,
                        message=f"Lámina candidata '{lbl or f'Lámina {p_cand}'}' en página física {p_cand}; requiere confirmación docente.",
                        details={"index": c_idx, "page": p_cand, "label": lbl},
                    )
                )
    elif raw_cands is not None:
        items.append(
            VerificationItem(
                item_id="annex_candidates_malformed",
                path="annex_candidates",
                scope=SCOPE_ANNEX,
                target="annex_candidates",
                status=STATUS_BLOCKED,
                message="Estructura malformada: annex_candidates debe ser una lista.",
                details={"type": type(raw_cands).__name__},
            )
        )

    # F. Operational Queue Traversal (F7, SCOPE_QUEUE)
    # Only derive operational queue if the structure is safe (no structural blocks detected)
    has_structural_blocks = any(i.status == STATUS_BLOCKED for i in items)
    if not is_structurally_empty and not has_structural_blocks:
        try:
            from curriculum.source_interpreter import ImportDossier, derive_operational_queue
            if isinstance(dossier, ImportDossier):
                q_dossier = dossier
            elif dossier_obj is not None:
                q_dossier = dossier_obj
            else:
                q_dossier = ImportDossier.from_dict(dossier_dict)

            queue = derive_operational_queue(q_dossier)
            for q_it in queue.items:
                q_status = (
                    STATUS_CHECKED
                    if q_it.priority_state in ("resolved", "confirmed")
                    else STATUS_NEEDS_TEACHER_REVIEW
                )
                items.append(
                    VerificationItem(
                        item_id=f"q_{q_it.item_id}",
                        path=f"queue/{q_it.item_id}",
                        scope=SCOPE_QUEUE,
                        target=f"queue.{q_it.target_id}",
                        status=q_status,
                        page_number=q_it.page_number,
                        message=(
                            f"Ítem en cola operativa: {q_it.human_label} ({q_it.priority_state}). "
                            f"{q_it.problem_summary or q_it.blocks_action or 'Requiere atención docente.'}"
                        ),
                        details={
                            "priority_state": q_it.priority_state,
                            "blocks_action": q_it.blocks_action,
                            "problem_summary": q_it.problem_summary,
                        },
                    )
                )
        except Exception as q_exc:
            items.append(
                VerificationItem(
                    item_id="queue_derivation_error",
                    path="queue/derivation",
                    scope=SCOPE_QUEUE,
                    target="queue.derivation",
                    status=STATUS_BLOCKED,
                    message=f"Inconsistencia en la cola operativa: {q_exc}",
                    details={"error": str(q_exc)},
                )
            )

    # 3. Calculate derived metrics
    # Dedup checked items by field/target to avoid inflation from duplicate evidence
    _checked_fields = set()
    for i in items:
        if i.status == STATUS_CHECKED:
            _field_key = (i.details.get("field_name", ""), i.scope, i.target.rsplit(".", 1)[0] if ".evidence." in i.target else i.target)
            _checked_fields.add(_field_key)
    checked_count = len(_checked_fields)
    needs_review_count = sum(1 for i in items if i.status == STATUS_NEEDS_TEACHER_REVIEW)
    blocked_count = sum(1 for i in items if i.status == STATUS_BLOCKED)
    total_items = len(items)
    is_valid = (blocked_count == 0)

    return VerificationReport(
        schema_version=VERIFICATION_SCHEMA_VERSION,
        dossier_version=dossier_version,
        source_sha256=actual_sha256,
        is_valid=is_valid,
        checked_count=checked_count,
        needs_review_count=needs_review_count,
        blocked_count=blocked_count,
        total_items=total_items,
        items=[item.to_dict() for item in items],
    )


def compute_canonical_verification_report(
    dossier: Any,
    pdf_source: Any,
) -> dict[str, Any]:
    """Pure canonical deriver of the verification report dict for a dossier and PDF source."""
    report = verify_curriculum_dossier(dossier, pdf_source)
    return report.to_dict()


def validate_canonical_verification_report(
    dossier: Any,
    pdf_source: Any,
    persisted_report: Any,
) -> bool:
    """Strict canonical validator: recomputes verification report from dossier + PDF source
    and requires exact canonical equality to the persisted report.

    Fails closed on missing, malformed, extra forged, stale, or inconsistent reports.
    """
    if not isinstance(persisted_report, dict) or not persisted_report:
        return False

    if set(persisted_report.keys()) != CANONICAL_REPORT_KEYS:
        return False

    if persisted_report.get("schema_version") != VERIFICATION_SCHEMA_VERSION:
        return False

    dossier_version = getattr(dossier, "version", None) if not isinstance(dossier, dict) else dossier.get("version")
    if persisted_report.get("dossier_version") != dossier_version:
        return False

    # Recompute canonical report
    try:
        expected = compute_canonical_verification_report(dossier, pdf_source)
    except Exception as exc:
        logger.warning("Error recomputando reporte canónico para validación: %s", exc)
        return False

    if not expected["is_valid"] or expected["blocked_count"] > 0:
        return False

    # Check equality of scalar fields
    for k in (
        "schema_version",
        "dossier_version",
        "source_sha256",
        "is_valid",
        "checked_count",
        "needs_review_count",
        "blocked_count",
        "total_items",
    ):
        if persisted_report.get(k) != expected.get(k):
            return False

    # Check items list exact match
    persisted_items = persisted_report.get("items")
    if not isinstance(persisted_items, list) or len(persisted_items) != len(expected["items"]):
        return False

    if persisted_items != expected["items"]:
        return False

    return True
