"""Explicit hierarchy-selection policy shared by Atlas retrieval entry points."""

from __future__ import annotations

from typing import Literal

from curriculum.atlas.text import normalize_atlas_text


HierarchyFilterMode = Literal["prefer", "strict"]


def validate_hierarchy_filter(
    hierarchy_filter: dict[str, str] | None,
    mode: HierarchyFilterMode,
) -> None:
    """Reject unknown modes and malformed strict selections rather than broaden them."""
    if mode not in ("prefer", "strict"):
        raise ValueError("hierarchy_filter_mode debe ser 'prefer' o 'strict'.")
    if mode != "strict" or hierarchy_filter is None:
        return
    if not isinstance(hierarchy_filter, dict) or any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, str)
        or not normalize_atlas_text(value)
        for key, value in hierarchy_filter.items()
    ):
        raise ValueError("hierarchy_filter estricto requiere claves y valores de texto no vacíos.")


def matches_hierarchy(
    hierarchy: dict[str, str],
    hierarchy_filter: dict[str, str] | None,
) -> bool:
    """AND over explicit keys, using normalized equality, never inferred aliases.

    Missing or empty metadata cannot satisfy a selection. An empty selection
    imposes no restriction. Callers validate selection values before searching.
    """
    for key, expected in (hierarchy_filter or {}).items():
        actual = hierarchy.get(key)
        if not isinstance(actual, str) or not actual.strip():
            return False
        if normalize_atlas_text(actual) != normalize_atlas_text(expected):
            return False
    return True
