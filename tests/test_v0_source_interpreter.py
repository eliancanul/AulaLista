"""Tests for AulaLista V0 Curriculum Source Interpreter."""

import hashlib
import json
from pathlib import Path
import re
import pytest

from curriculum.source_interpreter import (
    ORIGIN_EXTRACTED,
    ORIGIN_PROPOSED,
    ORIGIN_TEACHER_ENTERED,
    REVIEW_CONFIRMED,
    REVIEW_CORRECTED,
    REVIEW_PENDING,
    STATUS_AMBIGUOUS,
    STATUS_CONFLICTING,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    AnnexReference,
    CurriculumSourceInterpreter,
    HistoryDelta,
    HistoryEntry,
    ImportDossier,
    InterpretedField,
    SelectionError,
    SessionPlan,
    SourceReference,
    build_daily_guide,
    compute_reextract_diff,
    export_annexes,
    propose_activity_variant,
    resolve,
)

C01_PATH = Path("output/pdf/prueba-issue-96-paginas-4-a-8.pdf")
C01_SHA256 = "33d7c2862a7d14127b2906518b26bc16f0f571f85d765dd6cd63325f52337648"

C02_PATH = Path("/Users/dojo/Downloads/curricula completa.pdf")
C03_PATH = Path("/Users/dojo/Downloads/Planeacio5toGradoSemana02MeReconozco_a_Através_De_Mi_Familia.docx.pdf")
C04_PATH = Path("/Users/dojo/Downloads/planeacion-julio-quinto-grado.pdf")


def test_source_reference_contract():
    ref = SourceReference(
        document_sha256="abc123",
        page_number=2,
        printed_label="Página 2",
        excerpt="Realice un juego de repaso...",
    )
    data = ref.to_dict()
    assert data["document_sha256"] == "abc123"
    assert data["page_number"] == 2
    assert data["excerpt"] == "Realice un juego de repaso..."

    restored = SourceReference.from_dict(data)
    assert restored.document_sha256 == ref.document_sha256
    assert restored.page_number == ref.page_number
    assert restored.excerpt == ref.excerpt


def test_interpreted_field_multidimensional_uncertainty():
    field = InterpretedField(
        name="proyecto",
        value="El uso de las vocales y la letra M",
        origin=ORIGIN_EXTRACTED,
        status=STATUS_SUPPORTED,
        review=REVIEW_PENDING,
        reason="Mención explícita en portada",
        action_required="Validar concordancia",
        evidence=[
            SourceReference(
                document_sha256="abc123",
                page_number=1,
                excerpt="Proyecto: El uso de las vocales...",
            )
        ],
    )
    serialized = field.to_dict()
    deserialized = InterpretedField.from_dict(serialized)
    assert deserialized.name == "proyecto"
    assert deserialized.origin == ORIGIN_EXTRACTED
    assert deserialized.status == STATUS_SUPPORTED
    assert deserialized.review == REVIEW_PENDING
    assert len(deserialized.evidence) == 1
    assert deserialized.evidence[0].page_number == 1


def test_annex_reference_contract_starts_unconfirmed():
    """P0-3: AnnexReferences start with confirmed_page=None and review=pending."""
    annex = AnnexReference(
        annex_number="1",
        raw_mention="anexo 1 y 2 del cuadernillo de actividades",
        source_pages=[2],
        candidate_pages=[3],
        status=STATUS_SUPPORTED,
        review=REVIEW_PENDING,
        reason="Lámina detectada en página 3",
        action_required="Verificar lámina",
    )
    assert annex.confirmed_page is None
    assert annex.review == REVIEW_PENDING
    d = annex.to_dict()
    assert d["confirmed_page"] is None
    restored = AnnexReference.from_dict(d)
    assert restored.annex_number == "1"
    assert restored.candidate_pages == [3]
    assert restored.source_pages == [2]
    assert restored.confirmed_page is None


def test_session_plan_composite_id_and_provenance():
    """P0-2 & P1-5: SessionPlan carries composite session_id, project_title, continues_on."""
    plan = SessionPlan(
        session_id="p2_s1",
        session_number=1,
        title="Lunes - Sesión 1: Identificación",
        project_title="El uso de las vocales y la letra M",
        day_of_week="Lunes",
        pages=[2, 3],
        continues_on=[3],
        layout_fidelity="structured",
        layout_notes="Continuación detectada en página 3.",
    )
    d = plan.to_dict()
    assert d["session_id"] == "p2_s1"
    assert d["project_title"] == "El uso de las vocales y la letra M"
    assert d["continues_on"] == [3]

    restored = SessionPlan.from_dict(d)
    assert restored.session_id == "p2_s1"
    assert restored.project_title == "El uso de las vocales y la letra M"
    assert restored.pages == [2, 3]
    assert restored.continues_on == [3]


def test_c01_pdf_manifest_hash_and_page_count():
    assert C01_PATH.exists(), f"PDF fixture C01 missing at {C01_PATH}"
    content = C01_PATH.read_bytes()
    computed_sha = hashlib.sha256(content).hexdigest()
    assert computed_sha == C01_SHA256


def test_c01_full_finalidad_extraction_no_truncation():
    """P1-4: Finalidad in C01 must NOT be truncated to 4 lines; extracts all 508 characters."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH, selection={"session_number": 1})
    fin = dossier.general_fields.get("finalidad")
    assert fin is not None
    assert fin.status == STATUS_SUPPORTED
    # Must contain full pedagogical scope without cutoff
    assert len(fin.value) == 508
    assert fin.value.endswith("desarrollar la atención y la memoria visual.")
    assert "formación de palabras sencillas" in fin.value
    assert "motricidad fina" in fin.value


def test_c01_annexes_start_unconfirmed():
    """P0-3: Annexes in C01 start candidate/pending with confirmed_page=None."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH, selection={"session_number": 1})
    s1 = dossier.sessions[0]
    for a in s1.annex_references:
        assert a.confirmed_page is None
        assert a.review == REVIEW_PENDING
        assert len(a.candidate_pages) > 0


def test_c02_session_disambiguation_no_collision():
    """P0-2: C02 has repeated session numbers across 4 projects; session_ids must not collide."""
    if not C02_PATH.exists():
        pytest.skip("C02 corpus file not available in test environment.")
    dossier = CurriculumSourceInterpreter.prepare(C02_PATH)
    assert dossier.page_count == 44
    assert len(dossier.sessions) == 20

    # Ensure all session_ids are unique
    session_ids = [s.session_id for s in dossier.sessions]
    assert len(session_ids) == len(set(session_ids)), "Collision detected among session_ids!"

    # Verify project titles are captured across different projects
    project_titles = {s.project_title for s in dossier.sessions}
    assert len(project_titles) >= 3, f"Expected multiple projects, got: {project_titles}"

    # Verify lookups by composite id
    s_first = dossier.get_session("p5_s1")
    assert s_first is not None
    assert s_first.session_number == 1


def test_c03_canonical_campos_and_multi_page_continuation():
    """P1-5 & canonical fields: 'De lo humano y lo comunitario' not split on 'y'; S2 continuation."""
    if not C03_PATH.exists():
        pytest.skip("C03 corpus file not available in test environment.")
    dossier = CurriculumSourceInterpreter.prepare(C03_PATH)

    # 1. Canonical fields: must contain 'De lo humano y lo comunitario' intact
    campos = dossier.general_fields.get("campos_formativos")
    assert campos is not None
    assert "De lo humano y lo comunitario" in campos.value
    # Must NOT contain fragmented 'lo comunitario'
    assert "lo comunitario" not in campos.value

    # 2. Session 2 spans pages 2 and 3 (continuation)
    s2 = next((s for s in dossier.sessions if s.session_number == 2), None)
    assert s2 is not None
    assert 2 in s2.pages
    assert 3 in s2.pages
    assert 3 in s2.continues_on
    # Session 2 Cierre is on page 3 and must be captured
    assert "cierre" in s2.fields
    assert "asamblea" in s2.fields["cierre"].value.lower() or "cartulina" in s2.fields["cierre"].value.lower()


def test_c04_day_based_sessions():
    """C04 planning is organized by day (Lunes, Martes, etc.) rather than 'SESIÓN N'."""
    if not C04_PATH.exists():
        pytest.skip("C04 corpus file not available in test environment.")
    dossier = CurriculumSourceInterpreter.prepare(C04_PATH)
    assert len(dossier.sessions) >= 5
    # Verify days are detected as session titles
    days_found = {s.day_of_week for s in dossier.sessions if s.day_of_week}
    assert "Lunes" in days_found
    assert "Martes" in days_found


def test_resolve_partial_updates_preserves_untouched_fields():
    """P1-6: Partial POST/corrections payload must NOT overwrite omitted fields with empty strings."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH, selection={"session_number": 1})
    orig_desarrollo = dossier.sessions[0].fields["desarrollo"].value
    orig_proposito = dossier.general_fields["proposito"].value

    # Submit only 'inicio'
    corrections = {
        "session_number": 1,
        "session_fields": {
            "inicio": "Nuevo inicio exclusivamente.",
        },
    }
    resolved = resolve(dossier, corrections, actor="Docente")

    # 'inicio' is updated
    assert resolved.sessions[0].fields["inicio"].value == "Nuevo inicio exclusivamente."
    # 'desarrollo' is preserved intact
    assert resolved.sessions[0].fields["desarrollo"].value == orig_desarrollo
    # 'proposito' is preserved intact
    assert resolved.general_fields["proposito"].value == orig_proposito


def test_confirm_all_does_not_auto_confirm_candidates_or_missing_fields():
    """P0-3: confirm_all must NOT confirm candidate annexes nor convert missing/ambiguous to confirmed."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH, selection={"session_number": 1})
    s1 = dossier.sessions[0]
    # In C01, contexto_ejecucion is AMBIGUOUS because of home task
    assert s1.fields["contexto_ejecucion"].status == STATUS_AMBIGUOUS

    # Execute confirm_all
    corrections = {
        "session_number": 1,
        "reviews": {"__all__": "confirmed"},
    }
    resolved = resolve(dossier, corrections, actor="Docente")

    # 1. Ambiguous field stays PENDING (not confirmed)
    assert resolved.sessions[0].fields["contexto_ejecucion"].review == REVIEW_PENDING

    # 2. Supported fields ARE confirmed
    assert resolved.sessions[0].fields["inicio"].review == REVIEW_CONFIRMED

    # 3. Annexes remain PENDING with confirmed_page=None
    for a in resolved.sessions[0].annex_references:
        assert a.confirmed_page is None
        assert a.review == REVIEW_PENDING


def test_v1_contract_stubs_raise_not_implemented():
    """S-04: V1 stubs raise NotImplementedError and are documented as V1 capabilities."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH, selection={"session_number": 1})
    s1 = dossier.sessions[0]
    with pytest.raises(NotImplementedError) as exc1:
        build_daily_guide(s1, {"duration_minutes": 60})
    assert "Fase V1" in str(exc1.value)
    with pytest.raises(NotImplementedError) as exc2:
        propose_activity_variant(s1, "necesidad", [])
    assert "Fase V1" in str(exc2.value)
    with pytest.raises(NotImplementedError) as exc3:
        export_annexes(s1.annex_references)
    assert "Fase V1" in str(exc3.value)


def test_cooperative_cancellation_and_timeout():
    """P1-7: prepare() respects cooperative cancellation and timeout."""
    from curriculum.source_interpreter import InterpretationCancelledError

    with pytest.raises((TimeoutError, InterpretationCancelledError)) as exc:
        CurriculumSourceInterpreter.prepare(
            C01_PATH,
            is_cancelled=lambda: True,
        )
    assert "cancelada cooperativamente" in str(exc.value)


def test_sol_output_1_invalid_selection_raises_value_error():
    """Sol Item 1: Invalid selection on prepare() must NOT silently fallback; raises ValueError."""
    # 1. Invalid session_id
    with pytest.raises(ValueError) as exc1:
        CurriculumSourceInterpreter.prepare(
            C01_PATH, selection={"session_id": "p999_s999", "pages": [999]}
        )
    assert "fuera de rango" in str(exc1.value) or "no existe" in str(exc1.value)

    # 2. Out of range session number
    with pytest.raises(ValueError) as exc2:
        CurriculumSourceInterpreter.prepare(C01_PATH, selection={"session_number": 999})
    assert "999 no existe" in str(exc2.value)

    # 3. C02 ambiguous session number without project/session_id
    if C02_PATH.exists():
        with pytest.raises(ValueError) as exc3:
            CurriculumSourceInterpreter.prepare(C02_PATH, selection={"session_number": 1})
        assert "ambigua" in str(exc3.value)


def test_sol_output_2_invalid_annex_confirmation_rejected():
    """Sol Item 2: Annex confirmation with non-candidate page must raise ValueError without partial mutation."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH, selection={"session_number": 1})
    orig_version = dossier.version
    # Candidate for Anexo 1 is [3]. Attempting to confirm page 1 must be rejected!
    corrections = {
        "session_number": 1,
        "session_fields": {"inicio": "Nuevo inicio"},
        "annex_confirmations": {"1": 1},
    }
    with pytest.raises(ValueError) as exc:
        resolve(dossier, corrections, actor="Docente")
    assert "no es una lámina candidata válida" in str(exc.value)
    # Version must NOT be bumped and partial mutation must NOT be applied
    assert dossier.version == orig_version


