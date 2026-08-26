"""Machine-readable contract for the teacher workflow documentation (#18)."""

from pathlib import Path


ROOT = Path(__file__).parents[1]
CONTEXT = ROOT / "CONTEXT.md"
FLOW = ROOT / "docs" / "teacher-flow.md"
ADR = ROOT / "docs" / "adr" / "0006-teacher-workflow-and-human-curriculum-progress.md"


def test_teacher_workflow_vocabulary_and_authority_contract_are_documented():
    context = CONTEXT.read_text()
    flow = FLOW.read_text()
    adr = ADR.read_text()
    combined = "\n".join((context, flow, adr))

    for term in ("TeacherWorkflow", "CurriculumProgress", "ActivityDraft", "ActivityReview"):
        assert term in context

    for state in ("Actividad propuesta", "Borrador editable", "En revisión docente", "Publicada", "Sesión preparada", "Sesión activa", "Sesión cerrada"):
        assert state in flow

    assert "Crear una actividad no cambia `CurriculumProgress`" in flow
    assert "Publicar una actividad no cambia `CurriculumProgress`" in flow
    assert "Cerrar una sesión ofrece registrar el tema trabajado" in flow
    assert "confirmación explícita del maestro" in flow
    assert "No hay suficiente fuente local" in combined
    assert "snapshot" in combined.lower()
    assert adr.startswith("# ADR-0006:")


def test_curriculum_and_student_roadmap_progress_contract_is_explicitly_separate():
    flow = FLOW.read_text()
    forbidden_automatic_transition = "crear, publicar o cerrar una actividad avanza automáticamente el currículo"
    assert forbidden_automatic_transition not in flow.lower()
    assert "La sugerencia no es una transición de estado" in flow
    assert "StudentRoadmapProgress" in flow
    assert "COMPLETADA" in flow
