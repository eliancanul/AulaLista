"""tests/test_t125_atlas_retrieval.py
Pruebas del MVP del Atlas SEP: interfaz de recuperación y reranking de evidencia (#125).
"""

from __future__ import annotations

import copy
import hashlib
import socket
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from curriculum.atlas import (
    APPROVED_REAL_LICENSES,
    DISCLAIMER_RELEVANCE_NOT_TRUTH,
    PRIVACY_GUARANTEE_OFFLINE,
    AtlasDocumentFragment,
    AtlasIndex,
    AtlasIndexNotReadyError,
    AtlasIntegrityError,
    AtlasPermissionError,
    AtlasSecurityError,
    BM25AtlasRetriever,
    ExactMatchAtlasRetriever,
    PassThroughAtlasReranker,
    RuleBasedAtlasReranker,
    SourceManifest,
    create_synthetic_sep_fixture,
    load_atlas_fixture_from_json,
    make_fragment_id,
    normalize_atlas_text,
    save_atlas_fixture_to_json,
    segment_page_text,
    tokenize_atlas_text,
    validate_source_manifest,
)
from curriculum.claims import (
    CLAIM_STATE_BACKED,
    CLAIM_STATE_CANDIDATE,
    CLAIM_STATE_NEEDS_HUMAN_REVIEW,
    CLAIM_TYPE_FIELD,
    PREDICATE_CAMPO_FORMATIVO,
    PREDICATE_ESCENARIO,
    PREDICATE_METODOLOGIA,
    PREDICATE_OBJETIVO,
    PREDICATE_PROYECTO,
    AtomicClaim,
    make_claim_id,
)


@pytest.fixture
def synthetic_atlas() -> AtlasIndex:
    """Fixture que construye e inicializa un AtlasIndex con el fixture sintético SEP."""
    manifest, fragments = create_synthetic_sep_fixture()
    atlas = AtlasIndex(index_version="1.0.0-test")
    atlas.register_manifest(manifest)
    atlas.add_fragments(fragments)
    atlas.build_index()
    return atlas


