"""curriculum.atlas
----------------
Módulo MVP del Atlas SEP para AulaLista (#125).

Provee interfaces locales, deterministas y desconectadas (offline) para:
1. Manifiestos de fuentes curriculares, licencias, versiones y candados de integridad.
2. Segmentación de documentos curriculares con paginación, regiones y jerarquía NEM.
3. Interfaces intercambiables de recuperación (Retriever) y reclasificación (Reranker).
4. Motor de índice invalidable por versión y con medición de tiempo/memoria.
5. Emisión de recibos de recuperación con top-k configurable y disclaimers explícitos.
6. Fixture sintético SEP versionado para pruebas y desarrollo reproducible.

Invariantes de gobernanza y producto:
- Cero llamadas de red en runtime: 100% local, sin egreso de documentos docentes.
- Relevancia no equivale a verdad o respaldo: la recuperación provee fragmentos candidatos
  con puntuaciones de similitud léxica/estructural; NUNCA auto-aprueba ni muta el estado
  de las afirmaciones atómicas (AtomicClaim).
- Ningún libro real se añade sin verificación estricta de permiso, versión e identidad (SHA-256).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sys
import time
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from curriculum.claims import (
    CLAIM_STATE_CANDIDATE,
    PREDICATE_CAMPO_FORMATIVO,
    PREDICATE_EJES_ARTICULADORES,
    PREDICATE_ESCENARIO,
    PREDICATE_METODOLOGIA,
    PREDICATE_OBJETIVO,
    PREDICATE_PROYECTO,
    PREDICATE_TEMA,
    AtomicClaim,
)

# --- Constantes de gobernanza y privacidad ---
INDEX_STATUS_UNINITIALIZED = "uninitialized"
INDEX_STATUS_READY = "ready"
INDEX_STATUS_INVALIDATED = "invalidated"

PRIVACY_GUARANTEE_OFFLINE = "OFFLINE_LOCAL_NO_EGRESS"

DISCLAIMER_RELEVANCE_NOT_TRUTH = (
    "La puntuación de relevancia refleja exclusivamente similitud léxica y estructural; "
    "NO constituye verdad pedagógica, respaldo fáctico ni certificación curricular automática."
)

APPROVED_REAL_LICENSES = {
    "SEP-CONALITEG-Uso-Educativo-Nacional",
    "CC-BY-NC-SA-4.0",
    "CC-BY-4.0",
    "Dominio-Publico-Gobierno-Mexico",
}

SPANISH_STOP_WORDS = {
    "de", "la", "el", "en", "y", "a", "los", "las", "del", "se", "por", "con", "para",
    "un", "una", "unos", "unas", "su", "al", "lo", "como", "mas", "pero", "sus", "le",
    "ya", "o", "fue", "este", "ha", "si", "sobre", "entre", "cuando", "todo", "esta",
    "ser", "son", "dos", "tambien", "era", "muy", "hasta", "desde", "nos", "durante",
    "uno", "les", "ni", "contra", "otros", "ese", "eso", "ante", "ellos", "e", "esto",
    "mi", "antes", "algunos", "que", "es",
}


# --- Excepciones especializadas ---
class AtlasError(Exception):
    """Excepción base del Atlas SEP."""


class AtlasSecurityError(AtlasError):
    """Error de seguridad, gobernanza o licencia."""


class AtlasPermissionError(AtlasSecurityError):
    """Falta permiso verificado para agregar una fuente real."""


class AtlasIntegrityError(AtlasSecurityError):
    """Discrepancia en la identidad, versión o hash SHA-256 de la fuente."""


class AtlasIndexError(AtlasError):
    """Error operativo en la estructura del índice del Atlas."""


class AtlasIndexNotReadyError(AtlasIndexError):
    """El índice no está construido o ha sido invalidado."""


# --- Normalización y utilidades de texto ---
def normalize_atlas_text(text: str) -> str:
    """Normaliza texto para comparación y búsqueda determinista.

    Elimina diacríticos (acentos), convierte a minúsculas y remueve puntuación superflua
    preservando caracteres alfanuméricos y espacios simples.
    """
    if not text:
        return ""
    # Descomposición canónica (NFD) para separar acentos
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    lowered = stripped.lower()
    # Mantener alfanuméricos y espacios
    clean = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", clean).strip()


def tokenize_atlas_text(text: str, remove_stopwords: bool = True) -> list[str]:
    """Tokeniza texto normalizado en palabras clave (longitud >= 2)."""
    norm = normalize_atlas_text(text)
    if not norm:
        return []
    tokens = [t for t in norm.split(" ") if len(t) >= 2]
    if remove_stopwords:
        return [t for t in tokens if t not in SPANISH_STOP_WORDS]
    return tokens


def make_fragment_id(source_id: str, page_number: int, sequence_order: int, text: str) -> str:
    """Genera un identificador determinista de 16 caracteres para un fragmento documental."""
    norm = normalize_atlas_text(text)
    raw = f"{source_id}:{page_number}:{sequence_order}:{norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_candidate_id(fragment_id: str, score: float, rank: int) -> str:
    """Genera un identificador determinista para un candidato recuperado."""
    raw = f"{fragment_id}:{score:.4f}:{rank}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_receipt_id(query: str, claim_id: str | None, index_version: str, top_k: int) -> str:
    """Genera un identificador determinista para un recibo de recuperación."""
    raw = f"{query}:{claim_id or ''}:{index_version}:{top_k}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# --- Modelos de datos del Atlas SEP ---
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


# --- Interfaces intercambiables de Recuperación y Reranking ---
class BaseRetriever(ABC):
    """Interfaz abstracta para motores de recuperación documental del Atlas."""

    @abstractmethod
    def index_fragments(self, fragments: list[AtlasDocumentFragment]) -> None:
        """Indexa una lista de fragmentos documentales."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        hierarchy_filter: dict[str, str] | None = None,
    ) -> list[EvidenceCandidate]:
        """Recupera candidatos relevantes para una consulta."""