def test_sol_output_3_confirm_all_session_review_derived():
    """Sol Item 3: confirm_all must derive SessionPlan.review from components; stays pending if annexes or context unresolved."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH, selection={"session_number": 1})
    s1 = dossier.sessions[0]
    assert s1.fields["contexto_ejecucion"].status == STATUS_AMBIGUOUS

    # Execute confirm_all
    resolved = resolve(dossier, {"session_number": 1, "reviews": {"__all__": "confirmed"}}, actor="Docente")
    s1_res = resolved.sessions[0]

    # SessionPlan.review MUST be 'pending' because context is ambiguous and annexes are unconfirmed
    assert s1_res.review == REVIEW_PENDING
    assert s1_res.fields["contexto_ejecucion"].review == REVIEW_PENDING
    assert s1_res.annex_references[0].review == REVIEW_PENDING


def test_page_extraction_failure_downgrades_status_and_records_warning():
    """Sol Item 6: Page text extraction errors are recorded as warnings and downgrade field status."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH)
    # Manually inject warning for page 2 to verify contract
    dossier.page_warnings[2] = "Fallo simulado de OCR/lectura en página 2."
    s1 = dossier.sessions[0]
    # Re-evaluate parse with warned page
    plan = CurriculumSourceInterpreter._parse_session_block(
        session_id=s1.session_id,
        session_number=s1.session_number,
        title=s1.title,
        project_title=s1.project_title,
        day_of_week=s1.day_of_week,
        pages=[2],
        continues_on=[],
        layout_fidelity="linearized_heuristics",
        layout_notes="",
        block_text="Inicio: Actividad.\nDesarrollo: Central.\nCierre: Final.",
        sha256=dossier.source_sha256,
        annex_candidates=[],
        page_warnings={2: "Fallo de lectura"},
    )
    # Fields on warned page must be AMBIGUOUS, never SUPPORTED
    assert plan.fields["inicio"].status == STATUS_AMBIGUOUS
    assert plan.fields["desarrollo"].status == STATUS_AMBIGUOUS
    assert plan.fields["cierre"].status == STATUS_AMBIGUOUS


def test_c03_campos_formativos_deduplication_and_provenance_page():
    """Sol Item 8: C03 canonical fields deduplicated case-insensitively; real physical page provenance."""
    if not C03_PATH.exists():
        pytest.skip("C03 not available.")
    dossier = CurriculumSourceInterpreter.prepare(C03_PATH)
    campos_val = dossier.general_fields["campos_formativos"].value
    # Must NOT have duplicates
    assert len(campos_val) == len(set(campos_val))
    # Must contain 'De lo humano y lo comunitario' exactly once
    assert campos_val.count("De lo humano y lo comunitario") == 1
    # Evidence must have valid 1-indexed page
    for field_obj in dossier.general_fields.values():
        if field_obj.evidence:
            assert 1 <= field_obj.evidence[0].page_number <= dossier.page_count


def test_c04_honest_matrix():
    """Sol Item 9 & Gate Final: C04 honest extraction matrix without garbage project title or column headers as campos."""
    if not C04_PATH.exists():
        pytest.skip("C04 not available.")
    dossier = CurriculumSourceInterpreter.prepare(C04_PATH)
    # 1. Project title in general_fields must be missing or ambiguous without garbage matching 'Proyectos'
    p_field = dossier.general_fields["proyecto"]
    assert p_field.status in (STATUS_MISSING, STATUS_AMBIGUOUS)
    assert p_field.value != "s Eje Seleccionados:"
    assert "s Eje" not in p_field.value

    # 2. Session project title must NOT contain mid-sentence garbage
    for s in dossier.sessions:
        assert not s.project_title.startswith("s Comunitarios")
        assert "Preguntar:" not in s.project_title

    # 3. Campos formativos must NOT contain table header column 'Proyectos Eje y Libro'
    campos = dossier.general_fields["campos_formativos"].value
    assert "Proyectos Eje y Libro" not in campos
    assert "Lenguajes" in campos

    # 4. Metodología must not be truncated or runaway
    met = dossier.general_fields["metodologia"].value
    assert len(met) <= 150
    assert "Aprendizaje Basado en Proyectos Comunitarios" in met


def test_layout_fidelity_linearized_heuristics():
    """Sol Item 7: layout_fidelity declared as linearized_heuristics with honest notes."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH)
    s1 = dossier.sessions[0]
    assert s1.layout_fidelity == "linearized_heuristics"
    assert "reconstrucción heurística" in s1.layout_notes.lower()


def test_resolve_invalid_session_id_raises_value_error():
    """Gate Final: resolve() rejects nonexistent session_id directly with ValueError before mutating or versioning."""
    dossier = CurriculumSourceInterpreter.prepare(C01_PATH)
    orig_version = dossier.version
    orig_val = dossier.sessions[0].fields["inicio"].value
    with pytest.raises(ValueError) as exc:
        resolve(
            dossier,
            {
                "session_id": "does-not-exist",
                "session_number": 1,
                "session_fields": {"inicio": "WRONG SESSION"},
            },
        )
    assert "no existe" in str(exc.value)
    assert dossier.version == orig_version
    assert dossier.sessions[0].fields["inicio"].value == orig_val


def test_resolve_ambiguous_session_number_raises_value_error():
    """Gate Final: resolve() rejects session_number when multiple sessions share that number (e.g. C02)."""
    if not C02_PATH.exists():
        pytest.skip("C02 not available.")
    dossier = CurriculumSourceInterpreter.prepare(C02_PATH)
    with pytest.raises(ValueError) as exc:
        resolve(
            dossier,
            {
                "session_number": 1,
                "session_fields": {"inicio": "AMBIGUOUS MUTATION"},
            },
        )
    assert "ambigua" in str(exc.value).lower() or "session_id" in str(exc.value).lower()


def test_advanced_audit_invalid_annex_is_atomic_for_all_fields():
    """Advanced audit Item 2: invalid annex confirmation rejects atomically before any mutation."""
    d = CurriculumSourceInterpreter.prepare(C01_PATH)
    s = d.sessions[0]
    original = d.general_fields["proyecto"].value
    start = s.fields["inicio"].value
    with pytest.raises(ValueError):
        resolve(
            d,
            {
                "session_id": s.session_id,
                "general_fields": {"proyecto": "MUTATED"},
                "session_fields": {"inicio": "MUTATED"},
                "annex_confirmations": {"1": "1"},
            },
        )
    assert d.version == 1
    assert d.general_fields["proyecto"].value == original
    assert s.fields["inicio"].value == start


def test_advanced_audit_selection_pages_must_match_selected_session():
    """Advanced audit Item 1: selection pages must match the session's physical pages."""
    d = CurriculumSourceInterpreter.prepare(C01_PATH)
    s = d.sessions[0]
    wrong_page = 5 if 5 not in s.pages else 1
    with pytest.raises(ValueError) as exc:
        CurriculumSourceInterpreter.prepare(C01_PATH, {"session_id": s.session_id, "pages": [wrong_page]})
    assert "inconsistente" in str(exc.value).lower() or "páginas" in str(exc.value).lower()


def test_advanced_audit_selection_by_pages_only_must_be_unequivocal():
    """Advanced audit Item 1: selection solely by pages must be unequivocal and not pick first match."""
    # In C01, page 2 contains both session 1 (p2_s1) and session 2 (p2_s2)
    with pytest.raises(ValueError) as exc:
        CurriculumSourceInterpreter.prepare(C01_PATH, {"pages": [2]})
    assert "ambigua" in str(exc.value).lower() or "session_id" in str(exc.value).lower()


def test_advanced_audit_blank_teacher_correction_is_missing_not_supported():
    """Advanced audit Item 4: empty teacher corrections become missing / pending, not supported."""
    d = CurriculumSourceInterpreter.prepare(C01_PATH)
    s = d.sessions[0]
    resolved = resolve(
        d,
        {
            "session_id": s.session_id,
            "general_fields": {"proyecto": ""},
            "session_fields": {"inicio": ""},
        },
    )
    assert resolved.general_fields["proyecto"].status == STATUS_MISSING
    assert resolved.general_fields["proyecto"].origin == ORIGIN_TEACHER_ENTERED
    assert resolved.sessions[0].fields["inicio"].status == STATUS_MISSING
    assert resolved.sessions[0].review == REVIEW_PENDING


def test_advanced_audit_execution_context_is_not_invented_or_misattributed():
    """Advanced audit Item 6: execution context must not fabricate supported/extracted Aula without evidence."""
    c01 = CurriculumSourceInterpreter.prepare(C01_PATH)
    home_context = c01.sessions[0].fields["contexto_ejecucion"]
    assert home_context.status == STATUS_AMBIGUOUS
    assert home_context.origin == ORIGIN_PROPOSED

    if C04_PATH.exists():
        c04 = CurriculumSourceInterpreter.prepare(C04_PATH)
        context = c04.sessions[0].fields["contexto_ejecucion"]
        assert not (context.value == "Aula" and context.origin == ORIGIN_EXTRACTED and context.status == STATUS_SUPPORTED)
        assert context.status in (STATUS_MISSING, STATUS_AMBIGUOUS)


def test_session_continuation_never_jumps_nonconsecutive_pages():
    """Blocker B1: Sessions must never jump intermediate pages without headers to absorb later pages."""
    pages = [
        "PROYECTO: PROYECTO DEMO\nSESIÓN 1: Apertura\nInicio: Dinámica inicial.\nDesarrollo: Explicación.",
        "Texto institucional o página intermedia sin encabezado de sesión.",
        "Desarrollo de actividades\nSESIÓN 2: Segunda sesión\nInicio: Retomar actividad.",
    ]
    sessions = CurriculumSourceInterpreter._detect_sessions(pages, "dummy_sha", [], {})
    s1 = sessions[0]
    # Must NOT jump from page 1 to page 3
    assert s1.pages == [1]
    assert "desarrollo de actividades" not in s1.fields.get("evaluacion", InterpretedField(name="evaluacion", value="")).value.lower()
    assert 3 not in s1.pages


def test_session_continuation_rejects_rubric_barrier_on_next_page():
    """Blocker B1: Last session must never absorb a rubric table from the next page even if it contains 'Evaluación'."""
    pages = [
        "PROYECTO: PROYECTO DEMO\nSESIÓN 1: Cierre de proyecto\nInicio: Repaso.\nDesarrollo: Actividad.\nCierre: Conclusión.\nEvaluación: Observación directa.",
        "Rúbrica de evaluación: PROYECTO DEMO\nCriterios de Evaluación\nNivel Sobresaliente\nNivel Satisfactorio",
    ]
    sessions = CurriculumSourceInterpreter._detect_sessions(pages, "dummy_sha", [], {})
    s1 = sessions[0]
    assert s1.pages == [1]
    assert "rúbrica" not in s1.fields["evaluacion"].value.lower()


def test_evidence_citations_use_exact_physical_page():
    """Blocker B1: Evidence citations must cite the exact physical page where the snippet appears."""
    pages = [
        "PROYECTO: PROYECTO MULTIPAGE\nSESIÓN 1: Sesión continua\nInicio: Abrir la clase en plenaria.\nDesarrollo: Trabajo en equipos con material.",
        "Cierre: Asamblea general para compartir conclusiones en cartulina.\nSESIÓN 2: Siguiente sesión",
    ]
    sessions = CurriculumSourceInterpreter._detect_sessions(pages, "dummy_sha", [], {})
    s1 = sessions[0]
    assert s1.pages == [1, 2]
    assert s1.fields["inicio"].evidence[0].page_number == 1
    assert s1.fields["desarrollo"].evidence[0].page_number == 1
    assert s1.fields["cierre"].evidence[0].page_number == 2


def test_annex_mention_provenance_multipage_synthetic():
    """F5: In multipage sessions, annex mention provenance must cite exact mention page and not session_pages[0]."""
    pages = [
        "PROYECTO: PROYECTO ANEXOS\nSESIÓN 1: Sesión con anexo en continuación\nInicio: Apertura sin anexos.\nDesarrollo: Explicación general.",
        "Cierre: Resolver el anexo 9 en equipos.\nSESIÓN 2: Otra sesión",
        "ANEXO 9\nLámina de actividades para recortar",
    ]
    annex_candidates = [{"page": 3, "number": "9", "label": "ANEXO 9"}]
    sessions = CurriculumSourceInterpreter._detect_sessions(pages, "dummy_sha", annex_candidates, {})
    s1 = sessions[0]
    assert s1.pages == [1, 2]
    assert len(s1.annex_references) == 1
    a9 = s1.annex_references[0]
    assert a9.annex_number == "9"
    # source_pages must represent the real mention page(s), not all session pages
    assert a9.source_pages == [2]
    assert a9.candidate_pages == [3]
    assert a9.confirmed_page is None
    assert a9.review == REVIEW_PENDING
    assert a9.status == STATUS_SUPPORTED
    # Evidence for mention must cite page 2
    mention_ev = [ev for ev in a9.evidence if ev.page_number == 2]
    assert len(mention_ev) >= 1
    assert "anexo 9" in mention_ev[0].excerpt.lower()
    # Evidence for candidate must cite page 3
    cand_ev = [ev for ev in a9.evidence if ev.page_number == 3]
    assert len(cand_ev) >= 1
    # Reason must name page 2
    assert "pág. 2" in a9.reason


