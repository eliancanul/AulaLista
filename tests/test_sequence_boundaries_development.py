"""Synthetic development regressions derived from #144's structural pattern.

Authored text only: no pilot PDF, extracted pilot output, or held-out evaluation.
These assertions measure software behavior, not pedagogical/human validation.
"""

import copy
import hashlib

import pytest

from curriculum.source_interpreter import CurriculumSourceInterpreter, ImportDossier
from curriculum.source_segments import scan_session_segments
from curriculum.verification import verify_curriculum_dossier


OLD_METADATA = (
    "DATOS GENERALES\nCampo formativo: Lenguajes\n"
    "INTENCIÓN DIDÁCTICA: Describir objetos del entorno.\n"
)
NEW_METADATA = (
    "DATOS GENERALES\nCampo formativo: Saberes y pensamiento científico\n"
    "INTENCIÓN DIDÁCTICA: Comparar longitudes con unidades propias.\n"
)
SESSION = (
    "SESIÓN 1: Describir\nInicio: Observar una piedra.\n"
    "Desarrollo: Dibujar sus detalles.\nCierre: Compartir la descripción.\n"
    "Producto del proyecto: Un dibujo.\nEvaluación: Registro breve.\n"
    "Recursos: Papel y colores.\n"
)
NEXT_BODY = "Inicio: Comparar dos listones.\nDesarrollo: Registrar sus longitudes.\nCierre: Explicar la comparación.\n"


def source(pages):
    content = "\n---DEVELOPMENT-PAGE---\n".join(pages).encode()
    return content, hashlib.sha256(content).hexdigest(), pages


def dossier_for(pages):
    _, sha, _ = source(pages)
    return ImportDossier(
        source_sha256=sha, source_name="synthetic-development-144.pdf", page_count=len(pages),
        general_fields=CurriculumSourceInterpreter._extract_general_fields(pages, sha, {}),
        sessions=CurriculumSourceInterpreter._detect_sessions(pages, sha, [], {}),
    )


def fixture_pages(next_body=NEXT_BODY):
    return [OLD_METADATA + "Proyecto: Objetos cercanos\n" + SESSION, NEW_METADATA + next_body]


def checked_for(report, prefix):
    return any(item["status"] == "checked" and item["target"].startswith(prefix) for item in report.items)


def test_new_untitled_planning_block_does_not_continue_previous_session():
    pages = fixture_pages()
    d = dossier_for(pages)
    assert len(d.sessions) == 1  # Do not invent another session/project.
    s = d.sessions[0]
    assert s.pages == [1]
    assert s.continues_on == []
    assert all("listones" not in a.description and "longitudes" not in a.description for a in s.activities)
    assert NEW_METADATA + NEXT_BODY in s.layout_notes
    assert "página física 2" in s.layout_notes
    assert s.status == "ambiguous"
    assert s.fields["cierre"].status == "ambiguous"


def test_untitled_restart_invalidates_prior_project_context_for_later_explicit_session():
    pages = fixture_pages("SESIÓN 2: Comparar\n" + NEXT_BODY)
    first, second = dossier_for(pages).sessions
    assert first.project_title == "Objetos cercanos"
    assert second.project_title == ""
    assert second.project_context["status"] == "missing"
    assert second.project_context["anchor"] is None
    assert second.project_context["project_id"] is None
    assert second.project_context["review"] == "pending"


def test_verifier_recomputes_restart_even_when_dossier_hides_uncertainty():
    pages = fixture_pages()
    d = dossier_for(pages)
    s = d.sessions[0]
    s.pages = [1, 2]
    s.layout_notes = ""
    s.status = "supported"
    s.fields["inicio"].value = "Comparar dos listones."
    s.fields["inicio"].origin, s.fields["inicio"].status = "extracted", "supported"
    s.fields["inicio"].evidence[0].page_number = 2
    s.fields["inicio"].evidence[0].excerpt = "Comparar dos listones."
    assert not checked_for(verify_curriculum_dossier(d, source(pages)), "session.p1_s1.inicio")


def test_old_context_cannot_be_transplanted_after_restart():
    pages = fixture_pages("SESIÓN 2: Comparar\n" + NEXT_BODY)
    d = dossier_for(pages)
    d.sessions[1].project_context = copy.deepcopy(d.sessions[0].project_context)
    d.sessions[1].project_title = d.sessions[0].project_title
    report = verify_curriculum_dossier(d, source(pages))
    assert any(i["status"] == "blocked" and i["target"] == "session.p2_s2.project_context" for i in report.items)


@pytest.mark.parametrize("prefix", [
    "",
    OLD_METADATA,
    "DATOS GENERALES\n",  # An isolated heading is not a universal boundary.
    "Campo formativo: Saberes y pensamiento científico\n",
    "INTENCIÓN DIDÁCTICA: Comparar longitudes.\n",
    "El texto menciona DATOS GENERALES y Campo formativo: Lenguajes.\n",
    'Leer el siguiente ejemplo: "\n' + NEW_METADATA + '"\n',
])
def test_legitimate_continuation_and_repeated_or_quoted_headings_are_retained(prefix):
    pages = [OLD_METADATA + "Proyecto: Objetos cercanos\n" + SESSION, prefix + "Cierre: Continuar la descripción.\n"]
    segments = scan_session_segments(pages, source(pages)[1])
    assert [p for p, _ in segments[0].page_segments] == [1, 2]
    assert "Continuar la descripción." in segments[0].page_segments[1][1]
    assert not segments[0].unassigned_segments
