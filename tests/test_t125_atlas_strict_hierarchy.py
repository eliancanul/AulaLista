"""Explicit curriculum restrictions, using only invented, synthetic documents."""

from __future__ import annotations

import copy
import hashlib
import socket
from dataclasses import replace
from unittest.mock import Mock

import pytest

from curriculum.atlas import (
    DISCLAIMER_RELEVANCE_NOT_TRUTH,
    PRIVACY_GUARANTEE_OFFLINE,
    AtlasDocumentFragment,
    AtlasIndex,
    AtlasIntegrityError,
    AtlasPermissionError,
    AtlasRetrievalContractError,
    AtlasSecurityError,
    BM25AtlasRetriever,
    ExactMatchAtlasRetriever,
    EvidenceCandidate,
    PassThroughAtlasReranker,
    RuleBasedAtlasReranker,
    SourceManifest,
    make_fragment_id,
)
from curriculum.claims import (
    CLAIM_STATE_CANDIDATE,
    CLAIM_TYPE_FIELD,
    PREDICATE_CAMPO_FORMATIVO,
    PREDICATE_ESCENARIO,
    PREDICATE_METODOLOGIA,
    PREDICATE_PROYECTO,
    AtomicClaim,
)


SELECTION = {"grado": "3°", "fase": "Fase 4"}
QUERY = "lectura mapas"


def fragment(source, page=1, *, hierarchy=None, text=QUERY):
    return AtlasDocumentFragment(
        fragment_id=make_fragment_id(source, page, 1, text),
        source_id=source,
        page_number=page,
        text=text,
        hierarchy=dict(SELECTION if hierarchy is None else hierarchy),
        region={"x": 1.0, "y": 2.0, "width": 30.0, "height": 40.0},
        sequence_order=1,
    )


def manifest_for(source, version="synthetic-v1"):
    return SourceManifest(
        source_id=source,
        title="Invented document for software tests",
        publisher="Synthetic test author",
        edition_year=2026,
        version=version,
        license="synthetic-test-only",
        sha256=hashlib.sha256(source.encode()).hexdigest(),
        is_synthetic=True,
    )


def build_atlas(retriever_type, fragments, reranker=None):
    atlas = AtlasIndex(
        index_version="strict-synthetic-v1",
        retriever=retriever_type(),
        reranker=reranker or PassThroughAtlasReranker(),
    )
    for source in sorted({f.source_id for f in fragments}):
        atlas.register_manifest(manifest_for(source, version=f"synthetic-{source}-v1"))
    atlas.add_fragments(fragments)
    atlas.build_index()
    return atlas


def claim_for(predicate=PREDICATE_PROYECTO, value=QUERY):
    return AtomicClaim(
        claim_id="synthetic-selection-claim",
        claim_type=CLAIM_TYPE_FIELD,
        subject="document",
        predicate=predicate,
        object_value=value,
        state=CLAIM_STATE_CANDIDATE,
    )


def candidates_for(atlas, entrypoint, selection, *, mode="strict", top_k=3):
    kwargs = {
        "hierarchy_filter": selection,
        "hierarchy_filter_mode": mode,
        "top_k": top_k,
    }
    if entrypoint == "retriever":
        return atlas.retriever.retrieve(QUERY, **kwargs)
    if entrypoint == "retrieve":
        return atlas.retrieve(QUERY, **kwargs).candidates
    claim = claim_for()
    original = copy.deepcopy(claim)
    result = atlas.retrieve_for_claim(claim, **kwargs)
    assert claim == original
    return result.candidates


