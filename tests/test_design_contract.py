"""Machine-testable contract for the canonical AulaLista design."""
from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
DESIGN = ROOT / "DESIGN.md"
CSS = ROOT / "static" / "curriculum" / "aulalista.css"


# Estas plantillas todavía comparten la hoja canónica; la lista explícita evita
# tratar como contrato las clases dinámicas o las de librerías externas.
TEMPLATE_CLASS_CONTRACT = {
    "templates/curriculum/tutor_import_detail.html": {
        "subtopic-form", "keep-toggle", "field-title", "acts-field",
        "topic-block", "subtopic-block", "subtopic-head", "activity-head",
        "activity-title", "activity-objective", "activity-details",
        "activity-foot", "remove-form", "issue-list", "convert-bar",
        "technical-log-links", "review-intro", "topup-form", "is-valid",
        "is-invalid",
    },
    "templates/curriculum/student_roadmap.html": {
        "viewed-icon", "current-icon", "available-icon", "locked-icon",
    },
}


def read_design() -> str:
    return DESIGN.read_text(encoding="utf-8")


def test_css_contract_covers_legacy_import_and_roadmap_legend_templates():
    css = CSS.read_text(encoding="utf-8")
    for template_name, classes in TEMPLATE_CLASS_CONTRACT.items():
        template = (ROOT / template_name).read_text(encoding="utf-8")
        for class_name in classes:
            assert class_name in template
            assert f".{class_name}" in css, (
                f"{template_name} usa .{class_name}, pero falta en aulalista.css"
            )


def test_canonical_contract_exists_and_records_the_hybrid_decision():
    design = read_design()
    for heading in (
        "# AulaLista — contrato de diseño canónico",
        "## Decisión y límites",
        "## Sistema de tokens",
        "## Componentes",
        "## Estados y superficies",
        "## Responsive y accesibilidad",
        "## Local, privacidad y datos",
    ):
        assert heading in design
    assert "C — Aula directa" in design
    assert "B" in design and "unidades → lecciones → actividades" in design
    assert "A" in design and "EditorialReviewer" in design
    assert "No afirma validación pedagógica" in design


def test_contract_defines_local_tokens_and_sober_content_first_components():
    design = read_design()
    for token in (
        "--color-ink",
        "--color-action",
        "--color-paper",
        "--color-surface",
        "--color-review",
        "--color-error",
        "--color-focus",
        "--space-1",
        "--space-2",
        "--space-3",
        "--space-4",
        "--radius",
        "--text-body",
        "--target-min",
    ):
        assert token in design
    for component in (
        "Skip link",
        "Header",
        "PrimaryAction",
        "Roadmap",
        "Status",
        "EditorialBoundary",
        "SessionCard",
        "ProjectionMode",
    ):
        assert component in design
    assert "contenido primero" in design.lower()
    assert "superficies sobrias" in design.lower()
    assert "una acción principal" in design.lower()


def test_contract_covers_roadmap_states_and_legible_progress():
    design = read_design().lower()
    for state in ("visto", "actual", "disponible", "bloqueado", "completado"):
        assert state in design
    for unit in ("unidades", "lecciones", "actividades"):
        assert unit in design
    for phrase in ("progreso legible", "no es puntuación", "no declara aprendizaje"):
        assert phrase in design


def test_contract_requires_surface_states_for_every_context():
    design = read_design().lower()
    contexts = ("general", "student", "teacher", "questionnaire", "projection", "results")
    states = ("empty", "loading", "error", "ready")
    for context in contexts:
        assert context in design
        for state in states:
            assert f"{context}:" in design and state in design
    for classroom_state in ("espera", "activo", "cerrado", "error"):
        assert classroom_state in design


def test_contract_enforces_offline_privacy_accessibility_and_motion_boundaries():
    design = read_design()
    lower = design.lower()
    for phrase in (
        "sin cdn",
        "sin red",
        "assets locales",
        "44px",
        "alto contraste",
        "legible en proyección",
        "prefers-reduced-motion",
        "sin nombres",
        "sin correo",
        "sin matrícula",
        "datos sintéticos",
        "alias temporales",
        "pseudónimos y acotados",
        "control autenticado de la maestra",
        "nunca se proyectan públicamente",
        "se purgan al completar el turno o cerrar la sesión",
    ):
        assert phrase in lower
    assert "solo en memoria" not in lower
    assert "desaparecen al cerrar la sesión o recargar" not in lower
    assert "recargar" not in lower
    assert not re.search(r"https?://|fonts\.googleapis|unpkg|jsdelivr", design, re.I)
    assert "identificador opaco" in lower
    assert "editorialreviewer" in lower and "maestra activa" in lower
    assert "ia solo propone" in lower
