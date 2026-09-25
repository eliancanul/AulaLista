"""curriculum.atlas.index
-----------------------
Motor de catálogo e indexación local determinista del Atlas SEP.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import time

from curriculum.atlas.constants import (
    DISCLAIMER_RELEVANCE_NOT_TRUTH,
    PRIVACY_GUARANTEE_OFFLINE,
)
from curriculum.atlas.exceptions import (
    AtlasIndexNotReadyError,
    AtlasSecurityError,
)
from curriculum.atlas.models import (
    AtlasDocumentFragment,
    EvidenceCandidate,
    IndexMetrics,
    RetrievalReceipt,
    SourceManifest,
    validate_source_manifest,
)
from curriculum.atlas.rerankers import BaseReranker, RuleBasedAtlasReranker
from curriculum.atlas.retrievers import BM25AtlasRetriever, BaseRetriever
from curriculum.atlas.text import make_receipt_id
from curriculum.claims import (
    PREDICATE_CAMPO_FORMATIVO,
    PREDICATE_ESCENARIO,
    PREDICATE_METODOLOGIA,
    AtomicClaim,
)


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
        self._manifests[manifest.source_id] = copy.deepcopy(manifest)
        self._is_ready = False

    def add_fragment(self, fragment: AtlasDocumentFragment) -> None:
        """Agrega un fragmento documental. Requiere que su fuente esté registrada."""
        if fragment.source_id not in self._manifests:
            raise AtlasSecurityError(
                f"Fuente '{fragment.source_id}' no registrada en el Atlas. Registre su manifiesto primero."
            )
        self._fragments[fragment.fragment_id] = copy.deepcopy(fragment)
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
        hash_seed = json.dumps(
            {
                "index_version": self.index_version,
                "manifests": [self._manifests[key].to_dict() for key in sorted(self._manifests)],
                "fragments": [self._fragments[key].to_dict() for key in sorted(self._fragments)],
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
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

    def _make_receipt_id(
        self,
        query: str,
        claim_id: str | None,
        top_k: int,
        hierarchy_filter: dict[str, str] | None,
        candidates: list[EvidenceCandidate],
    ) -> str:
        context = json.dumps(
            {
                "index_hash": self._metrics.index_hash,
                "hierarchy_filter": hierarchy_filter or {},
                "retriever": self.retriever.__class__.__name__,
                "reranker": self.reranker.__class__.__name__,
                "candidates": [
                    {
                        "fragment_id": candidate.fragment.fragment_id,
                        "retrieval_score": candidate.retrieval_score,
                        "final_score": candidate.final_score,
                        "rank": candidate.rank,
                    }
                    for candidate in candidates
                ],
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return make_receipt_id(query, claim_id, context, top_k)

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        hierarchy_filter: dict[str, str] | None = None,
    ) -> RetrievalReceipt:
        """Ejecuta una búsqueda de fragmentos relevantes generando un recibo formal."""
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k debe ser un entero positivo.")
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

        receipt_id = self._make_receipt_id(query, None, top_k, hierarchy_filter, final_candidates)
        is_empty = len(final_candidates) == 0

        return RetrievalReceipt(
            receipt_id=receipt_id,
            query=query,
            claim_id=None,
            index_version=self.index_version,
            top_k=top_k,
            candidates=copy.deepcopy(final_candidates),
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
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k debe ser un entero positivo.")
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

        receipt_id = self._make_receipt_id(query, claim.claim_id, top_k, effective_filter, final_candidates)
        is_empty = len(final_candidates) == 0

        # INVARIANTE: El estado de la afirmación no cambia por el simple hecho de consultar
        # El llamante recibe el recibo para el tribunal NLI (#126).

        return RetrievalReceipt(
            receipt_id=receipt_id,
            query=query,
            claim_id=claim.claim_id,
            index_version=self.index_version,
            top_k=top_k,
            candidates=copy.deepcopy(final_candidates),
            total_candidates_found=len(raw_candidates),
            is_empty=is_empty,
            retriever_name=self.retriever.__class__.__name__,
            reranker_name=self.reranker.__class__.__name__,
            execution_time_ms=elapsed_ms,
            privacy_guarantee=PRIVACY_GUARANTEE_OFFLINE,
            disclaimer=DISCLAIMER_RELEVANCE_NOT_TRUTH,
        )