@pytest.fixture(params=[BM25AtlasRetriever, ExactMatchAtlasRetriever])
def retriever_type(request):
    return request.param


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
@pytest.mark.parametrize("top_k", [1, 3])
def test_strict_filters_before_top_k_and_reranking(retriever_type, entrypoint, top_k):
    # Nine stronger distractors exceed even the index's 2 * top_k window.
    distractors = [
        fragment(f"distractor-{i}", hierarchy={"grado": "6°", "fase": "Fase 5"})
        for i in range(9)
    ]
    compatible = [
        fragment("selected-a", page=17, text="lectura " + "contenido " * 30),
        fragment("selected-b", page=23, text="mapas " + "contenido " * 30),
    ]
    reranker = Mock(wraps=PassThroughAtlasReranker())
    atlas = build_atlas(retriever_type, distractors + compatible, reranker)
    # Demonstrate that filtering after legacy truncation would lose all evidence.
    legacy = atlas.retriever.retrieve(QUERY, top_k=6, hierarchy_filter=SELECTION)
    assert all(c.fragment.source_id.startswith("distractor-") for c in legacy)

    candidates = candidates_for(atlas, entrypoint, SELECTION, top_k=top_k)

    assert len(candidates) == min(top_k, 2)
    assert {c.fragment.source_id for c in candidates} <= {"selected-a", "selected-b"}
    assert len({c.fragment.fragment_id for c in candidates}) == len(candidates)
    assert [c.rank for c in candidates] == list(range(1, len(candidates) + 1))
    if entrypoint != "retriever":
        seen = reranker.rerank.call_args.kwargs["candidates"]
        assert {c.fragment.source_id for c in seen} == {"selected-a", "selected-b"}


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
def test_strict_requires_every_selected_key(retriever_type, entrypoint):
    fragments = [
        fragment("complete"),
        fragment("grade-only", hierarchy={"grado": "3°", "fase": "Fase 5"}),
        fragment("phase-only", hierarchy={"grado": "6°", "fase": "Fase 4"}),
        fragment("no-grade", hierarchy={"fase": "Fase 4"}),
        fragment("no-phase", hierarchy={"grado": "3°"}),
        fragment("no-metadata", hierarchy={}),
        fragment("empty-grade", hierarchy={"grado": "", "fase": "Fase 4"}),
        fragment("blank-phase", hierarchy={"grado": "3°", "fase": "   "}),
        fragment("unknown-grade", hierarchy={"grado": "desconocido", "fase": "Fase 4"}),
        fragment("empty-normalized-grade", hierarchy={"grado": "?!", "fase": "Fase 4"}),
    ]
    atlas = build_atlas(retriever_type, fragments)
    candidates = candidates_for(atlas, entrypoint, SELECTION, top_k=20)
    assert [c.fragment.source_id for c in candidates] == ["complete"]


@pytest.mark.parametrize("selection", [
    {"grado": "99", "fase": "99"},
    {"grado": "3°", "fase": "Fase 5"},
    {"grado": "3°", "unknown_level": "selected"},
])
@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
def test_impossible_selection_is_empty_without_fallback(retriever_type, selection, entrypoint):
    atlas = build_atlas(retriever_type, [
        fragment("third"),
        fragment("sixth", hierarchy={"grado": "6°", "fase": "Fase 5"}),
    ])
    assert candidates_for(atlas, entrypoint, selection) == []
    if entrypoint != "retriever":
        method = getattr(atlas, entrypoint)
        query = QUERY if entrypoint == "retrieve" else claim_for()
        receipt = method(query, hierarchy_filter=selection, hierarchy_filter_mode="strict")
        assert receipt.is_empty
        assert receipt.total_candidates_found == 0
        assert receipt.privacy_guarantee == PRIVACY_GUARANTEE_OFFLINE
        assert receipt.disclaimer == DISCLAIMER_RELEVANCE_NOT_TRUTH


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
def test_matching_normalizes_values_without_inventing_curriculum_aliases(retriever_type, entrypoint):
    atlas = build_atlas(retriever_type, [
        fragment("complete", hierarchy={**SELECTION, "campo_formativo": "Léngüajes"}),
        fragment("grade-word", hierarchy={"grado": "tercero", "fase": "Fase 4"}),
    ])
    selection = {"grado": "3°", "fase": " FASE   4 ", "campo_formativo": "lenguajes"}
    assert [c.fragment.source_id for c in candidates_for(atlas, entrypoint, selection)] == ["complete"]


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
def test_identical_text_preserves_distinct_provenance(retriever_type, entrypoint):
    fragments = [fragment("source-a", 4), fragment("source-b", 81)]
    wrong_grade = fragment("source-c", 19, hierarchy={"grado": "1°", "fase": "Fase 3"})
    atlas = build_atlas(retriever_type, [wrong_grade] + fragments)
    original_hash = atlas.get_metrics().index_hash
    candidates = candidates_for(atlas, entrypoint, SELECTION, top_k=10)
    assert {c.fragment.fragment_id for c in candidates} == {f.fragment_id for f in fragments}
    assert {c.fragment.source_id: c.fragment for c in candidates} == {f.source_id: f for f in fragments}
    assert atlas.get_metrics().index_hash == original_hash
    assert atlas.index_version == "strict-synthetic-v1"
    # Source versions remain in their manifests and still affect index identity.
    atlas.register_manifest(manifest_for("source-a", "synthetic-source-a-v2"))
    assert atlas.build_index().index_hash != original_hash


