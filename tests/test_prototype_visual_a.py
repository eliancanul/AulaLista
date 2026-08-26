from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
PROTOTYPE = ROOT / "prototypes" / "visual-a"


def read(name: str) -> str:
    return (PROTOTYPE / name).read_text(encoding="utf-8")


def test_visual_a_is_an_offline_navigable_prototype():
    html = read("index.html")
    css = read("styles.css")
    js = read("app.js")
    assert '<script src="app.js"' in html
    assert 'href="styles.css"' in html
    for route in ("inicio", "estudiante", "docente", "actividad"):
        assert f'data-route="{route}"' in html or f'#{route}' in js
    assert "DemoPackage" in html
    assert "datos sintéticos" in html.lower()
    assert "EditorialReviewer" in html
    assert "solo propone" in html.lower()
    assert "published" not in html.lower() or "publish" not in html.lower()
    assert "prefers-reduced-motion" in css
    assert ":focus-visible" in css
    assert "matchMedia" in js
    assert "localStorage" in js


def test_visual_a_covers_required_states_and_local_participants():
    html = read("index.html")
    js = read("app.js")
    combined = f"{html}\n{js}".lower()
    for state in ("espera", "activa", "cerrada", "error"):
        assert state in combined
    for phrase in ("camino", "temas vistos", "enlace", "qr", "apodo", "conteo"):
        assert phrase in combined
    assert "sin cuenta" in combined
    assert "puntuación individual" in combined


def test_visual_a_has_no_network_or_identity_leaks():
    for name in ("index.html", "styles.css", "app.js", "DESIGN.md", "README.md"):
        content = read(name)
        assert not re.search(r"https?://|//cdn|fonts\.googleapis|unpkg|jsdelivr", content, re.I)
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", content, re.I)
    assert "Alice" not in read("index.html")
    assert "student@example" not in read("index.html")
