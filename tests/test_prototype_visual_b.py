"""Contract tests for the isolated Visual B static prototype."""
from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
PROTOTYPE = ROOT / "prototypes" / "visual-b"


def read(name: str) -> str:
    return (PROTOTYPE / name).read_text(encoding="utf-8")


def test_visual_b_static_bundle_and_docs_exist():
    for name in ("index.html", "styles.css", "app.js", "DESIGN.md", "README.md"):
        assert (PROTOTYPE / name).is_file(), name


def test_visual_b_has_the_five_navigable_experiences():
    html = read("index.html")
    for screen in ("home", "student", "roadmap", "teacher", "active"):
        assert f'id="screen-{screen}"' in html
        assert f'data-screen="{screen}"' in html


def test_visual_b_marks_synthetic_data_and_human_boundaries():
    bundle = "\n".join(read(name) for name in ("index.html", "app.js", "DESIGN.md", "README.md"))
    assert "Demostración sintética" in bundle
    assert "EditorialReviewer" in bundle
    assert "IA" in bundle
    assert "maestra" in bundle
    assert "no publica" in bundle.lower()


def test_visual_b_exposes_roadmap_states_and_session_states():
    html = read("index.html")
    for label in (
        "disponible",
        "visto",
        "actual",
        "bloqueado",
        "completado",
        "Espera",
        "Activo",
        "Cerrado",
        "Error",
    ):
        assert label.lower() in html.lower()
    assert "unidades" in html.lower()
    assert "lecciones" in html.lower()
    assert "actividades" in html.lower()


def test_visual_b_is_offline_and_does_not_expose_sensitive_identity_patterns():
    bundle = "\n".join(read(name) for name in ("index.html", "styles.css", "app.js"))
    assert not re.search(r"(?:https?:)?//", bundle)
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f-]{27,}", bundle, re.I)
    for forbidden in ("@anthropic", "cdn.", "unpkg", "jsdelivr", "<img", "<source", "data:image"):
        assert forbidden.lower() not in bundle.lower()
    for forbidden in ("correo", "matrícula", "contraseña", "password", "puntuación individual"):
        assert forbidden.lower() not in bundle.lower()


def test_visual_b_has_accessible_responsive_and_reduced_motion_hooks():
    html = read("index.html")
    css = read("styles.css")
    assert 'lang="es"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-label="' in html
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "projection" in css
    assert "@media (max-width: 520px)" in css


def test_visual_b_js_keeps_ephemeral_nicknames_only_in_memory():
    js = read("app.js")
    docs = "\n".join(read(name) for name in ("index.html", "README.md", "DESIGN.md"))
    assert "addEventListener" in js
    assert "qr" in js.lower()
    assert "apodo" in js.lower()
    assert "activo" in js.lower()
    assert "cerrado" in js.lower()
    assert "error" in js.lower()
    for source in (js, docs):
        for forbidden in ("localStorage", "sessionStorage", "IndexedDB", "cookie"):
            assert forbidden.lower() not in source.lower()
    assert "initialSession" in js
    assert "memoria" in docs.lower()
    assert "se borra al cerrar" in docs.lower()
    assert re.search(r"session\.nicknames\s*=\s*\[\]", js)
    assert re.search(r"if \(state === 'cerrado'\)\s*\{.*?session\.nicknames\s*=\s*\[\];.*?renderSession\(\);", js, re.S)
