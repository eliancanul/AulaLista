from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from curriculum.source_interpreter import (
    ORIGIN_EXTRACTED,
    ORIGIN_PROPOSED,
    STATUS_CONFLICTING,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    ImportDossier,
    InterpretedField,
    SessionActivity,
    SessionPlan,
)

# --- Tipos de afirmación curricular ---
CLAIM_TYPE_FIELD = "field"
CLAIM_TYPE_ENTITY = "entity"
CLAIM_TYPE_RELATION = "relation"

# --- Estados ternarios y de gobernanza ---
CLAIM_STATE_CANDIDATE = "candidate"
CLAIM_STATE_BACKED = "backed"
CLAIM_STATE_CONTRADICTED = "contradicted"
CLAIM_STATE_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
CLAIM_STATE_NEEDS_HUMAN_REVIEW = "needs_human_review"

# --- Predicados canónicos NEM (Nueva Escuela Mexicana) ---
PREDICATE_PROYECTO = "proyecto"
PREDICATE_CAMPO_FORMATIVO = "campo_formativo"
PREDICATE_ESCENARIO = "escenario"                 # Aula | Escolar | Comunitario
PREDICATE_EJES_ARTICULADORES = "ejes_articuladores" # Inclusión, Pensamiento crítico, etc.
PREDICATE_METODOLOGIA = "metodologia"             # ABPC | STEAM | ABP | AS
PREDICATE_TEMA = "tema"
PREDICATE_OBJETIVO = "objetivo"                   # Propósito / PDA
PREDICATE_DURACION = "duracion_minutos"
PREDICATE_PERTENECE_A_SESION = "pertenece_a_sesion"
PREDICATE_REQUIERE_ANEXO = "requiere_anexo"
PREDICATE_ESTADO_ACTIVIDAD = "estado_actividad"

# --- Estados de actividad y recursos (Acuerdo hilo 01a0c549) ---
ACTIVITY_STATUS_IDENTIFIED = "actividad_identificada"
ACTIVITY_STATUS_RESOURCE_MISSING = "actividad_identificada_con_recurso_faltante"
ACTIVITY_STATUS_NO_ACTIVITY = "sin_actividad_identificada"
ACTIVITY_STATUS_PENDING = "pendiente_de_determinar"


def make_claim_id(subject: str, predicate: str, object_value: Any, doc_sha: str = "") -> str:
    """Genera un identificador único determinista para una afirmación."""
    raw = f"{doc_sha}:{subject}:{predicate}:{str(object_value)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class AtomicClaim:
    """Representa una afirmación curricular atómica verificable."""
    claim_id: str                      # Hash determinista de 16 caracteres
    claim_type: str                    # CLAIM_TYPE_FIELD | CLAIM_TYPE_ENTITY | CLAIM_TYPE_RELATION
    subject: str                       # ej: "document", "session:s1", "activity:act_01"
    predicate: str                     # ej: "campo_formativo", "escenario", "pertenece_a_sesion"
    object_value: Any                  # ej: "Lenguajes", "Comunitario", 45
    source_doc_sha256: str = ""        # Hash del PDF origen
    page_number: int | None = None     # Página física
    region: dict | None = None         # Bbox o coordenadas si aplica
    excerpt: str = ""                  # Fragmento de texto literal
    extraction_method: str = "v0"      # Identificador del método
    extraction_version: str = "1.0"
    state: str = CLAIM_STATE_CANDIDATE # candidate | backed | contradicted | insufficient_evidence | needs_human_review
    confidence: float | None = None    # Confianza calibrada del tribunal (0.0 a 1.0)
    dependencies: list[str] = field(default_factory=list) # IDs de afirmaciones padre
    alternatives: list[Any] = field(default_factory=list) # Alternativas en caso de ambigüedad
    metadata: dict = field(default_factory=dict)          # Metadatos adicionales (ej: notas para creación futura)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> AtomicClaim:
        d = dict(data)
        return cls(**d)