def test_resolve_identical_payload_with_crlf_and_empty_annex_is_noop():
    """F1: Re-submitting identical values (including CRLF newlines and empty annex radio) is no-op."""
    dossier = ImportDossier(
        source_sha256="dummy_sha",
        source_name="Plan Demo",
        page_count=2,
        general_fields={
            "proyecto": InterpretedField(name="proyecto", value="Proyecto A", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
            "proposito": InterpretedField(name="proposito", value="Línea 1\nLínea 2", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
        },
        sessions=[
            SessionPlan(
                session_id="p1_s1",
                session_number=1,
                title="Sesión 1",
                project_title="Proyecto A",
                day_of_week="Lunes",
                pages=[1],
                continues_on=[],
                layout_fidelity="linearized",
                layout_notes="",
                fields={
                    "inicio": InterpretedField(name="inicio", value="Inicio texto\ncon salto", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
                    "contexto_ejecucion": InterpretedField(name="contexto_ejecucion", value="Aula", status=STATUS_AMBIGUOUS, review=REVIEW_PENDING),
                },
                annex_references=[
                    AnnexReference(
                        annex_number="1",
                        raw_mention="anexo 1",
                        source_pages=[1],
                        candidate_pages=[2],
                        status=STATUS_SUPPORTED,
                        review=REVIEW_PENDING,
                        confirmed_page=None,
                    )
                ],
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
            )
        ],
        selection={"session_id": "p1_s1", "session_number": 1},
        version=1,
    )

    # Re-submit identical values, with browser CRLF in multiline strings and empty annex radio
    payload = {
        "general_fields": {
            "proyecto": "Proyecto A",
            "proposito": "Línea 1\r\nLínea 2",
        },
        "session_id": "p1_s1",
        "session_number": 1,
        "session_fields": {
            "inicio": "Inicio texto\r\ncon salto",
            "contexto_ejecucion": "Aula",
        },
        "annex_confirmations": {
            "1": "",  # Radio left empty
        },
    }

    resolved = resolve(dossier, payload, actor="Docente")
    # Must be complete no-op: version unchanged, no history, no review change
    assert resolved.version == 1
    assert len(resolved.history) == 0
    assert resolved.general_fields["proyecto"].review == REVIEW_PENDING
    assert resolved.general_fields["proposito"].review == REVIEW_PENDING
    assert resolved.general_fields["proposito"].origin == ORIGIN_EXTRACTED
    s1 = resolved.sessions[0]
    assert s1.fields["inicio"].review == REVIEW_PENDING
    assert s1.fields["inicio"].origin == ORIGIN_EXTRACTED
    assert s1.fields["contexto_ejecucion"].review == REVIEW_PENDING
    assert s1.fields["contexto_ejecucion"].status == STATUS_AMBIGUOUS
    assert s1.annex_references[0].confirmed_page is None
    assert s1.annex_references[0].review == REVIEW_PENDING


def test_resolve_editing_single_field_only_modifies_that_field():
    """F1: Editing exactly one field only affects that field and bumps version once."""
    dossier = ImportDossier(
        source_sha256="dummy_sha",
        source_name="Plan Demo",
        page_count=2,
        general_fields={
            "proyecto": InterpretedField(name="proyecto", value="Proyecto A", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
            "proposito": InterpretedField(name="proposito", value="Línea 1\nLínea 2", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
        },
        sessions=[
            SessionPlan(
                session_id="p1_s1",
                session_number=1,
                title="Sesión 1",
                pages=[1],
                fields={
                    "inicio": InterpretedField(name="inicio", value="Inicio", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
                },
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
            )
        ],
        selection={"session_id": "p1_s1", "session_number": 1},
        version=1,
    )

    payload = {
        "general_fields": {
            "proyecto": "Proyecto Modificado",  # Only this changed!
            "proposito": "Línea 1\r\nLínea 2",  # CRLF but same text
        },
        "session_id": "p1_s1",
        "session_number": 1,
        "session_fields": {
            "inicio": "Inicio",  # unchanged
        },
    }

    resolved = resolve(dossier, payload, actor="Docente")
    assert resolved.version == 2
    assert len(resolved.history) == 1
    # Only proyecto changed
    assert resolved.general_fields["proyecto"].value == "Proyecto Modificado"
    assert resolved.general_fields["proyecto"].review == REVIEW_CORRECTED
    assert resolved.general_fields["proyecto"].origin == ORIGIN_TEACHER_ENTERED
    assert resolved.general_fields["proyecto"].original_value == "Proyecto A"
    # proposito and inicio remain untouched and PENDING
    assert resolved.general_fields["proposito"].review == REVIEW_PENDING
    assert resolved.general_fields["proposito"].origin == ORIGIN_EXTRACTED
    assert resolved.sessions[0].fields["inicio"].review == REVIEW_PENDING
    assert resolved.sessions[0].fields["inicio"].origin == ORIGIN_EXTRACTED


def test_confirm_all_does_not_confirm_ambiguous_missing_conflicting_or_annexes():
    """F1: confirm_all confirms supported fields but NEVER ambiguous, missing, conflicting or annexes."""
    dossier = ImportDossier(
        source_sha256="dummy_sha",
        source_name="Plan Demo",
        page_count=2,
        general_fields={
            "proyecto": InterpretedField(name="proyecto", value="Proyecto A", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
            "finalidad": InterpretedField(name="finalidad", value="Finalidad B", status=STATUS_CONFLICTING, review=REVIEW_PENDING),
        },
        sessions=[
            SessionPlan(
                session_id="p1_s1",
                session_number=1,
                title="Sesión 1",
                pages=[1],
                fields={
                    "inicio": InterpretedField(name="inicio", value="Inicio", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
                    "desarrollo": InterpretedField(name="desarrollo", value="", status=STATUS_MISSING, review=REVIEW_PENDING),
                    "contexto_ejecucion": InterpretedField(name="contexto_ejecucion", value="Aula", status=STATUS_AMBIGUOUS, review=REVIEW_PENDING),
                },
                annex_references=[
                    AnnexReference(
                        annex_number="1",
                        raw_mention="anexo 1",
                        source_pages=[1],
                        candidate_pages=[2],
                        status=STATUS_SUPPORTED,
                        review=REVIEW_PENDING,
                        confirmed_page=None,
                    )
                ],
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
            )
        ],
        selection={"session_id": "p1_s1", "session_number": 1},
        version=1,
    )

    payload = {
        "session_id": "p1_s1",
        "session_number": 1,
        "reviews": {"__all__": "confirmed"},
    }

    resolved = resolve(dossier, payload, actor="Docente")
    assert resolved.version == 2
    # Supported fields confirmed
    assert resolved.general_fields["proyecto"].review == REVIEW_CONFIRMED
    assert resolved.sessions[0].fields["inicio"].review == REVIEW_CONFIRMED
    # Conflicting, missing, ambiguous must NOT be confirmed
    assert resolved.general_fields["finalidad"].review == REVIEW_PENDING
    assert resolved.sessions[0].fields["desarrollo"].review == REVIEW_PENDING
    assert resolved.sessions[0].fields["contexto_ejecucion"].review == REVIEW_PENDING
    # Annexes must NOT be confirmed
    assert resolved.sessions[0].annex_references[0].confirmed_page is None
    assert resolved.sessions[0].annex_references[0].review == REVIEW_PENDING


def test_resolve_pure_noop_does_not_mutate_session_review_on_inconsistent_aggregate():
    """B2: resolve() must be a pure no-op when there are no effective changes, preserving session review."""
    dossier = ImportDossier(
        source_sha256="dummy_sha",
        source_name="Plan Demo",
        page_count=2,
        general_fields={
            "proyecto": InterpretedField(name="proyecto", value="Proyecto A", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
        },
        sessions=[
            SessionPlan(
                session_id="p1_s1",
                session_number=1,
                title="Sesión 1",
                pages=[1],
                fields={
                    "inicio": InterpretedField(name="inicio", value="Inicio", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
                    "desarrollo": InterpretedField(name="desarrollo", value="Desarrollo", status=STATUS_SUPPORTED, review=REVIEW_PENDING),
                },
                annex_references=[
                    AnnexReference(
                        annex_number="1",
                        raw_mention="anexo 1",
                        source_pages=[1],
                        candidate_pages=[2],
                        status=STATUS_SUPPORTED,
                        review=REVIEW_PENDING,
                        confirmed_page=None,
                    )
                ],
                status=STATUS_SUPPORTED,
                # Inconsistent aggregate: review is CONFIRMED even though components are PENDING
                review=REVIEW_CONFIRMED,
            )
        ],
        selection={"session_id": "p1_s1", "session_number": 1},
        version=7,
    )

    # 1. No-op payload (identical values)
    payload_noop = {
        "session_id": "p1_s1",
        "session_number": 1,
        "general_fields": {"proyecto": "Proyecto A"},
        "session_fields": {"inicio": "Inicio", "desarrollo": "Desarrollo"},
        "annex_confirmations": {"1": ""},
    }

    resolved = resolve(dossier, payload_noop, actor="Docente")
    # Must NOT mutate anything, including session.review
    assert resolved.version == 7
    assert len(resolved.history) == 0
    assert resolved.sessions[0].review == REVIEW_CONFIRMED

    # 2. General field edit only: does not impact session components, so session.review is not recomputed
    payload_general_edit = {
        "session_id": "p1_s1",
        "session_number": 1,
        "general_fields": {"proyecto": "Proyecto Editado"},
    }
    resolved2 = resolve(dossier, payload_general_edit, actor="Docente")
    assert resolved2.version == 8
    assert resolved2.sessions[0].review == REVIEW_CONFIRMED

    # 3. Session field edit: DOES impact session, so session.review IS recomputed
    payload_session_edit = {
        "session_id": "p1_s1",
        "session_number": 1,
        "session_fields": {"inicio": "Inicio Modificado"},
    }
    resolved3 = resolve(dossier, payload_session_edit, actor="Docente")
    assert resolved3.version == 9
    assert resolved3.sessions[0].review == REVIEW_PENDING


def test_campos_formativos_legacy_string_and_normalization():
    """B3: normalize_campos_formativos handles legacy string atomically and resolve treats string/list as semantically equal."""
    from curriculum.source_interpreter import normalize_campos_formativos

    assert normalize_campos_formativos("Legado no canónico") == ["Legado no canónico"]
    assert normalize_campos_formativos("Lenguajes, Ética, naturaleza y sociedades") == ["Lenguajes, Ética, naturaleza y sociedades"]
    assert normalize_campos_formativos(["Lenguajes", "Ética, naturaleza y sociedades"]) == ["Lenguajes", "Ética, naturaleza y sociedades"]
    assert normalize_campos_formativos([]) == []
    assert normalize_campos_formativos(None) == []
    assert normalize_campos_formativos("") == []

    dossier = ImportDossier(
        source_sha256="dummy_sha",
        source_name="Plan Demo",
        page_count=2,
        general_fields={
            "campos_formativos": InterpretedField(
                name="campos_formativos",
                value="Legado no canónico",
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
            ),
        },
        sessions=[],
        selection={},
        version=1,
    )

    # Submitting list with same legacy value is a no-op (no mutation)
    payload = {
        "general_fields": {
            "campos_formativos": ["Legado no canónico"],
        }
    }
    resolved = resolve(dossier, payload)
    assert resolved.version == 1
    assert len(resolved.history) == 0

    # Submitting empty list clears to [] and marks missing/pending
    payload_empty = {
        "general_fields": {
            "campos_formativos": [],
        }
    }
    resolved2 = resolve(dossier, payload_empty)
    assert resolved2.version == 2
    cf = resolved2.general_fields["campos_formativos"]
    assert cf.value == []
    assert cf.status == STATUS_MISSING
    assert cf.review == REVIEW_PENDING


def test_derive_campos_formativos_options_exact_matching():
    """B3: derive_campos_formativos_options performs exact matching on legacy strings without substring matching."""
    from curriculum.source_interpreter import derive_campos_formativos_options, CANONICAL_CAMPOS

    # 1. Ambiguous legacy string containing multiple comma-separated canonical names
    legacy = "Lenguajes, Ética, naturaleza y sociedades"
    opts = derive_campos_formativos_options(legacy)
    selected = [o["value"] for o in opts if o["selected"]]
    # Exactly one option selected: the legacy atomic option, NOT the partial canonical options!
    assert selected == [legacy]
    # Check that canonical options are present but NOT selected
    for o in opts:
        if o["value"] in CANONICAL_CAMPOS:
            assert not o["selected"], f"Canonical option {o['value']} should NOT be selected for legacy atomic string"
        elif o["value"] == legacy:
            assert o["selected"], "Legacy atomic option must be selected"

    # 2. Simple legacy non-canonical string
    simple_legacy = "Legado no canónico"
    opts2 = derive_campos_formativos_options(simple_legacy)
    assert [o["value"] for o in opts2 if o["selected"]] == [simple_legacy]

    # 3. Canonical list
    canonical_list = ["Lenguajes", "Ética, naturaleza y sociedades"]
    opts3 = derive_campos_formativos_options(canonical_list)
    assert [o["value"] for o in opts3 if o["selected"]] == canonical_list

    # 4. Empty and None
    assert [o["value"] for o in opts3 if o["selected"]] == canonical_list
    assert [o["value"] for o in derive_campos_formativos_options([]) if o["selected"]] == []
    assert [o["value"] for o in derive_campos_formativos_options(None) if o["selected"]] == []


def test_f3_structured_deltas_resolve_chain_a_b_c():
    """F3: Each effective resolve decision records structured JSON-serializable deltas.
    Two successive corrections A -> B -> C preserve intermediate state B in history.
    """
    dossier = ImportDossier(
        source_sha256="dummy_sha",
        source_name="Plan Demo",
        page_count=5,
        version=1,
        general_fields={
            "proyecto": InterpretedField(
                name="proyecto",
                value="A",
                origin=ORIGIN_EXTRACTED,
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
                reason="Portada del documento",
                original_reason="Portada del documento",
                action_required="Validar título",
                current_action="Dato fundamentado en la fuente; pendiente de confirmación docente.",
                evidence=[
                    SourceReference(document_sha256="dummy_sha", page_number=1, excerpt="Proyecto: A")
                ],
            ),
        },
        sessions=[
            SessionPlan(
                session_id="p2_s1",
                session_number=1,
                title="Sesión 1",
                pages=[2],
                fields={
                    "inicio": InterpretedField(
                        name="inicio",
                        value="Inicio original",
                        origin=ORIGIN_EXTRACTED,
                        status=STATUS_SUPPORTED,
                        review=REVIEW_PENDING,
                    )
                },
            )
        ],
        selection={"session_id": "p2_s1", "session_number": 1},
    )

    # 1. First correction: A -> B
    payload_b = {
        "general_fields": {"proyecto": "B"},
        "session_id": "p2_s1",
    }
    v2 = resolve(dossier, payload_b, actor="Docente Ana")
    assert v2.version == 2
    assert len(v2.history) == 1
    h1 = v2.history[0]
    assert h1["version"] == 2
    assert h1["action"] == "resolve"
    assert h1["actor"] == "Docente Ana"
    assert "deltas" in h1
    assert len(h1["deltas"]) == 1

    d1 = h1["deltas"][0]
    assert d1["scope"] == "general"
    assert d1["field"] == "proyecto"
    assert d1["before"]["value"] == "A"
    assert d1["before"]["origin"] == ORIGIN_EXTRACTED
    assert d1["before"]["status"] == STATUS_SUPPORTED
    assert d1["before"]["review"] == REVIEW_PENDING
    assert len(d1["before"]["evidence"]) == 1
    assert d1["after"]["value"] == "B"
    assert d1["after"]["origin"] == ORIGIN_TEACHER_ENTERED
    assert d1["after"]["status"] == STATUS_SUPPORTED
    assert d1["after"]["review"] == REVIEW_CORRECTED

    # Ensure JSON serializable
    json.dumps(d1)

    # 2. Second correction: B -> C
    payload_c = {
        "general_fields": {"proyecto": "C"},
        "session_id": "p2_s1",
    }
    v3 = resolve(v2, payload_c, actor="Docente Carlos")
    assert v3.version == 3
    assert len(v3.history) == 2
    h2 = v3.history[1]
    assert h2["version"] == 3
    assert h2["actor"] == "Docente Carlos"
    assert "deltas" in h2
    assert len(h2["deltas"]) == 1

    d2 = h2["deltas"][0]
    assert d2["scope"] == "general"
    assert d2["field"] == "proyecto"
    # Intermediate state B is preserved as 'before' in v3 and was 'after' in v2!
    assert d2["before"]["value"] == "B"
    assert d2["before"]["origin"] == ORIGIN_TEACHER_ENTERED
    assert d2["before"]["review"] == REVIEW_CORRECTED
    assert d2["after"]["value"] == "C"
    assert d2["after"]["origin"] == ORIGIN_TEACHER_ENTERED
    assert d2["after"]["review"] == REVIEW_CORRECTED

    # original_value on field retains initial extracted value A
    assert v3.general_fields["proyecto"].original_value == "A"
    assert v3.general_fields["proyecto"].value == "C"


def test_f3_structured_deltas_confirmations_empties_and_annexes():
    """F3: Explicit confirmations, field empties/clears, and annex associations/disassociations record deltas."""
    dossier = ImportDossier(
        source_sha256="dummy_sha",
        source_name="Plan Demo",
        page_count=5,
        version=1,
        general_fields={
            "proyecto": InterpretedField(
                name="proyecto",
                value="Proyecto Alpha",
                origin=ORIGIN_EXTRACTED,
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
                reason="Razón original",
                original_reason="Razón original",
            ),
        },
        sessions=[
            SessionPlan(
                session_id="p2_s1",
                session_number=1,
                title="Sesión 1",
                pages=[2],
                fields={
                    "inicio": InterpretedField(
                        name="inicio",
                        value="Actividad inicial",
                        origin=ORIGIN_EXTRACTED,
                        status=STATUS_SUPPORTED,
                        review=REVIEW_PENDING,
                        reason="Texto extraído p.2",
                        original_reason="Texto extraído p.2",
                    )
                },
                annex_references=[
                    AnnexReference(
                        annex_number="1",
                        raw_mention="ver Anexo 1",
                        source_pages=[2],
                        candidate_pages=[4],
                        status=STATUS_SUPPORTED,
                        review=REVIEW_PENDING,
                        reason="Candidata detectada en pág 4",
                    )
                ],
            )
        ],
        selection={"session_id": "p2_s1", "session_number": 1},
    )

    # 1. Confirm general field explicitly
    v2 = resolve(
        dossier,
        {
            "reviews": {"proyecto": "confirmed"},
            "session_id": "p2_s1",
        },
    )
    assert v2.version == 2
    delta_confirm = v2.history[-1]["deltas"][0]
    assert delta_confirm["scope"] == "general"
    assert delta_confirm["field"] == "proyecto"
    assert delta_confirm["before"]["review"] == REVIEW_PENDING
    assert delta_confirm["after"]["review"] == REVIEW_CONFIRMED

    # 2. Empty a session field (clear value)
    v3 = resolve(
        v2,
        {
            "session_id": "p2_s1",
            "session_fields": {"inicio": ""},
        },
    )
    assert v3.version == 3
    delta_empty = v3.history[-1]["deltas"][0]
    assert delta_empty["scope"] == "session"
    assert delta_empty["session_id"] == "p2_s1"
    assert delta_empty["field"] == "inicio"
    assert delta_empty["before"]["value"] == "Actividad inicial"
    assert delta_empty["after"]["value"] == ""
    assert delta_empty["after"]["status"] == STATUS_MISSING
    assert delta_empty["after"]["review"] == REVIEW_PENDING

    # 3. Confirm annex candidate page 4
    v3.annex_candidates = [{"page": 4, "label": "Lámina del Anexo 1"}]
    pdf_source = (b"%PDF-1.4", v3.source_sha256, ["p1", "p2", "p3", "Lámina del Anexo 1", "p5"])
    v4 = resolve(
        v3,
        {
            "session_id": "p2_s1",
            "annex_confirmations": {"1": "4"},
        },
        pdf_source=pdf_source,
    )
    assert v4.version == 4
    delta_annex = v4.history[-1]["deltas"][0]
    assert delta_annex["scope"] == "annex"
    assert delta_annex["session_id"] == "p2_s1"
    assert delta_annex["field"] == "annex_1"
    assert delta_annex["before"]["confirmed_page"] is None
    assert delta_annex["before"]["review"] == REVIEW_PENDING
    assert delta_annex["after"]["confirmed_page"] == 4
    assert delta_annex["after"]["review"] == REVIEW_CONFIRMED

    # 4. Disassociate annex (unset confirmed page)
    v5 = resolve(
        v4,
        {
            "session_id": "p2_s1",
            "annex_confirmations": {"1": ""},
        },
        pdf_source=pdf_source,
    )
    assert v5.version == 5
    delta_disassoc = v5.history[-1]["deltas"][0]
    assert delta_disassoc["scope"] == "annex"
    assert delta_disassoc["field"] == "annex_1"
    assert delta_disassoc["before"]["confirmed_page"] == 4
    assert delta_disassoc["after"]["confirmed_page"] is None
    assert delta_disassoc["after"]["review"] == REVIEW_PENDING


def test_f3_backward_compatibility_legacy_dossier_without_deltas():
    """F3: Legacy dossiers without 'deltas' in history load cleanly without error and without fabricating history."""
    legacy_data = {
        "source_sha256": "dummy_sha",
        "source_name": "Plan Demo",
        "page_count": 2,
        "version": 2,
        "status": "active",
        "selection": {},
        "general_fields": {},
        "sessions": [],
        "annex_candidates": [],
        "page_warnings": {},
        "history": [
            {
                "version": 2,
                "action": "resolve",
                "actor": "Docente",
                "timestamp": "2026-09-10T12:00:00Z",
                "changes": ["Campo general 'proyecto' corregido por docente."],
                "summary": "Resolución v2: 1 decisiones docentes registradas.",
                # Note: NO 'deltas' key present in legacy entry
            }
        ],
    }
    dossier = ImportDossier.from_dict(legacy_data)
    assert dossier.version == 2
    assert len(dossier.history) == 1
    entry = dossier.history[0]
    # deltas should default to [] or empty list
    assert entry.get("deltas", []) == []


def test_f4_original_reason_preserved_and_current_action_cleared_on_resolve():
    """F4: Original justification/reason is preserved; current_action is cleared on resolve;
    emptied required field switches to missing/requires_resolution; accepted proposals stay resolved.
    """
    from curriculum.source_interpreter import derive_field_operational_state

    # 1. Field starting supported/pending
    f1 = InterpretedField(
        name="proyecto",
        value="Proyecto Original",
        origin=ORIGIN_EXTRACTED,
        status=STATUS_SUPPORTED,
        review=REVIEW_PENDING,
        reason="Mención en página 1 del PDF",
        original_reason="Mención en página 1 del PDF",
    )
    state, action = derive_field_operational_state(f1)
    assert state == "needs_review"
    assert action != ""

    dossier = ImportDossier(
        source_sha256="dummy_sha",
        source_name="Plan Demo",
        page_count=5,
        version=1,
        general_fields={
            "proyecto": f1,
            "contexto_propuesto": InterpretedField(
                name="contexto_propuesto",
                value="Aula escolar",
                origin=ORIGIN_PROPOSED,
                status=STATUS_AMBIGUOUS,
                review=REVIEW_PENDING,
                reason="Inferencia heurística",
                original_reason="Inferencia heurística",
            ),
        },
        sessions=[],
        selection={},
    )

    # 2. Confirm f1 explicitly: action clears, yellow warning disappears, original_reason preserved
    v2 = resolve(dossier, {"reviews": {"proyecto": "confirmed"}})
    proj = v2.general_fields["proyecto"]
    assert proj.review == REVIEW_CONFIRMED
    assert proj.current_action == ""
    assert proj.original_reason == "Mención en página 1 del PDF"
    state2, action2 = derive_field_operational_state(proj)
    assert state2 == "resolved"
    assert action2 == ""

    # 3. Explicitly confirm proposed/ambiguous field: stays ambiguous/proposed in origin/status,
    # but becomes resolved operatively with current_action cleared
    v3 = resolve(v2, {"reviews": {"contexto_propuesto": "confirmed"}})
    ctx = v3.general_fields["contexto_propuesto"]
    assert ctx.status == STATUS_AMBIGUOUS
    assert ctx.origin == ORIGIN_PROPOSED
    assert ctx.review == REVIEW_CONFIRMED
    state_ctx, action_ctx = derive_field_operational_state(ctx)
    assert state_ctx == "resolved"
    assert action_ctx == ""
    assert ctx.current_action == ""
    assert ctx.original_reason == "Inferencia heurística"

    # 4. Teacher empties a field: becomes missing, pending, requires_resolution, original_reason preserved
    v4 = resolve(v3, {"general_fields": {"proyecto": ""}})
    proj_empty = v4.general_fields["proyecto"]
    assert proj_empty.value == ""
    assert proj_empty.status == STATUS_MISSING
    assert proj_empty.review == REVIEW_PENDING
    assert proj_empty.original_reason == "Mención en página 1 del PDF"
    state_empty, action_empty = derive_field_operational_state(proj_empty)
    assert state_empty == "requires_resolution"
    assert "requiere" in action_empty.lower() or "captura" in action_empty.lower()
    assert proj_empty.current_action == action_empty


def test_f6_manual_annex_page_association_and_validation():
    """F6: Teacher can manually associate and confirm a physical PDF page (1..page_count)
    for annexes without automatic candidates. Page 0 or > page_count are strictly rejected.
    """
    dossier = ImportDossier(
        source_sha256="dummy_sha",
        source_name="Plan Demo",
        page_count=5,
        version=1,
        general_fields={},
        sessions=[
            SessionPlan(
                session_id="p2_s1",
                session_number=1,
                title="Sesión 1",
                pages=[2],
                annex_references=[
                    AnnexReference(
                        annex_number="3",
                        raw_mention="Recortar las figuras del Anexo 3",
                        source_pages=[2],
                        candidate_pages=[],  # No automatic candidates detected!
                        status=STATUS_SUPPORTED,
                        review=REVIEW_PENDING,
                        reason="Sin lámina detectada automáticamente",
                    )
                ],
            )
        ],
        selection={"session_id": "p2_s1", "session_number": 1},
    )

    # 1. Invalid manual page 0 -> ValueError (rejected before mutation)
    with pytest.raises(ValueError, match="rango"):
        resolve(
            dossier,
            {
                "session_id": "p2_s1",
                "annex_confirmations": {"3": "0"},
            },
        )
    assert dossier.version == 1

    # 2. Invalid manual page > page_count (page 6 in a 5-page PDF) -> ValueError
    with pytest.raises(ValueError, match="rango"):
        resolve(
            dossier,
            {
                "session_id": "p2_s1",
                "annex_confirmations": {"3": "6"},
            },
        )
    assert dossier.version == 1

    # 3. Valid manual page (pág 5) -> Associated and confirmed with physical evidence!
    dossier.annex_candidates = [{"page": 5, "label": "Lámina manual Anexo 3"}]
    pdf_source = (b"%PDF-1.4", dossier.source_sha256, ["p1", "p2", "p3", "p4", "Lámina manual Anexo 3"])
    v2 = resolve(
        dossier,
        {
            "session_id": "p2_s1",
            "annex_confirmations": {"3": "5"},
        },
        pdf_source=pdf_source,
    )
    assert v2.version == 2
    annex = v2.sessions[0].annex_references[0]
    assert annex.confirmed_page == 5
    assert annex.review == REVIEW_CONFIRMED
    assert annex.status == STATUS_SUPPORTED
    assert annex.origin == "teacher_selected_source_page"
    # candidate_pages remains untouched (still [])
    assert annex.candidate_pages == []
    # Delta recorded
    delta = v2.history[-1]["deltas"][0]
    assert delta["scope"] == "annex"
    assert delta["field"] == "annex_3"
    assert delta["before"]["confirmed_page"] is None
    assert delta["after"]["confirmed_page"] == 5
    assert delta["after"]["origin"] == "teacher_selected_source_page"

    # 4. Disassociate manual annex: returns to unconfirmed/pending
    v3 = resolve(
        v2,
        {
            "session_id": "p2_s1",
            "annex_confirmations": {"3": ""},
        },
        pdf_source=pdf_source,
    )
    assert v3.version == 3
    annex_dis = v3.sessions[0].annex_references[0]
    assert annex_dis.confirmed_page is None
    assert annex_dis.review == REVIEW_PENDING
    assert annex_dis.origin == ORIGIN_EXTRACTED


def test_b4_parse_canonical_positive_int_strict_types():
    """B4: parse_canonical_positive_int accepts int > 0 or canonical string ^[1-9][0-9]*$.
    Rejects bool, float, negative/zero, and non-canonical string representations.
    """
    from curriculum.source_interpreter import parse_canonical_positive_int

    assert parse_canonical_positive_int(1) == 1
    assert parse_canonical_positive_int(42) == 42
    assert parse_canonical_positive_int("1") == 1
    assert parse_canonical_positive_int("42") == 42

    # Strict rejection of non-int / non-canonical types
    for invalid in [
        True,
        False,
        1.0,
        1.5,
        0,
        -1,
        "+1",
        "-1",
        "01",
        " 1 ",
        "1 ",
        " 1",
        "1.0",
        "1e0",
        "",
        " ",
        None,
        [],
        {},
    ]:
        with pytest.raises(ValueError):
            parse_canonical_positive_int(invalid)


def test_b1_history_delta_and_entry_schema_and_complete_snapshots():
    """B1: Every delta in resolve/reextract has change_type and complete before/after snapshots."""
    from curriculum.source_interpreter import HistoryDelta, HistoryEntry

    dossier = ImportDossier(
        source_sha256="sha123",
        source_name="Test Doc",
        page_count=5,
        version=1,
        general_fields={
            "proyecto": InterpretedField(
                name="proyecto",
                value="Proyecto A",
                origin=ORIGIN_EXTRACTED,
                status=STATUS_SUPPORTED,
                review=REVIEW_PENDING,
                reason="En página 1",
                original_value="Proyecto A",
                evidence=[SourceReference("sha123", 1, "Pág 1", "Texto A")],
            )
        },
        sessions=[
            SessionPlan(
                session_id="p1_s1",
                session_number=1,
                title="Sesión 1",
                pages=[1],
                annex_references=[
                    AnnexReference(
                        annex_number="1",
                        raw_mention="Anexo 1",
                        source_pages=[1],
                        candidate_pages=[3],
                        status=STATUS_SUPPORTED,
                        review=REVIEW_PENDING,
                    )
                ],
            )
        ],
    )

    # 1. resolve() delta has change_type and complete before/after
    v2 = resolve(dossier, {"general_fields": {"proyecto": "Proyecto B"}})
    h_entry = v2.history[-1]
    assert "deltas" in h_entry
    delta = h_entry["deltas"][0]
    assert delta["change_type"] == "modified"
    assert delta["scope"] == "general"
    assert delta["field"] == "proyecto"
    assert "stable_id" in delta
    # before and after must be complete (including name, original_value, evidence)
    assert delta["before"]["name"] == "proyecto"
    assert delta["before"]["original_value"] == "Proyecto A"
    assert delta["before"]["value"] == "Proyecto A"
    assert len(delta["before"]["evidence"]) == 1
    assert delta["after"]["value"] == "Proyecto B"
    assert delta["after"]["origin"] == ORIGIN_TEACHER_ENTERED

    # 2. from_dict normalizes non-dict legacy history without 500
    legacy_data = dossier.to_dict()
    legacy_data["history"] = [
        "raw string history item from old script",
        12345,
        {"action": "legacy_action", "summary": "Old entry without deltas"},
    ]
    loaded_dossier = ImportDossier.from_dict(legacy_data)
    assert len(loaded_dossier.history) == 3
    assert all(isinstance(h, dict) for h in loaded_dossier.history)
    assert loaded_dossier.history[0]["action"] in ("legacy_raw", "legacy_entry")
    assert loaded_dossier.history[2]["deltas"] == []


def test_b2_reextract_stable_session_diff_when_page_moves():
    """B2: Same session moving from p1 to p2 is recognized as 'modified' session_id, not removed+added."""
    from curriculum.source_interpreter import compute_reextract_diff

    old_d = ImportDossier(
        source_sha256="old_sha",
        source_name="Doc Old",
        page_count=5,
        version=1,
        sessions=[
            SessionPlan(
                session_id="p1_s1",
                session_number=1,
                title="Sesión 1: Convivencia",
                project_title="Proyecto Escolar",
                pages=[1],
                fields={
                    "inicio": InterpretedField(name="inicio", value="Actividad inicio", status=STATUS_SUPPORTED)
                },
                annex_references=[
                    AnnexReference(
                        annex_number="1",
                        raw_mention="Anexo 1",
                        source_pages=[1],
                        candidate_pages=[4],
                        status=STATUS_SUPPORTED,
                    )
                ],
            )
        ],
    )

    # In new extraction, session content moved to page 2 -> session_id becomes p2_s1
    new_d = ImportDossier(
        source_sha256="new_sha",
        source_name="Doc New",
        page_count=5,
        version=2,
        sessions=[
            SessionPlan(
                session_id="p2_s1",
                session_number=1,
                title="Sesión 1: Convivencia",
                project_title="Proyecto Escolar",
                pages=[2],
                fields={
                    "inicio": InterpretedField(name="inicio", value="Actividad inicio", status=STATUS_SUPPORTED)
                },
                annex_references=[
                    AnnexReference(
                        annex_number="1",
                        raw_mention="Anexo 1",
                        source_pages=[2],
                        candidate_pages=[5],
                        status=STATUS_SUPPORTED,
                    )
                ],
            )
        ],
    )

    deltas = compute_reextract_diff(old_d, new_d)
    # Must NOT produce a removed session + added session!
    session_adds = [d for d in deltas if d["scope"] == "session" and d["field"] == "session" and d["change_type"] == "added"]
    session_removes = [d for d in deltas if d["scope"] == "session" and d["field"] == "session" and d["change_type"] == "removed"]
    assert len(session_adds) == 0, f"Unexpected session adds: {session_adds}"
    assert len(session_removes) == 0, f"Unexpected session removes: {session_removes}"

    # Must produce modified session_id delta
    sid_delta = next((d for d in deltas if d["scope"] == "session" and d["field"] == "session_id"), None)
    assert sid_delta is not None
    assert sid_delta["change_type"] == "modified"
    assert sid_delta["before"]["session_id"] == "p1_s1"
    assert sid_delta["after"]["session_id"] == "p2_s1"


def test_b3_legacy_f4_no_invention_and_central_derivation():
    """B3: Loading legacy dict without original_reason keeps original_reason=None.
    current_action is centrally derived and does not trust stale legacy text.
    """
    from curriculum.source_interpreter import derive_field_operational_state

    # 1. Legacy dict without original_reason
    legacy_field_data = {
        "name": "inicio",
        "value": "",  # missing / empty
        "origin": ORIGIN_EXTRACTED,
        "status": STATUS_MISSING,
        "review": REVIEW_PENDING,
        "reason": "CURRENT ACTION MESSAGE",
        "action_required": "STALE OLD ACTION",
        "current_action": "STALE OLD ACTION",
    }
    field_obj = InterpretedField.from_dict(legacy_field_data)
    # original_reason must NOT be copied from reason!
    assert field_obj.original_reason is None or field_obj.original_reason == ""
    # current_action must be derived centrally, ignoring "STALE OLD ACTION"
    assert field_obj.current_action != "STALE OLD ACTION"
    assert "requiere captura" in field_obj.current_action.lower()


def test_b5_manual_annex_association_evidence():
    """B5: Associating a manual page adds a SourceReference with role='teacher_selected_source_page'.
    Disassociation removes that reference.
    """
    dossier = ImportDossier(
        source_sha256="sha_pdf_5",
        source_name="Doc 5",
        page_count=5,
        version=1,
        sessions=[
            SessionPlan(
                session_id="p1_s1",
                session_number=1,
                title="Sesión 1",
                pages=[1],
                annex_references=[
                    AnnexReference(
                        annex_number="2",
                        raw_mention="Anexo 2",
                        source_pages=[1],
                        candidate_pages=[],
                        status=STATUS_SUPPORTED,
                        evidence=[],  # No initial candidate evidence
                    )
                ],
            )
        ],
        selection={"session_id": "p1_s1", "session_number": 1},
    )

    # 1. Without physical PDF, selection is honest pending review and creates NO false evidence
    v_no_pdf = resolve(
        dossier,
        {
            "session_id": "p1_s1",
            "annex_confirmations": {"2": 4},
        },
    )
    annex_no_pdf = v_no_pdf.sessions[0].annex_references[0]
    assert annex_no_pdf.confirmed_page == 4
    assert annex_no_pdf.review == REVIEW_PENDING
    assert not any(getattr(ev, "role", "") == "teacher_selected_source_page" for ev in annex_no_pdf.evidence)

    # 2. With verified physical PDF text, confirmed and creates SourceReference
    dossier.annex_candidates = [{"page": 4, "label": "Lámina Anexo 2"}]
    pdf_source = (b"%PDF-1.4", dossier.source_sha256, ["p1", "p2", "p3", "Lámina Anexo 2", "p5"])
    v2 = resolve(
        dossier,
        {
            "session_id": "p1_s1",
            "annex_confirmations": {"2": 4},
            "manual_annex_confirmations": {"2": {"page": 4, "confirmed": True}},
        },
        pdf_source=pdf_source,
    )
    annex = v2.sessions[0].annex_references[0]
    assert annex.confirmed_page == 4
    assert annex.review == REVIEW_CONFIRMED
    manual_ev = next((ev for ev in annex.evidence if getattr(ev, "role", "") == "teacher_selected_source_page"), None)
    assert manual_ev is not None
    assert manual_ev.page_number == 4
    assert manual_ev.document_sha256 == "sha_pdf_5"
    assert manual_ev.excerpt == "Lámina Anexo 2"

    # Disassociation removes it
    v3 = resolve(
        v2,
        {
            "session_id": "p1_s1",
            "annex_confirmations": {"2": ""},
        },
        pdf_source=pdf_source,
    )
    annex_v3 = v3.sessions[0].annex_references[0]
    assert annex_v3.confirmed_page is None
    manual_ev_v3 = next((ev for ev in annex_v3.evidence if getattr(ev, "role", "") == "teacher_selected_source_page"), None)
    assert manual_ev_v3 is None


def test_b6_annex_reference_id_unique_and_no_collision():
    """B6: Duplicate annex_number in same session gets unique reference_id.
    resolve updates only the targeted reference_id.
    """
    sess = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        annex_references=[
            AnnexReference(
                annex_number="1",
                raw_mention="Primer anexo 1",
                source_pages=[1],
                candidate_pages=[3],
            ),
            AnnexReference(
                annex_number="1",
                raw_mention="Segundo anexo 1 (distinto tema)",
                source_pages=[1],
                candidate_pages=[4],
            ),
        ],
    )
    # Ensure reference_ids exist and are distinct
    assert hasattr(sess.annex_references[0], "reference_id")
    ref0 = sess.annex_references[0]
    ref1 = sess.annex_references[1]
    # If not assigned yet, ensure they are unique once instantiated or normalized
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc",
        page_count=5,
        sessions=[sess],
        selection={"session_id": "p1_s1"},
    )
    dossier_loaded = ImportDossier.from_dict(dossier.to_dict())
    r0 = dossier_loaded.sessions[0].annex_references[0]
    r1 = dossier_loaded.sessions[0].annex_references[1]
    assert r0.reference_id != ""
    assert r1.reference_id != ""
    assert r0.reference_id != r1.reference_id

    # Resolving using r1's reference_id should ONLY update r1, not r0!
    v2 = resolve(
        dossier_loaded,
        {
            "session_id": "p1_s1",
            "annex_confirmations": {r1.reference_id: 4},
        },
    )
    target_r0 = v2.sessions[0].annex_references[0]
    target_r1 = v2.sessions[0].annex_references[1]
    assert target_r0.confirmed_page is None
    assert target_r1.confirmed_page == 4


def test_b1_rereview_session_movement_delta_complete_snapshots_and_resilient_history_entry():
    """B1 rereview: Session movement delta must have complete SessionPlan before/after snapshots.
    HistoryEntry.from_dict must never raise on malformed version/deltas and must not invent deltas.
    """
    old_s = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        project_title="Proyecto A",
        pages=[1],
        fields={
            "inicio": InterpretedField(name="inicio", value="Actividad 1"),
        },
    )
    new_s = SessionPlan(
        session_id="p2_s1",
        session_number=1,
        title="Sesión 1",
        project_title="Proyecto A",
        pages=[2],
        fields={
            "inicio": InterpretedField(name="inicio", value="Actividad 1"),
        },
    )
    old_d = ImportDossier(
        source_sha256="sha1",
        source_name="doc",
        page_count=5,
        sessions=[old_s],
        selection={"session_id": "p1_s1"},
    )
    new_d = ImportDossier(
        source_sha256="sha1",
        source_name="doc",
        page_count=5,
        sessions=[new_s],
        selection={"session_id": "p2_s1"},
    )
    diff = compute_reextract_diff(old_d, new_d)
    move_deltas = [d for d in diff if d.get("field") == "session_id"]
    assert len(move_deltas) == 1
    d = move_deltas[0]
    assert d.get("change_type") == "modified"
    # before and after must be full SessionPlan snapshots
    assert isinstance(d["before"], dict)
    assert d["before"]["session_id"] == "p1_s1"
    assert "fields" in d["before"]
    assert "annex_references" in d["before"]
    assert isinstance(d["after"], dict)
    assert d["after"]["session_id"] == "p2_s1"
    assert "fields" in d["after"]
    assert "annex_references" in d["after"]

    # HistoryEntry.from_dict resilience
    entry_bad_ver = HistoryEntry.from_dict({"version": "bad"})
    assert entry_bad_ver.version == 0

    # HistoryEntry.from_dict must NOT create dummy HistoryDelta from {"foo": "bar"}
    entry_bad_delta = HistoryEntry.from_dict({"deltas": [{"foo": "bar"}]})
    assert entry_bad_delta.deltas == []

    # Non-dict inputs
    assert HistoryEntry.from_dict(None).action in ("legacy_raw", "legacy_malformed", "unknown")
    assert HistoryEntry.from_dict("raw_str").version == 0
    assert HistoryEntry.from_dict(123).version == 0


def test_b2_rereview_content_fingerprint_session_matching_swap_and_annex_continuity():
    """B2 rereview: Content fingerprint matching distinguishes swapped sessions with same headers.
    Annex reference_id does not churn when session moves physical pages.
    """
    # Swap probe: Two sessions with identical headers, different contents
    s1_old = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Mismo Título",
        project_title="Mismo Proyecto",
        pages=[1],
        fields={"inicio": InterpretedField(name="inicio", value="Contenido Alfa")},
    )
    s2_old = SessionPlan(
        session_id="p1_s1_2",
        session_number=1,
        title="Mismo Título",
        project_title="Mismo Proyecto",
        pages=[1],
        fields={"inicio": InterpretedField(name="inicio", value="Contenido Beta")},
    )
    # In new document, order is swapped
    s1_new = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Mismo Título",
        project_title="Mismo Proyecto",
        pages=[1],
        fields={"inicio": InterpretedField(name="inicio", value="Contenido Beta")},
    )
    s2_new = SessionPlan(
        session_id="p1_s1_2",
        session_number=1,
        title="Mismo Título",
        project_title="Mismo Proyecto",
        pages=[1],
        fields={"inicio": InterpretedField(name="inicio", value="Contenido Alfa")},
    )

    d_old = ImportDossier(source_sha256="sha", source_name="doc", page_count=5, sessions=[s1_old, s2_old])
    d_new = ImportDossier(source_sha256="sha", source_name="doc", page_count=5, sessions=[s1_new, s2_new])
    diff = compute_reextract_diff(d_old, d_new)

    # Content-based match should match s1_old (Alfa) with s2_new (Alfa), and s2_old (Beta) with s1_new (Beta).
    # Since their contents are unchanged (only positions swapped), there should be NO field modification deltas!
    field_mods = [d for d in diff if d.get("scope") == "session" and d.get("field") == "inicio"]
    assert len(field_mods) == 0, f"Expected 0 field modifications on swap, got: {field_mods}"

    # Annex continuity probe:
    ref_orig = AnnexReference(annex_number="1", raw_mention="Anexo 1", source_pages=[1], candidate_pages=[3])
    sess_with_annex_p1 = SessionPlan(session_id="p1_s1", session_number=1, title="S1", pages=[1], annex_references=[ref_orig])
    doss_p1 = ImportDossier(source_sha256="sha", source_name="doc", page_count=5, sessions=[sess_with_annex_p1])
    doss_p1_loaded = ImportDossier.from_dict(doss_p1.to_dict())
    r_id_p1 = doss_p1_loaded.sessions[0].annex_references[0].reference_id

    # Move session to p2
    ref_moved = AnnexReference(annex_number="1", raw_mention="Anexo 1", source_pages=[2], candidate_pages=[3])
    sess_with_annex_p2 = SessionPlan(session_id="p2_s1", session_number=1, title="S1", pages=[2], annex_references=[ref_moved])
    doss_p2 = ImportDossier(source_sha256="sha", source_name="doc", page_count=5, sessions=[sess_with_annex_p2])
    doss_p2_loaded = ImportDossier.from_dict(doss_p2.to_dict())
    r_id_p2 = doss_p2_loaded.sessions[0].annex_references[0].reference_id

    # Reference ID must NOT churn due to physical page change!
    assert r_id_p1 == r_id_p2

    # And diff should NOT report annex as removed+added
    diff_annex = compute_reextract_diff(doss_p1_loaded, doss_p2_loaded)
    annex_churn = [d for d in diff_annex if d.get("scope") == "annex" and d.get("change_type") in ("added", "removed")]
    assert len(annex_churn) == 0, f"Expected no annex churn on session page move, got: {annex_churn}"


def test_b3_rereview_empty_field_cannot_be_confirmed_and_derivation_preserved():
    """B3 rereview: An empty field must not be marked confirmed or have empty current_action."""
    f_empty = InterpretedField(name="cierre", value="", status=STATUS_MISSING, review=REVIEW_PENDING)
    sess = SessionPlan(session_id="p1_s1", session_number=1, title="S1", pages=[1], fields={"cierre": f_empty})
    dossier = ImportDossier(source_sha256="sha", source_name="doc", page_count=5, sessions=[sess], selection={"session_id": "p1_s1"})

    # Try to confirm an empty field
    v2 = resolve(dossier, {"session_id": "p1_s1", "reviews": {"cierre": REVIEW_CONFIRMED}})
    res_field = v2.sessions[0].fields["cierre"]
    assert res_field.review != REVIEW_CONFIRMED
    assert res_field.operational_state == "requires_resolution"
    assert res_field.current_action != ""


def test_b4_rereview_strict_resolve_session_number_and_whitespace_annex_rejection():
    """B4 rereview: resolve rejects whitespace session_number and whitespace annex page choice."""
    sess = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="S1",
        pages=[1],
        annex_references=[
            AnnexReference(annex_number="1", raw_mention="Anexo 1", source_pages=[1], candidate_pages=[3], confirmed_page=3)
        ],
    )
    dossier = ImportDossier(source_sha256="sha", source_name="doc", page_count=5, sessions=[sess], selection={"session_id": "p1_s1"})

    # Whitespace session_number must raise SelectionError
    with pytest.raises(SelectionError):
        resolve(dossier, {"session_id": "p1_s1", "session_number": " "})
    with pytest.raises(SelectionError):
        resolve(dossier, {"session_id": "p1_s1", "session_number": "\t"})
    with pytest.raises(SelectionError):
        resolve(dossier, {"session_id": "p1_s1", "session_number": "+1"})

    # Whitespace in annex_confirmations must raise ValueError (not silently unconfirm)
    with pytest.raises(ValueError):
        resolve(dossier, {"session_id": "p1_s1", "annex_confirmations": {"1": " "}})
    with pytest.raises(ValueError):
        resolve(dossier, {"session_id": "p1_s1", "annex_confirmations": {"1": "\t"}})


def test_b5_rereview_idempotent_manual_evidence_repair_and_clean_disassociation():
    """B5 rereview:
    1) If already confirmed but missing/stale manual evidence, re-confirming repairs it and emits delta.
    2) If confirmed_page is None but stale manual evidence exists, disassociating cleans it and emits delta.
    """
    # 1) Already confirmed at page 3, but NO manual evidence
    annex1 = AnnexReference(
        annex_number="1",
        raw_mention="Anexo 1",
        source_pages=[1],
        candidate_pages=[],
        confirmed_page=3,
        review=REVIEW_CONFIRMED,
        evidence=[],  # Missing manual evidence
    )
    sess1 = SessionPlan(session_id="p1_s1", session_number=1, title="S1", pages=[1], annex_references=[annex1])
    doss1 = ImportDossier(source_sha256="hash_pdf", source_name="doc", page_count=5, sessions=[sess1], selection={"session_id": "p1_s1"})
    doss1.annex_candidates = [{"page": 3, "label": "Lámina del Anexo 1"}]
    pdf_source = (b"%PDF-1.4", "hash_pdf", ["p1", "p2", "Lámina del Anexo 1", "p4", "p5"])

    prev_v1 = doss1.version
    v2 = resolve(
        doss1,
        {
            "session_id": "p1_s1",
            "annex_confirmations": {annex1.reference_id or "1": 3},
            "manual_annex_confirmations": {annex1.reference_id or "1": {"page": 3, "confirmed": True}},
        },
        pdf_source=pdf_source,
    )
    # Evidence must now be repaired
    annex_v2 = v2.sessions[0].annex_references[0]
    manual_evs = [ev for ev in annex_v2.evidence if getattr(ev, "role", "") == "teacher_selected_source_page"]
    assert len(manual_evs) == 1
    assert manual_evs[0].page_number == 3
    assert manual_evs[0].document_sha256 == "hash_pdf"
    assert manual_evs[0].excerpt == "Lámina del Anexo 1"
    # A delta must have been registered for this repair
    assert v2.version == prev_v1 + 1

    # 2) confirmed_page is None, but has a stale manual evidence
    stale_ev = SourceReference(role="teacher_selected_source_page", page_number=2, document_sha256="old_hash")
    annex2 = AnnexReference(
        annex_number="2",
        raw_mention="Anexo 2",
        source_pages=[1],
        candidate_pages=[],
        confirmed_page=None,
        evidence=[stale_ev],
    )
    sess2 = SessionPlan(session_id="p1_s1", session_number=1, title="S1", pages=[1], annex_references=[annex2])
    doss2 = ImportDossier(source_sha256="hash_pdf", source_name="doc", page_count=5, sessions=[sess2], selection={"session_id": "p1_s1"})

    prev_v2 = doss2.version
    v3 = resolve(
        doss2,
        {
            "session_id": "p1_s1",
            "annex_confirmations": {annex2.reference_id or "2": ""},
        },
    )
    annex_v3 = v3.sessions[0].annex_references[0]
    manual_evs_v3 = [ev for ev in annex_v3.evidence if getattr(ev, "role", "") == "teacher_selected_source_page"]
    assert len(manual_evs_v3) == 0
    assert v3.version == prev_v2 + 1


def test_b6_rereview_reference_id_sanitization_and_collision_detection():
    """B6 rereview:
    1) Malformed/adversarial reference_id is sanitized/regenerated.
    2) Duplicate reference_id in session raises ValueError instead of silent first().
    3) Key matching reference_id of one annex and annex_number of another raises ValueError.
    """
    # 1) Adversarial reference_id
    annex_adv = AnnexReference(
        annex_number="1",
        raw_mention="Anexo",
        reference_id='x" onfocus="bad',
    )
    sess = SessionPlan(session_id="p1_s1", session_number=1, title="S1", pages=[1], annex_references=[annex_adv])
    doss = ImportDossier(source_sha256="hash", source_name="doc", page_count=5, sessions=[sess])
    doss_loaded = ImportDossier.from_dict(doss.to_dict())
    clean_id = doss_loaded.sessions[0].annex_references[0].reference_id
    assert '<' not in clean_id and '"' not in clean_id and ' ' not in clean_id
    assert re.match(r"^[a-zA-Z0-9_-]+$", clean_id)

    # 2) Duplicate reference_id raises ValueError
    annex_dup1 = AnnexReference(annex_number="1", raw_mention="A1", reference_id="same_id", candidate_pages=[2])
    annex_dup2 = AnnexReference(annex_number="2", raw_mention="A2", reference_id="same_id", candidate_pages=[2])
    sess_dup = SessionPlan(session_id="p1_s1", session_number=1, title="S1", pages=[1], annex_references=[annex_dup1, annex_dup2])
    doss_dup = ImportDossier(source_sha256="hash", source_name="doc", page_count=5, sessions=[sess_dup], selection={"session_id": "p1_s1"})
    with pytest.raises(ValueError, match="[Aa]mbigua|[Dd]uplicad"):
        resolve(doss_dup, {"session_id": "p1_s1", "annex_confirmations": {"same_id": 2}})

    # 3) Key collision: reference_id of one equals annex_number of another
    annex_c1 = AnnexReference(annex_number="2", raw_mention="A1", reference_id="target", candidate_pages=[2])
    annex_c2 = AnnexReference(annex_number="target", raw_mention="A2", reference_id="other", candidate_pages=[2])
    sess_col = SessionPlan(session_id="p1_s1", session_number=1, title="S1", pages=[1], annex_references=[annex_c1, annex_c2])
    doss_col = ImportDossier(source_sha256="hash", source_name="doc", page_count=5, sessions=[sess_col], selection={"session_id": "p1_s1"})
    with pytest.raises(ValueError, match="[Aa]mbigua|[Cc]olis"):
        resolve(doss_col, {"session_id": "p1_s1", "annex_confirmations": {"target": 2}})


def test_b1_final_review_history_and_deltas_deserialization_no_500():
    """B1 final review:
    1) history=3 does not raise TypeError, normalizes safely.
    2) history=[{"version": {}, "schema_version": [], "deltas": 3}] does not raise.
    3) delta with non-dict before/after is rejected by HistoryDelta.from_dict.
    4) Template renders successfully with degraded entries.
    """
    from django.template.loader import render_to_string

    # 1) history=3
    d1 = ImportDossier.from_dict({"history": 3, "page_count": 1})
    assert isinstance(d1.history, list)

    # 2) version: {}, schema_version: [], deltas: 3
    d2 = ImportDossier.from_dict({"history": [{"version": {}, "schema_version": [], "deltas": 3}], "page_count": 1})
    assert isinstance(d2.history, list)
    assert len(d2.history) == 1
    assert d2.history[0]["version"] == 0
    assert d2.history[0]["deltas"] == []

    # 3) delta with non-dict before/after
    with pytest.raises(ValueError, match="dict"):
        HistoryDelta.from_dict({
            "scope": "session",
            "field": "inicio",
            "change_type": "modified",
            "before": "bad",
            "after": 7,
        })

    # HistoryEntry filters out the invalid delta
    entry = HistoryEntry.from_dict({
        "version": 1,
        "action": "resolve",
        "deltas": [{"scope": "session", "field": "inicio", "change_type": "modified", "before": "bad", "after": 7}],
    })
    assert entry.deltas == []

    # 4) Template renders without 500
    mock_job = type("MockJob", (), {"pk": 1})()
    html = render_to_string("curriculum/tutor_import_interpretation.html", {
        "dossier": d2,
        "job": mock_job,
        "selected_session": None,
        "campos_formativos_options": [],
    })
    assert "Historial de Decisiones Editoriales y Auditoría" in html


def test_b2_final_review_ambiguous_identity_when_multiple_repeated_sessions_change_simultaneously():
    """B2 final review:
    When a group has >1 sessions with identical semantic headers, and both change content simultaneously
    (so no fingerprint matches), do NOT arbitrarily pair them 1-to-1 in order.
    Instead, emit delta with change_type="ambiguous_identity" and before/after lists of candidates.
    """
    s1_old = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Repetida",
        project_title="Proyecto",
        pages=[1],
        fields={"inicio": InterpretedField(name="inicio", value="Contenido Alfa Antiguo")},
    )
    s2_old = SessionPlan(
        session_id="p1_s1_2",
        session_number=1,
        title="Repetida",
        project_title="Proyecto",
        pages=[1],
        fields={"inicio": InterpretedField(name="inicio", value="Contenido Beta Antiguo")},
    )
    # Both change content simultaneously in new document
    s1_new = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Repetida",
        project_title="Proyecto",
        pages=[1],
        fields={"inicio": InterpretedField(name="inicio", value="Contenido Gamma Nuevo")},
    )
    s2_new = SessionPlan(
        session_id="p1_s1_2",
        session_number=1,
        title="Repetida",
        project_title="Proyecto",
        pages=[1],
        fields={"inicio": InterpretedField(name="inicio", value="Contenido Delta Nuevo")},
    )

    d_old = ImportDossier(source_sha256="sha", source_name="doc", page_count=2, sessions=[s1_old, s2_old])
    d_new = ImportDossier(source_sha256="sha", source_name="doc", page_count=2, sessions=[s1_new, s2_new])
    diff = compute_reextract_diff(d_old, d_new)

    ambig_deltas = [d for d in diff if d.get("change_type") == "ambiguous_identity"]
    assert len(ambig_deltas) == 1
    d_ambig = ambig_deltas[0]
    assert d_ambig["scope"] == "session"
    assert isinstance(d_ambig["before"], list)
    assert len(d_ambig["before"]) == 2
    assert isinstance(d_ambig["after"], list)
    assert len(d_ambig["after"]) == 2
    assert d_ambig.get("confidence") == "ambiguous"

    # No fake added or removed deltas
    add_rem_deltas = [d for d in diff if d.get("change_type") in ("added", "removed")]
    assert len(add_rem_deltas) == 0


def test_b3_final_review_legacy_empty_field_normalized_never_confirmed_or_corrected():
    """B3 final review:
    1) Legacy field with empty value and review confirmed/corrected normalizes to pending and requires_resolution.
    2) In resolve(), confirming an empty field or confirm_all on an empty field never leaves it confirmed.
    """
    # 1) from_dict normalization
    f_dict = {"name": "proposito", "value": "", "status": "supported", "review": "confirmed"}
    field = InterpretedField.from_dict(f_dict)
    assert field.review == REVIEW_PENDING
    assert field.status == STATUS_MISSING
    assert field.operational_state == "requires_resolution"
    assert "captura" in field.current_action.lower()

    f_dict_corr = {"name": "proposito", "value": "   ", "status": "supported", "review": "corrected"}
    field_corr = InterpretedField.from_dict(f_dict_corr)
    assert field_corr.review == REVIEW_PENDING
    assert field_corr.status == STATUS_MISSING

    # 2) In resolve(): reviews={"proposito": "confirmed"} or reviews={"__all__": "confirmed"}
    f_empty = InterpretedField(name="proposito", value="", review=REVIEW_PENDING)
    sess = SessionPlan(session_id="p1_s1", session_number=1, title="S1", pages=[1], fields={"proposito": f_empty})
    doss = ImportDossier(source_sha256="sha", source_name="doc", page_count=2, sessions=[sess], selection={"session_id": "p1_s1"})

    v2 = resolve(doss, {"session_id": "p1_s1", "reviews": {"proposito": "confirmed"}})
    f_res = v2.sessions[0].fields["proposito"]
    assert f_res.review == REVIEW_PENDING
    assert f_res.operational_state == "requires_resolution"

    v3 = resolve(doss, {"session_id": "p1_s1", "reviews": {"__all__": "confirmed"}})
    f_res3 = v3.sessions[0].fields["proposito"]
    assert f_res3.review == REVIEW_PENDING
    assert f_res3.operational_state == "requires_resolution"


def test_b4_final_review_session_number_presence_strict_rejection_of_empty_string():
    """B4 final review:
    1) If session_number is supplied (even ''), it must be parsed canonically and rejected if empty.
    2) Only absence of session_number key allows selection by session_id.
    """
    sess = SessionPlan(session_id="p1_s1", session_number=1, title="S1", pages=[1])
    doss = ImportDossier(source_sha256="sha", source_name="doc", page_count=2, sessions=[sess], selection={"session_id": "p1_s1"})

    # session_number is present as empty string -> MUST RAISE SelectionError
    with pytest.raises(SelectionError, match="session_number"):
        resolve(doss, {"session_id": "p1_s1", "session_number": ""})

    # session_number is absent -> succeeds
    prev_v = doss.version
    v2 = resolve(doss, {"session_id": "p1_s1", "general_fields": {"proposito": "Nuevo Propósito"}})
    assert v2.version == prev_v + 1


def test_b6_final_review_duplicate_reference_id_regeneration_and_legacy_tracking():
    """B6 final review:
    1) _ensure_session_annex_ids detects existing in seen and regenerates duplicate to unique canonical ID.
    2) from_dict with two 'dup' reference_ids produces two different, HTML-safe IDs.
    3) legacy_reference_ids records 'dup' for tracing.
    4) Round-trip stable.
    """
    raw_payload = {
        "source_sha256": "sha",
        "source_name": "doc",
        "page_count": 2,
        "sessions": [{
            "session_id": "p1_s1",
            "session_number": 1,
            "title": "S1",
            "pages": [1],
            "annex_references": [
                {"annex_number": "1", "raw_mention": "Anexo 1", "reference_id": "dup", "candidate_pages": [2]},
                {"annex_number": "2", "raw_mention": "Anexo 2", "reference_id": "dup", "candidate_pages": [2]},
            ],
        }],
    }
    doss = ImportDossier.from_dict(raw_payload)
    annexes = doss.sessions[0].annex_references
    assert len(annexes) == 2
    id1, id2 = annexes[0].reference_id, annexes[1].reference_id
    assert id1 != id2
    assert re.match(r"^[a-zA-Z0-9_-]+$", id1)
    assert re.match(r"^[a-zA-Z0-9_-]+$", id2)
    # Both have "dup" tracked in legacy_reference_ids
    assert "dup" in getattr(annexes[0], "legacy_reference_ids", []) or "dup" in getattr(annexes[1], "legacy_reference_ids", [])

    # Round-trip stability
    doss2 = ImportDossier.from_dict(doss.to_dict())
    annexes2 = doss2.sessions[0].annex_references
    assert annexes2[0].reference_id == id1
    assert annexes2[1].reference_id == id2


def test_f7_deriver_supported_pending_is_yellow_pending_review():
    """F7: supported + pending must be yellow ('pending_review'), never green."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        derive_operational_queue,
        PRIORITY_PENDING_REVIEW,
    )
    sess = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        fields={
            "inicio": InterpretedField(
                name="inicio",
                value="Actividad de inicio",
                status="supported",
                review="pending",
            )
        },
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=2,
        sessions=[sess],
    )
    q = derive_operational_queue(dossier, session_filter="p1_s1")
    inicio_item = next(it for it in q.items if it.field_name == "inicio")
    assert inicio_item.priority_state == PRIORITY_PENDING_REVIEW
    assert inicio_item.priority_state != "reviewed"


def test_f7_deriver_missing_required_is_red_requires_resolution():
    """F7: missing required field must be red ('requires_resolution') with blocking action."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        derive_operational_queue,
        PRIORITY_REQUIRES_RESOLUTION,
    )
    sess = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        fields={
            "inicio": InterpretedField(
                name="inicio",
                value="",
                status="missing",
                review="pending",
            )
        },
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=2,
        sessions=[sess],
    )
    q = derive_operational_queue(dossier, session_filter="p1_s1")
    inicio_item = next(it for it in q.items if it.field_name == "inicio")
    assert inicio_item.priority_state == PRIORITY_REQUIRES_RESOLUTION
    assert inicio_item.is_required is True
    assert "Bloquea" in inicio_item.blocks_action


