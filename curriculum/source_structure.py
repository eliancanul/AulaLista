"""Conservative source blocks for phase-based plans, independent of lessons.

Roles and associations are review candidates. Every fragment keeps physical
page offsets; unknown text is retained instead of promoted to an activity.
"""
import re


_PHASE = re.compile(r"^Fase\s*#?\s*(\d+)(?:\s*[.:-]\s*(.*))?$", re.IGNORECASE)
_RESOURCE = re.compile(r"^(?:Recursos(?:\s+e)?|Materiales|implicaciones)\b", re.IGNORECASE)
_END = re.compile(r"^(?:Productos(?:\s+y\s+evidencias)?|Evaluaci[oó]n|Aspectos\s+a\s+evaluar)\b", re.IGNORECASE)
_BULLET = re.compile(r"^(?P<marker>[•*\-]|\d+[.)])\s*(?P<text>.+)$")
_ACTIVITY = re.compile(r"^Actividad\b", re.IGNORECASE)
_HOMEWORK = re.compile(r"^Tarea(?:\s+(?:en|para)\s+casa)?\s*[:.-]", re.IGNORECASE)
_HOMEWORK_LABEL = re.compile(r"^Tarea(?:\s+(?:en|para)\s+casa)?\s*[:.-]\s*$", re.IGNORECASE)
_ACTION = re.compile(
    r"^(?:[a-záéíóúñ]+(?:ar|er|ir)(?:se)?|"
    r"observa|compara|escribe|lee|dibuja|resuelve|comenta|explica|comparte|"
    r"observan|comparan|escriben|leen|dibujan|resuelven|comentan|explican|"
    r"observen|comparen|escriban|lean|dibujen|resuelvan|comenten|expliquen)\b",
    re.IGNORECASE,
)
_INTRODUCTORY = re.compile(r"^(?:En|De|Con|A|Al|Antes|Despu[eé]s|Luego|Posteriormente)\b", re.IGNORECASE)
_ADVERBIAL = re.compile(r"^[a-záéíóúñ]+mente\s*,\s*", re.IGNORECASE)


def _starts_instruction(text):
    if _ACTION.match(text):
        return True
    adverbial = _ADVERBIAL.match(text)
    if adverbial and _ACTION.match(text[adverbial.end():]):
        return True
    if _INTRODUCTORY.match(text):
        return any(_ACTION.fullmatch(word.strip(".,:;")) for word in text.split()[1:12])
    return False


def scan_phase_structure(pages, segments, sha):
    """Return literal, ordered blocks and evidenced phases within one scope."""
    phases, blocks = [], []
    phase_id = None
    resource_context = False
    homework_context = False
    ended = False
    principal = None
    for page_number, segment in segments:
        offset = pages[page_number - 1].find(segment)
        for raw in segment.splitlines(keepends=True):
            text = raw.strip()
            start = offset + len(raw) - len(raw.lstrip())
            offset += len(raw)
            if not text:
                continue
            fragment = {
                "document_sha256": sha, "page_number": page_number,
                "text_start": start, "text_end": start + len(text), "excerpt": text,
            }
            match = _PHASE.fullmatch(text)
            if match:
                ended = False
                phase_id = f"phase_p{page_number}_{start}"
                phases.append({"phase_id": phase_id, "number": match[1],
                               "title": match[2] or "", "evidence": [fragment]})
                resource_context = False
                homework_context = False
                principal = None
                continue
            parent_id = None
            if text.upper() == "DESARROLLO DEL PROYECTO":
                role = "heading"
                homework_context = False
            elif _END.match(text):
                ended = True
                phase_id = None
                homework_context = False
                role = "heading"
            elif ended:
                role = "unassigned"
            elif _RESOURCE.match(text):
                resource_context = True
                homework_context = False
                role = "resource_heading"
            elif _ACTIVITY.match(text):
                role = "activity"
            elif _HOMEWORK.match(text):
                role = "heading" if _HOMEWORK_LABEL.fullmatch(text) else "instruction"
                homework_context, resource_context = True, False
            else:
                bullet = _BULLET.fullmatch(text)
                content = bullet["text"] if bullet else text
                if _HOMEWORK.match(content):
                    role = "heading" if _HOMEWORK_LABEL.fullmatch(content) else "instruction"
                    homework_context, resource_context = True, False
                elif content.startswith(("¿", "?")):
                    role = "question"
                    parent_id = principal["block_id"] if principal else None
                elif (bullet and bullet["marker"][0].isdigit() and principal
                      and principal["text"].endswith(":")):
                    role = "step"
                    parent_id = principal["block_id"]
                elif bullet:
                    role = ("instruction" if _starts_instruction(content) else
                            "resource" if resource_context else "unassigned")
                elif homework_context and _starts_instruction(text):
                    role = "instruction"
                elif (principal and principal["phase_id"] == phase_id and text[0].islower()
                      and not principal["text"].endswith((".", ":", "?", "!", ";"))):
                    principal["text"] += " " + text
                    principal["evidence"].append(fragment)
                    continue
                else:
                    role = "unassigned"
                if bullet:
                    text = content
            blocks.append({
                "block_id": f"block_p{page_number}_{start}", "role": role,
                "text": text, "phase_id": phase_id, "parent_id": parent_id,
                "evidence": [fragment], "origin": "proposed",
                "status": "ambiguous", "review": "pending",
            })
            if role in {"instruction", "activity"}:
                principal = blocks[-1]
            elif role not in {"question", "step"}:
                principal = None
    return {"schema_version": 1, "phases": phases, "blocks": blocks}