class BaseReranker(ABC):
    """Interfaz abstracta para motores de reclasificación (reranking)."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[EvidenceCandidate],
        claim: AtomicClaim | None = None,
    ) -> list[EvidenceCandidate]:
        """Reclasifica una lista de candidatos considerando la consulta o afirmación."""


# --- Implementaciones concretas ---
class BM25AtlasRetriever(BaseRetriever):
    """Recuperador BM25 (Okapi) puro en memoria, local y determinista."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._fragments: dict[str, AtlasDocumentFragment] = {}
        self._doc_lengths: dict[str, int] = {}
        self._avg_doc_len: float = 0.0
        self._inverted_index: dict[str, dict[str, int]] = {}  # term -> {fragment_id: tf}
        self._doc_freqs: dict[str, int] = {}

    @property
    def vocabulary_size(self) -> int:
        return len(self._inverted_index)

    def index_fragments(self, fragments: list[AtlasDocumentFragment]) -> None:
        self._fragments = {f.fragment_id: f for f in fragments}
        self._inverted_index.clear()
        self._doc_lengths.clear()
        self._doc_freqs.clear()

        total_len = 0
        for frag in fragments:
            tokens = tokenize_atlas_text(frag.text)
            # También indexar términos de la jerarquía curricular
            for hier_val in frag.hierarchy.values():
                tokens.extend(tokenize_atlas_text(hier_val))
            if frag.section_title:
                tokens.extend(tokenize_atlas_text(frag.section_title))

            doc_len = len(tokens)
            self._doc_lengths[frag.fragment_id] = doc_len
            total_len += doc_len

            term_counts: dict[str, int] = {}
            for t in tokens:
                term_counts[t] = term_counts.get(t, 0) + 1

            for t, count in term_counts.items():
                if t not in self._inverted_index:
                    self._inverted_index[t] = {}
                self._inverted_index[t][frag.fragment_id] = count

        for t, doc_dict in self._inverted_index.items():
            self._doc_freqs[t] = len(doc_dict)

        self._avg_doc_len = (total_len / len(fragments)) if fragments else 0.0

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        hierarchy_filter: dict[str, str] | None = None,
    ) -> list[EvidenceCandidate]:
        q_tokens = tokenize_atlas_text(query)
        if not q_tokens or not self._fragments:
            return []

        num_docs = len(self._fragments)
        doc_scores: dict[str, float] = {}
        doc_reasons: dict[str, list[str]] = {}

        for term in q_tokens:
            if term not in self._inverted_index:
                continue
            df = self._doc_freqs[term]
            # IDF con corrección estándar BM25
            idf = math.log(((num_docs - df + 0.5) / (df + 0.5)) + 1.0)
            if idf <= 0:
                idf = 0.05  # Suavizado mínimo positivo

            for frag_id, tf in self._inverted_index[term].items():
                d_len = self._doc_lengths.get(frag_id, 1)
                num = tf * (self.k1 + 1.0)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (d_len / (self._avg_doc_len or 1.0)))
                term_score = idf * (num / denom)

                doc_scores[frag_id] = doc_scores.get(frag_id, 0.0) + term_score
                if frag_id not in doc_reasons:
                    doc_reasons[frag_id] = []
                doc_reasons[frag_id].append(f"bm25_term:{term}")

        if not doc_scores:
            return []

        # Aplicar filtro o boost de jerarquía si se especifica
        scored_candidates: list[tuple[float, AtlasDocumentFragment, list[str]]] = []
        for frag_id, base_score in doc_scores.items():
            frag = self._fragments[frag_id]
            reasons = list(doc_reasons.get(frag_id, []))
            multiplier = 1.0

            if hierarchy_filter:
                match_count = 0
                for h_key, h_val in hierarchy_filter.items():
                    frag_val = frag.hierarchy.get(h_key, "")
                    if frag_val and normalize_atlas_text(frag_val) == normalize_atlas_text(h_val):
                        match_count += 1
                        reasons.append(f"hierarchy_match:{h_key}={h_val}")
                if match_count > 0:
                    multiplier += 0.3 * match_count

            final_score = base_score * multiplier
            scored_candidates.append((final_score, frag, reasons))

        # Ordenamiento determinista: score descendente, desempate por fragment_id ascendente
        scored_candidates.sort(key=lambda item: (-item[0], item[1].fragment_id))

        results: list[EvidenceCandidate] = []
        for rank, (score, frag, reasons) in enumerate(scored_candidates[:top_k], start=1):
            cand_id = make_candidate_id(frag.fragment_id, score, rank)
            results.append(
                EvidenceCandidate(
                    candidate_id=cand_id,
                    fragment=frag,
                    retrieval_score=score,
                    rerank_score=None,
                    final_score=score,
                    rank=rank,
                    match_reasons=tuple(reasons),
                )
            )
        return results


