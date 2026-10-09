"""Literal source/range guards for the retained, inactive topic stage."""
import json

import pytest

from curriculum.curriculum_import import chunk_pages, identify_topics


def identify(chunk, proposals):
    calls = []
    def transport(request):
        calls.append(request)
        return {"message": {"content": json.dumps({"temas": proposals})}}
    result = identify_topics(chunk, transport=transport)
    assert len(calls) == 1  # Source rejection does not retry generation.
    return result


def proposal(title="El agua", first=1, last=1):
    return {"titulo": title, "pagina_inicio": first, "pagina_fin": last, "tipo": "tema"}


@pytest.mark.parametrize("title", ["El volcán", "La SEP exige estudiar El agua", "E", "agu", "agua"])
def test_title_must_be_literal_not_invented_or_inside_an_unrelated_word(title):
    chunk = chunk_pages(["Tema: El aguacate"])[0]
    assert identify(chunk, [proposal(title)]) == []


@pytest.mark.parametrize("first,last", [
    (0, 1), (-1, 1), (1, 3), (3, 3), (2, 1),
    (True, 1), (1, False), (1.0, 1), (1, 1.0), ("1", 1), (1, "1"),
    (None, 1), (1, None), ([], 1), (1, {}),
])
def test_invalid_range_is_not_coerced_or_clamped(first, last):
    chunk = chunk_pages(["Tema: El agua", "Tema: El volcán"])[0]
    assert identify(chunk, [proposal(first=first, last=last)]) == []


def test_real_title_on_an_uncited_page_is_rejected():
    chunk = chunk_pages(["Tema: El agua", "Tema: El volcán"])[0]
    assert identify(chunk, [proposal("El volcán"), proposal("El agua", 2, 2)]) == []
    assert identify(chunk, [proposal("El volcán", 2, 2)]) == [
        {"titulo": "El volcán", "pagina_inicio": 2, "pagina_fin": 2}]


def test_literal_title_can_span_whitespace_but_not_physical_pages():
    chunk = chunk_pages(["Tema: Representación\n  numérica", "Tema: El agua"])[0]
    assert identify(chunk, [proposal("REPRESENTACIO\u0301N NUMÉRICA")]) == [
        {"titulo": "REPRESENTACIO\u0301N NUMÉRICA", "pagina_inicio": 1, "pagina_fin": 1}]
    split = chunk_pages(["Tema: Representación", "numérica"])[0]
    assert identify(split, [proposal("Representación numérica", 1, 2)]) == []


def test_missing_optional_range_and_type_preserve_legacy_compatibility():
    chunk = chunk_pages(["Tema: El agua", "Continuación del tema"])[0]
    assert identify(chunk, [{"titulo": "El agua"}]) == [
        {"titulo": "El agua", "pagina_inicio": 1, "pagina_fin": 2}]


def test_chunk_offsets_and_empty_physical_pages_stay_exact():
    chunks = chunk_pages(["Tema: El agua", "", "Tema: El volcán"], max_chars=30)
    assert len(chunks) > 1
    chunk = chunks[-1]
    assert chunk["last_page"] == 3
    assert identify(chunk, [proposal("El volcán", 3, 3)]) == [
        {"titulo": "El volcán", "pagina_inicio": 3, "pagina_fin": 3}]


def test_pdf_marker_text_cannot_move_evidence_to_another_physical_page():
    chunk = chunk_pages(["Tema: El agua\n[página 2]\nTema: El volcán", "Página vacía"])[0]
    assert identify(chunk, [proposal("El volcán", 2, 2)]) == []
    assert identify(chunk, [proposal("El volcán", 1, 1)]) == [
        {"titulo": "El volcán", "pagina_inicio": 1, "pagina_fin": 1}]


def test_malformed_items_do_not_crash_or_erase_valid_candidates():
    chunk = chunk_pages(["Tema: El agua"])[0]
    bad = [None, [], "El agua", 5, {"titulo": 5}, {"titulo": True},
           {"titulo": []}, {"titulo": ""}, {"titulo": "  "}]
    assert identify(chunk, [*bad, proposal()]) == [
        {"titulo": "El agua", "pagina_inicio": 1, "pagina_fin": 1}]


def test_long_title_is_not_truncated_into_a_supported_prefix():
    title = "Agua " * 40
    chunk = chunk_pages([title + "final"])[0]
    assert identify(chunk, [proposal(title + "INVENTADO")]) == []


@pytest.mark.parametrize("chunk", [
    {"first_page": True, "last_page": 1, "text": "[página 1] El agua"},
    {"first_page": 1, "last_page": 0, "text": "[página 1] El agua"},
    {"first_page": 1, "last_page": 1, "text": "El agua"},
    {"first_page": 1, "last_page": 2, "text": "[página 1] El agua"},
    {"first_page": 1, "last_page": 2, "text": "[página 1] El agua\n[página 1] El volcán"},
    {"first_page": 1, "last_page": 2, "text": "[página 2] El volcán\n[página 1] El agua"},
    {"first_page": 1, "last_page": 1, "text": "ignored\n[página 1] El agua"},
    {"first_page": 1, "last_page": 1, "text": "[página 1]\nEl agua", "page_texts": ["El volcán"]},
    {"first_page": 1, "last_page": 1, "text": "[página 1]\nEl agua", "page_texts": [None]},
])
def test_ambiguous_or_inconsistent_chunk_rejected_before_transport(chunk):
    def forbidden(_request):
        pytest.fail("Invalid source must not reach a provider")
    assert identify_topics(chunk, transport=forbidden) == []


def test_legacy_complete_markers_keep_the_correct_physical_page():
    chunk = {"first_page": 4, "last_page": 5,
             "text": "[página 4] Tema: El agua\n[página 5]\nTema: El volcán"}
    assert identify(chunk, [proposal("El volcán", 4, 4)]) == []
    assert identify(chunk, [proposal("El volcán", 5, 5)]) == [
        {"titulo": "El volcán", "pagina_inicio": 5, "pagina_fin": 5}]