def _map_field_to_claim(
    subject: str,
    predicate: str,
    interpreted_field: InterpretedField,
    doc_sha: str,
    dependencies: list[str] | None = None,
) -> AtomicClaim:
    """Mapea un InterpretedField a un AtomicClaim respetando las reglas de gobernanza.

    Aplica las invariantes del Issue #124 y #118:
    - Conflicto explícito -> contradicted
    - Dato faltante o vacío -> insufficient_evidence
    - Origen propuesto/inferido -> needs_human_review (NUNCA backed)
    - Extracción literal con evidencia del mismo documento -> backed
    """
    val = interpreted_field.value
    stat = interpreted_field.status
    orig = interpreted_field.origin

    # 1. Extraer página y texto de la evidencia física
    page = None
    excerpt = ""
    region = None
    source_matches = False
    if interpreted_field.evidence:
        first_ev = interpreted_field.evidence[0]
        page = getattr(first_ev, "page_number", None)
        excerpt = getattr(first_ev, "excerpt", "")
        region = getattr(first_ev, "region", None)
        source_matches = getattr(first_ev, "document_sha256", None) == doc_sha and bool(doc_sha)
        if not source_matches:
            page, excerpt, region = None, "", None

    # 2. Evaluar el estado según las reglas de negocio
    if stat == STATUS_CONFLICTING:
        initial_state = CLAIM_STATE_CONTRADICTED
    elif stat == STATUS_MISSING or not str(val).strip():
        initial_state = CLAIM_STATE_INSUFFICIENT_EVIDENCE
    elif orig in (ORIGIN_PROPOSED, "inferred"):
        # REGLA DE ORO: Lo deducido por IA jamás se auto-aprueba
        initial_state = CLAIM_STATE_NEEDS_HUMAN_REVIEW
    elif stat == STATUS_SUPPORTED and orig == ORIGIN_EXTRACTED and page is not None and excerpt.strip():
        initial_state = CLAIM_STATE_BACKED
    else:
        initial_state = CLAIM_STATE_CANDIDATE

    cid = make_claim_id(subject, predicate, val, doc_sha)
    return AtomicClaim(
        claim_id=cid,
        claim_type=CLAIM_TYPE_FIELD,
        subject=subject,
        predicate=predicate,
        object_value=val,
        source_doc_sha256=doc_sha,
        page_number=page,
        region=region,
        excerpt=excerpt,
        extraction_method="source_interpreter_v0",
        state=initial_state,
        dependencies=dependencies or [],
    )


def _map_activity_to_claims(
    activity: SessionActivity,
    session_subject: str,
    doc_sha: str,
) -> list[AtomicClaim]:
    """Traduce una SessionActivity a afirmaciones de relación y estado de recursos.

    Aplica las distinciones del Hilo 01a0c549:
    - Relación de pertenencia actividad -> sesión.
    - Detección de anexos y distinción de 'recurso faltante'.
    """
    claims: list[AtomicClaim] = []
    act_subject = f"activity:{activity.activity_id}"
    act_page = None
    act_excerpt = ""
    act_region = None
    if getattr(activity, "evidence", None):
        first_ev = activity.evidence[0]
        if doc_sha and getattr(first_ev, "document_sha256", None) == doc_sha:
            act_page = getattr(first_ev, "page_number", None)
            act_excerpt = getattr(first_ev, "excerpt", "")
            act_region = getattr(first_ev, "region", None)
    has_act_evidence = act_page is not None and bool(act_excerpt.strip())

    # 1. Relación estructural: La actividad pertenece a la sesión
    cid_rel = make_claim_id(act_subject, PREDICATE_PERTENECE_A_SESION, session_subject, doc_sha)
    claims.append(
        AtomicClaim(
            claim_id=cid_rel,
            claim_type=CLAIM_TYPE_RELATION,
            subject=act_subject,
            predicate=PREDICATE_PERTENECE_A_SESION,
            object_value=session_subject,
            source_doc_sha256=doc_sha,
            page_number=act_page,
            region=act_region,
            excerpt=act_excerpt,
            extraction_method="source_interpreter_v0",
            state=CLAIM_STATE_BACKED if has_act_evidence else CLAIM_STATE_CANDIDATE,
        )
    )

    # 2. Relaciones con Anexos requeridos
    annex_ids = getattr(activity, "annex_ids", []) or []
    for annex_id in annex_ids:
        cid_annex = make_claim_id(act_subject, PREDICATE_REQUIERE_ANEXO, annex_id, doc_sha)
        claims.append(
            AtomicClaim(
                claim_id=cid_annex,
                claim_type=CLAIM_TYPE_RELATION,
                subject=act_subject,
                predicate=PREDICATE_REQUIERE_ANEXO,
                object_value=annex_id,
                source_doc_sha256=doc_sha,
                page_number=act_page,
                extraction_method="source_interpreter_v0",
                state=CLAIM_STATE_CANDIDATE,
            )
        )

    # 3. Estado operativo de la actividad (Acuerdo Hilo 01a0c549)
    status_value = ACTIVITY_STATUS_IDENTIFIED
    cid_status = make_claim_id(act_subject, PREDICATE_ESTADO_ACTIVIDAD, status_value, doc_sha)
    claims.append(
        AtomicClaim(
            claim_id=cid_status,
            claim_type=CLAIM_TYPE_FIELD,
            subject=act_subject,
            predicate=PREDICATE_ESTADO_ACTIVIDAD,
            object_value=status_value,
            source_doc_sha256=doc_sha,
            page_number=act_page,
            region=act_region,
            extraction_method="source_interpreter_v0",
            state=CLAIM_STATE_BACKED if has_act_evidence else CLAIM_STATE_CANDIDATE,
        )
    )

    return claims


