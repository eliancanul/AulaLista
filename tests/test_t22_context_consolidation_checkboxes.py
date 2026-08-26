"""Issues #42, #43 and #44: aligned context, fuzzy consolidation, checkboxes."""

import os

import django
import pytest


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum import curriculum_import as pipeline  # noqa: E402
from curriculum.views import _subtopics_from_post, _topics_from_post  # noqa: E402


SOURCE = "\n\n".join(
    f"[página {page}]\ncontenido de la página {page}" for page in range(1, 31)
)


# --- #42: contexto alineado al rango de páginas -----------------------------


def test_context_for_pages_extracts_the_topic_window():
    window = pipeline.context_for_pages(SOURCE, 16, 27)
    assert "[página 15]" in window  # padding
    assert "[página 16]" in window
    assert "[página 27]" in window
    assert "[página 28]" in window  # padding
    assert "página 4" not in window.replace("[página 14]", "").replace("[página 24]", "")


def test_context_for_pages_falls_back_to_head_without_markers():
    text = "texto sin marcadores de página " * 200
    assert pipeline.context_for_pages(text, 5, 9) == text[:4000]
    assert pipeline.context_for_pages("", 5, 9) == ""


def test_propose_subtopics_receives_window_matching_topic_citations():
    captured = {}

    def transport(request):
        import json

        captured["prompt"] = json.loads(request.data)["messages"][1]["content"]
        return {
            "message": {
                "content": json.dumps(
                    {"subtemas": ["uno"], "actividades_sugeridas": 2}
                )
            }
        }

    window = pipeline.context_for_pages(SOURCE, 20, 22)
    pipeline.propose_subtopics("Números", window, transport=transport)
    assert "[página 20]" in captured["prompt"]
    assert "[página 22]" in captured["prompt"]


# --- #43: consolidación difusa -----------------------------------------------


def test_consolidate_topics_merges_near_duplicates_with_overlapping_ranges():
    merged = pipeline.consolidate_topics(
        [
            [
                {
                    "titulo": "El uso de las vocales y la letra M",
                    "pagina_inicio": 4,
                    "pagina_fin": 15,
                }
            ],
            [{"titulo": "Aprendizaje de las vocales", "pagina_inicio": 6, "pagina_fin": 10}],
            [{"titulo": "Vocales", "pagina_inicio": 6, "pagina_fin": 9}],
            [{"titulo": "Letra M", "pagina_inicio": 10, "pagina_fin": 13}],
        ]
    )

    titles = [topic["titulo"] for topic in merged]
    assert len(merged) == 2
    vocales = next(t for t in merged if "vocales" in t["titulo"].lower())
    letra_m = next(t for t in merged if "letra m" in t["titulo"].lower())
    assert vocales["pagina_inicio"] == 4 and vocales["pagina_fin"] == 15
    assert letra_m["pagina_inicio"] == 10 and letra_m["pagina_fin"] == 13


def test_consolidate_topics_keeps_distinct_topics_sharing_a_fragment():
    merged = pipeline.consolidate_topics(
        [
            [{"titulo": "Fracciones", "pagina_inicio": 1, "pagina_fin": 5}],
            [{"titulo": "Suma de fracciones", "pagina_inicio": 20, "pagina_fin": 25}],
        ]
    )
    assert len(merged) == 2  # rangos sin solape → no se fusionan


# --- #44: checkboxes por presencia -------------------------------------------


def test_unchecked_topics_are_dropped_by_absence_of_key():
    post = {
        "topic_0": "Tema conservado",
        "start_0": "1",
        "end_0": "2",
        "keep_0": "on",
        # topic_1 desmarcado: su keep_1 nunca viaja
        "topic_1": "Tema descartado",
        "start_1": "3",
        "end_1": "4",
    }
    topics = _topics_from_post(post)
    assert [topic["titulo"] for topic in topics] == ["Tema conservado"]


def test_unchecked_subtopics_are_dropped_by_absence_of_key():
    post = {
        "heading_0": "Fracciones",
        "start_0": "1",
        "end_0": "2",
        "keep_topic_0": "on",
        "keep_0_0": "on",
        "topic_0_sub_0": "Suma conservada",
        "acts_0_0": "1",
        # keep_0_1 ausente: descartado
        "topic_0_sub_1": "Resta descartada",
        "acts_0_1": "2",
    }
    topics = _subtopics_from_post(post)
    assert len(topics) == 1
    assert [sub["titulo"] for sub in topics[0]["subtemas"]] == ["Suma conservada"]
