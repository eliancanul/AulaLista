"""GREEN tests for implicit project finality, phase-based planning, and bounded tribunal receipts.

Enforces:
1. Implicit finalidad extraction without header, strictly separating located presence from inferred role.
2. Two certainty axes: physical presence verified, semantic role remains ambiguous/teacher review pending.
3. No false candidate on generic administrative intro.
4. Physical duration across pages 1->2 preserved without converting to sessions/minutes/dates.
5. First activity on page 2 proposed as inicio, preserving all activity texts and order without loss/duplication.
6. Phases != sessions: ambiguous project review unit without invented classes.
7. Two-week plan without timetable: moments distribution editable without invented minutes or dates.
8. Bounded shadow tribunal: typed hypotheses tested against Atlas/Fakes with abstention and no claim mutation.
9. Persistence and teacher authority: resolve preserves source + edited value, no CurriculumProgress advance.
10. Regressions: explicit Finalidad kept as extracted/supported, no default 2 weeks on documents without suggestion.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from curriculum.atlas import AtlasIndex, create_synthetic_sep_fixture
from curriculum.atlas.models import AtlasDocumentFragment
from curriculum.claims import (
    AtomicClaim,
    CLAIM_STATE_BACKED,
    CLAIM_STATE_CANDIDATE,
    CLAIM_STATE_NEEDS_HUMAN_REVIEW,
    compile_dossier_to_atomic_claims,
)
from curriculum.source_interpreter import (
    ORIGIN_EXTRACTED,
    ORIGIN_PROPOSED,
    ORIGIN_TEACHER_ENTERED,
    REVIEW_CORRECTED,
    REVIEW_PENDING,
    STATUS_AMBIGUOUS,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    CurriculumSourceInterpreter,
    ImportDossier,
    resolve,
)
from curriculum.tribunal import (
    MINILM_CANDIDATE,
    NLIClass,
    NLIModelConfig,
    RawNLIOutput,
    RunStatus,
    Tribunal,
    Verdict,
    build_claim_hypothesis,
)
from curriculum.verification import (
    STATUS_BLOCKED,
    STATUS_NEEDS_TEACHER_REVIEW,
    verify_curriculum_dossier,
)
from test_t15_curriculum_import import make_minimal_pdf


def _make_fake_adapter(outputs):
    class FakeAdapter:
        def __init__(self, outs):
            self.outputs = outs
            self.calls = []

        def infer_batch(self, pairs):
            self.calls.append(pairs)
            if isinstance(self.outputs, Exception):
                raise self.outputs
            return self.outputs

    return FakeAdapter(outputs)


def _config():
    labels = {"LABEL_0": NLIClass.CONTRADICTION, "LABEL_1": NLIClass.NEUTRAL, "LABEL_2": NLIClass.ENTAILMENT}
    return NLIModelConfig(
        model_id=MINILM_CANDIDATE,
        version="synthetic-v1",
        label_mapping=labels,
        timeout_seconds=0.5,
        runtime_config={"device": "cpu"},
    )


def _score(entailment=0.0, contradiction=0.0, neutral=0.0):
    return RawNLIOutput({"LABEL_0": contradiction, "LABEL_1": neutral, "LABEL_2": entailment})


# ==============================================================================
# GREEN 1: Finalidad sin rótulo
# ==============================================================================
def test_green_1_implicit_finalidad_extracted_as_ambiguous_candidate_with_physical_provenance():
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Bosque Escenario Aula.\n"
        "Paginas de la 10 a la 25\n"
        "Explorar leyendas tradicionales sobre los animales de la region y crear un compendio colectivo "
        "ilustrado para fomentar la preservacion de la fauna silvestre en la comunidad escolar.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de Se sugiere dos",
        "aplicacion semanas\n"
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de bienvenida y dialogo sobre la fauna.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))

    fin = dossier.general_fields["finalidad"]
    expected_paragraph = (
        "Explorar leyendas tradicionales sobre los animales de la region y crear un compendio colectivo "
        "ilustrado para fomentar la preservacion de la fauna silvestre en la comunidad escolar."
    )
    assert fin.value == expected_paragraph
    assert fin.origin == ORIGIN_PROPOSED
    assert fin.status == STATUS_AMBIGUOUS
    assert fin.review == REVIEW_PENDING
    assert "inferida en portada sin encabezado" in fin.reason.lower()
    assert len(fin.evidence) == 1
    assert fin.evidence[0].page_number == 1
    assert fin.evidence[0].document_sha256 == dossier.source_sha256
    assert fin.evidence[0].excerpt.strip() != ""
    # PDA table header is NOT included
    assert "Contenidos" not in fin.value
    assert "Proceso de desarrollo" not in fin.value


def test_green_1_implicit_finalidad_with_project_word_in_purpose_body():
    """Verify that the word 'proyecto' inside purpose body does not cause truncation or premature cutting."""
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Huellas Comunitarias Escenario Aula.\n"
        "Paginas de la 10 a la 25\n"
        "Organizar brigadas escolares con la finalidad de diseñar un proyecto comunitario sobre el reciclaje "
        "y cuidado del medio ambiente en la escuela para sensibilizar a la poblacion estudiantil.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de diagnostico sobre residuos.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    fin = dossier.general_fields["finalidad"]
    expected_paragraph = (
        "Organizar brigadas escolares con la finalidad de diseñar un proyecto comunitario sobre el reciclaje "
        "y cuidado del medio ambiente en la escuela para sensibilizar a la poblacion estudiantil."
    )
    assert fin.value == expected_paragraph
    assert "proyecto comunitario" in fin.value
    assert fin.origin == ORIGIN_PROPOSED
    assert fin.status == STATUS_AMBIGUOUS
    assert fin.review == REVIEW_PENDING
    assert len(fin.evidence) == 1
    assert fin.evidence[0].page_number == 1
    assert fin.evidence[0].document_sha256 == dossier.source_sha256
    assert fin.evidence[0].excerpt.strip() != ""
    assert "Contenidos" not in fin.value
    assert "Proceso de desarrollo" not in fin.value

    # Physical verification passes without blocking
    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0

    # Also verify case with wrapped line starting with 'proyecto' without separate header
    pages_without_header = [
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Investigar la historia comunitaria para elaborar un\n"
        "proyecto de rescate cultural en la escuela primaria y compartir relatos.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields = CurriculumSourceInterpreter._extract_general_fields(pages_without_header, dossier.source_sha256, {})
    fin_wrapped = fields["finalidad"]
    assert fin_wrapped.value == (
        "Investigar la historia comunitaria para elaborar un "
        "proyecto de rescate cultural en la escuela primaria y compartir relatos."
    )
    assert fin_wrapped.status == STATUS_AMBIGUOUS


def test_green_1_implicit_finalidad_cuts_before_multiline_table_column_headers():
    """Verify that table headers on independent lines (multiline table structure) do not leak into finalidad."""
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3\n"
        "Proyecto Guardianes del Bosque Escenario Aula.\n"
        "Paginas de la 12 a la 24\n"
        "Explorar leyendas tradicionales sobre los animales de la region para crear un compendio colectivo ilustrado.\n"
        "Campos formativos\n"
        "Lenguajes\n"
        "Contenidos\n"
        "Narracion y descripcion de hechos comunitarios\n"
        "Procesos de desarrollo de aprendizaje\n"
        "Identifica y comprende relatos orales de su localidad\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de lectura de leyendas.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    fin = dossier.general_fields["finalidad"]

    assert fin.value == (
        "Explorar leyendas tradicionales sobre los animales de la region para crear un compendio colectivo ilustrado."
    )
    assert fin.origin == ORIGIN_PROPOSED
    assert fin.status == STATUS_AMBIGUOUS
    assert fin.review == REVIEW_PENDING
    assert len(fin.evidence) == 1
    assert fin.evidence[0].page_number == 1

    # Table columns and values on independent lines are NOT absorbed
    assert "Campos formativos" not in fin.value
    assert "Lenguajes" not in fin.value
    assert "Contenidos" not in fin.value
    assert "Narracion" not in fin.value
    assert "Procesos de desarrollo" not in fin.value
    assert "Metodologia" not in fin.value
    assert "Tiempo de aplicacion" not in fin.value

    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0


def test_green_1_implicit_finalidad_does_not_absorb_subsequent_independent_paragraphs():
    """Verify that subsequent independent paragraphs and notes are delimited by paragraph structure."""
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Agua Escenario Comunitario.\n"
        "Paginas de la 15 a la 28\n"
        "Indagar sobre las fuentes de agua locales y elaborar carteles informativos para sensibilizar a la comunidad escolar.\n"
        "\n"
        "Nota al docente: Solicitar a las familias recipientes limpios con una semana de anticipacion.\n"
        "Campos formativos\n"
        "Lenguajes\n"
        "Contenidos\n"
        "Cuidado de los ecosistemas\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de recorrido escolar.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    fin = dossier.general_fields["finalidad"]

    assert fin.value == (
        "Indagar sobre las fuentes de agua locales y elaborar carteles informativos para sensibilizar a la comunidad escolar."
    )
    assert fin.origin == ORIGIN_PROPOSED
    assert fin.status == STATUS_AMBIGUOUS
    assert fin.review == REVIEW_PENDING
    assert len(fin.evidence) == 1
    assert fin.evidence[0].page_number == 1

    # Neither the subsequent independent note nor table headers are absorbed
    assert "Nota al docente" not in fin.value
    assert "recipientes limpios" not in fin.value
    assert "Campos formativos" not in fin.value
    assert "Cuidado de los ecosistemas" not in fin.value

    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0


def test_green_1_implicit_finalidad_with_uppercase_prose_starting_with_project_title():
    """Verify that purpose prose opening with 'Proyecto Comunitario...' or 'Proyecto 1...' is not cut as a header."""
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Comunitario orientado a investigar la flora y fauna local para elaborar un herbario escolar "
        "y difundir sus beneficios en asamblea comunitaria.\n"
        "Campos formativos\n"
        "Lenguajes\n"
        "Contenidos\n"
        "Biodiversidad y medio ambiente\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de recorrido en areas verdes.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    fin = dossier.general_fields["finalidad"]

    expected_val = (
        "Proyecto Comunitario orientado a investigar la flora y fauna local para elaborar un herbario escolar "
        "y difundir sus beneficios en asamblea comunitaria."
    )
    assert fin.value == expected_val
    assert fin.origin == ORIGIN_PROPOSED
    assert fin.status == STATUS_AMBIGUOUS
    assert fin.review == REVIEW_PENDING
    assert len(fin.evidence) == 1
    assert fin.evidence[0].page_number == 1
    assert fin.evidence[0].document_sha256 == dossier.source_sha256
    assert fin.evidence[0].excerpt.strip() != ""
    assert "Campos formativos" not in fin.value

    # Physical verification passes
    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0

    # Also verify case with 'Proyecto 1...'
    pages_p1 = [
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto 1 para fomentar la lectura compartida de cuentos tradicionales en asamblea escolar.\n"
        "Campos formativos\n"
        "Lenguajes\n"
        "Contenidos\n"
        "Narracion tradicional\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields_p1 = CurriculumSourceInterpreter._extract_general_fields(pages_p1, dossier.source_sha256, {})
    fin_p1 = fields_p1["finalidad"]
    assert fin_p1.value == "Proyecto 1 para fomentar la lectura compartida de cuentos tradicionales en asamblea escolar."
    assert fin_p1.status == STATUS_AMBIGUOUS


def test_green_1_implicit_finalidad_negative_case_without_finalistic_verb_remains_missing():
    """Verify that 'Proyecto ... para ...' without an action/pedagogical verb is not treated as finalidad."""
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Comunitario para tercer grado y turno matutino\n"
        "Campos formativos\n"
        "Lenguajes\n"
        "Contenidos\n"
        "Narracion sobre hechos comunitarios\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de bienvenida comunitaria.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    fin = dossier.general_fields["finalidad"]

    # Invariant: text without finalistic verb does NOT become finalidad
    assert fin.status == STATUS_MISSING
    assert fin.value == ""
    assert fin.origin == ORIGIN_PROPOSED
    assert "No se localizó sección de finalidad explícita ni un candidato" in fin.reason

    # Verification report treats missing canonical field as pending teacher review without blocking
    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0

    # Also verify with _extract_general_fields for additional non-finalistic phrases
    pages_non_final = [
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Comunitario para primer grado\n"
        "Campos formativos\n"
        "Lenguajes\n"
        "Contenidos\n"
        "Narracion\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields_non_final = CurriculumSourceInterpreter._extract_general_fields(pages_non_final, dossier.source_sha256, {})
    assert fields_non_final["finalidad"].status == STATUS_MISSING
    assert fields_non_final["finalidad"].value == ""


def test_green_1_implicit_finalidad_with_unlisted_generic_intro_and_connector_start():
    """Verify that an unlisted generic intro with a pedagogical verb is ignored and connector starts candidate."""
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Bosque Escenario Aula.\n"
        "Paginas de la 10 a la 25\n"
        "Durante las jornadas tecnicas el colectivo docente acordo promover estrategias de inclusion y convivencia escolar.\n"
        "Con la finalidad de explorar leyendas tradicionales sobre los animales de la region y crear un compendio colectivo "
        "ilustrado para fomentar la preservacion de la fauna silvestre en la comunidad escolar.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de bienvenida y dialogo sobre la fauna.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    fin = dossier.general_fields["finalidad"]

    expected_val = (
        "Con la finalidad de explorar leyendas tradicionales sobre los animales de la region y crear un compendio colectivo "
        "ilustrado para fomentar la preservacion de la fauna silvestre en la comunidad escolar."
    )
    # Generic intro with mid-sentence verb 'promover' is NOT chosen
    assert "Durante las jornadas tecnicas" not in fin.value
    assert "acordo promover" not in fin.value

    # Real finalidad starting with connector 'Con la finalidad de...' is selected
    assert fin.value == expected_val

    # 'Con la finalidad de' is NOT misinterpreted as an explicit section header
    assert fin.origin == ORIGIN_PROPOSED
    assert fin.status == STATUS_AMBIGUOUS
    assert fin.review == REVIEW_PENDING
    assert len(fin.evidence) == 1
    assert fin.evidence[0].page_number == 1
    assert fin.evidence[0].document_sha256 == dossier.source_sha256

    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0

    # Also verify connector 'Tiene como finalidad...' and 'Tiene por objetivo...'
    pages_tiene = [
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Reunion escolar para analizar diagnosticos iniciales del ciclo.\n"
        "Tiene por objetivo diseñar un huerto escolar colectivo para cultivar hortalizas y plantas medicinales.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields_tiene = CurriculumSourceInterpreter._extract_general_fields(pages_tiene, dossier.source_sha256, {})
    fin_tiene = fields_tiene["finalidad"]
    assert fin_tiene.value == "Tiene por objetivo diseñar un huerto escolar colectivo para cultivar hortalizas y plantas medicinales."
    assert "Reunion escolar" not in fin_tiene.value
    assert fin_tiene.status == STATUS_AMBIGUOUS


def test_green_1_implicit_finalidad_accepts_para_action_but_rejects_nominal_connector():
    """A paragraph starting with Para needs an action; a bare purpose label does not make metadata a goal."""
    pages_para = [
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Agua Escenario Comunitario.\n"
        "Para contribuir al cuidado del agua en la comunidad y promover hábitos responsables.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields_para = CurriculumSourceInterpreter._extract_general_fields(pages_para, "synthetic-sha", {})
    fin_para = fields_para["finalidad"]
    assert fin_para.value == "Para contribuir al cuidado del agua en la comunidad y promover hábitos responsables."
    assert fin_para.status == STATUS_AMBIGUOUS
    assert fin_para.origin == ORIGIN_PROPOSED

    pages_para_que = [
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Agua Escenario Comunitario.\n"
        "Para que la comunidad participe en el cuidado del agua.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields_para_que = CurriculumSourceInterpreter._extract_general_fields(pages_para_que, "synthetic-sha", {})
    fin_para_que = fields_para_que["finalidad"]
    assert fin_para_que.value == "Para que la comunidad participe en el cuidado del agua."
    assert fin_para_que.status == STATUS_AMBIGUOUS

    pages_reflexione = [
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Agua Escenario Comunitario.\n"
        "Para que el alumnado reflexione sobre su comunidad y sus recursos naturales.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields_reflexione = CurriculumSourceInterpreter._extract_general_fields(pages_reflexione, "synthetic-sha", {})
    fin_reflexione = fields_reflexione["finalidad"]
    assert fin_reflexione.value == "Para que el alumnado reflexione sobre su comunidad y sus recursos naturales."
    assert fin_reflexione.status == STATUS_AMBIGUOUS

    pages_conozca = [
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Memoria Local Escenario Comunitario.\n"
        "Para que el alumnado conozca los relatos de su comunidad.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields_conozca = CurriculumSourceInterpreter._extract_general_fields(pages_conozca, "synthetic-sha", {})
    fin_conozca = fields_conozca["finalidad"]
    assert fin_conozca.value == "Para que el alumnado conozca los relatos de su comunidad."
    assert fin_conozca.status == STATUS_AMBIGUOUS

    pages_distinga = [
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Memoria Local Escenario Comunitario.\n"
        "Para que el alumnado distinga fuentes confiables de opiniones.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields_distinga = CurriculumSourceInterpreter._extract_general_fields(pages_distinga, "synthetic-sha", {})
    fin_distinga = fields_distinga["finalidad"]
    assert fin_distinga.value == "Para que el alumnado distinga fuentes confiables de opiniones."
    assert fin_distinga.status == STATUS_AMBIGUOUS

    pages_nominal = [
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Agua Escenario Comunitario.\n"
        "Con la finalidad de actividades para tercer grado y turno matutino.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas"
    ]
    fields_nominal = CurriculumSourceInterpreter._extract_general_fields(pages_nominal, "synthetic-sha", {})
    fin_nominal = fields_nominal["finalidad"]
    assert fin_nominal.status == STATUS_MISSING
    assert fin_nominal.value == ""


def test_green_1_implicit_finalidad_delimits_split_line_section_labels():
    """Verify that section labels split across lines (e.g. Ajustes\\nrazonables) are not absorbed into finalidad."""
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Agua Escenario Comunitario.\n"
        "Paginas de la 15 a la 28\n"
        "Indagar sobre las fuentes de agua locales y elaborar carteles informativos para sensibilizar a la comunidad escolar.\n"
        "Ajustes\n"
        "razonables\n"
        "Realizar adecuaciones en macro-tipo para estudiantes que lo requieran.\n"
        "Campos formativos\n"
        "Lenguajes\n"
        "Contenidos\n"
        "Cuidado de los ecosistemas\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de recorrido escolar.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    fin = dossier.general_fields["finalidad"]

    expected_val = (
        "Indagar sobre las fuentes de agua locales y elaborar carteles informativos para sensibilizar a la comunidad escolar."
    )
    assert fin.value == expected_val

    # Split label and its content are NOT absorbed
    assert "Ajustes" not in fin.value
    assert "razonables" not in fin.value
    assert "macro-tipo" not in fin.value
    assert "Campos formativos" not in fin.value

    assert fin.origin == ORIGIN_PROPOSED
    assert fin.status == STATUS_AMBIGUOUS
    assert fin.review == REVIEW_PENDING
    assert len(fin.evidence) == 1
    assert fin.evidence[0].page_number == 1

    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0


# ==============================================================================
# GREEN 2: Dos ejes de certeza (Física cotejada vs Función semántica inferida)
# ==============================================================================
def test_green_2_two_certainty_axes_physical_verified_semantic_role_pending_review():
    pdf_bytes = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Proyecto Ecologico Escenario Aula.\n"
        "Investigar la flora y fauna local para elaborar un herbario escolar ilustrado.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de exploracion en areas verdes.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))

    # Axis 1: Physical verification against PDF text passes without blocking
    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0
    fin_item = next(it for it in report.items if it["target"] == "general.finalidad")
    assert fin_item["status"] == STATUS_NEEDS_TEACHER_REVIEW
    assert fin_item["details"]["evidence_citations"][0]["matched"] is True

    # Axis 2: Atomic claim does NOT become backed by physical presence alone
    claims = compile_dossier_to_atomic_claims(dossier)
    fin_claim = next(
        c for c in claims
        if c.subject == "document"
        and c.predicate == "objetivo"
        and c.object_value == dossier.general_fields["finalidad"].value
    )
    assert fin_claim.state == CLAIM_STATE_NEEDS_HUMAN_REVIEW
    assert fin_claim.state != CLAIM_STATE_BACKED

    # Tribunal in shadow mode evaluates hypothesis without changing editorial state
    hypothesis = build_claim_hypothesis(fin_claim)
    assert "Investigar la flora y fauna" in hypothesis

    fake_adapter = _make_fake_adapter([_score(entailment=9.0)])
    manifest, _ = create_synthetic_sep_fixture()
    atlas = AtlasIndex(index_version="syn-1")
    atlas.register_manifest(manifest)
    atlas.add_fragment(AtlasDocumentFragment(
        fragment_id="frag_p1",
        source_id=manifest.source_id,
        page_number=1,
        text="Investigar la flora y fauna local para elaborar un herbario escolar ilustrado.",
    ))
    atlas.build_index()

    retrieval = atlas.retrieve_for_claim(fin_claim, top_k=1)
    tribunal = Tribunal(_config(), fake_adapter)
    receipt = tribunal.evaluate(fin_claim, retrieval, hypothesis)

    # Shadow receipt confirms NLI support, but AtomicClaim and dossier are untouched
    assert receipt.verdict == Verdict.SUPPORT
    assert receipt.shadow_mode is True
    assert fin_claim.state == CLAIM_STATE_NEEDS_HUMAN_REVIEW
    assert dossier.general_fields["finalidad"].review == REVIEW_PENDING


# ==============================================================================
# GREEN 3: No falsa finalidad (Párrafo genérico no se toma como finalidad)
# ==============================================================================
def test_green_3_no_false_finalidad_on_generic_intro_leaves_field_missing():
    pdf_bytes = make_minimal_pdf([
        "Ciclo Escolar 2023-2024. Escuela Primaria Urbana Federal Benito Juarez.\n"
        "Zona Escolar 15. Sector 03. Turno Matutino. Docente titular: Juan Perez.\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Convivencia Escolar Escenario Aula.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de integracion grupal.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))

    fin = dossier.general_fields["finalidad"]
    assert fin.value == ""
    assert fin.status == STATUS_MISSING
    assert fin.origin == ORIGIN_PROPOSED
    assert "no se localizó sección de finalidad explícita ni un candidato" in fin.reason.lower()
    assert fin.evidence == []


def test_green_3_generic_pedagogical_intro_before_delimited_candidate_selects_complete_candidate():
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Agua Escenario Comunitario.\n"
        "Paginas de la 15 a la 28\n"
        "El enfoque pedagogico de la Nueva Escuela Mexicana promueve la participacion comunitaria, "
        "el dialogo reflexivo y la formacion integral de las y los estudiantes.\n"
        "Indagar sobre las fuentes de abastecimiento y la calidad del agua en nuestra localidad y diseñar "
        "una campaña comunitaria con carteles y folletos informativos para sensibilizar a la poblacion "
        "sobre el consumo responsable y sustentable del recurso hidrico.\n"
        "Docentes y estudiantes organizaran los recorridos por el campo y analizaran el ciclo del agua en asamblea comunitaria.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de bienvenida y diagnostico.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))

    fin = dossier.general_fields["finalidad"]
    expected_selected = (
        "Indagar sobre las fuentes de abastecimiento y la calidad del agua en nuestra localidad y diseñar "
        "una campaña comunitaria con carteles y folletos informativos para sensibilizar a la poblacion "
        "sobre el consumo responsable y sustentable del recurso hidrico. "
        "Docentes y estudiantes organizaran los recorridos por el campo y analizaran el ciclo del agua en asamblea comunitaria."
    )
    # 1. Selected text is complete (includes both sentences, not cut at 'Docentes', 'campo', or 'ciclo')
    assert fin.value == expected_selected
    assert "Docentes y estudiantes organizaran" in fin.value
    assert "campo" in fin.value
    assert "ciclo del agua" in fin.value

    # 2. Generic pedagogical intro is NOT chosen
    assert "El enfoque pedagogico" not in fin.value
    assert "Nueva Escuela Mexicana" not in fin.value

    # 3. PDA table and methodology header are excluded
    assert "Contenidos" not in fin.value
    assert "Proceso de desarrollo" not in fin.value
    assert "Metodologia" not in fin.value

    # 4. Uncertainty states: proposed + ambiguous + pending
    assert fin.origin == ORIGIN_PROPOSED
    assert fin.status == STATUS_AMBIGUOUS
    assert fin.review == REVIEW_PENDING

    # 5. Provenance: correct physical page 1 and verified physical citation
    assert len(fin.evidence) == 1
    assert fin.evidence[0].page_number == 1
    assert fin.evidence[0].document_sha256 == dossier.source_sha256
    assert fin.evidence[0].excerpt.strip() != ""

    # 6. Physical verification passes without blocks
    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0
    fin_report_item = next(it for it in report.items if it["target"] == "general.finalidad")
    assert fin_report_item["status"] == STATUS_NEEDS_TEACHER_REVIEW
    assert fin_report_item["details"]["evidence_citations"][0]["matched"] is True


# ==============================================================================
# GREEN 4: Duración física (Salto de página 1->2 sin convertir a sesiones ni fechas)
# ==============================================================================
def test_green_4_physical_duration_spanning_pages_never_invents_sessions_or_dates():
    pdf_bytes = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Transformacion Escenario Aula.\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de Se sugiere dos",
        "aplicacion semanas\n"
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de analisis.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))

    dur = dossier.general_fields["duracion_proyecto"]
    assert dur.value == "Se sugiere dos semanas"
    assert dur.status == STATUS_AMBIGUOUS
    assert dur.origin == ORIGIN_PROPOSED
    # Physical evidence across both pages
    assert len(dur.evidence) == 2
    assert dur.evidence[0].page_number == 1
    assert "Tiempo de Se sugiere dos" in dur.evidence[0].excerpt
    assert dur.evidence[1].page_number == 2
    assert "aplicacion semanas" in dur.evidence[1].excerpt

    # Never converted into sessions, calendar days, or minutes
    assert "sesion" not in dur.value.lower()
    assert "minuto" not in dur.value.lower()
    assert "14" not in dur.value

    # Physical verification accepts the cross-page evidence without contradiction
    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0


def test_green_4_impossible_cross_page_citation_falls_back_to_ambiguous_without_fabricated_evidence():
    # If text is somehow scrambled and physical excerpts do not match page text
    pages = [
        "Metodologia ABPC Tiempo de",
        "Fase #1 Planeacion\nActividad 1.",
    ]
    fields = CurriculumSourceInterpreter._extract_general_fields(pages, "b" * 64, {})
    dur = fields.get("duracion_proyecto")
    # Does not fabricate an impossible citation
    assert dur is None or dur.status in (STATUS_MISSING, STATUS_AMBIGUOUS)
    if dur is not None:
        for ev in dur.evidence:
            assert ev.excerpt.strip() != ""


def test_green_4_does_not_join_unrelated_application_text_from_page_two():
    pdf_bytes = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Transformacion Escenario Aula.\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de Se sugiere dos",
        "Aplicación digital para entregar tareas semanales.\n"
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de analisis.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))

    dur = dossier.general_fields["duracion_proyecto"]
    assert dur.value != "Se sugiere dos semanas"
    assert all(ev.page_number != 2 or "aplicaci" not in ev.excerpt.lower() for ev in dur.evidence)

    later_mention_pdf = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Transformacion Escenario Aula.\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de Se sugiere dos",
        "Nota general del proyecto.\n"
        "Descripción de otra actividad.\n"
        "Contexto adicional del grupo.\n"
        "Aplicación de dos semanas para otra actividad.\n"
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de analisis.",
    ])
    later_mention_dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(later_mention_pdf))
    later_duration = later_mention_dossier.general_fields["duracion_proyecto"]
    assert later_duration.value != "Se sugiere dos semanas"
    assert all(ev.page_number != 2 for ev in later_duration.evidence)


# ==============================================================================
# GREEN 5: Primera actividad en p. 2 y orden completo sin pérdidas ni duplicados
# ==============================================================================
def test_green_5_first_activity_proposed_as_inicio_preserving_order_and_all_activities():
    pdf_bytes = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Mosaico Cultural Escenario Aula.\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de bienvenida y lectura compartida del cuento tradicional.\n"
        "Actividad de elaboracion de preguntas reflexivas en equipos.",
        "Fase #2. Accion\n"
        "Actividad de redaccion del borrador de leyenda comunitaria.\n"
        "Actividad de revision por pares del borrador escrito.",
        "Fase #3. Intervencion\n"
        "Actividad de presentacion final de la narracion en asamblea.",
        "ANEXO\nFicha de trabajo.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    sess = dossier.sessions[0]

    # Total activities detected in exact order
    assert len(sess.activities) == 5
    descriptions = [a.description for a in sess.activities]
    assert descriptions[0].startswith("Actividad de bienvenida")
    assert descriptions[1].startswith("Actividad de elaboracion")
    assert descriptions[2].startswith("Actividad de redaccion")
    assert descriptions[3].startswith("Actividad de revision")
    assert descriptions[4].startswith("Actividad de presentacion")

    # First activity proposed for inicio
    assert sess.fields["inicio"].value == descriptions[0]
    assert sess.fields["inicio"].origin == ORIGIN_PROPOSED
    assert sess.fields["inicio"].status == STATUS_AMBIGUOUS
    assert sess.fields["inicio"].evidence[0].page_number == 2

    # Intermediate activities in desarrollo, final in cierre
    desarrollo_val = sess.fields["desarrollo"].value
    for mid_desc in descriptions[1:4]:
        assert mid_desc in desarrollo_val
    assert sess.fields["cierre"].value == descriptions[4]

    # Invariant: No activity lost, no activity duplicated
    all_moment_text = f"{sess.fields['inicio'].value}\n{sess.fields['desarrollo'].value}\n{sess.fields['cierre'].value}"
    for desc in descriptions:
        assert all_moment_text.count(desc) == 1


def test_green_5_numbered_activities_keep_order_and_continuation_evidence():
    pdf_bytes = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Mosaico Cultural Escenario Aula.\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "1. Leer una leyenda de la comunidad en voz alta.\n"
        "   Después, identificar personajes y lugares mencionados.\n"
        "2. Escribir un final alternativo para la leyenda.\n"
        "3. Compartir las versiones en un círculo de lectura.\n"
        "Recursos\n1. Cuaderno del aula.\n2. Cartulina para los trabajos.\n"
        "Productos y evidencias de aprendizaje\n"
        "Texto final revisado por el grupo.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    session = dossier.sessions[0]

    assert session.title == "Proyecto sin sesiones explícitas"
    assert len(session.activities) == 3
    first, second, third = session.activities
    assert first.order == 1
    assert first.description == "Leer una leyenda de la comunidad en voz alta. Después, identificar personajes y lugares mencionados."
    assert second.order == 2
    assert second.description == "Escribir un final alternativo para la leyenda."
    assert third.order == 3
    assert third.description == "Compartir las versiones en un círculo de lectura."
    assert all(activity.evidence[0].page_number == 2 for activity in session.activities)
    assert all("Cuaderno del aula" not in activity.description for activity in session.activities)

    # Some exported documents place this label before the actual activity list.
    prefix_label_pdf = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Mosaico Cultural Escenario Aula.\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Recursos e implicaciones\n"
        "Actividad 1: Elaborar una pregunta para iniciar el diálogo.\n"
        "Actividad 2: Compartir ideas en equipo.",
    ])
    prefix_label_dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(prefix_label_pdf))
    prefix_label_session = prefix_label_dossier.sessions[0]
    assert len(prefix_label_session.activities) == 2
    assert prefix_label_session.activities[0].description == "Actividad 1: Elaborar una pregunta para iniciar el diálogo."
    assert prefix_label_session.activities[1].description == "Actividad 2: Compartir ideas en equipo."

    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0


# ==============================================================================
# GREEN 6: Fases != Sesiones (Unidad ambigua de revisión sin inventar clases)
# ==============================================================================
def test_green_6_phases_do_not_become_sessions():
    pages = [
        "Fase 4 Grado 3 Campo Lenguajes\nProyecto Arte Comunitario Escenario Aula.\n",
        "DESARROLLO DEL PROYECTO\nFase #1. Planeacion\nActividad de bocetos.",
        "Fase #2. Accion\nActividad de pintura en mural.",
        "Fase #3. Intervencion\nActividad de inauguracion del mural.",
    ]
    sessions = CurriculumSourceInterpreter._detect_sessions(pages, "c" * 64, [], {})

    # Exactly 1 review unit, NOT 3 sessions
    assert len(sessions) == 1
    review_unit = sessions[0]
    assert review_unit.status == STATUS_AMBIGUOUS
    assert "sin sesiones explícitas" in review_unit.title.lower()
    assert review_unit.pages == [2, 3, 4]
    # No class session minutes invented
    assert review_unit.fields["duracion"].status == STATUS_MISSING
    assert review_unit.fields["duracion"].value == ""


# ==============================================================================
# GREEN 7: Planeación sin horario (Duración global sugerida editable)
# ==============================================================================
def test_green_7_two_week_plan_without_timetable_moments_editable():
    pdf_bytes = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Semillas Vivas Escenario Aula.\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de Se sugiere dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de siembra inicial.",
        "Fase #2. Accion\n"
        "Actividad de bitacora de riego.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    assert dossier.general_fields["duracion_proyecto"].value == "Se sugiere dos semanas"
    assert dossier.sessions[0].fields["duracion"].value == ""
    orig_version = dossier.version

    # Teacher confirms moments distribution with their own schedule
    corrections = {
        "session_id": dossier.sessions[0].session_id,
        "session_fields": {
            "inicio": "Actividad de siembra adaptada al martes",
            "duracion": "50 minutos acordados para clase 1",
        },
    }
    updated = resolve(dossier, corrections, actor="Docente Titular")
    assert updated.sessions[0].fields["inicio"].value == "Actividad de siembra adaptada al martes"
    assert updated.sessions[0].fields["inicio"].origin == ORIGIN_TEACHER_ENTERED
    assert updated.sessions[0].fields["inicio"].review == REVIEW_CORRECTED
    assert updated.sessions[0].fields["duracion"].value == "50 minutos acordados para clase 1"
    assert updated.sessions[0].fields["duracion"].origin == ORIGIN_TEACHER_ENTERED
    assert updated.version == orig_version + 1


# ==============================================================================
# GREEN 8: Tribunal acotado con Fakes (Hipótesis tipadas y no mutación)
# ==============================================================================
def test_green_8_bounded_tribunal_typed_hypotheses_and_abstention():
    manifest, _ = create_synthetic_sep_fixture()
    atlas = AtlasIndex(index_version="syn-1")
    atlas.register_manifest(manifest)
    atlas.add_fragments([
        AtlasDocumentFragment(
            fragment_id="frag_p1_obj",
            source_id=manifest.source_id,
            page_number=1,
            text="Explorar leyendas tradicionales para preservar la fauna silvestre.",
        ),
        AtlasDocumentFragment(
            fragment_id="frag_p1_dur",
            source_id=manifest.source_id,
            page_number=1,
            text="Tiempo de aplicacion Se sugiere dos semanas.",
        ),
        AtlasDocumentFragment(
            fragment_id="frag_p2_act",
            source_id=manifest.source_id,
            page_number=2,
            text="Actividad inicial individual de observacion de animales locales.",
        ),
    ])
    atlas.build_index()

    claims = [
        AtomicClaim(
            claim_id="c_obj", claim_type="field", subject="document", predicate="objetivo",
            object_value="Explorar leyendas tradicionales para preservar la fauna silvestre.",
            state=CLAIM_STATE_NEEDS_HUMAN_REVIEW,
        ),
        AtomicClaim(
            claim_id="c_dur", claim_type="field", subject="document", predicate="duracion_proyecto",
            object_value="Se sugiere dos semanas",
            state=CLAIM_STATE_NEEDS_HUMAN_REVIEW,
        ),
        AtomicClaim(
            claim_id="c_act", claim_type="field", subject="session:p2", predicate="inicio",
            object_value="Actividad inicial individual de observacion de animales locales.",
            state=CLAIM_STATE_NEEDS_HUMAN_REVIEW,
        ),
    ]

    # Test SUPPORT, NEUTRAL (insufficient_evidence), CONTRADICTION, TIE, and DISAGREEMENT
    cfg = _config()

    # 1. Objetivo with support
    ret_obj = atlas.retrieve_for_claim(claims[0], top_k=1)
    hyp_obj = build_claim_hypothesis(claims[0])
    rec_obj = Tribunal(cfg, _make_fake_adapter([_score(entailment=7.0)])).evaluate(claims[0], ret_obj, hyp_obj)
    assert rec_obj.verdict == Verdict.SUPPORT
    assert claims[0].state == CLAIM_STATE_NEEDS_HUMAN_REVIEW  # INVARIANT: Shadow mode does not mutate claim

    # 2. Duracion with neutral -> insufficient evidence
    ret_dur = atlas.retrieve_for_claim(claims[1], top_k=1)
    hyp_dur = build_claim_hypothesis(claims[1])
    rec_dur = Tribunal(cfg, _make_fake_adapter([_score(neutral=8.0)])).evaluate(claims[1], ret_dur, hyp_dur)
    assert rec_dur.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert rec_dur.reason in ("neutral", "neutral_or_tie")
    assert rec_dur.decisions[0].reason == "neutral"
    assert claims[1].state == CLAIM_STATE_NEEDS_HUMAN_REVIEW

    # 3. Inicio with tie -> insufficient evidence
    ret_act = atlas.retrieve_for_claim(claims[2], top_k=1)
    hyp_act = build_claim_hypothesis(claims[2])
    rec_tie = Tribunal(cfg, _make_fake_adapter([_score(entailment=5.0, contradiction=5.0)])).evaluate(claims[2], ret_act, hyp_act)
    assert rec_tie.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert rec_tie.reason in ("tie", "neutral_or_tie")
    assert rec_tie.decisions[0].reason == "tie"

    # 4. Contradiction
    rec_contra = Tribunal(cfg, _make_fake_adapter([_score(contradiction=6.0)])).evaluate(claims[2], ret_act, hyp_act)
    assert rec_contra.verdict == Verdict.CONTRADICTION
    assert claims[2].state == CLAIM_STATE_NEEDS_HUMAN_REVIEW

    # 5. Empty retrieval (no candidates found) -> completed with no_candidates
    ret_empty = atlas.retrieve_for_claim(
        AtomicClaim(claim_id="c_none", claim_type="field", subject="doc", predicate="inexistente", object_value="xyz123"),
        top_k=1,
    )
    rec_none = Tribunal(cfg, _make_fake_adapter([])).evaluate(
        AtomicClaim(claim_id="c_none", claim_type="field", subject="doc", predicate="inexistente", object_value="xyz123"),
        ret_empty,
        "Hipotesis cualquiera",
    )
    assert rec_none.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert rec_none.reason == "no_candidates"


# ==============================================================================
# GREEN 9: Persistencia y autoridad docente (resolve, auditoría, no avance de CurriculumProgress)
# ==============================================================================
def test_green_9_teacher_correction_persists_with_audit_trail_and_no_progress_advance():
    pdf_bytes = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Historia Comunitaria Escenario Aula.\n"
        "Conocer relatos locales para reflexionar sobre identidad.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de lectura guiada.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    orig_fin_val = dossier.general_fields["finalidad"].value
    orig_version = dossier.version

    # Teacher corrects finalidad
    corrections = {
        "general_fields": {
            "finalidad": "Redaccion corregida por la docente con enfoque intercultural",
        }
    }
    updated = resolve(dossier, corrections, actor="Mtra. Elena")

    assert updated.version == orig_version + 1
    fin = updated.general_fields["finalidad"]
    assert fin.value == "Redaccion corregida por la docente con enfoque intercultural"
    assert fin.original_value == orig_fin_val
    assert fin.origin == ORIGIN_TEACHER_ENTERED
    assert fin.review == REVIEW_CORRECTED

    # Audit delta is recorded in history
    assert updated.history
    all_deltas = [d for h in updated.history for d in h.get("deltas", [])]
    fin_delta = next(d for d in all_deltas if d.get("field") == "finalidad")
    assert fin_delta["before"]["value"] == orig_fin_val
    assert fin_delta["after"]["value"] == "Redaccion corregida por la docente con enfoque intercultural"

    # Serializing and reloading preserves all details
    data = updated.to_dict()
    reloaded = ImportDossier.from_dict(data)
    assert reloaded.version == updated.version
    assert reloaded.general_fields["finalidad"].value == fin.value
    assert reloaded.general_fields["finalidad"].original_value == orig_fin_val
    assert reloaded.general_fields["finalidad"].review == REVIEW_CORRECTED


# ==============================================================================
# GREEN 10: Regresión (Finalidad explícita, documentos sin duración, hash ajeno)
# ==============================================================================
def test_green_10_regression_explicit_finalidad_preserved_as_extracted():
    pdf_bytes = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Titulo Escenario Aula.\n"
        "Finalidad: Los estudiantes comprenderan los textos narrativos.\n"
        "Metodologia: Aprendizaje basado en proyectos\n"
        "SESION 1: Inicio de clase\n"
        "Inicio: Dinamica de presentacion.\n"
        "Desarrollo: Lectura individual.\n"
        "Cierre: Sintesis grupal.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))

    fin = dossier.general_fields["finalidad"]
    assert fin.value == "Los estudiantes comprenderan los textos narrativos."
    assert fin.origin == ORIGIN_EXTRACTED
    assert fin.status == STATUS_SUPPORTED

    # Document without duration suggestion does NOT get two weeks
    dur = dossier.general_fields.get("duracion_proyecto")
    assert dur is None or dur.value == ""


def test_green_10_regression_foreign_hash_triggers_blocked_evidence():
    pdf_bytes = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Proyecto Ejemplo Escenario Aula.\n"
        "Finalidad: Comprender textos narrativos comunitarios.\n"
        "Metodologia Aprendizaje basado en proyectos\n"
        "SESION 1: Inicio de clase\n"
        "Inicio: Actividad inicial.\n"
        "Desarrollo: Actividad central.\n"
        "Cierre: Actividad final.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    assert dossier.general_fields["finalidad"].evidence

    # Tamper document with foreign SHA
    dossier.general_fields["finalidad"].evidence[0].document_sha256 = "0" * 64
    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is False
    assert report.blocked_count >= 1
