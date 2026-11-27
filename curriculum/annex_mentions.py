"""Literal numbered annex mentions; never scan across intervening prose/numbers.

The literal parser identifies references, not obligation or availability. The
separate bounded helper can withhold necessity or recognize explicit instructions;
all results remain subject to contextual and editorial review.
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


# A deliberately bounded interpretation of instructions, separate from mention
# identity. Unknown discourse is withheld; this is not a general Spanish parser.
_USE = r'(?:consultar|usar|utilizar|leer|resolver|trabajar|revisar|completar|comparar|responder|registrar|escribir|dibujar|colorear|recortar|pegar|observar|analizar|relacionar|traer|entregar|llenar|contestar|realizar)'
_CONDITION = re.compile(
    r'\b(?:si|cuando|opcional(?:mente)?|quizas?|podria[n]?|puede[n]?|podra[n]?)\b'
    r'|\b(?:en caso de|tal vez|de ser necesario|a eleccion)\b'
)
_NEGATIVE = re.compile(r'\b(?:no|sin|evitar|omitir|prescindir)\b')
_USE_PRONOUN = r'(?:consultarlo|usarlo|utilizarlo|resolverlo|trabajarlo|revisarlo|corregirlo)'
_ANAPHOR = re.compile(r'\b(?:' + _USE_PRONOUN + r'|este anexo|ese anexo|dicho anexo)\b')


def annex_requirement(text: str, annex_number: str) -> bool | None:
    """Infer only a bounded explicit need, retaining false/unknown separately.

    This helper neither detects a physical sheet nor changes literal mentions.
    Conditions and unresolved/ambiguous anaphora withhold necessity (None).
    Positive and negative uses of the same resource also withhold necessity.
    """
    import unicodedata

    folded = ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                     if not unicodedata.combining(c))
    number = str(annex_number).lstrip('0') or '0'
    outcomes: list[bool | None] = []
    # Keep semicolons within the sentence: a following anaphoric instruction
    # may negate or qualify the referenced use. Never cross activity bullets.
    sentences = re.split(r'[.!?]+|\n\s*(?:[-•]|actividad\s*\d+\s*[:.-])', folded)
    for sentence in sentences:
        mentions = list(iter_annex_mentions(sentence))
        targets = [mention for mention in mentions if number in mention.numbers]
        if not targets:
            continue
        if _CONDITION.search(sentence) or re.search(r'\bo\s+(?:(?:el|los)\s+)?anexos?\b', sentence):
            outcomes.append(None)
            continue
        distinct = {n for mention in mentions for n in mention.numbers}
        for mention in targets:
            clause_start = sentence.rfind(';', 0, mention.start) + 1
            prefix = sentence[clause_start:mention.start]
            # A new coordinated instruction has its own polarity. Number lists
            # are untouched because their conjunction is not followed by a verb.
            prefix = re.split(r'\b(?:y|pero|sino)\s+(?=(?:no\s+)?' + _USE + r'\b)', prefix)[-1]
            reminder = re.search(r'\bno\s+olvidar\s+(?:' + _USE + r'\s+)?(?:el|los)?\s*$', prefix)
            if _NEGATIVE.search(prefix) and not reminder:
                direct_negative = re.search(
                    r'\b(?:no|sin)\s+(?:volver\s+a\s+)?' + _USE + r'\s+(?:el|los|un|unos)?\s*$'
                    r'|\bsin\s+(?:el|los)?\s*$'
                    r'|\bno\s+(?:hace falta|es necesario|se requiere|requiere|se necesita|necesita)\b'
                    r'|\b(?:evitar|omitir|prescindir de)\s+(?:' + _USE + r'\s+)?(?:el|los)?\s*$',
                    prefix,
                )
                # Incidental negation ("sin prisa", "sin ayuda") is not a
                # negation of using the annex; unsupported scope is withheld.
                outcome = False if direct_negative else None
            elif re.search(r'\b(?:sustituir|reemplazar)\b', prefix):
                if re.search(r'\bpor\s+(?:el|los)?\s*$', prefix) and list(iter_annex_mentions(prefix)):
                    outcome = True
                elif re.search(r'\b(?:sustituir|reemplazar)\s+(?:el|los)?\s*$', prefix):
                    outcome = False
                else:
                    outcome = None
            elif reminder or re.search(r'\b' + _USE + r'\b|\b(?:requiere|requieren|necesita|necesitan)\b', prefix):
                outcome = True
            else:
                outcome = None

            following = sentence[mention.end:]
            if re.match(r'\s+(?:no\s+es\s+(?:necesario|obligatorio|requerido)|no\s+hace\s+falta)\b', following):
                outcome = False
            elif re.match(r'\s+es\s+(?:necesario|obligatorio|requerido)\b', following):
                outcome = True
            # Resolve only a singular, local antecedent. With multiple possible
            # resources, a pronoun must not silently choose the nearest number.
            if _ANAPHOR.search(following):
                if len(distinct) != 1:
                    outcome = None
                elif re.search(r'\b(?:no hace falta|no es necesario|no se requiere)\b[^;]*' + _ANAPHOR.pattern
                               + r'|\b(?:no|sin)\s+(?:volver\s+a\s+)?' + _USE_PRONOUN + r'\b', following):
                    outcome = False
                elif _NEGATIVE.search(following):
                    outcome = None
                elif re.search(r'\b' + _USE_PRONOUN + r'\b', following):
                    outcome = None if outcome is False else True
            outcomes.append(outcome)
    if not outcomes or any(value is None for value in outcomes):
        return None
    return outcomes[0] if all(value == outcomes[0] for value in outcomes) else None
