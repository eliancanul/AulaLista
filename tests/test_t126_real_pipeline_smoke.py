"""Smoke local: planeación real C02 -> intérprete -> claims -> Atlas -> NLI.

Optativo porque el PDF privado de calibración y los pesos no forman parte del
checkout reproducible. El Atlas usado aquí es explícitamente sintético. Esta
prueba verifica el cableado, no precisión ni respaldo curricular.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from curriculum.atlas import AtlasIndex, create_synthetic_sep_fixture
from curriculum.claims import PREDICATE_CAMPO_FORMATIVO, compile_dossier_to_atomic_claims
from curriculum.source_interpreter import CurriculumSourceInterpreter
from curriculum.tribunal import MDEBERTA_CANDIDATE, MINILM_CANDIDATE, RunStatus
from curriculum.tribunal_transformers import load_cached_tribunal


CORPUS_MANIFEST = Path("docs/research/goldset-importacion-curricular-manifest-v1.json")
CHECKPOINTS = (
    (MINILM_CANDIDATE, "0a71e92a985b6e1ad1828cf67ce9c459639c1dca"),
    (MDEBERTA_CANDIDATE, "b5113eb38ab63efdd7f280f8c144ea8b13f978ce"),
)


@pytest.mark.real_nli_smoke
@pytest.mark.skipif(
    os.environ.get("AULALISTA_RUN_REAL_NLI_SMOKE") != "1",
    reason="Ejecutar explícitamente con AULALISTA_RUN_REAL_NLI_SMOKE=1",
)
def test_private_full_calibration_pdf_through_complete_shadow_path():
    corpus = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    source_entry = next(document for document in corpus["documents"] if document["id"] == "C02")
    assert source_entry["split"] == "calibration"
    source_path = Path(source_entry["path"])
    assert source_path.is_file(), "Falta el PDF privado completo de calibración C02"
    source_bytes = source_path.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    assert source_sha == source_entry["sha256"], "La identidad del PDF C02 cambió"

    manifest, fragments = create_synthetic_sep_fixture()
    assert manifest.is_synthetic is True
    atlas = AtlasIndex(index_version="c01-shadow-smoke-v1")
    atlas.register_manifest(manifest)
    atlas.add_fragments(fragments)
    atlas.build_index()

    # Bloquea cualquier egreso durante la lectura privada y ambos runtimes.
    with patch.object(socket.socket, "connect", side_effect=AssertionError("egreso de red prohibido")):
        dossier = CurriculumSourceInterpreter.prepare(source_path)
        assert dossier.source_sha256 == source_sha
        assert dossier.page_count == source_entry["page_count"] == 44
        assert dossier.verification_report is not None
        assert dossier.verification_report["source_sha256"] == source_sha
        assert dossier.verification_report["blocked_count"] == 0

        claims = compile_dossier_to_atomic_claims(dossier)
        # El compendio no declara un campo global inequívoco en su portada;
        # elegir una afirmación localizada en una sesión evita inventarlo.
        assert next(item for item in claims if item.predicate == PREDICATE_CAMPO_FORMATIVO).page_number is None
        claim = next(item for item in claims if item.predicate == "inicio" and item.page_number is not None and item.excerpt.strip())
        assert claim.source_doc_sha256 == source_sha
        assert "vocales" in str(claim.object_value).lower()
        original_state = claim.state  # Procedencia del PDF, no veredicto NLI.

        retrieval = atlas.retrieve_for_claim(claim, top_k=2)
        assert retrieval.claim_id == claim.claim_id
        assert retrieval.candidates
        assert all(candidate.fragment.source_id == manifest.source_id for candidate in retrieval.candidates)

        summaries = []
        for model_id, revision in CHECKPOINTS:
            tribunal = load_cached_tribunal(
                model_id, revision, timeout_seconds=60, batch_size=2, device="cpu"
            )
            receipt = tribunal.evaluate(
                claim, retrieval, "La sesión inicia con un juego de repaso de las vocales."
            )
            assert receipt.status == RunStatus.COMPLETED
            assert receipt.retrieval_receipt_id == retrieval.receipt_id
            assert receipt.claim_id == claim.claim_id
            assert receipt.model_id == model_id
            assert receipt.model_version == revision
            assert receipt.shadow_mode is True
            assert len(receipt.decisions) == len(retrieval.candidates)
            assert all(decision.pair.receipt_id == retrieval.receipt_id for decision in receipt.decisions)
            assert claim.state == original_state
            json.dumps(receipt.to_dict())
            summaries.append({
                "model": model_id,
                "status": receipt.status.value,
                "reason": receipt.reason,
                "candidate_count": len(receipt.decisions),
                "latency_ms": round(receipt.latency_ms, 1),
            })

    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_sha
    print(json.dumps({
        "source_id": "C02",
        "source_sha256": source_sha,
        "source_pages": dossier.page_count,
        "claim_count": len(claims),
        "atlas_source_kind": "synthetic_fixture",
        "retrieval_receipt_id": retrieval.receipt_id,
        "runs": summaries,
        "semantic_metrics_authorized": False,
    }, ensure_ascii=False))