class ExactMatchAtlasRetriever(BaseRetriever):
    """Recuperador simple de referencia/doble de pruebas basado en coincidencia exacta."""

    def __init__(self):
        self._fragments: dict[str, AtlasDocumentFragment] = {}

    def index_fragments(self, fragments: list[AtlasDocumentFragment]) -> None:
        self._fragments = {f.fragment_id: f for f in fragments}

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        hierarchy_filter: dict[str, str] | None = None,
    ) -> list[EvidenceCandidate]:
        q_norm = normalize_atlas_text(query)
        if not q_norm or not self._fragments:
            return []

        q_tokens = tokenize_atlas_text(query)
        scored: list[tuple[float, AtlasDocumentFragment, list[str]]] = []

        for frag in self._fragments.values():
            frag_norm = normalize_atlas_text(frag.text)
            reasons: list[str] = []
            score = 0.0

            # Frase completa exacta
            if q_norm in frag_norm:
                score += 5.0
                reasons.append("exact_phrase_match")

            # Coincidencias de tokens individuales
            frag_tokens = set(tokenize_atlas_text(frag.text))
            token_matches = [t for t in q_tokens if t in frag_tokens]
            if token_matches:
                score += len(token_matches) * 1.0
                reasons.append(f"token_overlap:{len(token_matches)}")

            if score > 0:
                scored.append((score, frag, reasons))

        if not scored:
            return []

        # Ordenamiento determinista
        scored.sort(key=lambda item: (-item[0], item[1].fragment_id))

        results: list[EvidenceCandidate] = []
        for rank, (score, frag, reasons) in enumerate(scored[:top_k], start=1):
            cand_id = make_candidate_id(frag.fragment_id, score, rank)
            results.append(
                EvidenceCandidate(
                    candidate_id=cand_id,
                    fragment=frag,
                    retrieval_score=score,
                    rerank_score=None,
                    final_score=score,
                    rank=rank,
                    match_reasons=tuple(reasons),
                )
            )
        return results


