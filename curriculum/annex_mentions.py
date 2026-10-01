"""Literal numbered annex mentions; never scan across intervening prose/numbers.

This parser identifies textual references, not obligation, pedagogical suitability
or availability. Negated and conditional uses still require contextual review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERN = re.compile(
    r'(?<!\w)(?:anexos?|cuadernillo\s+de\s+actividades\s+anexos?)\s*'
    r'([0-9]+(?:\s*(?:,|y)\s*[0-9]+)*)(?!\w)', re.I,
)


@dataclass(frozen=True)
class AnnexMention:
    numbers: tuple[str, ...]
    start: int
    end: int
    text: str


def iter_annex_mentions(text: str):
    for match in _PATTERN.finditer(text):
        # A trailing coordinated numeral can quantify something other than an
        # annex ("anexo 1 y 2 páginas después"). Do not promote that count to a
        # target. The directly named first annex is unaffected.
        parts = list(re.finditer(r'[0-9]+', match.group(1)))
        end = match.end()
        if len(parts) > 1 and re.match(
            r'\s+(?:p[aá]ginas?|puntos?|ejercicios?|preguntas?|veces|minutos?|d[ií]as?|horas?|tarjetas?)\b',
            text[end:], re.I,
        ):
            parts.pop()
            end = match.start(1) + parts[-1].end()
        # Canonicalize padding without Python's large-string int conversion.
        numbers = tuple(dict.fromkeys(part.group().lstrip('0') or '0' for part in parts))
        yield AnnexMention(numbers, match.start(), end, text[match.start():end])
