"""Synthetic regressions, not an independent curriculum-quality evaluation.

These inputs are authored for the bug fix. They exercise mechanical matching,
page attribution and fail-closed coverage; no teacher annotation is implied.
"""

import copy
import hashlib
import io
import unicodedata

import pytest

from curriculum.claims import compile_dossier_to_atomic_claims
from curriculum.source_interpreter import (
    CANONICAL_CAMPOS,
    ORIGIN_EXTRACTED,
    REVIEW_PENDING,
    STATUS_AMBIGUOUS,
    STATUS_SUPPORTED,
    CurriculumSourceInterpreter,
    ImportDossier,
)
from curriculum.verification import verify_curriculum_dossier
from test_t15_curriculum_import import make_minimal_pdf


def extract(pages, warnings=None):
    return CurriculumSourceInterpreter._extract_general_fields(
        pages, "synthetic-sha", warnings or {}
    )["campos_formativos"]


@pytest.mark.parametrize("raw,canonical", [
    ("SABERES Y PENSAMIENTO CIENTIFICO", CANONICAL_CAMPOS[1]),
    ("ETICA, NATURALEZA Y SOCIEDADES", CANONICAL_CAMPOS[2]),
    (unicodedata.normalize("NFD", CANONICAL_CAMPOS[1]), CANONICAL_CAMPOS[1]),
    ("Saberes y\npensamiento científico", CANONICAL_CAMPOS[1]),
    ("De lo humano\ny lo comunitario", CANONICAL_CAMPOS[3]),
    ("Ｌｅｎｇｕａｊｅｓ", CANONICAL_CAMPOS[0]),
    ("Saberes\u00a0y\u200bpensamiento científico", CANONICAL_CAMPOS[1]),
    ("Saberes\r\ny\t\tpensamiento\n\ncientífico", CANONICAL_CAMPOS[1]),
])
def test_normalized_names_keep_exact_physical_source(raw, canonical):
    pages = ["Portada administrativa", f"Campo formativo: {raw}"]
    field = extract(pages)
    assert field.value == [canonical]
    assert field.origin == ORIGIN_EXTRACTED
    assert field.status == STATUS_SUPPORTED
    assert field.review == REVIEW_PENDING
    assert len(field.evidence) == 1
    assert field.evidence[0].page_number == 2
    assert field.evidence[0].excerpt == raw
    assert field.evidence[0].excerpt in pages[1]


def test_deduplication_preserves_canonical_order_and_real_pages():
    pages = ["DE LO HUMANO Y LO COMUNITARIO", "LENGUAJES\nLenguajes"]
    field = extract(pages)
    assert field.value == [CANONICAL_CAMPOS[0], CANONICAL_CAMPOS[3]]
    assert [(ev.page_number, ev.excerpt) for ev in field.evidence] == [
        (2, "LENGUAJES"), (1, "DE LO HUMANO Y LO COMUNITARIO")
    ]


@pytest.mark.parametrize("pages", [
    ["Campo: Saberes y pensamiento", "científico"],
    ["Saberes y pensamiento científicoindustrial"],
    ["Metalenguajes"],
    ["Saberes y científico pensamiento"],
    ["Portada", "Otra página", "Otra página", "Lenguajes"],
])
def test_incomplete_reordered_subword_or_out_of_overview_names_abstain(pages):
    field = extract(pages)
    assert not any(c in field.value for c in CANONICAL_CAMPOS)
    assert field.status != STATUS_SUPPORTED


def test_warning_uses_actual_citation_page_not_field_label_page():
    field = extract(["Campo formativo:", "LENGUAJES"], {2: "Captura parcial"})
    assert field.status == STATUS_AMBIGUOUS
    assert field.evidence[0].page_number == 2


def test_unrelated_warning_does_not_degrade_and_unicode_prefix_keeps_offsets():
    pages = ["Página con advertencia", "Oficina ﬁnal: Campo: lenguajes"]
    field = extract(pages, {1: "Captura parcial"})
    assert field.status == STATUS_SUPPORTED
    assert field.evidence[0].page_number == 2
    assert field.evidence[0].excerpt == "lenguajes"


def test_punctuation_around_name_does_not_change_source_excerpt():
    raw = "«LENGUAJES»"
    field = extract([f"Campo formativo: {raw}"])
    assert field.value == ["Lenguajes"]
    assert field.evidence[0].excerpt == raw


def dossier_and_source():
    # The verifier's documented cached source route avoids font-encoding effects.
    pages = ["Campo formativo: LENGUAJES", "Campo: SABERES Y PENSAMIENTO CIENTIFICO"]
    data = b"synthetic cached physical source for campos regression"
    sha = hashlib.sha256(data).hexdigest()
    field = CurriculumSourceInterpreter._extract_general_fields(pages, sha, {})["campos_formativos"]
    dossier = ImportDossier(
        source_sha256=sha, source_name="synthetic.pdf", page_count=2,
        general_fields={"campos_formativos": field}, sessions=[],
    )
    return dossier, (data, sha, pages)


