"""tests/test_t124_atomic_claims.py
Pruebas del contrato de afirmaciones atómicas y compilador curricular canónico (#124).
"""

import copy
import pytest

from curriculum.claims import (
    ACTIVITY_STATUS_IDENTIFIED,
    CLAIM_STATE_BACKED,
    CLAIM_STATE_CANDIDATE,
    CLAIM_STATE_CONTRADICTED,
    CLAIM_STATE_INSUFFICIENT_EVIDENCE,
    CLAIM_STATE_NEEDS_HUMAN_REVIEW,
    CLAIM_TYPE_ENTITY,
    CLAIM_TYPE_FIELD,
    CLAIM_TYPE_RELATION,
    PREDICATE_CAMPO_FORMATIVO,
    PREDICATE_DURACION,
    PREDICATE_ESTADO_ACTIVIDAD,
    PREDICATE_PERTENECE_A_SESION,
    PREDICATE_PROYECTO,
    PREDICATE_REQUIERE_ANEXO,
    PREDICATE_TEMA,
    AtomicClaim,
    compile_dossier_to_atomic_claims,
    make_claim_id,
)
from curriculum.source_interpreter import (
    AnnexReference,
    ORIGIN_EXTRACTED,
    ORIGIN_PROPOSED,
    ORIGIN_TEACHER_ENTERED,
    STATUS_CONFLICTING,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    ImportDossier,
    InterpretedField,
    SessionActivity,
    SessionPlan,
    SourceReference,
)


def _make_field(
    name: str,
    value: str,
    *,
    origin: str = ORIGIN_EXTRACTED,
    status: str = STATUS_SUPPORTED,
    page: int = 1,
    doc_sha: str = "sha_test_123",
) -> InterpretedField:
    """Helper sintético para construir un InterpretedField de prueba."""
    ev = [SourceReference(document_sha256=doc_sha, page_number=page, excerpt=value)] if page else []
    return InterpretedField(
        name=name,
        value=value,
        origin=origin,
        status=status,
        evidence=ev,
    )


def _make_dossier(
    doc_sha: str,
    general_fields: dict | None = None,
    sessions: list | None = None,
) -> ImportDossier:
    """Helper sintético que asegura que source_name y page_count siempre existan."""
    return ImportDossier(
        source_sha256=doc_sha,
        source_name="test_planeacion.pdf",
        page_count=2,
        general_fields=general_fields or {},
        sessions=sessions or [],
    )