def test_f7_deriver_optional_absent_is_neutral_not_specified():
    """F7: optional absent field must be neutral ('not_specified'), never red or blocking."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        derive_operational_queue,
        PRIORITY_NOT_SPECIFIED,
        PRIORITY_REQUIRES_RESOLUTION,
    )
    sess = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        fields={
            "materiales": InterpretedField(
                name="materiales",
                value="",
                status="missing",
                review="pending",
            ),
            "evaluacion": InterpretedField(
                name="evaluacion",
                value="",
                status="missing",
                review="pending",
            ),
        },
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=2,
        sessions=[sess],
    )
    q = derive_operational_queue(dossier, session_filter="p1_s1")
    mat_item = next(it for it in q.items if it.field_name == "materiales")
    eval_item = next(it for it in q.items if it.field_name == "evaluacion")
    assert mat_item.priority_state == PRIORITY_NOT_SPECIFIED
    assert mat_item.priority_state != PRIORITY_REQUIRES_RESOLUTION
    assert mat_item.is_required is False
    assert mat_item.blocks_action == ""
    assert eval_item.priority_state == PRIORITY_NOT_SPECIFIED


def test_f7_deriver_confirmed_or_corrected_is_green_reviewed():
    """F7: human confirmed or corrected non-empty field is green ('reviewed')."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        derive_operational_queue,
        PRIORITY_REVIEWED,
    )
    sess = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        fields={
            "inicio": InterpretedField(
                name="inicio",
                value="Inicio confirmado",
                status="supported",
                review="confirmed",
            ),
            "desarrollo": InterpretedField(
                name="desarrollo",
                value="Desarrollo editado",
                status="supported",
                review="corrected",
            ),
        },
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=2,
        sessions=[sess],
    )
    q = derive_operational_queue(dossier, session_filter="p1_s1")
    inicio_item = next(it for it in q.items if it.field_name == "inicio")
    des_item = next(it for it in q.items if it.field_name == "desarrollo")
    assert inicio_item.priority_state == PRIORITY_REVIEWED
    assert des_item.priority_state == PRIORITY_REVIEWED
    assert inicio_item.blocks_action == ""


