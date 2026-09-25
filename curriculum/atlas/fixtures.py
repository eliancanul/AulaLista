"""curriculum.atlas.fixtures
--------------------------
Fixtures sintéticos SEP versionados y serialización JSON para pruebas del Atlas.
"""

from __future__ import annotations

import json
from pathlib import Path

from curriculum.atlas.models import AtlasDocumentFragment, SourceManifest, segment_page_text


def create_synthetic_sep_fixture() -> tuple[SourceManifest, list[AtlasDocumentFragment]]:
    """Crea el fixture SEP sintético oficial para pruebas y desarrollo (#125).

    Representa la estructura de Primaria Fase 3 (1° Grado), Lenguajes, Proyectos de Aula:
    - Proyecto: "El nombrario del grupo"
    - Metodología: Aprendizaje Basado en Proyectos Comunitarios (ABPC)
    - Contenido y PDA: Escritura de nombres en la lengua materna
    - Ejes articuladores y recursos de aula.
    """
    manifest = SourceManifest(
        source_id="sep_primaria_fase3_lenguajes_sintetico_v1",
        title="Atlas SEP Sintético — Primaria Fase 3 (1° Grado) — Proyectos de Aula",
        publisher="Secretaría de Educación Pública (Fixture Sintético de Prueba)",
        edition_year=2024,
        version="1.0.0-synthetic",
        license="SEP-CONALITEG-Uso-Educativo-Nacional",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        hierarchy_levels=("fase", "grado", "campo_formativo", "metodologia"),
        is_synthetic=True,
        verified_permission=True,
        verified_identity=True,
        metadata={"ambito": "Educación Primaria Oficial", "fase": "Fase 3", "grado": "1°"},
    )

    h_base = {
        "fase": "Fase 3",
        "grado": "1°",
        "campo_formativo": "Lenguajes",
        "metodologia": "Aprendizaje Basado en Proyectos Comunitarios (ABPC)",
        "escenario": "Aula",
    }

    pages_data = [
        (
            1,
            "Proyecto de Aula: El nombrario del grupo.\n\n"
            "Propósito: Que las alumnas y los alumnos conozcan la escritura de su nombre, "
            "lo comparen con los nombres de sus compañeras y compañeros del aula, reconozcan "
            "su identidad y elaboren un collage y gafetes con su nombre propio.",
            "Presentación del Proyecto y Propósito",
        ),
        (
            2,
            "Metodología: Aprendizaje Basado en Proyectos Comunitarios (ABPC - 11 momentos).\n\n"
            "Fase 1: Momentos 1 a 3 (Identificación, Recuperación y Planificación).\n\n"
            "En el Momento 1 de Identificación, las niñas y niños identifican su nombre en gafetes de bienvenida "
            "y tarjetas con fotos dispuestas en el salón.",
            "Estructura Metodológica ABPC",
        ),
        (
            3,
            "Contenido curricular oficial: Escritura de nombres en la lengua materna.\n\n"
            "Procesos de Desarrollo de Aprendizaje (PDA): Escribe su nombre y lo compara con los nombres de sus "
            "compañeros. Identifica la letra inicial y final de su nombre, reconociendo sonidos semejantes.",
            "Contenidos y PDA de la Fase 3",
        ),
        (
            4,
            "Ejes articuladores del proyecto: Inclusión, Apropiación de las culturas a través de la lectura "
            "y la escritura, y Artes y experiencias estéticas.\n\n"
            "Actividades de desarrollo psicomotriz: Trazado de letras iniciales con plastilina, arena y pintura dactilar.",
            "Ejes Articuladores y Expresión Artística",
        ),
        (
            5,
            "Recursos didácticos y anexos requeridos para la sesión:\n\n"
            "Materiales: Cartulina, tarjetas blancas para gafetes de bienvenida, plastilina de colores, "
            "tijeras de punta redonda y pegamento blanco. Anexo 1: Plantilla para gafete ilustrado.",
            "Recursos Didácticos y Anexos",
        ),
    ]

    fragments: list[AtlasDocumentFragment] = []
    for page_num, text, sec_title in pages_data:
        frags = segment_page_text(
            source_id=manifest.source_id,
            page_number=page_num,
            page_text=text,
            hierarchy=h_base,
            section_title=sec_title,
        )
        fragments.extend(frags)

    return manifest, fragments


def save_atlas_fixture_to_json(
    manifest: SourceManifest,
    fragments: list[AtlasDocumentFragment],
    file_path: Path | str,
) -> None:
    """Exporta el manifiesto y fragmentos a un archivo JSON versionado."""
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "manifest": manifest.to_dict(),
        "fragments": [f.to_dict() for f in fragments],
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_atlas_fixture_from_json(file_path: Path | str) -> tuple[SourceManifest, list[AtlasDocumentFragment]]:
    """Carga un fixture de Atlas desde un archivo JSON versionado."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Fixture de Atlas no encontrado en '{p}'.")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    manifest = SourceManifest.from_dict(data["manifest"])
    fragments = [AtlasDocumentFragment.from_dict(fd) for fd in data["fragments"]]
    return manifest, fragments
