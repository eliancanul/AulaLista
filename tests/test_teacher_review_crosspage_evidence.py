"""Physical-page attribution for moments spanning existing session segments."""
import pytest

from curriculum.source_interpreter import CurriculumSourceInterpreter, ORIGIN_EXTRACTED, STATUS_SUPPORTED


def parse(segments):
    return CurriculumSourceInterpreter._parse_session_block(
        session_id="synthetic-session", session_number=1, title="Synthetic session",
        project_title="Synthetic project", day_of_week="", pages=[page for page, _ in segments],
        continues_on=[page for page, _ in segments[1:]], layout_fidelity="linearized_heuristics",
        layout_notes="Synthetic-only layout", block_text="\n".join(text for _, text in segments),
        sha256="a" * 64, annex_candidates=[], page_warnings={},
        pages_text=[text for _, text in segments], page_segments=segments,
    )


@pytest.mark.parametrize("heading,field,next_heading", [
    ("Inicio", "inicio", "Desarrollo"),
    ("Desarrollo", "desarrollo", "Cierre"),
    ("Cierre", "cierre", "Evaluación"),
    ("Evaluación", "evaluacion", "Recursos"),
    ("Recursos", "materiales", "Cierre"),
])
def test_crosspage_moment_preserves_complete_value_and_physical_fragments(heading, field, next_heading):
    first = "Comparar seis semillas y registrar los resultados. " * 5
    first = first.strip()
    second = "Continuación: explicar la comparación y preparar el relato."
    segments = [(1, f"Sesión 1\n{heading}: {first}"),
                (2, f"{second}\n{next_heading}: Finalizar.")]
    result = parse(segments).fields[field]
    assert result.value == f"{first}\n{second}"
    assert result.origin == ORIGIN_EXTRACTED and result.status == STATUS_SUPPORTED
    assert [(ref.page_number, ref.excerpt) for ref in result.evidence] == [(1, first), (2, second)]
    assert all(ref.document_sha256 == "a" * 64 for ref in result.evidence)
    assert all(ref.excerpt in segments[ref.page_number - 1][1] for ref in result.evidence)


def test_repeated_text_uses_section_offsets_not_first_matching_page():
    repeated = "Registrar los sonidos del entorno."
    result = parse([(1, f"Sesión 1\nInicio: {repeated}"),
                    (2, f"Desarrollo: {repeated}\nCierre: Compartir.")])
    assert result.fields["inicio"].evidence[0].page_number == 1
    assert result.fields["desarrollo"].evidence[0].page_number == 2
    assert result.fields["desarrollo"].value == repeated


def test_single_page_keeps_existing_preview_without_truncating_value():
    value = "Contenido sintético largo. " * 25
    result = parse([(1, f"Sesión 1\nDesarrollo: {value}\nCierre: Compartir.")]).fields["desarrollo"]
    assert result.value == value.strip()
    assert len(result.evidence) == 1
    assert result.evidence[0].excerpt == value[:200]