def test_prefer_keeps_previous_ranking_contract(retriever_type):
    fragments = [
        fragment("complete"),
        fragment("partial", hierarchy={"grado": "3°", "fase": "Fase 5"}),
        fragment("different", hierarchy={"grado": "6°", "fase": "Fase 5"}),
    ]
    atlas = build_atlas(retriever_type, fragments)
    retriever = atlas.retriever
    unfiltered = retriever.retrieve(QUERY, top_k=10)
    default = retriever.retrieve(QUERY, top_k=10, hierarchy_filter=SELECTION)
    explicit = retriever.retrieve(QUERY, top_k=10, hierarchy_filter=SELECTION, hierarchy_filter_mode="prefer")
    assert default == explicit
    assert len(default) == 3
    raw = {c.fragment.source_id: c.retrieval_score for c in unfiltered}
    scores = {c.fragment.source_id: c.retrieval_score for c in explicit}
    if retriever_type is BM25AtlasRetriever:
        assert scores["complete"] == pytest.approx(raw["complete"] * 1.6)
        assert scores["partial"] == pytest.approx(raw["partial"] * 1.3)
        assert scores["different"] == raw["different"]
    else:
        assert explicit == unfiltered
    assert retriever.retrieve(QUERY, hierarchy_filter={"grado": "99", "fase": "99"})
    for entrypoint in ("retrieve", "retrieve_for_claim"):
        method = getattr(atlas, entrypoint)
        query = QUERY if entrypoint == "retrieve" else claim_for()
        first = method(query, hierarchy_filter=SELECTION)
        second = method(query, hierarchy_filter=SELECTION, hierarchy_filter_mode="prefer")
        assert first.candidates == second.candidates
        assert first.receipt_id == second.receipt_id