def test_f7_deriver_conflicting_is_red_requires_resolution():
    """F7: conflicting field is blocking red ('requires_resolution')."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        derive_operational_queue,
        PRIORITY_REQUIRES_RESOLUTION,
    )
    sess = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        fields={
            "cierre": InterpretedField(
                name="cierre",
                value="Texto en conflicto",
                status="conflicting",
                review="pending",
            )
        },
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=2,
        sessions=[sess],
    )
    q = derive_operational_queue(dossier, session_filter="p1_s1")
    cierre_item = next(it for it in q.items if it.field_name == "cierre")
    assert cierre_item.priority_state == PRIORITY_REQUIRES_RESOLUTION
    assert "Conflicto" in cierre_item.problem_summary
    assert "Bloquea" in cierre_item.blocks_action


def test_f7_deriver_proposed_ambiguous_pending_is_yellow():
    """F7: proposed or ambiguous pending field is yellow ('pending_review')."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        derive_operational_queue,
        PRIORITY_PENDING_REVIEW,
    )
    sess = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        fields={
            "cierre": InterpretedField(
                name="cierre",
                value="Propuesta ambigua",
                status="ambiguous",
                origin="proposed",
                review="pending",
            )
        },
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=2,
        sessions=[sess],
    )
    q = derive_operational_queue(dossier, session_filter="p1_s1")
    cierre_item = next(it for it in q.items if it.field_name == "cierre")
    assert cierre_item.priority_state == PRIORITY_PENDING_REVIEW


