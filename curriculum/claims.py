from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from curriculum.source_interpreter import (
    ORIGIN_EXTRACTED,
    ORIGIN_PROPOSED,
    STATUS_AMBIGUOUS,
    STATUS_CONFLICTING,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    ImportDossier,
    InterpretedField,
    SessionActivity,
    SessionPlan,
    SourceReference,
)

# --- Tipos de afirmación curricular ---
CLAIM_TYPE_FIELD = "field"
CLAIM_TYPE_ENTITY = "entity"
CLAIM_TYPE_RELATION = "relation"

# --- Tipos de entidad curricular ---
ENTITY_TYPE_SESSION = "session"
ENTITY_TYPE_PROJECT_REVIEW = "project_review"

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
PREDICATE_DURACION_PROYECTO = "duracion_proyecto"
PREDICATE_PERTENECE_A_SESION = "pertenece_a_sesion"
PREDICATE_PERTENECE_A_UNIDAD_REVISION = "pertenece_a_unidad_revision"
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
    page_number: int | None = None     # Página física (legacy primario)
    region: dict | None = None         # Bbox o coordenadas si aplica
    excerpt: str = ""                  # Fragmento de texto literal (legacy primario)
    extraction_method: str = "v0"      # Identificador del método
    extraction_version: str = "1.0"
    state: str = CLAIM_STATE_CANDIDATE # candidate | backed | contradicted | insufficient_evidence | needs_human_review
    confidence: float | None = None    # Confianza calibrada del tribunal (0.0 a 1.0)
    dependencies: list[str] = field(default_factory=list) # IDs de afirmaciones padre
    alternatives: list[Any] = field(default_factory=list) # Alternativas en caso de ambigüedad
    metadata: dict = field(default_factory=dict)          # Metadatos adicionales (ej: notas para creación futura)
    evidence: list[SourceReference] = field(default_factory=list) # Citas físicas ordenadas (#128)

    def to_dict(self) -> dict:
        d = asdict(self)
        if "evidence" in d and isinstance(d["evidence"], list):
            d["evidence"] = [
                ev.to_dict() if hasattr(ev, "to_dict") else ev
                for ev in self.evidence
            ]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> AtomicClaim:
        d = dict(data)

        # Evitar convertir None explícito en la cadena literal "None"
        if d.get("source_doc_sha256") is None:
            d["source_doc_sha256"] = ""
        else:
            d["source_doc_sha256"] = str(d["source_doc_sha256"])

        if d.get("excerpt") is None:
            d["excerpt"] = ""
        else:
            d["excerpt"] = str(d["excerpt"])

        raw_evidence = d.get("evidence")
        if raw_evidence is not None and isinstance(raw_evidence, list):
            parsed = []
            for ev in raw_evidence:
                if isinstance(ev, SourceReference):
                    parsed.append(ev)
                elif isinstance(ev, dict):
                    parsed.append(SourceReference.from_dict(ev))
            d["evidence"] = parsed
        elif raw_evidence is None and d.get("page_number") is not None:
            # Retrocompatibilidad: reconstruye cita legacy si falta el campo evidence
            d["evidence"] = [
                SourceReference(
                    document_sha256=d["source_doc_sha256"],
                    page_number=int(d["page_number"]),
                    excerpt=d["excerpt"],
                    region=d.get("region"),
                )
            ]
        else:
            d["evidence"] = []
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
    evidence_refs: list[SourceReference] = []

    if interpreted_field.evidence:
        for ev in interpreted_field.evidence:
            if isinstance(ev, SourceReference):
                ev_ref = ev
            elif isinstance(ev, dict):
                ev_ref = SourceReference.from_dict(ev)
            else:
                continue
            ev_sha = getattr(ev_ref, "document_sha256", None) or ""
            if doc_sha and ev_sha == doc_sha:
                evidence_refs.append(ev_ref)

        if evidence_refs:
            source_matches = True
            first_ev = evidence_refs[0]
            page = getattr(first_ev, "page_number", None)
            excerpt = getattr(first_ev, "excerpt", "")
            region = getattr(first_ev, "region", None)

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
        evidence=evidence_refs,
    )