def compile_dossier_to_atomic_claims(dossier: ImportDossier) -> list[AtomicClaim]:
    """Compilador canónico puro: traduce un ImportDossier a una lista determinista de AtomicClaims.

    Invariantes arquitectónicas (#124):
    - Función pura: CERO escrituras a base de datos y sin efectos secundarios.
    - No aprueba, activa ni publica paquetes curriculares.
    - Orden determinista: Documento general -> Sesiones -> Actividades y relaciones.
    - Respeta la ontología canónica de la NEM.
    """
    claims: list[AtomicClaim] = []
    doc_sha = dossier.source_sha256 or ""

    # 1. Campos Generales del Documento
    general_predicates = {
        "proyecto": PREDICATE_PROYECTO,
        "campos_formativos": PREDICATE_CAMPO_FORMATIVO,
        "escenario": PREDICATE_ESCENARIO,
        "ejes_articuladores": PREDICATE_EJES_ARTICULADORES,
        "metodologia": PREDICATE_METODOLOGIA,
        "proposito": PREDICATE_OBJETIVO,
        "finalidad": PREDICATE_OBJETIVO,
    }

    for raw_name, field_obj in getattr(dossier, "general_fields", {}).items():
        predicate = general_predicates.get(raw_name, raw_name)
        claims.append(_map_field_to_claim("document", predicate, field_obj, doc_sha))

    # 2. Sesiones de clase
    for session in getattr(dossier, "sessions", []):
        session_subject = f"session:{session.session_id}"
        sess_page = session.pages[0] if getattr(session, "pages", None) else None

        # Afirmación de existencia de la sesión (entity)
        cid_sess = make_claim_id(session_subject, "es_entidad", "session", doc_sha)
        claims.append(
            AtomicClaim(
                claim_id=cid_sess,
                claim_type=CLAIM_TYPE_ENTITY,
                subject=session_subject,
                predicate="es_entidad",
                object_value="session",
                source_doc_sha256=doc_sha,
                page_number=sess_page,
                extraction_method="source_interpreter_v0",
                state=CLAIM_STATE_BACKED if sess_page is not None else CLAIM_STATE_CANDIDATE,
            )
        )

        # Campos de la sesión (inicio, desarrollo, cierre, tema, duración)
        session_predicates = {
            "tema": PREDICATE_TEMA,
            "duracion": PREDICATE_DURACION,
            "inicio": "inicio",
            "desarrollo": "desarrollo",
            "cierre": "cierre",
        }
        for raw_name, field_obj in getattr(session, "fields", {}).items():
            predicate = session_predicates.get(raw_name, raw_name)
            claims.append(_map_field_to_claim(session_subject, predicate, field_obj, doc_sha))

        # Actividades dentro de esta sesión
        for act in getattr(session, "activities", []):
            claims.extend(_map_activity_to_claims(act, session_subject, doc_sha))

    return claims
