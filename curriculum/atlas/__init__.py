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

from curriculum.atlas.constants import (
    APPROVED_REAL_LICENSES,
    DISCLAIMER_RELEVANCE_NOT_TRUTH,
    INDEX_STATUS_INVALIDATED,
    INDEX_STATUS_READY,
    INDEX_STATUS_UNINITIALIZED,
    PRIVACY_GUARANTEE_OFFLINE,
    SPANISH_STOP_WORDS,
)
from curriculum.atlas.exceptions import (
    AtlasError,
    AtlasIndexError,
    AtlasIndexNotReadyError,
    AtlasIntegrityError,
    AtlasPermissionError,
    AtlasRetrievalContractError,
    AtlasSecurityError,
)
from curriculum.atlas.fixtures import (
    create_synthetic_sep_fixture,
    load_atlas_fixture_from_json,
    save_atlas_fixture_to_json,
)
from curriculum.atlas.hierarchy import HierarchyFilterMode
from curriculum.atlas.index import AtlasIndex
from curriculum.atlas.models import (
    AtlasDocumentFragment,
    EvidenceCandidate,
    IndexMetrics,
    RetrievalReceipt,
    SourceManifest,
    segment_page_text,
    validate_source_manifest,
)
from curriculum.atlas.rerankers import (
    BaseReranker,
    PassThroughAtlasReranker,
    RuleBasedAtlasReranker,
)
from curriculum.atlas.retrievers import (
    BaseRetriever,
    BM25AtlasRetriever,
    ExactMatchAtlasRetriever,
)
from curriculum.atlas.text import (
    make_candidate_id,
    make_fragment_id,
    make_receipt_id,
    normalize_atlas_text,
    tokenize_atlas_text,
)

__all__ = [
    # Constantes
    "INDEX_STATUS_UNINITIALIZED",
    "INDEX_STATUS_READY",
    "INDEX_STATUS_INVALIDATED",
    "PRIVACY_GUARANTEE_OFFLINE",
    "DISCLAIMER_RELEVANCE_NOT_TRUTH",
    "APPROVED_REAL_LICENSES",
    "SPANISH_STOP_WORDS",
    # Excepciones
    "AtlasError",
    "AtlasSecurityError",
    "AtlasPermissionError",
    "AtlasIntegrityError",
    "AtlasIndexError",
    "AtlasIndexNotReadyError",
    "AtlasRetrievalContractError",
    # Texto
    "normalize_atlas_text",
    "tokenize_atlas_text",
    "make_fragment_id",
    "make_candidate_id",
    "make_receipt_id",
    # Modelos
    "SourceManifest",
    "validate_source_manifest",
    "AtlasDocumentFragment",
    "segment_page_text",
    "EvidenceCandidate",
    "RetrievalReceipt",
    "IndexMetrics",
    # Interfaces y Recuperadores
    "BaseRetriever",
    "HierarchyFilterMode",
    "BM25AtlasRetriever",
    "ExactMatchAtlasRetriever",
    # Interfaces y Rerankers
    "BaseReranker",
    "RuleBasedAtlasReranker",
    "PassThroughAtlasReranker",
    # Índice
    "AtlasIndex",
    # Fixtures
    "create_synthetic_sep_fixture",
    "save_atlas_fixture_to_json",
    "load_atlas_fixture_from_json",
]
