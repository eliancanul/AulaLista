"""curriculum.atlas.models
-----------------------
Modelos de datos del Atlas SEP: manifiestos, fragmentos, candidatos, recibos y métricas.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from curriculum.atlas.constants import (
    APPROVED_REAL_LICENSES,
    DISCLAIMER_RELEVANCE_NOT_TRUTH,
    PRIVACY_GUARANTEE_OFFLINE,
)
from curriculum.atlas.exceptions import (
    AtlasIntegrityError,
    AtlasPermissionError,
    AtlasSecurityError,
)
from curriculum.atlas.hierarchy import HierarchyFilterMode
from curriculum.atlas.text import make_fragment_id, tokenize_atlas_text


@dataclass(frozen=True)
class SourceManifest:
    """Manifiesto de gobernanza, licencia e identidad de una fuente curricular."""

    source_id: str
    title: str
    publisher: str
    edition_year: int
    version: str
    license: str
    sha256: str
    hierarchy_levels: tuple[str, ...] = ("fase", "grado", "campo_formativo", "tipo_libro")
    is_synthetic: bool = False
    verified_permission: bool = False
    verified_identity: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hierarchy_levels"] = list(self.hierarchy_levels)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceManifest:
        d = dict(data)
        if "hierarchy_levels" in d and isinstance(d["hierarchy_levels"], list):
            d["hierarchy_levels"] = tuple(d["hierarchy_levels"])
        return cls(**d)


def validate_source_manifest(manifest: SourceManifest, content_bytes: bytes | None = None) -> None:
    """Valida los candados de seguridad y procedencia para registrar una fuente en el Atlas.

    Invariante GREEN 5:
    - Ningún libro real se agrega sin revisar permiso, versión e identidad.
    - Fuentes sintéticas se admiten para pruebas si declaran is_synthetic=True.
    """
    for req in ("source_id", "title", "publisher", "version", "license", "sha256"):
        val = getattr(manifest, req, None)
        if not val or not str(val).strip():
            raise AtlasSecurityError(f"El campo '{req}' es obligatorio en el manifiesto de fuente.")

    if content_bytes is not None:
        actual_sha = hashlib.sha256(content_bytes).hexdigest()
        if actual_sha.lower() != manifest.sha256.lower():
            raise AtlasIntegrityError(
                f"Discrepancia de integridad: SHA-256 esperado '{manifest.sha256}' pero se obtuvo '{actual_sha}'."
            )

    # Candados para libros y fuentes reales
    if not manifest.is_synthetic:
        if not manifest.verified_permission:
            raise AtlasPermissionError(
                f"Bloqueo de seguridad: La fuente real '{manifest.source_id}' no cuenta con permiso de distribución verificado."
            )
        if not manifest.verified_identity:
            raise AtlasIntegrityError(
                f"Bloqueo de seguridad: La fuente real '{manifest.source_id}' no cuenta con identidad o versión oficial verificada."
            )
        clean_license = manifest.license.strip()
        if clean_license not in APPROVED_REAL_LICENSES:
            raise AtlasSecurityError(
                f"Bloqueo de seguridad: Licencia '{clean_license}' no autorizada para libros reales en AulaLista."
            )
        if content_bytes is None:
            raise AtlasIntegrityError(
                f"Bloqueo de seguridad: La fuente real '{manifest.source_id}' requiere contenido para verificar su SHA-256."
            )


@dataclass(frozen=True)
class AtlasDocumentFragment:
    """Fragmento curricular indexado con paginación, región y ontología NEM."""

    fragment_id: str
    source_id: str
    page_number: int
    text: str
    region: dict[str, float] | None = None
    hierarchy: dict[str, str] = field(default_factory=dict)
    section_title: str = ""
    sequence_order: int = 0
    token_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AtlasDocumentFragment:
        d = dict(data)
        return cls(**d)


def segment_page_text(
    source_id: str,
    page_number: int,
    page_text: str,
    hierarchy: dict[str, str],
    section_title: str = "",
    max_chars: int = 350,
    overlap_chars: int = 50,
    region: dict[str, float] | None = None,
) -> list[AtlasDocumentFragment]:
    """Segmenta el texto de una página en fragmentos curriculares coherentes."""
    cleaned = page_text.strip()
    if not cleaned:
        return []

    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    raw_chunks: list[str] = []

    for para in paragraphs:
        if len(para) <= max_chars:
            raw_chunks.append(para)
        else:
            # Segmentar por oraciones o longitud máxima con solapamiento
            start = 0
            while start < len(para):
                end = min(start + max_chars, len(para))
                if end < len(para):
                    last_space = para.rfind(" ", start, end)
                    if last_space > start + 50:
                        end = last_space
                chunk = para[start:end].strip()
                if chunk:
                    raw_chunks.append(chunk)
                if end >= len(para):
                    break
                start = max(end - overlap_chars, start + 1)

    fragments: list[AtlasDocumentFragment] = []
    for seq, chunk_text in enumerate(raw_chunks, start=1):
        frag_id = make_fragment_id(source_id, page_number, seq, chunk_text)
        tokens = tokenize_atlas_text(chunk_text)
        fragments.append(
            AtlasDocumentFragment(
                fragment_id=frag_id,
                source_id=source_id,
                page_number=page_number,
                text=chunk_text,
                region=region,
                hierarchy=dict(hierarchy),
                section_title=section_title,
                sequence_order=seq,
                token_count=len(tokens),
            )
        )
    return fragments


@dataclass(frozen=True)
class EvidenceCandidate:
    """Candidato de evidencia recuperado con sus puntuaciones de relevancia.

    INVARIANTE:
    Ni retrieval_score ni rerank_score representan probabilidad, verdad fáctica
    ni respaldo pedagógico automático.
    """

    candidate_id: str
    fragment: AtlasDocumentFragment
    retrieval_score: float
    rerank_score: float | None = None
    final_score: float = 0.0
    rank: int = 1
    match_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "fragment": self.fragment.to_dict(),
            "retrieval_score": round(self.retrieval_score, 4),
            "rerank_score": round(self.rerank_score, 4) if self.rerank_score is not None else None,
            "final_score": round(self.final_score, 4),
            "rank": self.rank,
            "match_reasons": list(self.match_reasons),
        }


@dataclass
class RetrievalReceipt:
    """Recibo formal de consulta y recuperación de evidencia en el Atlas SEP."""

    receipt_id: str
    query: str
    claim_id: str | None
    index_version: str
    top_k: int
    candidates: list[EvidenceCandidate]
    total_candidates_found: int
    is_empty: bool
    retriever_name: str
    reranker_name: str | None
    execution_time_ms: float
    privacy_guarantee: str = PRIVACY_GUARANTEE_OFFLINE
    disclaimer: str = DISCLAIMER_RELEVANCE_NOT_TRUTH
    hierarchy_filter: dict[str, str] = field(default_factory=dict)
    hierarchy_filter_mode: HierarchyFilterMode = "prefer"

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "query": self.query,
            "claim_id": self.claim_id,
            "index_version": self.index_version,
            "top_k": self.top_k,
            "candidates": [c.to_dict() for c in self.candidates],
            "total_candidates_found": self.total_candidates_found,
            "is_empty": self.is_empty,
            "retriever_name": self.retriever_name,
            "reranker_name": self.reranker_name,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "privacy_guarantee": self.privacy_guarantee,
            "disclaimer": self.disclaimer,
            "hierarchy_filter": dict(self.hierarchy_filter),
            "hierarchy_filter_mode": self.hierarchy_filter_mode,
        }


@dataclass(frozen=True)
class IndexMetrics:
    """Diagnóstico determinista de tamaño, tiempo y memoria del índice."""

    index_version: str
    index_hash: str
    fragment_count: int
    vocabulary_size: int
    manifest_count: int
    build_time_ms: float
    memory_bytes_approx: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