def test_f7_deriver_accepted_ambiguous_is_green_reviewed_preserving_origin():
    """F7: accepted ambiguous field is green ('reviewed') preserving origin and evidence."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        SourceReference,
        derive_operational_queue,
        PRIORITY_REVIEWED,
    )
    sess = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        fields={
            "cierre": InterpretedField(
                name="cierre",
                value="Propuesta aceptada por docente",
                status="ambiguous",
                origin="proposed",
                review="confirmed",
                evidence=[SourceReference(document_sha256="sha", page_number=1, excerpt="página 1")],
            )
        },
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=2,
        sessions=[sess],
    )
    q = derive_operational_queue(dossier, session_filter="p1_s1")
    cierre_item = next(it for it in q.items if it.field_name == "cierre")
    assert cierre_item.priority_state == PRIORITY_REVIEWED
    # Preserves evidence and origin
    assert len(cierre_item.source_refs) == 1
    assert cierre_item.page_number == 1


def test_f7_deriver_general_fields_appear_once_in_document_queue():
    """F7: general fields appear exactly once in the document queue across multiple sessions."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        derive_operational_queue,
    )
    sessions = [
        SessionPlan(session_id=f"p{i}_s{i}", session_number=i, title=f"Sesión {i}", pages=[i])
        for i in range(1, 6)
    ]
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=10,
        general_fields={
            "proyecto": InterpretedField(name="proyecto", value="Proyecto Único"),
            "proposito": InterpretedField(name="proposito", value="Propósito Único"),
        },
        sessions=sessions,
    )
    q = derive_operational_queue(dossier, session_filter=None)
    proj_items = [it for it in q.items if it.field_name == "proyecto"]
    prop_items = [it for it in q.items if it.field_name == "proposito"]
    assert len(proj_items) == 1
    assert len(prop_items) == 1
    assert proj_items[0].scope == "general"