def _map_activity_to_claims(
    activity: SessionActivity,
    session_subject: str,
    doc_sha: str = "",
    is_project_review: bool = False,
) -> list[AtomicClaim]:
    """Traduce una SessionActivity a afirmaciones de relación y estado de recursos.

    Aplica las distinciones del Hilo 01a0c549:
    - Relación de pertenencia actividad -> sesión o unidad de revisión.
    - Detección de anexos y distinción de 'recurso faltante'.
    """
    claims: list[AtomicClaim] = []
    act_subject = f"activity:{activity.activity_id}"
    act_page = None
    act_excerpt = ""
    act_region = None
    act_evidence_refs: list[SourceReference] = []

    if getattr(activity, "evidence", None):
        for ev in activity.evidence:
            if isinstance(ev, SourceReference):
                ev_ref = ev
            elif isinstance(ev, dict):
                ev_ref = SourceReference.from_dict(ev)
            else:
                continue
            ev_sha = getattr(ev_ref, "document_sha256", None) or ""
            if doc_sha and ev_sha == doc_sha:
                act_evidence_refs.append(ev_ref)

        if act_evidence_refs:
            first_ev = act_evidence_refs[0]
            act_page = getattr(first_ev, "page_number", None)
            act_excerpt = getattr(first_ev, "excerpt", "")
            act_region = getattr(first_ev, "region", None)

    has_act_evidence = act_page is not None and bool(act_excerpt.strip())

    # 1. Relación estructural: La actividad pertenece a la sesión o unidad de revisión
    is_review_unit = (
        is_project_review
        or session_subject.startswith(f"{ENTITY_TYPE_PROJECT_REVIEW}:")
        or session_subject.endswith("_project_review")
        or "project_review" in session_subject
    )
    if is_review_unit:
        rel_predicate = PREDICATE_PERTENECE_A_UNIDAD_REVISION
        rel_state = CLAIM_STATE_NEEDS_HUMAN_REVIEW
        rel_metadata = {
            "unit_type": ENTITY_TYPE_PROJECT_REVIEW,
            "reason": (
                "Relación a unidad sintética de revisión de proyecto sin sesiones explícitas; "
                "no constituye pertenencia a una sesión de clase respaldada documentalmente y requiere validación docente."
            ),
        }
    else:
        rel_predicate = PREDICATE_PERTENECE_A_SESION
        if has_act_evidence:
            rel_state = CLAIM_STATE_BACKED
            rel_metadata = {}
        else:
            rel_state = CLAIM_STATE_CANDIDATE
            rel_metadata = {}

    cid_rel = make_claim_id(act_subject, rel_predicate, session_subject, doc_sha)

    claims.append(
        AtomicClaim(
            claim_id=cid_rel,
            claim_type=CLAIM_TYPE_RELATION,
            subject=act_subject,
            predicate=rel_predicate,
            object_value=session_subject,
            source_doc_sha256=doc_sha,
            page_number=act_page,
            region=act_region,
            excerpt=act_excerpt,
            extraction_method="source_interpreter_v0",
            state=rel_state,
            metadata=rel_metadata,
            evidence=act_evidence_refs,
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
                evidence=act_evidence_refs,
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
            evidence=act_evidence_refs,
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
        "escenario_proyecto": PREDICATE_ESCENARIO,
        "ejes_articuladores": PREDICATE_EJES_ARTICULADORES,
        "metodologia": PREDICATE_METODOLOGIA,
        "proposito": PREDICATE_OBJETIVO,
        "finalidad": PREDICATE_OBJETIVO,
        "duracion_proyecto": PREDICATE_DURACION_PROYECTO,
    }

    for raw_name, field_obj in getattr(dossier, "general_fields", {}).items():
        predicate = general_predicates.get(raw_name, raw_name)
        claims.append(_map_field_to_claim("document", predicate, field_obj, doc_sha))

    # 2. Sesiones de clase y unidades de revisión de proyecto
    for session in getattr(dossier, "sessions", []):
        sess_id = str(getattr(session, "session_id", ""))
        sess_title = str(getattr(session, "title", "")).lower()
        sess_status = getattr(session, "status", None)
        is_phase_project_review = (
            sess_id.endswith("_project_review")
            or "sin sesiones explícitas" in sess_title
            or (sess_status == STATUS_AMBIGUOUS and "project" in sess_id)
        )

        entity_type = ENTITY_TYPE_PROJECT_REVIEW if is_phase_project_review else ENTITY_TYPE_SESSION
        prefix = ENTITY_TYPE_PROJECT_REVIEW if is_phase_project_review else ENTITY_TYPE_SESSION
        sess_id_raw = str(getattr(session, "session_id", ""))
        sess_id_clean = sess_id_raw.split(":", 1)[1] if ":" in sess_id_raw else sess_id_raw
        session_subject = f"{prefix}:{sess_id_clean}"
        sess_page = session.pages[0] if getattr(session, "pages", None) else None

        # Afirmación de existencia de la entidad (session o project_review)
        cid_sess = make_claim_id(session_subject, "es_entidad", entity_type, doc_sha)

        sess_metadata: dict[str, Any] = {}
        if is_phase_project_review:
            sess_state = CLAIM_STATE_NEEDS_HUMAN_REVIEW
            sess_metadata = {
                "unit_type": ENTITY_TYPE_PROJECT_REVIEW,
                "reason": (
                    "Unidad sintética de revisión de proyecto por fases sin sesiones explícitas; "
                    "no constituye una sesión de clase respaldada documentalmente y requiere validación docente."
                ),
            }
        elif sess_page is not None:
            sess_state = CLAIM_STATE_BACKED
        else:
            sess_state = CLAIM_STATE_CANDIDATE

        if getattr(session, "project_context", None) is not None:
            sess_metadata["project_context"] = copy.deepcopy(session.project_context)
        if getattr(session, "header_anchor", None) is not None:
            sess_metadata["header_anchor"] = copy.deepcopy(session.header_anchor)

        claims.append(
            AtomicClaim(
                claim_id=cid_sess,
                claim_type=CLAIM_TYPE_ENTITY,
                subject=session_subject,
                predicate="es_entidad",
                object_value=entity_type,
                source_doc_sha256=doc_sha,
                page_number=sess_page,
                extraction_method="source_interpreter_v0",
                state=sess_state,
                metadata=sess_metadata,
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

        # Actividades dentro de esta sesión o unidad de revisión
        for act in getattr(session, "activities", []):
            claims.extend(
                _map_activity_to_claims(
                    act,
                    session_subject,
                    doc_sha,
                    is_project_review=is_phase_project_review,
                )
            )

    return claims