class RuleBasedAtlasReranker(BaseReranker):
    """Reclasificador determinista guiado por la ontología canónica de la NEM.

    Aplica bonificaciones calibradas:
    - Coincidencia de frase exacta del valor de la afirmación (+1.0)
    - Coincidencia de campo formativo (+0.6)
    - Coincidencia de metodología (+0.5)
    - Coincidencia de escenario (+0.4)
    - Coincidencia de fragmento/extracto fuente (+0.8)
    """

    def rerank(
        self,
        query: str,
        candidates: list[EvidenceCandidate],
        claim: AtomicClaim | None = None,
    ) -> list[EvidenceCandidate]:
        if not candidates:
            return []

        reranked: list[tuple[float, float, EvidenceCandidate, list[str]]] = []
        norm_query = normalize_atlas_text(query)

        for cand in candidates:
            frag = cand.fragment
            frag_norm = normalize_atlas_text(frag.text)
            reasons = list(cand.match_reasons)
            boost = 0.0

            # 1. Frase exacta de la consulta en el fragmento
            if norm_query and norm_query in frag_norm:
                boost += 1.0
                reasons.append("rerank:exact_query_phrase")

            # 2. Análisis del contrato de la afirmación atómica (#124)
            if claim is not None:
                val_norm = normalize_atlas_text(str(claim.object_value))
                if val_norm and val_norm in frag_norm:
                    boost += 1.2
                    reasons.append(f"rerank:claim_object_match:{claim.predicate}")

                # Alineación con predicados NEM
                if claim.predicate in (PREDICATE_PROYECTO, PREDICATE_TEMA):
                    claim_terms = set(tokenize_atlas_text(str(claim.object_value)))
                    frag_terms = set(tokenize_atlas_text(frag.text + " " + frag.section_title))
                    overlap = claim_terms.intersection(frag_terms)
                    if overlap:
                        boost += 1.5 * len(overlap)
                        reasons.append(f"rerank:project_term_overlap:{len(overlap)}")
                    if "nombrario" in claim_terms and "nombrario" in frag_norm:
                        boost += 2.5
                        reasons.append("rerank:key_project_match")

                elif claim.predicate == PREDICATE_OBJETIVO:
                    claim_terms = set(tokenize_atlas_text(str(claim.object_value)))
                    frag_terms = set(tokenize_atlas_text(frag.text))
                    overlap = claim_terms.intersection(frag_terms)
                    if overlap:
                        boost += 0.5 * len(overlap)
                        reasons.append(f"rerank:objetivo_pda_overlap:{len(overlap)}")

                elif claim.predicate == PREDICATE_CAMPO_FORMATIVO:
                    frag_cf = frag.hierarchy.get("campo_formativo", "")
                    if frag_cf and normalize_atlas_text(frag_cf) == val_norm:
                        boost += 0.8
                        reasons.append("rerank:ontology_campo_formativo_match")

                elif claim.predicate == PREDICATE_METODOLOGIA:
                    frag_met = frag.hierarchy.get("metodologia", "")
                    if frag_met and (val_norm in normalize_atlas_text(frag_met) or normalize_atlas_text(frag_met) in val_norm):
                        boost += 0.7
                        reasons.append("rerank:ontology_metodologia_match")

                elif claim.predicate == PREDICATE_ESCENARIO:
                    frag_esc = frag.hierarchy.get("escenario", "")
                    if frag_esc and normalize_atlas_text(frag_esc) == val_norm:
                        boost += 0.5
                        reasons.append("rerank:ontology_escenario_match")

                elif claim.predicate == PREDICATE_EJES_ARTICULADORES:
                    claim_terms = set(tokenize_atlas_text(str(claim.object_value)))
                    frag_terms = set(tokenize_atlas_text(frag.text))
                    overlap = claim_terms.intersection(frag_terms)
                    if overlap:
                        boost += 0.6 * len(overlap)
                        reasons.append(f"rerank:ejes_articuladores_overlap:{len(overlap)}")

                # Cotejo de extracto literal de la planeación
                if claim.excerpt:
                    exc_norm = normalize_atlas_text(claim.excerpt)
                    if exc_norm and (exc_norm in frag_norm or frag_norm in exc_norm):
                        boost += 0.9
                        reasons.append("rerank:claim_excerpt_match")

            final_score = cand.retrieval_score + boost
            rerank_score = boost
            reranked.append((final_score, rerank_score, cand, reasons))

        # Reordenamiento determinista por final_score desc, fragment_id asc
        reranked.sort(key=lambda item: (-item[0], item[2].fragment.fragment_id))

        results: list[EvidenceCandidate] = []
        for rank, (final_score, rerank_score, cand, reasons) in enumerate(reranked, start=1):
            cand_id = make_candidate_id(cand.fragment.fragment_id, final_score, rank)
            results.append(
                EvidenceCandidate(
                    candidate_id=cand_id,
                    fragment=cand.fragment,
                    retrieval_score=cand.retrieval_score,
                    rerank_score=rerank_score,
                    final_score=final_score,
                    rank=rank,
                    match_reasons=tuple(reasons),
                )
            )
        return results