@pytest.mark.parametrize("predicate, key", [
    (PREDICATE_CAMPO_FORMATIVO, "campo_formativo"),
    (PREDICATE_ESCENARIO, "escenario"),
    (PREDICATE_METODOLOGIA, "metodologia"),
])
def test_strict_claim_does_not_turn_the_claim_into_an_implicit_restriction(retriever_type, predicate, key):
    atlas = build_atlas(retriever_type, [fragment("complete")])
    claim = claim_for(predicate)
    original = copy.deepcopy(claim)
    strict = atlas.retrieve_for_claim(claim, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict")
    direct = atlas.retrieve(QUERY, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict")
    assert strict.candidates == direct.candidates
    assert strict.hierarchy_filter == SELECTION
    assert claim == original
    # Explicit semantic selections, unlike unverified claim hints, are mandatory.
    assert atlas.retrieve_for_claim(
        claim, hierarchy_filter={**SELECTION, key: QUERY}, hierarchy_filter_mode="strict"
    ).is_empty
    preferred = atlas.retrieve_for_claim(claim, hierarchy_filter=SELECTION)
    assert preferred.hierarchy_filter == {**SELECTION, key: QUERY}


@pytest.mark.parametrize("entrypoint", ["retrieve", "retrieve_for_claim"])
def test_receipt_distinguishes_strict_from_prefer_and_copies_selection(retriever_type, entrypoint):
    atlas = build_atlas(retriever_type, [fragment("complete")])
    method = getattr(atlas, entrypoint)
    query = QUERY if entrypoint == "retrieve" else claim_for()
    selection = dict(SELECTION)
    strict = method(query, hierarchy_filter=selection, hierarchy_filter_mode="strict")
    preferred = method(query, hierarchy_filter=selection)
    repeated = method(query, hierarchy_filter=selection, hierarchy_filter_mode="strict")
    assert strict.receipt_id != preferred.receipt_id
    assert strict.receipt_id == repeated.receipt_id
    assert strict.candidates == repeated.candidates
    assert strict.hierarchy_filter_mode == "strict"
    assert preferred.hierarchy_filter_mode == "prefer"
    assert strict.to_dict()["hierarchy_filter_mode"] == "strict"
    assert strict.to_dict()["hierarchy_filter"] == SELECTION
    selection["grado"] = "6°"
    strict.to_dict()["hierarchy_filter"]["fase"] = "Fase 5"
    assert strict.hierarchy_filter == SELECTION
    strict.hierarchy_filter["grado"] = "6°"
    assert repeated.hierarchy_filter == SELECTION


@pytest.mark.parametrize("selection", [None, {}])
@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
def test_no_selected_keys_means_no_restriction(retriever_type, selection, entrypoint):
    atlas = build_atlas(retriever_type, [fragment("missing", hierarchy={}), fragment("complete")])
    assert candidates_for(atlas, entrypoint, selection) == candidates_for(
        atlas, entrypoint, selection, mode="prefer"
    )


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
@pytest.mark.parametrize("mode", ["strcit", "STRICT", "", None, True])
def test_unknown_mode_cannot_silently_fall_back(retriever_type, entrypoint, mode):
    atlas = build_atlas(retriever_type, [])
    with pytest.raises(ValueError, match="hierarchy_filter_mode"):
        candidates_for(atlas, entrypoint, SELECTION, mode=mode)


@pytest.mark.parametrize("selection", [
    {"grado": ""}, {"grado": "   "}, {"grado": "?!"}, {"grado": None},
    {"grado": 3}, {"grado": False}, {"": "3°"}, {"  ": "3°"}, {3: "3°"},
    [], [("grado", "3°")], "", "grado=3°",
])
@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
def test_invalid_strict_selection_is_rejected_even_on_empty_index(retriever_type, selection, entrypoint):
    atlas = build_atlas(retriever_type, [])
    with pytest.raises(ValueError, match="hierarchy_filter"):
        candidates_for(atlas, entrypoint, selection)


def test_strict_selection_does_not_bypass_source_gates(retriever_type):
    atlas = build_atlas(retriever_type, [])
    synthetic = manifest_for("unregistered")
    with pytest.raises(AtlasSecurityError, match="no registrada"):
        atlas.add_fragment(fragment("unregistered"))
    with pytest.raises(AtlasPermissionError):
        atlas.register_manifest(replace(synthetic, is_synthetic=False))
    with pytest.raises(AtlasIntegrityError):
        atlas.register_manifest(synthetic, content_bytes=b"mismatching synthetic bytes")
    assert atlas.retrieve(QUERY, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict").is_empty


@pytest.mark.parametrize("entrypoint", ["retrieve", "retrieve_for_claim"])
def test_legacy_custom_retriever_works_in_prefer_but_never_silently_downgrades_strict(entrypoint):
    class LegacyRetriever(BM25AtlasRetriever):
        def retrieve(self, query, top_k=3, hierarchy_filter=None):
            return super().retrieve(query, top_k, hierarchy_filter)

    atlas = build_atlas(LegacyRetriever, [fragment("complete")])
    method = getattr(atlas, entrypoint)
    query = QUERY if entrypoint == "retrieve" else claim_for()
    assert not method(query, hierarchy_filter=SELECTION).is_empty
    assert not method(query, hierarchy_filter=SELECTION, hierarchy_filter_mode="prefer").is_empty
    with pytest.raises(TypeError, match="hierarchy_filter_mode"):
        method(query, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict")


@pytest.mark.parametrize("entrypoint", ["retrieve", "retrieve_for_claim"])
def test_empty_receipt_identity_still_distinguishes_mode(retriever_type, entrypoint):
    atlas = build_atlas(retriever_type, [])
    method = getattr(atlas, entrypoint)
    query = QUERY if entrypoint == "retrieve" else claim_for()
    strict = method(query, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict")
    preferred = method(query, hierarchy_filter=SELECTION)
    assert strict.is_empty and preferred.is_empty
    assert strict.receipt_id != preferred.receipt_id


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
def test_selection_alone_cannot_fabricate_a_lexical_match(retriever_type, entrypoint):
    atlas = build_atlas(retriever_type, [fragment("complete", text="astronomia telescopios")])
    assert candidates_for(atlas, entrypoint, SELECTION) == []


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
@pytest.mark.parametrize("selection, expected", [
    ({"grado": "3°"}, {"complete", "grade-only", "different-phase"}),
    ({"fase": "Fase 4"}, {"complete", "phase-only", "different-grade"}),
])
def test_only_explicit_levels_are_required(retriever_type, entrypoint, selection, expected):
    atlas = build_atlas(retriever_type, [
        fragment("complete"),
        fragment("grade-only", hierarchy={"grado": "3°"}),
        fragment("phase-only", hierarchy={"fase": "Fase 4"}),
        fragment("different-phase", hierarchy={"grado": "3°", "fase": "Fase 5"}),
        fragment("different-grade", hierarchy={"grado": "6°", "fase": "Fase 4"}),
    ])
    candidates = candidates_for(atlas, entrypoint, selection, top_k=10)
    assert {c.fragment.source_id for c in candidates} == expected


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
def test_all_explicit_keys_are_conjunctive_without_a_hardcoded_allowlist(retriever_type, entrypoint):
    selection = {
        **SELECTION,
        "campo_formativo": "Lenguajes",
        "escenario": "Aula",
        "metodologia": "ABPC",
        "tipo_libro": "Proyectos",
        "custom_level": "selected",
    }
    fragments = [fragment("complete", hierarchy=selection)]
    for key in selection:
        fragments.append(fragment(f"wrong-{key}", hierarchy={**selection, key: "incompatible"}))
        fragments.append(fragment(f"missing-{key}", hierarchy={k: v for k, v in selection.items() if k != key}))
    atlas = build_atlas(retriever_type, fragments)
    candidates = candidates_for(atlas, entrypoint, selection, top_k=20)
    assert [c.fragment.source_id for c in candidates] == ["complete"]


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
@pytest.mark.parametrize("selection", [{"GRADO": "3°"}, {" grado ": "3°"}, {"grade": "3°"}])
def test_selection_keys_are_exact_and_never_rewritten(retriever_type, entrypoint, selection):
    atlas = build_atlas(retriever_type, [fragment("complete")])
    assert candidates_for(atlas, entrypoint, selection) == []


@pytest.mark.parametrize("predicate, key", [
    (PREDICATE_CAMPO_FORMATIVO, "campo_formativo"),
    (PREDICATE_ESCENARIO, "escenario"),
    (PREDICATE_METODOLOGIA, "metodologia"),
])
@pytest.mark.parametrize("selection", [None, {}, {"grado": "3°"}])
def test_rule_reranker_can_rank_counterevidence_without_filtering_it(retriever_type, predicate, key, selection):
    atlas = build_atlas(retriever_type, [
        fragment("supports-metadata", hierarchy={**SELECTION, key: QUERY}),
        fragment("opposes-metadata", hierarchy={**SELECTION, key: "otra propuesta"}),
        fragment("missing-metadata"),
    ], RuleBasedAtlasReranker())
    claim = claim_for(predicate)
    original = copy.deepcopy(claim)
    receipt = atlas.retrieve_for_claim(claim, hierarchy_filter=selection, hierarchy_filter_mode="strict")
    assert {c.fragment.source_id for c in receipt.candidates} == {
        "supports-metadata", "opposes-metadata", "missing-metadata",
    }
    assert receipt.candidates[0].fragment.source_id == "supports-metadata"
    assert receipt.hierarchy_filter == (selection or {})
    assert claim == original


@pytest.mark.parametrize("entrypoint", ["retrieve", "retrieve_for_claim"])
def test_strict_mode_is_local_to_each_call_and_deterministic_on_rebuild(retriever_type, entrypoint):
    fragments = [fragment("complete"), fragment("unknown", hierarchy={})]
    atlas = build_atlas(retriever_type, fragments, RuleBasedAtlasReranker())
    method = getattr(atlas, entrypoint)
    query = QUERY if entrypoint == "retrieve" else claim_for()
    preferred = method(query, hierarchy_filter=SELECTION)
    strict = method(query, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict")
    assert len(strict.candidates) == 1
    repeated_preferred = method(query, hierarchy_filter=SELECTION)
    assert len(repeated_preferred.candidates) == 2
    assert repeated_preferred.candidates == preferred.candidates
    assert repeated_preferred.receipt_id == preferred.receipt_id
    rebuilt = build_atlas(retriever_type, list(reversed(fragments)), RuleBasedAtlasReranker())
    repeated_strict = getattr(rebuilt, entrypoint)(
        query, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict"
    )
    assert repeated_strict.candidates == strict.candidates
    assert repeated_strict.receipt_id == strict.receipt_id


@pytest.mark.parametrize("entrypoint", ["retriever", "retrieve", "retrieve_for_claim"])
def test_strict_retrieval_and_rebuild_do_not_use_the_network(retriever_type, entrypoint, monkeypatch):
    def prohibit_network(*args, **kwargs):
        pytest.fail("Atlas strict must stay offline")

    monkeypatch.setattr(socket.socket, "connect", prohibit_network)
    monkeypatch.setattr(socket, "create_connection", prohibit_network)
    monkeypatch.setattr(socket, "getaddrinfo", prohibit_network)
    atlas = build_atlas(retriever_type, [fragment("complete")], RuleBasedAtlasReranker())
    assert candidates_for(atlas, entrypoint, SELECTION)


@pytest.mark.parametrize("entrypoint", ["retrieve", "retrieve_for_claim"])
@pytest.mark.parametrize("incompatible", [{"grado": "6°", "fase": "Fase 5"}, {}])
def test_index_rejects_retriever_that_ignores_strict_before_reranking(retriever_type, entrypoint, incompatible):
    class IgnoringStrictRetriever(retriever_type):
        def retrieve(self, query, top_k=3, hierarchy_filter=None, *, hierarchy_filter_mode="prefer"):
            # A legacy adapter accepts the new option but forgets to forward it.
            return super().retrieve(query, top_k, hierarchy_filter)

    reranker = Mock(wraps=PassThroughAtlasReranker())
    atlas = build_atlas(IgnoringStrictRetriever, [
        fragment("complete"), fragment("incompatible", hierarchy=incompatible),
    ], reranker)
    method = getattr(atlas, entrypoint)
    query = QUERY if entrypoint == "retrieve" else claim_for()
    # Detect even an incompatible candidate outside the eventual top_k=1.
    with pytest.raises(AtlasRetrievalContractError, match="retriever.*strict"):
        method(query, top_k=1, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict")
    reranker.rerank.assert_not_called()
    # The defensive check is opt-in and preserves the existing adapter contract.
    preferred = method(query, top_k=2, hierarchy_filter=SELECTION)
    assert len(preferred.candidates) == 2


@pytest.mark.parametrize("entrypoint", ["retrieve", "retrieve_for_claim"])
@pytest.mark.parametrize("incompatible", [{"grado": "6°", "fase": "Fase 5"}, {}])
@pytest.mark.parametrize("position", ["first", "last"])
def test_index_rejects_reranker_that_reintroduces_incompatible_candidate(
    retriever_type, entrypoint, incompatible, position,
):
    wrong = fragment("incompatible", hierarchy=incompatible)
    wrong_candidate = EvidenceCandidate("synthetic-incompatible-candidate", wrong, 999.0)

    class ReintroducingReranker(PassThroughAtlasReranker):
        def rerank(self, query, candidates, claim=None):
            assert {c.fragment.source_id for c in candidates} == {"complete"}
            reranked = super().rerank(query, candidates, claim)
            if position == "first":
                return [wrong_candidate] + reranked
            return reranked + [wrong_candidate]

    atlas = build_atlas(retriever_type, [fragment("complete"), wrong], ReintroducingReranker())
    method = getattr(atlas, entrypoint)
    query = QUERY if entrypoint == "retrieve" else claim_for()
    # Validate the entire reranker output before final truncation; do not hide it.
    with pytest.raises(AtlasRetrievalContractError, match="reranker.*strict"):
        method(query, top_k=1, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict")


@pytest.mark.parametrize("entrypoint", ["retrieve", "retrieve_for_claim"])
def test_index_rejects_reranker_fallback_when_strict_retrieval_is_empty(retriever_type, entrypoint):
    wrong = fragment("incompatible", hierarchy={"grado": "6°", "fase": "Fase 5"})
    wrong_candidate = EvidenceCandidate("synthetic-fallback-candidate", wrong, 1.0)

    class FallbackReranker(PassThroughAtlasReranker):
        def rerank(self, query, candidates, claim=None):
            assert candidates == []
            return [wrong_candidate]

    atlas = build_atlas(retriever_type, [wrong], FallbackReranker())
    method = getattr(atlas, entrypoint)
    query = QUERY if entrypoint == "retrieve" else claim_for()
    with pytest.raises(AtlasRetrievalContractError, match="reranker.*strict"):
        method(query, hierarchy_filter=SELECTION, hierarchy_filter_mode="strict")
