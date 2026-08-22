from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_t12_script_and_local_diagram_are_present():
    script = ROOT / "scripts" / "run_evidence_demo.py"
    diagram = ROOT / "docs" / "evidence" / "t12-network.mmd"

    assert script.exists()
    assert diagram.exists()
    assert "AULALISTA_DB_PATH" in script.read_text(encoding="utf-8")
    assert "database table is locked" in script.read_text(encoding="utf-8")
    diagram_text = diagram.read_text(encoding="utf-8")
    assert "AulaLista" in diagram_text
    assert "WAN desconectada" in diagram_text


def test_t12_documentation_separates_implementation_synthetic_content_and_future():
    document = (ROOT / "docs" / "evidence-demo.md").read_text(encoding="utf-8")

    for heading in (
        "## Qué está implementado y qué no",
        "### Infraestructura implementada",
        "### Contenido de demostración",
        "### Trabajo futuro",
    ):
        assert heading in document
    assert "No afirma impacto pedagógico" in document
    assert "no constituye pilotaje con menores" in document
    assert "no demuestra continuidad real durante emergencias" in document