def test_f7_deriver_2_to_20_sessions_exact_counts_and_stable_order():
    """F7: scaling from 2 to 20 sessions maintains exact counts and strictly stable priority ordering."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        AnnexReference,
        derive_operational_queue,
        PRIORITY_ORDER,
    )
    for n_sessions in (2, 20):
        sessions = []
        for i in range(1, n_sessions + 1):
            sess = SessionPlan(
                session_id=f"p{i}_s{i}",
                session_number=i,
                title=f"Sesión {i}",
                pages=[i],
                fields={
                    "inicio": InterpretedField(name="inicio", value=f"Inicio {i}", status="supported", review="pending"),
                    "desarrollo": InterpretedField(name="desarrollo", value="", status="missing", review="pending"),
                    "cierre": InterpretedField(name="cierre", value=f"Cierre {i}", status="supported", review="confirmed"),
                    "materiales": InterpretedField(name="materiales", value="", status="missing", review="pending"),
                },
                annex_references=[
                    AnnexReference(annex_number="1", raw_mention="Anexo 1", source_pages=[i], candidate_pages=[]),
                ],
            )
            sessions.append(sess)

        dossier = ImportDossier(
            source_sha256="sha",
            source_name="doc.pdf",
            page_count=30,
            general_fields={
                "proyecto": InterpretedField(name="proyecto", value="Mi Proyecto", status="supported", review="confirmed"),
                "campos_formativos": InterpretedField(name="campos_formativos", value=["Lenguajes"], status="supported", review="pending"),
            },
            sessions=sessions,
        )

        q1 = derive_operational_queue(dossier)
        q2 = derive_operational_queue(dossier)

        # 1. Total counts match sum of individual priorities exactly
        sum_counts = (
            q1.requires_resolution_count
            + q1.pending_review_count
            + q1.reviewed_count
            + q1.not_specified_count
        )
        assert sum_counts == q1.total_count == len(q1.items)

        # 2. Stable deterministic ordering across repeated calls
        keys_1 = [it.stable_key for it in q1.items]
        keys_2 = [it.stable_key for it in q2.items]
        assert keys_1 == keys_2

        # 3. Priority ordering strictly monotonic (red -> yellow -> neutral -> green)
        priority_ranks = [PRIORITY_ORDER[it.priority_state] for it in q1.items]
        assert priority_ranks == sorted(priority_ranks)


def test_f7_deriver_session_filter_scope():
    """F7: session filter limits queue items to targeted session and calculates exact scoped counts."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        AnnexReference,
        derive_operational_queue,
    )
    s1 = SessionPlan(
        session_id="p1_s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        fields={
            "inicio": InterpretedField(name="inicio", value="Inicio 1", status="supported", review="confirmed"),
        },
    )
    s2 = SessionPlan(
        session_id="p2_s2",
        session_number=2,
        title="Sesión 2",
        pages=[2],
        fields={
            "inicio": InterpretedField(name="inicio", value="", status="missing", review="pending"),
        },
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=5,
        sessions=[s1, s2],
    )
    q_s1 = derive_operational_queue(dossier, session_filter="p1_s1")
    assert all(it.session_id == "p1_s1" for it in q_s1.items)
    assert q_s1.scope == "p1_s1"
    assert "Sesión 1" in q_s1.scope_label

    q_s2 = derive_operational_queue(dossier, session_filter="p2_s2")
    assert all(it.session_id == "p2_s2" for it in q_s2.items)
    assert q_s2.scope == "p2_s2"