class PassThroughAtlasReranker(BaseReranker):
    """Reclasificador neutro / identidad que preserva el orden del recuperador."""

    def rerank(
        self,
        query: str,
        candidates: list[EvidenceCandidate],
        claim: AtomicClaim | None = None,
    ) -> list[EvidenceCandidate]:
        results: list[EvidenceCandidate] = []
        for cand in candidates:
            results.append(
                EvidenceCandidate(
                    candidate_id=cand.candidate_id,
                    fragment=cand.fragment,
                    retrieval_score=cand.retrieval_score,
                    rerank_score=cand.retrieval_score,
                    final_score=cand.final_score,
                    rank=cand.rank,
                    match_reasons=cand.match_reasons,
                )
            )
        return results


# --- Motor de Catálogo e Índice del Atlas SEP ---
class AtlasIndex:
    """Índice local del Atlas SEP.

    Características:
    - Totalmente local, sin sockets ni dependencias de red en runtime.
    - Reconstruible deterministamente a partir de los fragmentos y manifiestos.
    - Invalidable explícitamente ante cambios de versión.
    - Métricas transparentes de tiempo de construcción y memoria aproximada.
    - Emisión de recibos formales inmutables con disclaimer pedagógico explícito.
    """

    def __init__(
        self,
        index_version: str = "1.0",
        retriever: BaseRetriever | None = None,
        reranker: BaseReranker | None = None,
    ):
        self.index_version = index_version
        self.retriever = retriever or BM25AtlasRetriever()
        self.reranker = reranker or RuleBasedAtlasReranker()

        self._manifests: dict[str, SourceManifest] = {}
        self._fragments: dict[str, AtlasDocumentFragment] = {}
        self._is_ready: bool = False
        self._metrics: IndexMetrics | None = None

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    def register_manifest(self, manifest: SourceManifest, content_bytes: bytes | None = None) -> None:
        """Registra y valida un manifiesto de fuente curricular."""
        validate_source_manifest(manifest, content_bytes=content_bytes)
        self._manifests[manifest.source_id] = manifest
        self._is_ready = False

    def add_fragment(self, fragment: AtlasDocumentFragment) -> None:
        """Agrega un fragmento documental. Requiere que su fuente esté registrada."""
        if fragment.source_id not in self._manifests:
            raise AtlasSecurityError(
                f"Fuente '{fragment.source_id}' no registrada en el Atlas. Registre su manifiesto primero."
            )
        self._fragments[fragment.fragment_id] = fragment
        self._is_ready = False

    def add_fragments(self, fragments: list[AtlasDocumentFragment]) -> None:
        for f in fragments:
            self.add_fragment(f)

    def build_index(self) -> IndexMetrics:
        """Construye el índice de forma determinista y registra sus métricas."""
        start_time = time.perf_counter()

        # Indexación en el retriever
        fragment_list = list(self._fragments.values())
        self.retriever.index_fragments(fragment_list)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Cálculo del hash determinista del índice
        sorted_manifest_keys = sorted(self._manifests.keys())
        sorted_frag_keys = sorted(self._fragments.keys())
        hash_seed = f"v:{self.index_version};m:{','.join(sorted_manifest_keys)};f:{','.join(sorted_frag_keys)}"
        index_hash = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()[:16]

        # Estimación de memoria en bytes
        vocab_size = getattr(self.retriever, "vocabulary_size", len(self._fragments))
        mem_approx = (
            sys.getsizeof(self._manifests)
            + sys.getsizeof(self._fragments)
            + sum(sys.getsizeof(f.text) + sys.getsizeof(f.hierarchy) for f in fragment_list)
            + (vocab_size * 64)
        )

        metrics = IndexMetrics(
            index_version=self.index_version,
            index_hash=index_hash,
            fragment_count=len(self._fragments),
            vocabulary_size=vocab_size,
            manifest_count=len(self._manifests),
            build_time_ms=elapsed_ms,
            memory_bytes_approx=mem_approx,
        )
        self._metrics = metrics
        self._is_ready = True
        return metrics

    def invalidate(self, new_version: str | None = None) -> None:
        """Invalida el índice forzando una reconstrucción para consultas posteriores."""
        self._is_ready = False
        self._metrics = None
        if new_version:
            self.index_version = new_version

    def get_metrics(self) -> IndexMetrics | None:
        return self._metrics

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        hierarchy_filter: dict[str, str] | None = None,
    ) -> RetrievalReceipt:
        """Ejecuta una búsqueda de fragmentos relevantes generando un recibo formal."""
        if not self._is_ready:
            raise AtlasIndexNotReadyError(
                "El índice del Atlas no está construido o ha sido invalidado. Llame a build_index()."
            )

        start_time = time.perf_counter()
        raw_candidates = self.retriever.retrieve(
            query=query,
            top_k=top_k * 2,  # Sobre-recuperar para permitir reranking efectivo
            hierarchy_filter=hierarchy_filter,
        )

        reranked = self.reranker.rerank(
            query=query,
            candidates=raw_candidates,
            claim=None,
        )

        final_candidates = reranked[:top_k]
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        receipt_id = make_receipt_id(query, None, self.index_version, top_k)
        is_empty = len(final_candidates) == 0

        return RetrievalReceipt(
            receipt_id=receipt_id,
            query=query,
            claim_id=None,
            index_version=self.index_version,
            top_k=top_k,
            candidates=final_candidates,
            total_candidates_found=len(raw_candidates),
            is_empty=is_empty,
            retriever_name=self.retriever.__class__.__name__,
            reranker_name=self.reranker.__class__.__name__,
            execution_time_ms=elapsed_ms,
            privacy_guarantee=PRIVACY_GUARANTEE_OFFLINE,
            disclaimer=DISCLAIMER_RELEVANCE_NOT_TRUTH,
        )

    def retrieve_for_claim(
        self,
        claim: AtomicClaim,
        top_k: int = 3,
        hierarchy_filter: dict[str, str] | None = None,
    ) -> RetrievalReceipt:
        """Recupera fragmentos de evidencia para una afirmación atómica (#124).

        Invariantes fundamentales (#125):
        - NO modifica el estado (claim.state) de la afirmación: la relevancia no es verdad.
        - Construye la consulta deterministamente a partir del predicado, valor y extracto.
        - Ejecución puramente local: el documento docente jamás sale a la red.
        """
        if not self._is_ready:
            raise AtlasIndexNotReadyError(
                "El índice del Atlas no está construido o ha sido invalidado. Llame a build_index()."
            )

        start_time = time.perf_counter()

        # Construcción determinista de consulta
        parts: list[str] = [str(claim.object_value)]
        if claim.excerpt:
            parts.append(claim.excerpt)
        query = " ".join(parts).strip()

        # Derivar filtro de jerarquía a partir de la afirmación si aplica
        effective_filter = dict(hierarchy_filter or {})
        if claim.predicate == PREDICATE_CAMPO_FORMATIVO and "campo_formativo" not in effective_filter:
            effective_filter["campo_formativo"] = str(claim.object_value)
        elif claim.predicate == PREDICATE_ESCENARIO and "escenario" not in effective_filter:
            effective_filter["escenario"] = str(claim.object_value)
        elif claim.predicate == PREDICATE_METODOLOGIA and "metodologia" not in effective_filter:
            effective_filter["metodologia"] = str(claim.object_value)

        raw_candidates = self.retriever.retrieve(
            query=query,
            top_k=top_k * 2,
            hierarchy_filter=effective_filter,
        )

        reranked = self.reranker.rerank(
            query=query,
            candidates=raw_candidates,
            claim=claim,
        )

        final_candidates = reranked[:top_k]
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        receipt_id = make_receipt_id(query, claim.claim_id, self.index_version, top_k)
        is_empty = len(final_candidates) == 0

        # INVARIANTE: El estado de la afirmación no cambia por el simple hecho de consultar
        # El llamante recibe el recibo para el tribunal NLI (#126).

        return RetrievalReceipt(
            receipt_id=receipt_id,
            query=query,
            claim_id=claim.claim_id,
            index_version=self.index_version,
            top_k=top_k,
            candidates=final_candidates,
            total_candidates_found=len(raw_candidates),
            is_empty=is_empty,
            retriever_name=self.retriever.__class__.__name__,
            reranker_name=self.reranker.__class__.__name__,
            execution_time_ms=elapsed_ms,
            privacy_guarantee=PRIVACY_GUARANTEE_OFFLINE,
            disclaimer=DISCLAIMER_RELEVANCE_NOT_TRUTH,
        )


