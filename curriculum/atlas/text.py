"""curriculum.atlas.text
---------------------
Normalización de texto, tokenización en español y generadores deterministas de ID.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from curriculum.atlas.constants import SPANISH_STOP_WORDS


def normalize_atlas_text(text: str) -> str:
    """Normaliza texto para comparaciones léxicas deterministas en español.

    - Convierte a minúsculas.
    - Elimina acentos/diacríticos conservando caracteres legibles (NFD -> ASCII).
    - Colapsa espacios en blanco.
    - Elimina caracteres de control y puntuación innecesaria.
    """
    if not text:
        return ""
    # Descomposición canónica para separar letras de acentos
    decomposed = unicodedata.normalize("NFD", text.lower())
    # Filtrar marcas diacríticas (Mn = Mark, nonspacing)
    without_accents = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # Reemplazar caracteres especiales y puntuación por espacios simples
    cleaned = re.sub(r"[^\w\s]", " ", without_accents)
    # Colapsar espacios múltiples
    return re.sub(r"\s+", " ", cleaned).strip()


def tokenize_atlas_text(text: str, remove_stopwords: bool = True) -> list[str]:
    """Tokeniza un texto normalizado separando por palabras de 2 o más caracteres."""
    norm = normalize_atlas_text(text)
    if not norm:
        return []
    words = re.findall(r"\b\w{2,}\b", norm)
    if remove_stopwords:
        words = [w for w in words if w not in SPANISH_STOP_WORDS]
    return words


def make_fragment_id(source_id: str, page_number: int, sequence_order: int, text: str) -> str:
    """Genera un fragment_id determinista usando SHA-256."""
    norm = normalize_atlas_text(text)
    seed = f"{source_id}:{page_number}:{sequence_order}:{norm}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"frag_{source_id}_p{page_number}_s{sequence_order}_{digest}"


def make_candidate_id(fragment_id: str, score: float, rank: int) -> str:
    """Genera un candidate_id determinista para el recibo."""
    seed = f"{fragment_id}:{score:.4f}:{rank}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]
    return f"cand_{digest}_r{rank}"


def make_receipt_id(query: str, claim_id: str | None, index_version: str, top_k: int) -> str:
    """Genera un receipt_id determinista para auditoría inmutable."""
    seed = f"{query}:{claim_id or 'none'}:{index_version}:{top_k}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"rec_{digest}"