def test_f7_deriver_conflicting_always_red_even_if_review_confirmed():
    """B5: A field with status=conflicting MUST remain requires_resolution (red) even if review=confirmed."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        STATUS_CONFLICTING,
        REVIEW_CONFIRMED,
        PRIORITY_REQUIRES_RESOLUTION,
        derive_operational_queue,
    )
    f = InterpretedField(
        name="proyecto",
        value="Proyecto en disputa",
        status=STATUS_CONFLICTING,
        review=REVIEW_CONFIRMED,
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=1,
        general_fields={"proyecto": f},
    )
    q = derive_operational_queue(dossier)
    item = next(it for it in q.items if it.field_name == "proyecto")
    assert item.priority_state == PRIORITY_REQUIRES_RESOLUTION


def test_f7_deriver_annex_without_confirmed_page_is_not_reviewed():
    """B5: An annex reference with review=confirmed but confirmed_page=None CANNOT be reviewed."""
    from curriculum.source_interpreter import (
        ImportDossier,
        AnnexReference,
        SessionPlan,
        REVIEW_CONFIRMED,
        PRIORITY_PENDING_REVIEW,
        derive_operational_queue,
    )
    ref = AnnexReference(
        annex_number="1",
        raw_mention="Anexo 1",
        candidate_pages=[3, 4],
        confirmed_page=None,
        review=REVIEW_CONFIRMED,
    )
    sess = SessionPlan(
        session_id="s1",
        session_number=1,
        title="Sesión 1",
        pages=[1],
        annex_references=[ref],
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=5,
        sessions=[sess],
    )
    q = derive_operational_queue(dossier)
    annex_item = next(it for it in q.items if it.scope == "annex")
    assert annex_item.priority_state == PRIORITY_PENDING_REVIEW


def test_f7_deriver_progress_denominator_excludes_neutral_items():
    """B6: Progress calculation uses actionable items as denominator, excluding neutral optional items."""
    from curriculum.source_interpreter import (
        ImportDossier,
        InterpretedField,
        SessionPlan,
        REVIEW_CONFIRMED,
        STATUS_SUPPORTED,
        derive_operational_queue,
    )
    # Create dossier where all required items are confirmed, and optional are missing (neutral)
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=5,
        general_fields={
            "proyecto": InterpretedField(name="proyecto", value="P", status=STATUS_SUPPORTED, review=REVIEW_CONFIRMED),
            "campos_formativos": InterpretedField(name="campos_formativos", value=["Lenguajes"], status=STATUS_SUPPORTED, review=REVIEW_CONFIRMED),
            "proposito": InterpretedField(name="proposito", value="Prop", status=STATUS_SUPPORTED, review=REVIEW_CONFIRMED),
            "finalidad": InterpretedField(name="finalidad", value="Fin", status=STATUS_SUPPORTED, review=REVIEW_CONFIRMED),
        },
        sessions=[
            SessionPlan(
                session_id="s1",
                session_number=1,
                title="Sesión 1",
                pages=[1],
                fields={
                    "inicio": InterpretedField(name="inicio", value="Ini", status=STATUS_SUPPORTED, review=REVIEW_CONFIRMED),
                    "desarrollo": InterpretedField(name="desarrollo", value="Des", status=STATUS_SUPPORTED, review=REVIEW_CONFIRMED),
                    "cierre": InterpretedField(name="cierre", value="Cie", status=STATUS_SUPPORTED, review=REVIEW_CONFIRMED),
                },
            )
        ],
    )
    q = derive_operational_queue(dossier)
    # All 7 actionable items (4 general + 3 session) are reviewed
    assert q.reviewed_count == 7
    assert q.requires_resolution_count == 0
    assert q.pending_review_count == 0
    # Optional fields are not specified (neutral)
    assert q.not_specified_count > 0
    assert q.actionable_count == 7
    assert q.progress_percent == 100
    assert q.is_completed is True


def test_f7_deriver_ambiguous_numeric_scope_raises_selection_error():
    """B4: Numeric scope filter matching multiple sessions raises SelectionError without silent misselection."""
    import pytest
    from curriculum.source_interpreter import (
        ImportDossier,
        SessionPlan,
        SelectionError,
        derive_operational_queue,
    )
    # Two sessions in different projects with session_number=1
    s1 = SessionPlan(session_id="proj1_s1", session_number=1, title="Sesión 1", pages=[1])
    s2 = SessionPlan(session_id="proj2_s1", session_number=1, title="Sesión 1", pages=[2])
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=5,
        sessions=[s1, s2],
    )
    with pytest.raises(SelectionError, match="ambiguo"):
        derive_operational_queue(dossier, session_filter="1")

    # Exact session_id disambiguates
    q1 = derive_operational_queue(dossier, session_filter="proj1_s1")
    assert q1.scope == "proj1_s1"


def test_f7_deriver_opaque_item_id_uniqueness_with_duplicate_session_ids_and_annexes():
    """B1-B3: 20 sessions and adversarial duplicate session_ids/annexes produce strictly unique item_ids."""
    from curriculum.source_interpreter import (
        ImportDossier,
        SessionPlan,
        AnnexReference,
        derive_operational_queue,
    )
    # 1. Fail-closed: duplicate session_ids or duplicate reference_ids must raise SelectionError
    sessions_dup = [
        SessionPlan(
            session_id="adversarial:dup:id",
            session_number=1,
            title="Sesión 1",
            pages=[1],
            annex_references=[
                AnnexReference(annex_number="1", raw_mention="Anexo 1", reference_id="annex_dup"),
                AnnexReference(annex_number="1", raw_mention="Anexo 1 bis", reference_id="annex_dup"),
            ],
        ),
        SessionPlan(
            session_id="adversarial:dup:id",
            session_number=2,
            title="Sesión 2",
            pages=[2],
        ),
    ]
    dossier_dup = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=25,
        sessions=sessions_dup,
    )
    with pytest.raises(SelectionError):
        derive_operational_queue(dossier_dup)

    # 2. 20 distinct sessions produce strictly unique item_ids
    sessions = []
    for i in range(20):
        sessions.append(
            SessionPlan(
                session_id=f"session:colon:{i + 1}",
                session_number=i + 1,
                title=f"Sesión {i + 1}",
                pages=[i + 1],
                annex_references=[
                    AnnexReference(annex_number="1", raw_mention="Anexo 1", reference_id=f"annex_{i + 1}_1"),
                    AnnexReference(annex_number="2", raw_mention="Anexo 2", reference_id=f"annex_{i + 1}_2"),
                ],
            )
        )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=25,
        sessions=sessions,
    )
    q = derive_operational_queue(dossier)
    item_ids = [it.item_id for it in q.items]
    assert len(item_ids) == len(set(item_ids)), f"Item IDs must be strictly unique! {len(item_ids)} total vs {len(set(item_ids))} unique"



def test_f7_residual_annex_confirmed_without_coherent_evidence_is_not_reviewed():
    """Residual: Annex with confirmed_page but empty/incoherent evidence must NOT be marked reviewed."""
    from curriculum.source_interpreter import (
        AnnexReference,
        ImportDossier,
        SessionPlan,
        PRIORITY_REVIEWED,
        derive_operational_queue,
    )
    bad_annex = AnnexReference(
        annex_number="1",
        raw_mention="Anexo 1",
        candidate_pages=[],
        confirmed_page=3,
        review="confirmed",
        source_pages=[],
        evidence=[],
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=4,
        sessions=[SessionPlan(session_id="s1", session_number=1, title="S", pages=[1], annex_references=[bad_annex])],
    )
    q = derive_operational_queue(dossier)
    item = next(it for it in q.items if it.scope == "annex")
    assert item.priority_state != PRIORITY_REVIEWED


def test_f7_target_id_delimiter_collision_elimination():
    """Point 2: Delimiter collisions like session='a', ref='b:c' vs session='a:b', ref='c' produce distinct target_ids."""
    from curriculum.source_interpreter import (
        AnnexReference,
        ImportDossier,
        SessionPlan,
        SelectionError,
        derive_operational_queue,
    )
    dossier = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=5,
        sessions=[
            SessionPlan(
                session_id="a",
                session_number=1,
                title="A",
                pages=[1],
                annex_references=[AnnexReference(annex_number="1", raw_mention="A1", reference_id="b:c")],
            ),
            SessionPlan(
                session_id="a:b",
                session_number=2,
                title="B",
                pages=[2],
                annex_references=[AnnexReference(annex_number="2", raw_mention="A2", reference_id="c")],
            ),
        ],
    )
    q = derive_operational_queue(dossier)
    annex_targets = [it.target_id for it in q.items if it.scope == "annex"]
    assert len(annex_targets) == 2
    assert annex_targets[0] != annex_targets[1], f"Targets must be distinct: {annex_targets}"


def test_f7_annex_combined_namespace_fail_closed_and_intra_ref_dedup():
    """Point 1: Combined namespace per session (canonical, number, legacy) fails closed across distinct refs and dedups within same ref."""
    from curriculum.source_interpreter import (
        AnnexReference,
        ImportDossier,
        SessionPlan,
        SelectionError,
        derive_operational_queue,
    )

    # 1. Deduplication within the SAME reference: reference_id == annex_number == legacy token
    ref_same = AnnexReference(
        annex_number="1",
        raw_mention="Anexo 1",
        reference_id="1",
        legacy_reference_ids=["1"],
    )
    d_valid = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=3,
        sessions=[SessionPlan(session_id="s1", session_number=1, title="S1", pages=[1], annex_references=[ref_same])],
    )
    q_valid = derive_operational_queue(d_valid)
    assert len([it for it in q_valid.items if it.scope == "annex"]) == 1

    # 2. Canonical vs legacy of another ref -> SelectionError
    ref_canon = AnnexReference(annex_number="1", raw_mention="A1", reference_id="canonical", legacy_reference_ids=["alias"])
    ref_other = AnnexReference(annex_number="2", raw_mention="A2", reference_id="alias")
    d_canon_alias = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=3,
        sessions=[SessionPlan(session_id="s1", session_number=1, title="S1", pages=[1], annex_references=[ref_canon, ref_other])],
    )
    with pytest.raises(SelectionError):
        derive_operational_queue(d_canon_alias)

    # 3. Number vs reference_id of another ref -> SelectionError
    ref_num = AnnexReference(annex_number="custom_id", raw_mention="A1", reference_id="ref_1")
    ref_id = AnnexReference(annex_number="2", raw_mention="A2", reference_id="custom_id")
    d_num_id = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=3,
        sessions=[SessionPlan(session_id="s1", session_number=1, title="S1", pages=[1], annex_references=[ref_num, ref_id])],
    )
    with pytest.raises(SelectionError):
        derive_operational_queue(d_num_id)

    # 4. Duplicate numbers across distinct refs -> SelectionError
    ref_dup_num1 = AnnexReference(annex_number="1", raw_mention="A1", reference_id="ref_a")
    ref_dup_num2 = AnnexReference(annex_number="1", raw_mention="A2", reference_id="ref_b")
    d_dup_num = ImportDossier(
        source_sha256="sha",
        source_name="doc.pdf",
        page_count=3,
        sessions=[SessionPlan(session_id="s1", session_number=1, title="S1", pages=[1], annex_references=[ref_dup_num1, ref_dup_num2])],
    )
    with pytest.raises(SelectionError):
        derive_operational_queue(d_dup_num)