def field_items(dossier, source):
    report = verify_curriculum_dossier(dossier, source)
    return [i for i in report.items if i["target"].startswith("general.campos_formativos")]


def test_multipage_list_is_checked_only_with_complete_cited_coverage():
    dossier, source = dossier_and_source()
    field = dossier.general_fields["campos_formativos"]
    assert field.value == CANONICAL_CAMPOS[:2]
    items = field_items(dossier, source)
    assert len(items) == 2
    assert all(i["status"] == "checked" for i in items)
    claim = compile_dossier_to_atomic_claims(dossier)[0]
    assert claim.object_value == CANONICAL_CAMPOS[:2]
    assert [(e.page_number, e.excerpt) for e in claim.evidence] == [
        (1, "LENGUAJES"), (2, "SABERES Y PENSAMIENTO CIENTIFICO")
    ]
    assert field.review == REVIEW_PENDING


@pytest.mark.parametrize("mutation", [
    "uncited", "foreign_hash", "wrong_page", "unrelated_quote", "empty_value",
    "null_value", "bool_page", "out_of_range", "empty_excerpt", "subword_excerpt",
])
def test_multipage_coverage_cannot_use_missing_or_invalid_support(mutation):
    dossier, source = dossier_and_source()
    dossier = copy.deepcopy(dossier)
    field = dossier.general_fields["campos_formativos"]
    # The base assertion prevents an extraction miss from making the negative vacuous.
    assert field.value == CANONICAL_CAMPOS[:2]
    if mutation == "uncited":
        field.evidence.pop()
    elif mutation == "foreign_hash":
        field.evidence[-1].document_sha256 = "foreign"
    elif mutation == "wrong_page":
        field.evidence[-1].page_number = 1
    elif mutation == "unrelated_quote":
        field.evidence[-1].excerpt = "Campo:"
    elif mutation == "empty_value":
        field.value.append("")
    elif mutation == "null_value":
        field.value.append(None)
    elif mutation == "bool_page":
        field.evidence[-1].page_number = True
    elif mutation == "out_of_range":
        field.evidence[-1].page_number = 3
    elif mutation == "empty_excerpt":
        field.evidence[-1].excerpt = ""
    else:
        source[2][1] += "industrial"
        field.evidence[-1].excerpt += "industrial"
    items = field_items(dossier, source)
    assert items
    assert not any(i["status"] == "checked" for i in items)


def test_verifier_never_assembles_one_name_from_two_citations():
    dossier, source = dossier_and_source()
    field = dossier.general_fields["campos_formativos"]
    field.value = [CANONICAL_CAMPOS[1]]
    source[2][:] = ["Saberes y pensamiento", "científico"]
    field.evidence[0].excerpt = source[2][0]
    field.evidence[1].excerpt = source[2][1]
    assert all(i["status"] != "checked" for i in field_items(dossier, source))


@pytest.mark.parametrize("origin,status", [("proposed", "supported"), ("extracted", "ambiguous")])
def test_physical_coverage_never_removes_required_human_review(origin, status):
    dossier, source = dossier_and_source()
    field = dossier.general_fields["campos_formativos"]
    field.origin, field.status = origin, status
    assert any(i["status"] == "needs_teacher_review" for i in field_items(dossier, source))
    assert compile_dossier_to_atomic_claims(dossier)[0].state != "backed"


def test_generated_pdf_prepare_verify_compile_roundtrip():
    pdf = make_minimal_pdf([
        "Proyecto: Bitacora del patio\nCampo formativo: LENGUAJES",
        "Campo formativo: SABERES Y PENSAMIENTO\nCIENTIFICO",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf))
    field = dossier.general_fields["campos_formativos"]
    assert field.value == CANONICAL_CAMPOS[:2]
    assert [(e.page_number, e.excerpt) for e in field.evidence] == [
        (1, "LENGUAJES"), (2, "SABERES Y PENSAMIENTO\nCIENTIFICO")
    ]
    assert all(i["status"] == "checked" for i in field_items(dossier, io.BytesIO(pdf)))
    claim = next(c for c in compile_dossier_to_atomic_claims(dossier) if c.predicate == "campo_formativo")
    assert len(claim.evidence) == 2
    assert claim.to_dict() == next(
        c for c in compile_dossier_to_atomic_claims(ImportDossier.from_dict(dossier.to_dict()))
        if c.predicate == "campo_formativo"
    ).to_dict()