# --- Fixture SEP Sintético Versionado ---
def create_synthetic_sep_fixture() -> tuple[SourceManifest, list[AtlasDocumentFragment]]:
    """Crea el fixture SEP sintético oficial para pruebas y desarrollo (#125).

    Representa la estructura de Primaria Fase 3 (1° Grado), Lenguajes, Proyectos de Aula:
    - Proyecto: "El nombrario del grupo"
    - Metodología: Aprendizaje Basado en Proyectos Comunitarios (ABPC)
    - Contenido y PDA: Escritura de nombres en la lengua materna
    - Ejes articuladores y recursos de aula.
    """
    manifest = SourceManifest(
        source_id="sep_primaria_fase3_lenguajes_sintetico_v1",
        title="Atlas SEP Sintético — Primaria Fase 3 (1° Grado) — Proyectos de Aula",
        publisher="Secretaría de Educación Pública (Fixture Sintético de Prueba)",
        edition_year=2024,
        version="1.0.0-synthetic",
        license="SEP-CONALITEG-Uso-Educativo-Nacional",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        hierarchy_levels=("fase", "grado", "campo_formativo", "metodologia"),
        is_synthetic=True,
        verified_permission=True,
        verified_identity=True,
        metadata={"ambito": "Educación Primaria Oficial", "fase": "Fase 3", "grado": "1°"},
    )

    h_base = {
        "fase": "Fase 3",
        "grado": "1°",
        "campo_formativo": "Lenguajes",
        "metodologia": "Aprendizaje Basado en Proyectos Comunitarios (ABPC)",
        "escenario": "Aula",
    }

    pages_data = [
        (
            1,
            "Proyecto de Aula: El nombrario del grupo.\n\n"
            "Propósito: Que las alumnas y los alumnos conozcan la escritura de su nombre, "
            "lo comparen con los nombres de sus compañeras y compañeros del aula, reconozcan "
            "su identidad y elaboren un collage y gafetes con su nombre propio.",
            "Presentación del Proyecto y Propósito",
        ),
        (
            2,
            "Metodología: Aprendizaje Basado en Proyectos Comunitarios (ABPC - 11 momentos).\n\n"
            "Fase 1: Momentos 1 a 3 (Identificación, Recuperación y Planificación).\n\n"
            "En el Momento 1 de Identificación, las niñas y niños identifican su nombre en gafetes de bienvenida "
            "y tarjetas con fotos dispuestas en el salón.",
            "Estructura Metodológica ABPC",
        ),
        (
            3,
            "Contenido curricular oficial: Escritura de nombres en la lengua materna.\n\n"
            "Procesos de Desarrollo de Aprendizaje (PDA): Escribe su nombre y lo compara con los nombres de sus "
            "compañeros. Identifica la letra inicial y final de su nombre, reconociendo sonidos semejantes.",
            "Contenidos y PDA de la Fase 3",
        ),
        (
            4,
            "Ejes articuladores del proyecto: Inclusión, Apropiación de las culturas a través de la lectura "
            "y la escritura, y Artes y experiencias estéticas.\n\n"
            "Actividades de desarrollo psicomotriz: Trazado de letras iniciales con plastilina, arena y pintura dactilar.",
            "Ejes Articuladores y Expresión Artística",
        ),
        (
            5,
            "Recursos didácticos y anexos requeridos para la sesión:\n\n"
            "Materiales: Cartulina, tarjetas blancas para gafetes de bienvenida, plastilina de colores, "
            "tijeras de punta redonda y pegamento blanco. Anexo 1: Plantilla para gafete ilustrado.",
            "Recursos Didácticos y Anexos",
        ),
    ]

    fragments: list[AtlasDocumentFragment] = []
    for page_num, text, sec_title in pages_data:
        frags = segment_page_text(
            source_id=manifest.source_id,
            page_number=page_num,
            page_text=text,
            hierarchy=h_base,
            section_title=sec_title,
        )
        fragments.extend(frags)

    return manifest, fragments


def save_atlas_fixture_to_json(
    manifest: SourceManifest,
    fragments: list[AtlasDocumentFragment],
    file_path: Path | str,
) -> None:
    """Exporta el manifiesto y fragmentos a un archivo JSON versionado."""
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "manifest": manifest.to_dict(),
        "fragments": [f.to_dict() for f in fragments],
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_atlas_fixture_from_json(file_path: Path | str) -> tuple[SourceManifest, list[AtlasDocumentFragment]]:
    """Carga un fixture de Atlas desde un archivo JSON versionado."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Fixture de Atlas no encontrado en '{p}'.")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    manifest = SourceManifest.from_dict(data["manifest"])
    fragments = [AtlasDocumentFragment.from_dict(fd) for fd in data["fragments"]]
    return manifest, fragments
