"""Two independently supplied fictional contexts, not held-out or human gold."""
import io
import json
import socket
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from curriculum.source_interpreter import CurriculumSourceInterpreter
from test_t15_curriculum_import import make_minimal_pdf


FIXTURES = json.loads((Path(__file__).parent / "fixtures/source_structure/roles_unicode_v1.json").read_text())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Role acceptance is offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def prepare(pages):
    # Helvetica's visible middle dot has a ToUnicode mapping to the legacy
    # U+F0B7 bullet. The test exercises a real PDF without mocking extraction.
    pdf = make_minimal_pdf([p.replace("\uf0b7", "·") for p in pages])
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(pdf)))
    mapping = DecodedStreamObject()
    mapping.set_data(b"/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
                     b"/CMapType 2 def\n1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
                     b"1 beginbfchar\n<B7> <F0B7>\nendbfchar\nendcmap\n"
                     b"CMapName currentdict /CMap defineresource pop\nend\nend")
    for page in writer.pages:
        page["/Resources"]["/Font"]["/F1"][NameObject("/ToUnicode")] = writer._add_object(mapping)
    result = io.BytesIO()
    writer.write(result)
    return CurriculumSourceInterpreter.prepare(io.BytesIO(result.getvalue()))


def test_plain_homework_action_after_its_label_is_a_pending_instruction():
    case = FIXTURES["cases"][0]
    dossier = prepare(["Proyecto: Cuaderno del patio\nDESARROLLO DEL PROYECTO\n" + case["pages"][0]])
    blocks = dossier.sessions[0].source_structure["blocks"]
    target, = [b for b in blocks if b["text"].startswith(case["target_text_prefix"])]
    assert target["role"] == "instruction"
    assert (target["origin"], target["status"], target["review"]) == ("proposed", "ambiguous", "pending")
    assert all(not (b["text"] == "TAREA:" and b["role"] == "instruction") for b in blocks)
    assert dossier.declared_session_count == 0
    assert dossier.verification_report["blocked_count"] == 0


def test_adverbial_action_after_resources_is_a_pending_instruction():
    case = FIXTURES["cases"][1]
    dossier = prepare(["Proyecto: Cuaderno del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n" + case["pages"][0]])
    blocks = dossier.sessions[0].source_structure["blocks"]
    target, = [b for b in blocks if b["text"].startswith(case["target_text_prefix"])]
    assert target["role"] == "instruction"
    assert (target["origin"], target["status"], target["review"]) == ("proposed", "ambiguous", "pending")
    assert "registro de acuerdo con los comentarios del equipo." in target["text"]
    assert [b["role"] for b in blocks if b["text"] == "Bitácora."] == ["resource", "resource"]
    assert any(b["text"].startswith("Copiar") and b["role"] == "instruction" for b in blocks)
    assert dossier.declared_session_count == 0
    assert dossier.verification_report["blocked_count"] == 0


@pytest.mark.parametrize("after_label", [
    "Material pendiente.",
    "Individualmente, materiales para recortar.",
    "Recursos\nRealizar una cartulina de muestra.",
    "Fase #2. Accion\nRealizar una cartulina de muestra.",
])
def test_homework_does_not_promote_unrecognized_text_or_cross_a_new_section(after_label):
    dossier = prepare([
        "Proyecto: Cuaderno del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "TAREA:\n" + after_label,
    ])
    blocks = dossier.sessions[0].source_structure["blocks"]
    assert all(b["role"] != "instruction" for b in blocks)
    assert dossier.declared_session_count == 0
    assert dossier.verification_report["blocked_count"] == 0


def test_existing_introductory_phrase_survives_a_nested_adverbial_prefix():
    dossier = prepare([
        "Proyecto: Cuaderno del patio\nDESARROLLO DEL PROYECTO\nFase #1. Planeacion\n"
        "Recursos\n-Bitacora.\n* Posteriormente, en equipos, comparar los dibujos.\n",
    ])
    blocks = dossier.sessions[0].source_structure["blocks"]
    assert any(b["text"].startswith("Posteriormente") and b["role"] == "instruction" for b in blocks)