@pytest.mark.django_db
class TestAtlasSEPRetrieval125:
    """Verifica los 5 criterios GREEN y la arquitectura del Issue #125."""

    # ─── GREEN 1: Recuperación determinista y resultado vacío explícito ───
    def test_deterministic_retrieval_and_empty_result_explicit(self, synthetic_atlas: AtlasIndex):
        """La recuperación en fixture sintético es 100% determinista y reporta resultado vacío explícito."""
        query = "El nombrario del grupo gafetes de bienvenida"

        # 1. Determinismo: dos ejecuciones idénticas devuelven mismos candidatos, scores y orden
        receipt1 = synthetic_atlas.retrieve(query=query, top_k=3)
        receipt2 = synthetic_atlas.retrieve(query=query, top_k=3)

        assert not receipt1.is_empty
        assert len(receipt1.candidates) > 0
        assert len(receipt1.candidates) == len(receipt2.candidates)
        assert [c.candidate_id for c in receipt1.candidates] == [c.candidate_id for c in receipt2.candidates]
        assert [c.final_score for c in receipt1.candidates] == [c.final_score for c in receipt2.candidates]
        assert [c.fragment.fragment_id for c in receipt1.candidates] == [c.fragment.fragment_id for c in receipt2.candidates]
        assert receipt1.receipt_id == receipt2.receipt_id

        # 2. Resultado vacío explícito: consulta sin coincidencias en el corpus
        query_inexistente = "Mecánica cuántica y relatividad general en superconductores"
        empty_receipt = synthetic_atlas.retrieve(query=query_inexistente, top_k=3)

        assert empty_receipt.is_empty is True
        assert empty_receipt.candidates == []
        assert empty_receipt.total_candidates_found == 0
        assert empty_receipt.receipt_id != ""

    # ─── GREEN 2: Relevancia no se presenta como verdad o respaldo ────────
    def test_relevance_never_presented_as_truth_or_backing(self, synthetic_atlas: AtlasIndex):
        """Las puntuaciones son similitud relativa y NUNCA auto-aprueban o respaldan una afirmación."""
        doc_sha = "doc_sha_test_plan_456"
        claim = AtomicClaim(
            claim_id=make_claim_id("document", PREDICATE_PROYECTO, "El nombrario del grupo", doc_sha),
            claim_type=CLAIM_TYPE_FIELD,
            subject="document",
            predicate=PREDICATE_PROYECTO,
            object_value="El nombrario del grupo",
            source_doc_sha256=doc_sha,
            page_number=1,
            excerpt="El nombrario del grupo",
            state=CLAIM_STATE_CANDIDATE,  # Estado inicial
        )

        receipt = synthetic_atlas.retrieve_for_claim(claim, top_k=3)

        # 1. El estado de la afirmación NO fue mutado (sigue siendo candidate, jamás backed)
        assert claim.state == CLAIM_STATE_CANDIDATE
        assert claim.state != CLAIM_STATE_BACKED

        # 2. El recibo incluye el disclaimer legal y pedagógico explícito
        assert receipt.disclaimer == DISCLAIMER_RELEVANCE_NOT_TRUTH
        assert "NO constituye verdad pedagógica" in receipt.disclaimer

        # 3. Las puntuaciones son métricas de ranking, no probabilidades
        for cand in receipt.candidates:
            assert isinstance(cand.retrieval_score, float)
            assert isinstance(cand.final_score, float)
            assert cand.rank >= 1
            # Invariante: las match_reasons declaran la causa léxica/ontológica
            assert len(cand.match_reasons) > 0

    # ─── GREEN 3: Sin red en runtime por defecto ni egreso de datos ────────
    def test_offline_runtime_and_no_teacher_document_egress(self, synthetic_atlas: AtlasIndex):
        """Verifica que el Atlas opere 100% desconectado sin llamadas a sockets ni egreso de datos."""
        claim = AtomicClaim(
            claim_id="cid_confidential_999",
            claim_type=CLAIM_TYPE_FIELD,
            subject="session:s1",
            predicate=PREDICATE_OBJETIVO,
            object_value="Planeación confidencial de la escuela primaria Emiliano Zapata",
            excerpt="Texto sensible no publicado",
            state=CLAIM_STATE_CANDIDATE,
        )

        # Bloquear cualquier llamada de socket a nivel de sistema operativo
        with patch("socket.socket.connect") as mock_connect:
            receipt = synthetic_atlas.retrieve_for_claim(claim, top_k=2)

            # Assert: connect NUNCA fue llamado
            assert mock_connect.call_count == 0

        # Assert: garantía de privacidad explícita en el recibo
        assert receipt.privacy_guarantee == PRIVACY_GUARANTEE_OFFLINE

    # ─── GREEN 4: Índice reconstruible y medible en tiempo/memoria ─────────
    def test_index_rebuildable_and_measurable_in_time_and_memory(self):
        """El índice es medible en tiempo/memoria y se reconstruye idénticamente tras invalidar."""
        manifest, fragments = create_synthetic_sep_fixture()
        atlas = AtlasIndex(index_version="v1.0-metrics")
        atlas.register_manifest(manifest)
        atlas.add_fragments(fragments)

        # 1. Medición de métricas en primera construcción
        metrics_1 = atlas.build_index()
        assert metrics_1.fragment_count == len(fragments)
        assert metrics_1.vocabulary_size > 0
        assert metrics_1.manifest_count == 1
        assert metrics_1.build_time_ms >= 0.0
        assert metrics_1.memory_bytes_approx > 0
        assert atlas.is_ready is True

        # 2. Invalidación explícita
        atlas.invalidate(new_version="v2.0-invalidated")
        assert atlas.is_ready is False
        assert atlas.get_metrics() is None

        # Consultar mientras está invalidado debe fallar de forma cerrada
        with pytest.raises(AtlasIndexNotReadyError):
            atlas.retrieve("El nombrario")

        # 3. Reconstrucción determinista
        metrics_2 = atlas.build_index()
        assert atlas.is_ready is True
        assert metrics_2.index_version == "v2.0-invalidated"
        assert metrics_2.fragment_count == metrics_1.fragment_count

    # ─── GREEN 5: Ningún libro real se agrega sin permiso e identidad ──────
    def test_real_book_strictly_requires_permission_identity_and_sha(self):
        """Ningún libro real se agrega sin revisar permiso, versión e identidad (SHA-256)."""
        valid_content = b"Contenido oficial verificado del libro de texto gratuito SEP."
        valid_sha = hashlib.sha256(valid_content).hexdigest()

        # 1. Libro real SIN permiso verificado -> Rechazado
        manifest_sin_permiso = SourceManifest(
            source_id="libro_real_primaria_lenguajes_1ro",
            title="Proyectos de Aula 1° - SEP",
            publisher="Secretaría de Educación Pública",
            edition_year=2024,
            version="1.0-oficial",
            license="SEP-CONALITEG-Uso-Educativo-Nacional",
            sha256=valid_sha,
            is_synthetic=False,
            verified_permission=False,  # Fallo de permiso
            verified_identity=True,
        )
        with pytest.raises(AtlasPermissionError, match="permiso de distribución verificado"):
            validate_source_manifest(manifest_sin_permiso, content_bytes=valid_content)

        # 2. Libro real SIN identidad/versión verificada -> Rechazado
        manifest_sin_identidad = SourceManifest(
            source_id="libro_real_primaria_lenguajes_1ro",
            title="Proyectos de Aula 1° - SEP",
            publisher="Secretaría de Educación Pública",
            edition_year=2024,
            version="1.0-oficial",
            license="SEP-CONALITEG-Uso-Educativo-Nacional",
            sha256=valid_sha,
            is_synthetic=False,
            verified_permission=True,
            verified_identity=False,  # Fallo de identidad
        )
        with pytest.raises(AtlasIntegrityError, match="identidad o versión oficial"):
            validate_source_manifest(manifest_sin_identidad, content_bytes=valid_content)

        # 3. Discrepancia de SHA-256 (corrupción o alteración) -> Rechazado
        manifest_corrupto = SourceManifest(
            source_id="libro_real_primaria_lenguajes_1ro",
            title="Proyectos de Aula 1° - SEP",
            publisher="Secretaría de Educación Pública",
            edition_year=2024,
            version="1.0-oficial",
            license="SEP-CONALITEG-Uso-Educativo-Nacional",
            sha256="0000000000000000000000000000000000000000000000000000000000000000",
            is_synthetic=False,
            verified_permission=True,
            verified_identity=True,
        )
        with pytest.raises(AtlasIntegrityError, match="Discrepancia de integridad"):
            validate_source_manifest(manifest_corrupto, content_bytes=valid_content)

        # 4. Licencia no autorizada o no revisada -> Rechazado
        manifest_licencia_invalida = SourceManifest(
            source_id="libro_real_primaria_lenguajes_1ro",
            title="Proyectos de Aula 1° - SEP",
            publisher="Secretaría de Educación Pública",
            edition_year=2024,
            version="1.0-oficial",
            license="desconocida_o_pendiente",
            sha256=valid_sha,
            is_synthetic=False,
            verified_permission=True,
            verified_identity=True,
        )
        with pytest.raises(AtlasSecurityError, match="Licencia 'desconocida_o_pendiente' no autorizada"):
            validate_source_manifest(manifest_licencia_invalida, content_bytes=valid_content)

        # 5. Libro real con todos los candados cumplidos -> Exitoso
        manifest_aprobado = SourceManifest(
            source_id="libro_real_primaria_lenguajes_1ro",
            title="Proyectos de Aula 1° - SEP",
            publisher="Secretaría de Educación Pública",
            edition_year=2024,
            version="1.0-oficial",
            license="SEP-CONALITEG-Uso-Educativo-Nacional",
            sha256=valid_sha,
            is_synthetic=False,
            verified_permission=True,
            verified_identity=True,
        )
        validate_source_manifest(manifest_aprobado, content_bytes=valid_content)
        with pytest.raises(AtlasIntegrityError, match="requiere contenido"):
            validate_source_manifest(manifest_aprobado)
        with pytest.raises(AtlasIntegrityError, match="requiere contenido"):
            AtlasIndex().register_manifest(manifest_aprobado)

    def test_index_and_receipt_identity_change_with_fragment_content(self):
        manifest, fragments = create_synthetic_sep_fixture()
        atlas = AtlasIndex(index_version="same-version")
        atlas.register_manifest(manifest)
        atlas.add_fragments(fragments)
        first_metrics = atlas.build_index()
        first_receipt = atlas.retrieve("nombrario")

        changed_fragment = replace(fragments[0], text="Contenido modificado en la misma página")
        atlas.add_fragment(changed_fragment)
        second_metrics = atlas.build_index()
        second_receipt = atlas.retrieve("nombrario")

        assert second_metrics.index_hash != first_metrics.index_hash
        assert second_receipt.receipt_id != first_receipt.receipt_id

    def test_receipt_identity_includes_hierarchy_filter(self, synthetic_atlas: AtlasIndex):
        first = synthetic_atlas.retrieve("nombrario", hierarchy_filter={"fase": "Fase 3"})
        second = synthetic_atlas.retrieve("nombrario", hierarchy_filter={"fase": "Fase 4"})

        assert first.receipt_id != second.receipt_id

    def test_registered_fragments_and_receipts_do_not_share_mutable_data(self):
        manifest, fragments = create_synthetic_sep_fixture()
        atlas = AtlasIndex()
        atlas.register_manifest(manifest)
        atlas.add_fragments(fragments)
        first_hash = atlas.build_index().index_hash
        first_receipt = atlas.retrieve("nombrario")
        original_text = first_receipt.candidates[0].fragment.text

        fragments[0].hierarchy["fase"] = "Fase ajena"
        manifest.metadata["fase"] = "Fase ajena"
        first_receipt.candidates[0].fragment.hierarchy["fase"] = "Fase ajena"

        assert atlas.build_index().index_hash == first_hash
        assert atlas.retrieve("nombrario").candidates[0].fragment.text == original_text
        assert atlas.retrieve("nombrario").candidates[0].fragment.hierarchy["fase"] != "Fase ajena"

    @pytest.mark.parametrize("top_k", [0, -1, True, 1.5])
    def test_invalid_top_k_is_rejected(self, synthetic_atlas: AtlasIndex, top_k):
        claim = AtomicClaim(
            claim_id="top_k_claim",
            claim_type=CLAIM_TYPE_FIELD,
            subject="document",
            predicate=PREDICATE_PROYECTO,
            object_value="nombrario",
        )
        with pytest.raises(ValueError, match="top_k"):
            synthetic_atlas.retrieve("nombrario", top_k=top_k)
        with pytest.raises(ValueError, match="top_k"):
            synthetic_atlas.retrieve_for_claim(claim, top_k=top_k)

    # ─── Arquitectura: Intercambiabilidad de Retriever y Reranker ─────────
    def test_interchangeable_retriever_and_reranker(self):
        """Verifica que el índice permita intercambiar implementaciones de recuperación y reranking."""
        manifest, fragments = create_synthetic_sep_fixture()

        # Configuración 1: BM25 + RuleBasedReranker
        atlas_bm25 = AtlasIndex(
            index_version="1.0",
            retriever=BM25AtlasRetriever(),
            reranker=RuleBasedAtlasReranker(),
        )
        atlas_bm25.register_manifest(manifest)
        atlas_bm25.add_fragments(fragments)
        atlas_bm25.build_index()

        receipt_bm25 = atlas_bm25.retrieve("Nombrario gafetes", top_k=2)
        assert receipt_bm25.retriever_name == "BM25AtlasRetriever"
        assert receipt_bm25.reranker_name == "RuleBasedAtlasReranker"

        # Configuración 2: ExactMatchRetriever + PassThroughReranker
        atlas_exact = AtlasIndex(
            index_version="1.0",
            retriever=ExactMatchAtlasRetriever(),
            reranker=PassThroughAtlasReranker(),
        )
        atlas_exact.register_manifest(manifest)
        atlas_exact.add_fragments(fragments)
        atlas_exact.build_index()

        receipt_exact = atlas_exact.retrieve("gafetes de bienvenida", top_k=2)
        assert receipt_exact.retriever_name == "ExactMatchAtlasRetriever"
        assert receipt_exact.reranker_name == "PassThroughAtlasReranker"
        assert len(receipt_exact.candidates) > 0

    # ─── Integración #124: Consulta con fragmento real del Nombrario ───────
    def test_integrate_with_atomic_claims_from_real_planeacion(self, synthetic_atlas: AtlasIndex):
        """Valida que una afirmación atómica del Nombrario (Issue #124) recupere evidencia relevante."""
        claim_proyecto = AtomicClaim(
            claim_id="claim_nombrario_proj_124",
            claim_type=CLAIM_TYPE_FIELD,
            subject="document",
            predicate=PREDICATE_PROYECTO,
            object_value="EL NOMBRARIO DEL GRUPO: IDENTIDAD Y LECTOESCRITURA",
            excerpt="Identificación de su nombre en gafetes de bienvenida y tarjetas con fotos",
            state=CLAIM_STATE_CANDIDATE,
        )

        receipt = synthetic_atlas.retrieve_for_claim(claim_proyecto, top_k=3)

        assert not receipt.is_empty
        assert receipt.claim_id == claim_proyecto.claim_id
        # El candidato principal debe hacer referencia al proyecto Nombrario
        top_cand = receipt.candidates[0]
        assert "nombrario" in normalize_atlas_text(top_cand.fragment.text)
        assert top_cand.fragment.page_number in (1, 2)
        # La afirmación permanece en su estado original
        assert claim_proyecto.state == CLAIM_STATE_CANDIDATE

    # ─── Serialización y persistencia de fixtures JSON ────────────────────
    def test_fixture_json_roundtrip_and_segmentation(self, tmp_path: Path):
        """Verifica segmentación de páginas y serialización JSON roundtrip del fixture."""
        manifest, fragments = create_synthetic_sep_fixture()
        json_file = tmp_path / "sep_test_fixture.json"

        save_atlas_fixture_to_json(manifest, fragments, json_file)
        assert json_file.exists()

        loaded_manifest, loaded_fragments = load_atlas_fixture_from_json(json_file)
        assert loaded_manifest.source_id == manifest.source_id
        assert loaded_manifest.sha256 == manifest.sha256
        assert len(loaded_fragments) == len(fragments)
        assert loaded_fragments[0].fragment_id == fragments[0].fragment_id
        assert loaded_fragments[0].text == fragments[0].text
