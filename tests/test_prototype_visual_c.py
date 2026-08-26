from pathlib import Path
import re


ROOT = Path(__file__).parents[1] / "prototypes" / "visual-c"


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_prototype_c_has_isolated_static_deliverable():
    for name in ("index.html", "styles.css", "app.js", "DESIGN.md", "README.md"):
        assert (ROOT / name).is_file(), name


def test_prototype_c_names_the_four_local_routes_and_synthetic_demo():
    html = read("index.html")
    for route in ("home", "student", "teacher", "active"):
        assert f'id="{route}"' in html
    assert "Demostración sintética" in html
    assert "EditorialReviewer" in html
    assert "maestra" in html.lower()


def test_prototype_c_covers_states_and_classroom_controls():
    html = read("index.html")
    for state in ("espera", "activo", "cerrado", "error"):
        assert f'data-state="{state}"' in html
    for label in ("Preparar sesión", "Activar", "Cerrar sesión", "Continuar"):
        assert label in html
    assert "QR" in html
    assert "apodos locales" in html
    assert "0 participantes" in html


def test_prototype_c_works_without_remote_dependencies_and_supports_accessibility():
    html = read("index.html")
    css = read("styles.css")
    js = read("app.js")
    combined = html + css + js
    assert not re.search(r"(?:https?:)?//", combined)
    assert "prefers-reduced-motion" in css
    assert ":focus-visible" in css
    assert "viewport" in html
    assert "aria-live" in html
    assert "addEventListener" in js


def test_prototype_c_navigation_is_wired_to_local_views():
    html = read("index.html")
    js = read("app.js")
    for view in ("home", "student", "teacher", "active"):
        assert f'data-view="{view}"' in html
    assert "data-view" in js
    assert "classList" in js
    assert "local" in js.lower()
