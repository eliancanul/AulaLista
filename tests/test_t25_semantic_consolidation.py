"""Issue #47: pasada semántica de consolidación de temas.

Los 4 casos reales de la currícula de 44 páginas (issue #47) son fixtures
de aceptación: la consolidación heurística (#43) los deja fragmentados y la
pasada semántica vía LLM debe agruparlos en temas curriculares reales.
"""

import json
import os
from unittest.mock import patch

import django
import pytest


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum import curriculum_import as pipeline  # noqa: E402
from curriculum.curriculum_import import ImportPipelineError  # noqa: E402


def ok_chat(payload):
    def transport(request):
        return {"message": {"content": json.dumps(payload)}}

    return transport


# --- Fixtures reales del issue #47 -------------------------------------------

VOCALES_FRAGMENTS = [
    {"titulo": "El uso de las vocales y la letra M", "pagina_inicio": 4, "pagina_fin": 15},
    {"titulo": "Aprendizaje de vocales", "pagina_inicio": 5, "pagina_fin": 9},
    {"titulo": "Aprendizaje de la letra 'M'", "pagina_inicio": 10, "pagina_fin": 13},
]

NUMEROS_FRAGMENTS = [
    {"titulo": "Identificación y ordenación de números del 1 al 10", "pagina_inicio": 16, "pagina_fin": 18},
    {"titulo": "Canción para aprender números del 1 al 10", "pagina_inicio": 17, "pagina_fin": 17},
    {"titulo": "Colorear según números", "pagina_inicio": 18, "pagina_fin": 19},
    {"titulo": "Representación de números con carritos", "pagina_inicio": 19, "pagina_fin": 20},
    {"titulo": "Escribir números del 1 al 10", "pagina_inicio": 20, "pagina_fin": 21},
    {"titulo": "Identificar y clasificar figuras geométricas básicas", "pagina_inicio": 21, "pagina_fin": 23},
]

IDENTIDAD_FRAGMENTS = [
    {"titulo": "Identidad personal", "pagina_inicio": 24, "pagina_fin": 26},
    {"titulo": "Familia", "pagina_inicio": 26, "pagina_fin": 28},
    {"titulo": "Higiene y partes del cuerpo", "pagina_inicio": 28, "pagina_fin": 30},
    {"titulo": "Identificación personal", "pagina_inicio": 29, "pagina_fin": 31},
    {"titulo": "Reconociendo quién soy y de dónde vengo", "pagina_inicio": 31, "pagina_fin": 33},
]

EMOCIONES = [{"titulo": "Emociones y manejo del estrés", "pagina_inicio": 34, "pagina_fin": 36}]


# --- Casos de aceptación ------------------------------------------------------


def test_vocales_fragments_group_into_one_topic():
    transport = ok_chat(
        {
            "temas": [
                {"titulo": "Vocales y letra M", "indices": [0, 1, 2]},
            ]
        }
    )
    merged = pipeline.consolidate_topics_semantic(VOCALES_FRAGMENTS, transport=transport)
    assert len(merged) == 1
    assert merged[0]["titulo"] == "Vocales y letra M"
    # Citas ampliadas a la unión de las páginas de los miembros.
    assert merged[0]["pagina_inicio"] == 4
    assert merged[0]["pagina_fin"] == 15


def test_activity_titles_group_into_curricular_topic():
    transport = ok_chat(
        {
            "temas": [
                {"titulo": "Los números del 1 al 10", "indices": [0, 1, 2, 3, 4]},
                {"titulo": "Figuras geométricas básicas", "indices": [5]},
            ]
        }
    )
    merged = pipeline.consolidate_topics_semantic(NUMEROS_FRAGMENTS, transport=transport)
    assert [topic["titulo"] for topic in merged] == [
        "Los números del 1 al 10",
        "Figuras geométricas básicas",
    ]
    numeros = merged[0]
    assert numeros["pagina_inicio"] == 16 and numeros["pagina_fin"] == 21


def test_identidad_fragments_group_into_one_topic():
    transport = ok_chat(
        {"temas": [{"titulo": "Conozco mi nombre y mi identidad", "indices": [0, 1, 2, 3, 4]}]}
    )
    merged = pipeline.consolidate_topics_semantic(IDENTIDAD_FRAGMENTS, transport=transport)
    assert len(merged) == 1
    assert merged[0]["titulo"] == "Conozco mi nombre y mi identidad"
    assert merged[0]["pagina_inicio"] == 24 and merged[0]["pagina_fin"] == 33


def test_unclaimed_candidates_are_preserved():
    """Candidatos que el modelo no agrupa sobreviven tal cual."""

    transport = ok_chat({"temas": []})
    merged = pipeline.consolidate_topics_semantic(EMOCIONES, transport=transport)
    assert merged == EMOCIONES


# --- Robustez -----------------------------------------------------------------


def test_llm_failure_falls_back_to_candidates():
    def transport(request):
        raise OSError("ollama down")

    merged = pipeline.consolidate_topics_semantic(VOCALES_FRAGMENTS, transport=transport)
    assert merged == VOCALES_FRAGMENTS


def test_import_pipeline_error_falls_back_to_candidates():
    def transport(request):
        return {"message": {"content": "{no es json}"}}

    merged = pipeline.consolidate_topics_semantic(EMOCIONES, transport=transport)
    assert merged == EMOCIONES


def test_invalid_indices_are_ignored_and_dropped():
    transport = ok_chat(
        {
            "temas": [
                {"titulo": "Vocales", "indices": [0, 99]},  # 99 fuera de rango
                {"titulo": "Fantasma", "indices": []},  # sin miembros válidos
            ]
        }
    )
    merged = pipeline.consolidate_topics_semantic(VOCALES_FRAGMENTS + EMOCIONES, transport=transport)
    titles = [topic["titulo"] for topic in merged]
    # El grupo válido absorbe el candidato 0; el grupo vacío se descarta;
    # los no reclamados (1, 2, 3) se conservan.
    assert "Vocales" in titles
    assert "Fantasma" not in titles
    assert len(merged) == 4


def test_single_candidate_skips_llm_call():
    with patch.object(pipeline, "chat_json", side_effect=AssertionError("no debe llamarse")):
        merged = pipeline.consolidate_topics_semantic(EMOCIONES)
    assert merged == EMOCIONES


def test_stage_recorded_in_trace():
    entries = []
    pipeline.start_llm_trace()
    try:
        pipeline.consolidate_topics_semantic(
            VOCALES_FRAGMENTS,
            transport=ok_chat({"temas": [{"titulo": "Vocales", "indices": [0, 1, 2]}]}),
        )
        entries = pipeline.stop_llm_trace()
    finally:
        pipeline._trace.entries = None
    assert entries and entries[0]["stage"] == "consolidate_topics"


def test_duplicate_index_claimed_only_once():
    transport = ok_chat(
        {
            "temas": [
                {"titulo": "Primero", "indices": [0]},
                {"titulo": "Segundo", "indices": [0, 1]},  # 0 ya reclamado
            ]
        }
    )
    merged = pipeline.consolidate_topics_semantic(VOCALES_FRAGMENTS[:2], transport=transport)
    titles = [topic["titulo"] for topic in merged]
    assert "Primero" in titles
    # El índice 0 no puede estar en dos grupos; Segundo queda con el 1.
    segundo = next(t for t in merged if t["titulo"] == "Segundo")
    assert segundo["pagina_inicio"] == VOCALES_FRAGMENTS[1]["pagina_inicio"]
