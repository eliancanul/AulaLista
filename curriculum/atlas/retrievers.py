"""curriculum.atlas.retrievers
----------------------------
Interfaces y motores de recuperación documental para el Atlas SEP.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

from curriculum.atlas.hierarchy import (
    HierarchyFilterMode,
    matches_hierarchy,
    validate_hierarchy_filter,
)
from curriculum.atlas.models import AtlasDocumentFragment, EvidenceCandidate
from curriculum.atlas.text import (
    make_candidate_id,
    normalize_atlas_text,
    tokenize_atlas_text,
)


class BaseRetriever(ABC):
    """Interfaz abstracta para motores de recuperación documental del Atlas."""

    @abstractmethod
    def index_fragments(self, fragments: list[AtlasDocumentFragment]) -> None:
        """Construye o actualiza el índice interno a partir de una lista de fragmentos."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        hierarchy_filter: dict[str, str] | None = None,
        *,
        hierarchy_filter_mode: HierarchyFilterMode = "prefer",
    ) -> list[EvidenceCandidate]:
        """Recupera top-k; strict exige cada clave seleccionada antes de truncar.

        prefer conserva el ranking histórico de cada implementación. Los
        recuperadores personalizados deben implementar strict explícitamente;
        no es válido ignorarlo ni filtrar sólo después de seleccionar top-k.
        """


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
        *,
        hierarchy_filter_mode: HierarchyFilterMode = "prefer",
    ) -> list[EvidenceCandidate]:
        validate_hierarchy_filter(hierarchy_filter, hierarchy_filter_mode)
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

        # Excluir incompatibles antes de ordenar/truncar; prefer sólo bonifica.
        scored_candidates: list[tuple[float, AtlasDocumentFragment, list[str]]] = []
        for frag_id, base_score in doc_scores.items():
            frag = self._fragments[frag_id]
            if hierarchy_filter_mode == "strict" and not matches_hierarchy(frag.hierarchy, hierarchy_filter):
                continue
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
        *,
        hierarchy_filter_mode: HierarchyFilterMode = "prefer",
    ) -> list[EvidenceCandidate]:
        validate_hierarchy_filter(hierarchy_filter, hierarchy_filter_mode)
        q_norm = normalize_atlas_text(query)
        if not q_norm or not self._fragments:
            return []

        q_tokens = tokenize_atlas_text(query)
        scored: list[tuple[float, AtlasDocumentFragment, list[str]]] = []

        for frag in self._fragments.values():
            if hierarchy_filter_mode == "strict" and not matches_hierarchy(frag.hierarchy, hierarchy_filter):
                continue
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