@pytest.mark.django_db
class TestAtomicClaimsContract124:
    """Verifica los 5 criterios GREEN del Issue #124."""

    # --- GREEN 1: Jerarquía completa y ontología NEM ---
    def test_compile_full_hierarchy_and_nem_ontology(self):
        """Fixtures cubren actividad->sesión, anexo->actividad, campo formativo, tema y duración."""
        doc_sha = "doc_sha_nem_456"

        # 1. Campos generales
        general_fields = {
            "proyecto": _make_field("proyecto", "Álbum de mi comunidad", page=1, doc_sha=doc_sha),
            "campos_formativos": _make_field("campos_formativos", "Lenguajes", page=1, doc_sha=doc_sha),
            "escenario": _make_field("escenario", "Comunitario", page=1, doc_sha=doc_sha),
        }

        # 2. Actividad con anexo
        activity = SessionActivity(
            activity_id="act_01",
            title="Elaborar cartel",
            order=1,
            annex_ids=["anexo_4"],
            evidence=[SourceReference(document_sha256=doc_sha, page_number=2, excerpt="Elaborar cartel")],
            annex_evidence={"anexo_4": [SourceReference(
                document_sha256=doc_sha, page_number=2, excerpt="Consultar el anexo 4 para elaborar el cartel.",
            )]},
        )

        # 3. Sesión de clase
        session = SessionPlan(
            session_id="s1",
            session_number=1,
            title="Clase de inicio",
            pages=[2],
            fields={
                "tema": _make_field("tema", "Cuidado del agua", page=2, doc_sha=doc_sha),
                "duracion": _make_field("duracion", "50", page=2, doc_sha=doc_sha),
            },
            activities=[activity],
            annex_references=[AnnexReference(annex_number="4", raw_mention="anexo 4", reference_id="anexo_4")],
        )

        dossier = _make_dossier(doc_sha, general_fields=general_fields, sessions=[session])

        claims = compile_dossier_to_atomic_claims(dossier)
        assert len(claims) > 0

        # Verificar presencia de afirmaciones clave
        predicates = {c.predicate for c in claims}
        assert PREDICATE_PROYECTO in predicates
        assert PREDICATE_CAMPO_FORMATIVO in predicates
        assert PREDICATE_TEMA in predicates
        assert PREDICATE_DURACION in predicates
        assert PREDICATE_PERTENECE_A_SESION in predicates
        assert PREDICATE_REQUIERE_ANEXO in predicates

        # Verificar la relación actividad -> sesión
        act_rel = next(c for c in claims if c.predicate == PREDICATE_PERTENECE_A_SESION)
        assert act_rel.subject == "activity:act_01"
        assert act_rel.object_value == "session:s1"
        assert act_rel.claim_type == CLAIM_TYPE_RELATION

        # Verificar la relación anexo -> actividad
        annex_rel = next(c for c in claims if c.predicate == PREDICATE_REQUIERE_ANEXO)
        assert annex_rel.subject == "activity:act_01"
        assert annex_rel.object_value == "anexo_4"

    # --- GREEN 2: Candado de derivaciones e IA ---
    def test_derived_interpretation_never_auto_backed(self):
        """Un fragmento fuente localizado NO confirma automáticamente una interpretación propuesta."""
        doc_sha = "doc_sha_789"

        # Campo con origen propuesto (inferido por IA/modelo)
        inferred_field = _make_field(
            "campos_formativos",
            "Lenguajes (inferido)",
            origin=ORIGIN_PROPOSED,
            status=STATUS_SUPPORTED,
            page=1,
            doc_sha=doc_sha,
        )

        dossier = _make_dossier(doc_sha, general_fields={"campos_formativos": inferred_field})

        claims = compile_dossier_to_atomic_claims(dossier)
        assert len(claims) == 1
        claim = claims[0]

        # Invariante: Aunque la página física esté identificada, NO puede ser backed
        assert claim.state != CLAIM_STATE_BACKED
        assert claim.state == CLAIM_STATE_NEEDS_HUMAN_REVIEW

    def test_teacher_entry_with_page_is_not_source_backing(self):
        doc_sha = "sha_teacher_entry"
        field = _make_field("proyecto", "Proyecto corregido", origin=ORIGIN_TEACHER_ENTERED, doc_sha=doc_sha)
        claim = compile_dossier_to_atomic_claims(
            _make_dossier(doc_sha, general_fields={"proyecto": field})
        )[0]

        assert claim.state == CLAIM_STATE_CANDIDATE
        assert claim.page_number == 1

    def test_mismatched_source_hash_cannot_back_claim(self):
        field = _make_field("proyecto", "Proyecto ajeno", doc_sha="otro_documento")
        claim = compile_dossier_to_atomic_claims(
            _make_dossier("documento_actual", general_fields={"proyecto": field})
        )[0]

        assert claim.state == CLAIM_STATE_CANDIDATE
        assert claim.page_number is None
        assert claim.excerpt == ""

    def test_source_region_is_preserved_in_claim(self):
        doc_sha = "sha_region"
        field = _make_field("proyecto", "Proyecto localizado", doc_sha=doc_sha)
        field.evidence[0].region = {"x0": 0.1, "y0": 0.2, "x1": 0.7, "y1": 0.4}
        claim = compile_dossier_to_atomic_claims(
            _make_dossier(doc_sha, general_fields={"proyecto": field})
        )[0]

        assert claim.state == CLAIM_STATE_BACKED
        assert claim.region == field.evidence[0].region

    def test_activity_from_another_document_is_not_backed(self):
        activity = SessionActivity(
            activity_id="act_foreign",
            title="Actividad ajena",
            order=1,
            evidence=[SourceReference(document_sha256="otro_documento", page_number=2, excerpt="Actividad ajena")],
        )
        session = SessionPlan(session_id="s1", session_number=1, title="Sesión", pages=[2], activities=[activity])
        claims = compile_dossier_to_atomic_claims(_make_dossier("documento_actual", sessions=[session]))

        activity_claims = [claim for claim in claims if claim.subject == "activity:act_foreign"]
        assert activity_claims
        assert all(claim.state != CLAIM_STATE_BACKED for claim in activity_claims)
        assert all(claim.page_number is None for claim in activity_claims)

    # --- GREEN 3: Separación de ausencia y contradicción ---
    def test_absence_and_contradiction_remain_distinct(self):
        """Ausencia y contradicción permanecen formalmente separadas."""
        doc_sha = "doc_sha_abs_vs_conf"

        missing_field = _make_field("duracion", "", status=STATUS_MISSING, page=None)
        conflicting_field = _make_field("inicio", "Texto contradictorio", status=STATUS_CONFLICTING, page=1)

        dossier = _make_dossier(
            doc_sha,
            sessions=[
                SessionPlan(
                    session_id="s1",
                    session_number=1,
                    title="Sesión 1",
                    pages=[1],
                    fields={"duracion": missing_field, "inicio": conflicting_field},
                )
            ],
        )

        claims = compile_dossier_to_atomic_claims(dossier)

        duracion_claim = next(c for c in claims if c.predicate == PREDICATE_DURACION)
        inicio_claim = next(c for c in claims if c.predicate == "inicio")

        assert duracion_claim.state == CLAIM_STATE_INSUFFICIENT_EVIDENCE
        assert inicio_claim.state == CLAIM_STATE_CONTRADICTED
        assert duracion_claim.state != inicio_claim.state

    # --- GREEN 4: Determinismo y serialización roundtrip ---
    def test_deterministic_id_and_roundtrip_serialization(self):
        """Serialización versionada, determinista y reversible."""
        doc_sha = "sha_deterministic"
        field_obj = _make_field("proyecto", "Proyecto Comunitario", page=1, doc_sha=doc_sha)

        dossier = _make_dossier(doc_sha, general_fields={"proyecto": field_obj})

        # Compilar dos veces produce exactamente los mismos IDs en el mismo orden
        claims_run_1 = compile_dossier_to_atomic_claims(dossier)
        claims_run_2 = compile_dossier_to_atomic_claims(dossier)

        assert len(claims_run_1) == len(claims_run_2)
        assert [c.claim_id for c in claims_run_1] == [c.claim_id for c in claims_run_2]

        # Serialización roundtrip: AtomicClaim -> dict -> AtomicClaim
        claim = claims_run_1[0]
        as_dict = claim.to_dict()
        restored = AtomicClaim.from_dict(as_dict)

        assert restored.claim_id == claim.claim_id
        assert restored.predicate == claim.predicate
        assert restored.object_value == claim.object_value
        assert restored.state == claim.state

    # --- GREEN 5: Función pura sin mutaciones a BD ---
    def test_compiler_is_pure_and_has_no_db_side_effects(self):
        """El compilador no publica, activa ni modifica progreso curricular."""
        from curriculum.models import PublishedPackageSnapshot, CurriculumProgress

        doc_sha = "sha_pure_test"
        field_obj = _make_field("proyecto", "Proyecto Seguro", page=1, doc_sha=doc_sha)

        dossier = _make_dossier(doc_sha, general_fields={"proyecto": field_obj})

        snapshot_count_before = PublishedPackageSnapshot.objects.count()
        progress_count_before = CurriculumProgress.objects.count()

        # Ejecución del compilador
        claims = compile_dossier_to_atomic_claims(dossier)
        assert len(claims) > 0

        # Invariante: CERO escrituras en tablas curriculares productivas
        assert PublishedPackageSnapshot.objects.count() == snapshot_count_before
        assert CurriculumProgress.objects.count() == progress_count_before

    # --- GREEN 6: Fragmento de planeación real (1° Primaria - El Nombrario) ---
    def test_compile_real_planeacion_fragment_nombrario_1ro(self):
        """Compila un fragmento de una planeación real (Planeacion_1ro_Primaria_ABPC_Nombrario.pdf)."""
        from curriculum.claims import (
            PREDICATE_ESCENARIO,
            PREDICATE_METODOLOGIA,
            PREDICATE_EJES_ARTICULADORES,
        )

        doc_sha = "sha_nombrario_real_1ro"

        general_fields = {
            "proyecto": _make_field(
                "proyecto",
                "EL NOMBRARIO DEL GRUPO: IDENTIDAD Y LECTOESCRITURA",
                page=1,
                doc_sha=doc_sha,
            ),
            "metodologia": _make_field(
                "metodologia",
                "Aprendizaje Basado en Proyectos Comunitarios (ABPC - 11 momentos)",
                page=1,
                doc_sha=doc_sha,
            ),
            "escenario": _make_field("escenario", "Aula", page=1, doc_sha=doc_sha),
            "campos_formativos": _make_field("campos_formativos", "Lenguajes", page=1, doc_sha=doc_sha),
            "ejes_articuladores": _make_field(
                "ejes_articuladores",
                "Inclusión, Apropiación de las culturas",
                page=1,
                doc_sha=doc_sha,
            ),
        }

        act1 = SessionActivity(
            activity_id="act_gafetes_01",
            title="Identificación de su nombre en gafetes de bienvenida y tarjetas con fotos",
            order=1,
            evidence=[
                SourceReference(
                    document_sha256=doc_sha,
                    page_number=1,
                    excerpt="Identificación de su nombre en gafetes de bienvenida y tarjetas con fotos",
                )
            ],
        )
        act2 = SessionActivity(
            activity_id="act_plastilina_02",
            title="Trazado de letras iniciales con plastilina, arena y pintura dactilar",
            order=2,
            evidence=[
                SourceReference(
                    document_sha256=doc_sha,
                    page_number=1,
                    excerpt="Trazado de letras iniciales con plastilina, arena y pintura dactilar",
                )
            ],
        )

        session = SessionPlan(
            session_id="s1_nombrario",
            session_number=1,
            title="Fase 1: Momentos 1 a 3 (Identificación, Recuperación, Planificación)",
            pages=[1],
            fields={
                "tema": _make_field("tema", "Identidad y lectoescritura", page=1, doc_sha=doc_sha),
                "proposito": _make_field(
                    "proposito",
                    "Escribe su nombre y lo compara con los nombres de sus compañeros. "
                    "Identifica la letra inicial y final de su nombre.",
                    page=1,
                    doc_sha=doc_sha,
                ),
                "duracion": _make_field("duracion", "50", page=1, doc_sha=doc_sha),
            },
            activities=[act1, act2],
        )

        dossier = _make_dossier(
            doc_sha,
            general_fields=general_fields,
            sessions=[session],
        )

        claims = compile_dossier_to_atomic_claims(dossier)
        assert len(claims) >= 8

        # Verificar afirmaciones extraídas de la planeación real
        claims_by_pred = {c.predicate: c for c in claims}

        assert claims_by_pred[PREDICATE_PROYECTO].object_value == "EL NOMBRARIO DEL GRUPO: IDENTIDAD Y LECTOESCRITURA"
        assert claims_by_pred[PREDICATE_METODOLOGIA].object_value == "Aprendizaje Basado en Proyectos Comunitarios (ABPC - 11 momentos)"
        assert claims_by_pred[PREDICATE_ESCENARIO].object_value == "Aula"
        assert claims_by_pred[PREDICATE_CAMPO_FORMATIVO].object_value == "Lenguajes"
        assert claims_by_pred[PREDICATE_EJES_ARTICULADORES].object_value == "Inclusión, Apropiación de las culturas"

        # Verificar que las actividades queden asociadas a la sesión real
        act_claims = [c for c in claims if c.predicate == PREDICATE_PERTENECE_A_SESION]
        assert len(act_claims) == 2
        assert {c.subject for c in act_claims} == {"activity:act_gafetes_01", "activity:act_plastilina_02"}
        assert all(c.object_value == "session:s1_nombrario" for c in act_claims)
        assert all(c.state == CLAIM_STATE_BACKED for c in act_claims)
