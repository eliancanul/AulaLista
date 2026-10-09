"""Source-grounded worksheet candidates; discovery never confirms print pages."""
import hashlib
import re
import unicodedata


_NUMBERED = re.compile(r"^ANEXO\s*(?:#|No\.?|N°)?\s*0*(\d+)(?:\s*[-–—:]\s*(.*))?$", re.IGNORECASE)
_QUOTED = re.compile(r'["“«]([^"”»]{3,180})["”»]')
_MATERIAL = re.compile(r"\b(?:actividad(?:es)?|fichas?|hojas?|anexos?|ejercicios?)\b", re.IGNORECASE)
_RESET = re.compile(r"^[^\S\r\n]*(?:Proyecto\b|SESI[ÓO]N\b|DESARROLLO DEL PROYECTO\b|DATOS GENERALES\b)", re.IGNORECASE | re.MULTILINE)
_EDITORIAL = re.compile(
    r"^(?:(?:marca|sello)\s+)?editorial\b|^(?:copyright|ISBN|derechos\s+reservados)\b|©|^https?://|^www\.",
    re.IGNORECASE,
)
_EXERCISE = re.compile(
    r"^(?:observa|observar|lee|leer|escribe|escribir|dibuja|dibujar|completa|completar|"
    r"resuelve|resolver|relaciona|relacionar|explica|explicar|compara|comparar|"
    r"responde|responder|contesta|contestar|colorea|colorear|subraya|subrayar|"
    r"encierra|encerrar|ordena|ordenar|recorta|recortar)\b|^marca\s+(?:con|el|la|los|las|una?)\b",
    re.IGNORECASE,
)


def title_key(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", text.casefold())
                            if not unicodedata.combining(c)).split()).strip(' .:;"“”«»')


def worksheet_identity(title):
    """Stable material identity without using a physical page or printed number."""
    return "worksheet_" + hashlib.sha256(title_key(title).encode()).hexdigest()[:16]


def named_material_mentions(segments):
    """Quoted titles near a material noun, retaining every local occurrence."""
    mentions = []
    for page_number, text in segments:
        previous_material_end = None
        for match in _QUOTED.finditer(text):
            # Quoted names may wrap, but citations never cross physical pages.
            # Material context can qualify either side of the quoted name,
            # while a list continuation must have an explicit local connector.
            line_start = text.rfind("\n", 0, match.start()) + 1
            context = text[line_start:match.start()]
            line_end = text.find("\n", match.end())
            suffix = text[match.end():line_end if line_end != -1 else len(text)]
            material_context = bool(_MATERIAL.search(context) or _MATERIAL.search(suffix))
            if not context.strip() and line_start:
                previous_start = text.rfind("\n", 0, line_start - 1) + 1
                previous_line = text[previous_start:line_start].strip()
                material_context = material_context or bool(
                    _MATERIAL.search(previous_line)
                    and not re.search(r'[.!?"“”«»]', previous_line)
                )
            if previous_material_end is not None:
                gap = text[previous_material_end:match.start()]
                material_context = material_context or bool(
                    "\n\n" not in gap and re.fullmatch(r"\s*(?:[,;]|\by\b|\be\b)\s*", gap)
                )
            if material_context:
                title = " ".join(match[1].split())
                mentions.append({"title": title, "key": title_key(title),
                                 "identity": worksheet_identity(title),
                                 "page": page_number, "excerpt": match[0],
                                 "text_start": match.start(), "text_end": match.end()})
                previous_material_end = match.end()
            else:
                previous_material_end = None
    return mentions


def _page_lines(page):
    lines, offset = [], 0
    for raw in page.splitlines(keepends=True):
        text = raw.strip()
        start = offset + len(raw) - len(raw.lstrip())
        if text:
            lines.append((start, start + len(text), text))
        offset += len(raw)
    return lines


def _has_exercise_cue(text):
    if re.search(r"_{3,}|(?:^|\n)\s*[¿?]", text):
        return True
    return any(_EXERCISE.search(re.sub(r"^[\W\d_]+", "", line)) for line in text.splitlines())


def _is_editorial(text):
    return bool(_EDITORIAL.search(text)) and not _has_exercise_cue(text)


