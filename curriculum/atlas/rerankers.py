"""curriculum.atlas.rerankers
--------------------------
Interfaces y reclasificadores (rerankers) guiados por la ontología NEM para el Atlas SEP.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from curriculum.atlas.models import EvidenceCandidate
from curriculum.atlas.text import (
    make_candidate_id,
    normalize_atlas_text,
    tokenize_atlas_text,
)
from curriculum.claims import (
    PREDICATE_CAMPO_FORMATIVO,
    PREDICATE_EJES_ARTICULADORES,
    PREDICATE_ESCENARIO,
    PREDICATE_METODOLOGIA,
    PREDICATE_OBJETIVO,
    PREDICATE_PROYECTO,
    PREDICATE_TEMA,
    AtomicClaim,
)


class BaseReranker(ABC):
    """Interfaz abstracta para reclasificadores de evidencia del Atlas."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[EvidenceCandidate],
        claim: AtomicClaim | None = None,
    ) -> list[EvidenceCandidate]:
        """Reclasifica y repondera los candidatos en base a la consulta y/o afirmación."""


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
