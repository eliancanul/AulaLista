"""Tests for atomic claim provenance preservation and phase review unit authority.

Verifies:
1. Authority invariant: synthetic project review units (session_id *_project_review,
   without explicit session header, status ambiguous) must NOT compile to AtomicClaim
   `es_entidad=session` with state `backed` merely because pages exist; they must compile
   to `needs_human_review` with explicit metadata and reason.
2. Regression invariant: normal sessions with explicit pages remain backed.
3. Provenance preservation: multi-page field evidence (such as project duration spanning
   pages 1 and 2) preserves all SourceReference entries in order, while maintaining
   legacy page_number and excerpt contracts.
4. Tamper / hash mismatch: evidence references with mismatched document_sha256 are discarded
   and do not back the claim.
5. Serialization contract: to_dict/from_dict roundtrip preserves typed SourceReferences,
   and from_dict remains backward-compatible with legacy dicts lacking the `evidence` key.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from curriculum.claims import (
    AtomicClaim,
    CLAIM_STATE_BACKED,
    CLAIM_STATE_CANDIDATE,
    CLAIM_STATE_NEEDS_HUMAN_REVIEW,
    CLAIM_TYPE_ENTITY,
    CLAIM_TYPE_FIELD,
    CLAIM_TYPE_RELATION,
    ENTITY_TYPE_PROJECT_REVIEW,
    ENTITY_TYPE_SESSION,
    PREDICATE_DURACION_PROYECTO,
    PREDICATE_ESTADO_ACTIVIDAD,
    PREDICATE_PERTENECE_A_SESION,
    PREDICATE_PERTENECE_A_UNIDAD_REVISION,
    PREDICATE_PROYECTO,
    compile_dossier_to_atomic_claims,
)
from curriculum.source_interpreter import (
    ORIGIN_EXTRACTED,
    ORIGIN_PROPOSED,
    STATUS_AMBIGUOUS,
    STATUS_SUPPORTED,
    ImportDossier,
    InterpretedField,
    SessionActivity,
    SessionPlan,
    SourceReference,
)


DOC_SHA_SYNTHETIC = "a" * 64
FOREIGN_SHA_SYNTHETIC = "f" * 64


def _make_synthetic_dossier(
    doc_sha: str = DOC_SHA_SYNTHETIC,
    general_fields: dict[str, InterpretedField] | None = None,
    sessions: list[SessionPlan] | None = None,
) -> ImportDossier:
    return ImportDossier(
        source_sha256=doc_sha,
        source_name="planeacion_sintetica.pdf",
        page_count=3,
        general_fields=general_fields or {},
        sessions=sessions or [],
    )


# ==============================================================================
# 1. AUTORIDAD DOCENTE: Fases != Sesiones en compilación de entidades
# ==============================================================================

def test_phase_project_review_unit_compiles_to_needs_human_review_not_backed():
    """A synthetic project review session must never compile to backed session entity."""
    review_unit = SessionPlan(
        session_id="p1_project_review",
        session_number=1,
        title="Proyecto sin sesiones explícitas",
        project_title="Cuidado del Huerto Escolar",
        pages=[1, 2],
        layout_fidelity="linearized_heuristics",
        layout_notes="La fuente organiza el trabajo por fases del proyecto y no declara sesiones.",
        fields={
            "inicio": InterpretedField(
                name="inicio",
                value="Observar las plantas del huerto",
                origin=ORIGIN_PROPOSED,
                status=STATUS_AMBIGUOUS,
                evidence=[
                    SourceReference(
                        document_sha256=DOC_SHA_SYNTHETIC,
                        page_number=1,
                        excerpt="Observar las plantas del huerto",
                    )
                ],
            ),
        },
        activities=[
            SessionActivity(
                activity_id="p1_act_1",
                title="Actividad 1: Observar las plantas",
                description="Observar las plantas del huerto escolar y anotar dudas.",
                order=1,
                evidence=[
                    SourceReference(
                        document_sha256=DOC_SHA_SYNTHETIC,
                        page_number=1,
                        excerpt="Observar las plantas del huerto escolar",
                    )
                ],
            )
        ],
        status=STATUS_AMBIGUOUS,
        review="pending",
    )

    dossier = _make_synthetic_dossier(sessions=[review_unit])
    claims = compile_dossier_to_atomic_claims(dossier)

    entity_claim = next(
        c for c in claims
        if c.claim_type == CLAIM_TYPE_ENTITY
        and c.predicate == "es_entidad"
        and c.subject == "project_review:p1_project_review"
    )

    # Invariant (Slice C/C2): Must represent as project_review entity, NEVER affirm it is a session
    assert entity_claim.subject == "project_review:p1_project_review"
    assert not entity_claim.subject.startswith("session:")
    assert entity_claim.object_value == ENTITY_TYPE_PROJECT_REVIEW
    assert entity_claim.object_value != ENTITY_TYPE_SESSION
    assert entity_claim.object_value != "session"
    assert entity_claim.state != CLAIM_STATE_BACKED
    assert entity_claim.state == CLAIM_STATE_NEEDS_HUMAN_REVIEW
    assert entity_claim.metadata.get("unit_type") == "project_review"
    assert "sin sesiones explícitas" in entity_claim.metadata.get("reason", "").lower()

    # Invariant (Slice C/C2): activity -> unit under project_review must NEVER be backed and must use typed predicate and object
    rel_claim = next(
        c for c in claims
        if c.claim_type == CLAIM_TYPE_RELATION
        and c.subject == "activity:p1_act_1"
    )
    assert rel_claim.predicate == PREDICATE_PERTENECE_A_UNIDAD_REVISION
    assert rel_claim.predicate != PREDICATE_PERTENECE_A_SESION
    assert rel_claim.object_value == "project_review:p1_project_review"
    assert not rel_claim.object_value.startswith("session:")
    assert rel_claim.state != CLAIM_STATE_BACKED
    assert rel_claim.state == CLAIM_STATE_NEEDS_HUMAN_REVIEW
    assert rel_claim.metadata.get("unit_type") == ENTITY_TYPE_PROJECT_REVIEW
    assert "sin sesiones explícitas" in rel_claim.metadata.get("reason", "").lower()

    # Invariant (Slice C2): Fields attached to the review unit must also use project_review: prefix as subject
    field_claim = next(
        c for c in claims
        if c.claim_type == CLAIM_TYPE_FIELD
        and c.predicate == "inicio"
    )
    assert field_claim.subject == "project_review:p1_project_review"
    assert not field_claim.subject.startswith("session:")


def test_normal_numbered_session_compiles_to_backed_entity():
    """A standard session with an explicit physical page compiles to backed entity and keeps relation backed."""
    normal_activity = SessionActivity(
        activity_id="s1_act_1",
        title="Actividad 1: Apertura",
        description="Apertura y encuadre de la sesión.",
        order=1,
        evidence=[
            SourceReference(
                document_sha256=DOC_SHA_SYNTHETIC,
                page_number=1,
                excerpt="Apertura y encuadre de la sesión",
            )
        ],
    )
    normal_session = SessionPlan(
        session_id="s1_normal",
        session_number=1,
        title="Sesión 1: Apertura del ciclo",
        project_title="Cuidado del Huerto Escolar",
        pages=[1],
        layout_fidelity="verbatim_blocks",
        layout_notes="",
        fields={},
        activities=[normal_activity],
        status=STATUS_SUPPORTED,
        review="pending",
    )

    dossier = _make_synthetic_dossier(sessions=[normal_session])
    claims = compile_dossier_to_atomic_claims(dossier)

    entity_claim = next(
        c for c in claims
        if c.claim_type == CLAIM_TYPE_ENTITY
        and c.predicate == "es_entidad"
        and c.subject == "session:s1_normal"
    )

    assert entity_claim.object_value == ENTITY_TYPE_SESSION
    assert entity_claim.state == CLAIM_STATE_BACKED
    assert entity_claim.page_number == 1

    # Invariant (Slice C/C2): normal session activity relation with evidence remains backed
    normal_rel = next(
        c for c in claims
        if c.claim_type == CLAIM_TYPE_RELATION
        and c.predicate == PREDICATE_PERTENECE_A_SESION
        and c.subject == "activity:s1_act_1"
    )
    assert normal_rel.state == CLAIM_STATE_BACKED
    assert normal_rel.object_value == "session:s1_normal"
    assert normal_rel.object_value.startswith("session:")
    assert normal_rel.predicate == PREDICATE_PERTENECE_A_SESION
    assert normal_rel.predicate != PREDICATE_PERTENECE_A_UNIDAD_REVISION


def test_synthetic_project_review_unit_ontology_contracts():
    """Verify complete ontology for synthetic review units:
    - subject uses `project_review:<id>` (not `session:<id>`)
    - relation predicate is `pertenece_a_unidad_revision` (not `pertenece_a_sesion`)
    - object_value is `project_review:<id>`
    - state is `needs_human_review` with metadata
    - activities without evidence also preserve the relation as needs_human_review
    """
    review_unit = SessionPlan(
        session_id="fase_1_project_review",
        session_number=1,
        title="Fase 1: Lanzamiento del proyecto (sin sesiones explícitas)",
        project_title="Cuidado del Agua",
        pages=[1],
        layout_fidelity="linearized_heuristics",
        layout_notes="Organización por fases sin sesiones explícitas.",
        fields={
            "inicio": InterpretedField(
                name="inicio",
                value="Actividad inicial del proyecto",
                origin=ORIGIN_PROPOSED,
                status=STATUS_AMBIGUOUS,
            ),
        },
        activities=[
            SessionActivity(
                activity_id="f1_act_1",
                title="Lluvia de ideas",
                description="Lluvia de ideas sobre el agua",
                order=1,
                evidence=[],
            )
        ],
        status=STATUS_AMBIGUOUS,
        review="pending",
    )

    dossier = _make_synthetic_dossier(sessions=[review_unit])
    claims = compile_dossier_to_atomic_claims(dossier)

    # 1. Entity claim
    entity_claims = [c for c in claims if c.claim_type == CLAIM_TYPE_ENTITY]
    assert len(entity_claims) == 1
    ent = entity_claims[0]
    assert ent.subject == "project_review:fase_1_project_review"
    assert ent.predicate == "es_entidad"
    assert ent.object_value == ENTITY_TYPE_PROJECT_REVIEW
    assert ent.state == CLAIM_STATE_NEEDS_HUMAN_REVIEW
    assert ent.metadata.get("unit_type") == "project_review"
    assert not ent.subject.startswith("session:")

    # 2. Relation claim
    rel_claims = [c for c in claims if c.claim_type == CLAIM_TYPE_RELATION and c.subject == "activity:f1_act_1"]
    assert len(rel_claims) == 1
    rel = rel_claims[0]
    assert rel.predicate == PREDICATE_PERTENECE_A_UNIDAD_REVISION
    assert rel.predicate != PREDICATE_PERTENECE_A_SESION
    assert rel.object_value == "project_review:fase_1_project_review"
    assert not rel.object_value.startswith("session:")
    assert rel.state == CLAIM_STATE_NEEDS_HUMAN_REVIEW
    assert rel.metadata.get("unit_type") == "project_review"

    # 3. Field claim
    field_claim = next(c for c in claims if c.claim_type == CLAIM_TYPE_FIELD and c.predicate == "inicio")
    assert field_claim.subject == "project_review:fase_1_project_review"
    assert not field_claim.subject.startswith("session:")


# ==============================================================================
# 2. PROCEDENCIA MULTIPÁGINA: Preservación de citas en orden y contratos legacy
# ==============================================================================

def test_multipage_field_evidence_preserves_all_references_in_order():
    """Multi-page duration field preserves both page 1 and page 2 evidence references in claim."""
    ev_page_1 = SourceReference(
        document_sha256=DOC_SHA_SYNTHETIC,
        page_number=1,
        excerpt="Tiempo de aplicacion: Se sugiere",
    )
    ev_page_2 = SourceReference(
        document_sha256=DOC_SHA_SYNTHETIC,
        page_number=2,
        excerpt="dos semanas lectivas",
    )

    dur_field = InterpretedField(
        name="duracion_proyecto",
        value="Se sugiere dos semanas lectivas",
        origin=ORIGIN_PROPOSED,
        status=STATUS_AMBIGUOUS,
        evidence=[ev_page_1, ev_page_2],
    )

    dossier = _make_synthetic_dossier(general_fields={"duracion_proyecto": dur_field})
    claims = compile_dossier_to_atomic_claims(dossier)

    dur_claim = next(c for c in claims if c.predicate == PREDICATE_DURACION_PROYECTO)

    # Legacy contract: page_number and excerpt point to primary (first) citation
    assert dur_claim.page_number == 1
    assert dur_claim.excerpt == "Tiempo de aplicacion: Se sugiere"

    # New contract: all evidence references preserved in order
    assert len(dur_claim.evidence) == 2
    assert dur_claim.evidence[0].page_number == 1
    assert dur_claim.evidence[0].excerpt == "Tiempo de aplicacion: Se sugiere"
    assert dur_claim.evidence[0].document_sha256 == DOC_SHA_SYNTHETIC

    assert dur_claim.evidence[1].page_number == 2
    assert dur_claim.evidence[1].excerpt == "dos semanas lectivas"
    assert dur_claim.evidence[1].document_sha256 == DOC_SHA_SYNTHETIC


def test_activity_evidence_preserved_in_activity_claims():
    """Activity claims preserve their SourceReference evidence in the evidence attribute."""
    act_ev = SourceReference(
        document_sha256=DOC_SHA_SYNTHETIC,
        page_number=2,
        excerpt="Discutir en plenaria las normas del aula",
    )
    activity = SessionActivity(
        activity_id="act_01_plenaria",
        title="Actividad 1: Plenaria",
        description="Discutir en plenaria las normas del aula.",
        order=1,
        evidence=[act_ev],
    )
    session = SessionPlan(
        session_id="s1",
        session_number=1,
        title="Sesión 1",
        project_title="Convivencia Escolar",
        pages=[2],
        layout_fidelity="verbatim_blocks",
        layout_notes="",
        fields={},
        activities=[activity],
        status=STATUS_SUPPORTED,
        review="pending",
    )

    dossier = _make_synthetic_dossier(sessions=[session])
    claims = compile_dossier_to_atomic_claims(dossier)

    rel_claim = next(
        c for c in claims
        if c.subject == "activity:act_01_plenaria"
        and c.predicate == PREDICATE_PERTENECE_A_SESION
    )
    assert len(rel_claim.evidence) == 1
    assert rel_claim.evidence[0].page_number == 2
    assert rel_claim.evidence[0].excerpt == "Discutir en plenaria las normas del aula"


# ==============================================================================
# 3. SEGURIDAD Y HASH: Mismatch descarta evidencia ajena
# ==============================================================================

def test_evidence_with_foreign_sha_is_discarded_from_atomic_claim():
    """Evidence with mismatched document SHA is excluded from claim.evidence and cannot back claim."""
    legit_ev = SourceReference(
        document_sha256=DOC_SHA_SYNTHETIC,
        page_number=1,
        excerpt="Proyecto Comunitario del Agua",
    )
    foreign_ev = SourceReference(
        document_sha256=FOREIGN_SHA_SYNTHETIC,
        page_number=2,
        excerpt="Texto de otro archivo PDF",
    )

    field_obj = InterpretedField(
        name="proyecto",
        value="Proyecto Comunitario del Agua",
        origin=ORIGIN_EXTRACTED,
        status=STATUS_SUPPORTED,
        evidence=[legit_ev, foreign_ev],
    )

    dossier = _make_synthetic_dossier(general_fields={"proyecto": field_obj})
    claims = compile_dossier_to_atomic_claims(dossier)
    proj_claim = next(c for c in claims if c.predicate == PREDICATE_PROYECTO)

    # Only legitimate SHA reference is retained
    assert len(proj_claim.evidence) == 1
    assert proj_claim.evidence[0].document_sha256 == DOC_SHA_SYNTHETIC
    assert proj_claim.page_number == 1


def test_field_with_only_foreign_evidence_becomes_candidate_without_backing():
    """Field with solely foreign SHA evidence has empty evidence and candidate state."""
    foreign_ev = SourceReference(
        document_sha256=FOREIGN_SHA_SYNTHETIC,
        page_number=1,
        excerpt="Texto no coincidente",
    )

    field_obj = InterpretedField(
        name="proyecto",
        value="Proyecto Ficticio",
        origin=ORIGIN_EXTRACTED,
        status=STATUS_SUPPORTED,
        evidence=[foreign_ev],
    )

    dossier = _make_synthetic_dossier(general_fields={"proyecto": field_obj})
    claims = compile_dossier_to_atomic_claims(dossier)
    proj_claim = next(c for c in claims if c.predicate == PREDICATE_PROYECTO)

    assert proj_claim.evidence == []
    assert proj_claim.page_number is None
    assert proj_claim.excerpt == ""
    assert proj_claim.state == CLAIM_STATE_CANDIDATE


# ==============================================================================
# 4. SERIALIZACIÓN: Roundtrip to_dict / from_dict y retrocompatibilidad
# ==============================================================================

def test_atomic_claim_roundtrip_serialization_with_multipage_evidence():
    """AtomicClaim with multiple evidence references roundtrips perfectly through dict and JSON."""
    ev1 = SourceReference(document_sha256=DOC_SHA_SYNTHETIC, page_number=1, excerpt="Primera parte")
    ev2 = SourceReference(document_sha256=DOC_SHA_SYNTHETIC, page_number=2, excerpt="Segunda parte")

    claim = AtomicClaim(
        claim_id="c_roundtrip_1234",
        claim_type=CLAIM_TYPE_FIELD,
        subject="document",
        predicate="duracion_proyecto",
        object_value="Dos semanas",
        source_doc_sha256=DOC_SHA_SYNTHETIC,
        page_number=1,
        excerpt="Primera parte",
        state=CLAIM_STATE_NEEDS_HUMAN_REVIEW,
        metadata={"unit_type": "project_review"},
        evidence=[ev1, ev2],
    )

    serialized = claim.to_dict()

    # Must be JSON-serializable
    json_str = json.dumps(serialized)
    loaded_dict = json.loads(json_str)

    restored = AtomicClaim.from_dict(loaded_dict)

    assert restored.claim_id == claim.claim_id
    assert restored.predicate == claim.predicate
    assert restored.object_value == claim.object_value
    assert restored.page_number == 1
    assert restored.excerpt == "Primera parte"
    assert restored.metadata == {"unit_type": "project_review"}

    assert len(restored.evidence) == 2
    assert isinstance(restored.evidence[0], SourceReference)
    assert isinstance(restored.evidence[1], SourceReference)
    assert restored.evidence[0].page_number == 1
    assert restored.evidence[0].excerpt == "Primera parte"
    assert restored.evidence[1].page_number == 2
    assert restored.evidence[1].excerpt == "Segunda parte"


def test_atomic_claim_from_dict_backward_compatible_with_legacy_payload():
    """A legacy dict without the `evidence` key parses seamlessly and synthesizes evidence."""
    legacy_payload = {
        "claim_id": "c_legacy_9999",
        "claim_type": "field",
        "subject": "document",
        "predicate": "proyecto",
        "object_value": "Proyecto de Lectura",
        "source_doc_sha256": DOC_SHA_SYNTHETIC,
        "page_number": 3,
        "excerpt": "Cita legacy en pagina 3",
        "state": "backed",
        "extraction_method": "v0",
        "extraction_version": "1.0",
        "dependencies": [],
        "alternatives": [],
        "metadata": {},
    }

    claim = AtomicClaim.from_dict(legacy_payload)

    assert claim.claim_id == "c_legacy_9999"
    assert claim.page_number == 3
    assert claim.excerpt == "Cita legacy en pagina 3"

    # Synthesized from legacy page_number and excerpt
    assert len(claim.evidence) == 1
    assert isinstance(claim.evidence[0], SourceReference)
    assert claim.evidence[0].page_number == 3
    assert claim.evidence[0].excerpt == "Cita legacy en pagina 3"
    assert claim.evidence[0].document_sha256 == DOC_SHA_SYNTHETIC


def test_atomic_claim_from_dict_with_empty_or_none_page_number():
    """A payload without page_number yields an empty evidence list."""
    payload = {
        "claim_id": "c_no_page_0000",
        "claim_type": "field",
        "subject": "document",
        "predicate": "duracion",
        "object_value": "",
        "state": "insufficient_evidence",
    }
    claim = AtomicClaim.from_dict(payload)
    assert claim.evidence == []
    assert claim.page_number is None


def test_atomic_claim_from_dict_legacy_with_explicit_none_values():
    """A legacy dict with explicit None for source_doc_sha256 and excerpt does not coerce to literal 'None'."""
    legacy_payload = {
        "claim_id": "c_legacy_nulls",
        "claim_type": "field",
        "subject": "document",
        "predicate": "proyecto",
        "object_value": "Proyecto de Lectura",
        "source_doc_sha256": None,
        "page_number": 3,
        "excerpt": None,
        "state": "candidate",
    }
    claim = AtomicClaim.from_dict(legacy_payload)

    # Invariant (Slice C, Contrato 3): None must NOT be converted to the literal string "None"
    assert claim.source_doc_sha256 == ""
    assert claim.source_doc_sha256 != "None"
    assert claim.excerpt == ""
    assert claim.excerpt != "None"

    assert len(claim.evidence) == 1
    assert isinstance(claim.evidence[0], SourceReference)
    assert claim.evidence[0].document_sha256 == ""
    assert claim.evidence[0].document_sha256 != "None"
    assert claim.evidence[0].excerpt == ""
    assert claim.evidence[0].excerpt != "None"
    assert claim.evidence[0].page_number == 3