def _retain_content(candidate, page_number, page, start, end, *, boundary_prefix):
    """Keep excluded prefixes as source text rather than worksheet membership."""
    lines = _page_lines(page[start:end])
    usable = [text for _, _, text in lines if not _is_editorial(text)]
    uncertain_prefix = boundary_prefix and not _has_exercise_cue("\n".join(usable))
    for begin, finish, text in lines:
        excluded = _is_editorial(text) or uncertain_prefix
        fragment = {"page_number": page_number, "text_start": start + begin,
                    "text_end": start + finish, "excerpt": text,
                    "role": "unassigned" if excluded else "worksheet_content"}
        if excluded:
            fragment["reason"] = "editorial_or_unresolved_prefix"
            candidate["unassigned_fragments"].append(fragment)
        else:
            candidate["source_fragments"].append(fragment)
            if page_number not in candidate["candidate_exercise_pages"]:
                candidate["candidate_exercise_pages"].append(page_number)


def scan_annex_candidates(pages):
    """Keep numbered sheets and locate quoted-title worksheets with spans."""
    mentions = named_material_mentions(list(enumerate(pages, 1)))
    by_title = {}
    for mention in mentions:
        by_title.setdefault(mention["key"], mention)
    candidates = []
    for page_number, page in enumerate(pages, 1):
        lines = _page_lines(page)
        consumed_until = -1
        for index, (start, end, line) in enumerate(lines):
            if index <= consumed_until:
                continue
            numbered = _NUMBERED.fullmatch(line) if index < 6 else None
            mention = None
            label = line
            for last in range(index, len(lines)):
                possible_label = page[start:lines[last][1]]
                if len(possible_label) > 180:
                    break
                key = title_key(possible_label)
                found = by_title.get(key)
                if found:
                    mention, end, label = found, lines[last][1], possible_label
                    consumed_until = last
                if not any(title.startswith(key) for title in by_title):
                    break
            if numbered:
                candidates.append({"number": str(int(numbered[1])), "page": page_number,
                                   "label": line, "title": (numbered[2] or "").strip(),
                                   "heading_page": page_number, "heading_start": start,
                                   "heading_end": start + len(line)})
            elif (mention and (page_number, start) > (mention["page"], mention["text_end"])
                  and not any(item["page"] == page_number
                              and start < item["text_end"] and item["text_start"] < end
                              for item in mentions)):
                # A repeated quoted citation in a resource list is still a
                # mention, even when wrapping makes it look like a title line.
                # Keep its source evidence; only actual headings start ranges.
                candidates.append({
                    "number": "", "page": page_number, "label": label,
                    "title": mention["title"], "identity": mention["identity"],
                    "heading_page": page_number, "heading_start": start,
                    "heading_end": end,
                    "candidate_exercise_pages": [], "confirmed_pages": None,
                    "unassigned_fragments": [],
                    "source_fragments": [{"page_number": page_number, "text_start": start,
                                          "text_end": end, "excerpt": label,
                                          "role": "worksheet_heading"}],
                    "status": "ambiguous", "review": "pending",
                })
    for index, candidate in enumerate(candidates):
        if candidate["number"]:
            continue  # Keep numbered identity and the existing one-page candidate behavior.
        next_candidate = candidates[index + 1] if index + 1 < len(candidates) else None
        last_page = next_candidate["page"] if next_candidate else len(pages)
        for page_number in range(candidate["heading_page"], last_page + 1):
            page = pages[page_number - 1]
            start = candidate["heading_end"] if page_number == candidate["heading_page"] else 0
            end = (next_candidate.get("heading_start", 0)
                   if next_candidate and page_number == next_candidate["page"] else len(page))
            raw = page[start:end]
            boundary = _RESET.search(raw)
            if boundary:
                raw = raw[:boundary.start()]
            if not raw.strip():
                if boundary:
                    break
                continue
            _retain_content(
                candidate, page_number, page, start, start + len(raw),
                boundary_prefix=bool(next_candidate and page_number == next_candidate["page"]
                                     and page_number != candidate["heading_page"]),
            )
            if boundary:
                break
    return candidates
