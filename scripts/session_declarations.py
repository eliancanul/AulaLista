"""Detached, deterministic v1 candidates for literal session declarations.

Never imported by production. No PDF access, database, provider, network,
catalogue lookup, dossier mutation, or pedagogical approval. See the frozen
contract in docs/development/session-declarations-contract.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from curriculum.claims import AtomicClaim
from curriculum.overview_fields import _advance_quotes
from curriculum.source_interpreter import SourceReference
from curriculum.source_segments import (
    project_occurrences, safety_boundary_positions, scan_session_segments,
)

VERSION = 'session-declarations.v1'
MATCHER_VERSION = 'session-declarations-matcher.v2.0.1'
PREDICATES = {'contenido': 'contenido_declarado', 'pda': 'pda_declarado'}
MAX_CHARACTERS = 2_000_000
MAX_RECORDS = 2_000
H = r'[^\S\r\n]'
# Unicode horizontal whitespace only. Keep the older label grammar separate;
# the v2 numbered/container admissions must not join physical lines.
HORIZONTAL = r'[ \t\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]'
HORIZONTAL_ONLY = re.compile(rf'{HORIZONTAL}*')
VERTICAL = re.compile(r'[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]')
CONTENT = rf'Contenidos?(?:{H}+curricular(?:es)?)?'
LOCAL_CODE = r'[A-Za-z]{1,4}[0-9]{1,4}'
NUMBERED_PDA = rf'(?:{LOCAL_CODE}{HORIZONTAL}+)?PDA{HORIZONTAL}*[0-9]+'
PDA = rf'(?:{NUMBERED_PDA}|PDAs?|Procesos?{H}+de{H}+desarrollo{H}+de{H}+aprendizajes?(?:{H}*\(PDAs?\))?)'
COMBINED = rf'Contenidos?{H}*(?:/|y){H}*PDAs?'
LABEL = re.compile(rf'(?<!\w)(?P<label>{COMBINED}|{CONTENT}|{PDA})(?!\w)(?:{H}*:)?', re.I)
COMBINED_ONLY = re.compile(COMBINED, re.I)
HEADING = re.compile(
    r'^(?:Inicio|Desarrollo|Cierre|Tarea|Actividad(?:\s+\d+)?|'
    r'Campos?(?:\s+formativos?)?|Materiales(?:\s+did[aá]cticos)?|Recursos(?:\s+did[aá]cticos)?|'
    r'Evaluaci[oó]n|Productos?|Evidencias|Observaciones|Proyecto|DATOS GENERALES|'
    r'Tema(?:\s+de\s+la\s+sesi[oó]n)?|Objetivo|Prop[oó]sito|Finalidad|Tiempo|'
    r'Organizaci[oó]n|Fase|Anexos?|Metodolog[ií]a|Escenario|Grado|Temporalidad)\b\s*(?::|$)', re.I)
GENERIC_HEADING = re.compile(r'^[^\W\d_][^:\n]{0,79}:\s*$', re.UNICODE)
SESSION_OR_RESET = re.compile(r'^(?:SESI[OÓ]N\b|DATOS\s+GENERALES\b|(?:Nombre\s+del\s+)?Proyecto\s*:)', re.I)
CONTINUATION = re.compile(r'^Continuaci[oó]n\s+de\s+(?:la\s+)?sesi[oó]n\s+([1-9][0-9]*)\s*:?\s*$', re.I)
NEGATED = re.compile(r'^(?:No\s+(?:se\s+)?(?:trabaj|abord|aplic|inclu|contempl|correspon|selec)|'
                     r'No\s+(?:ser[aá](?:n)?|fue|fueron|es|son|est[aá](?:n)?)\s+'
                     r'(?:trabajad|abordad|aplicad|incluid|contemplad|seleccionad|adoptad|previst|programad)|'
                     r'Sin\s+(?:PDA|contenidos?)\b|Ning[uú]n\s+(?:PDA|contenido)\b)', re.I)
CONDITIONAL = re.compile(r'^(?:Si\s|En\s+caso\s+de\b|De\s+ser\s+posible\b|'
                         r'(?:Puede|Podr[ií]a)\s+(?:trabajarse|abordarse|incluirse)\b)', re.I)
NONAFFIRMATIVE = re.compile(r'^(?:Se\s+(?:sugiere|propone|recomienda)\b|Sugerid[oa]s?\b|'
                          r'Sugerencia\b|Propuest[oa]s?\b|Opcional\b|Tentativ[oa]\b|'
                          r'No\s+(?:definid[oa]|especificad[oa])\b|Se\s+omite\b|'
                          r'Pendiente\b|Por\s+definir\b|Posible\b)', re.I)
UNSPECIFIED = re.compile(r'^(?:N/?A|N\.A\.?|Ningun[oa]?|Ning[uú]n|Sin\s+(?:definir|especificar))[.!]?$', re.I)
SENTENCE_END = re.compile(r'[.!?][»”"\)\]]*$')
DANGLING_END = re.compile(r'(?:\b(?:y|e|o|u|de|del|para|con|en|a)|[,;:–—-])\s*$', re.I)
BULLET = re.compile(r'^(?:[-•*]|[0-9]+[.)])\s*\S')


def snapshot_hash(pages):
    return hashlib.sha256(json.dumps(list(pages), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _ref(pages, source, page, start, end, role):
    return SourceReference(document_sha256=source, page_number=page,
                           excerpt=pages[page - 1][start:end],
                           region={'kind': 'text_offsets', 'start': start, 'end': end}, role=role).to_dict()


def _lines(page):
    return [(m.start(), m.end(), m.group().rstrip('\r\n'))
            for m in re.finditer(r'[^\r\n]*(?:\r\n|\n|\r|$)', page) if m.group()]


def _bare_header(line):
    stripped = line.strip()
    return bool(re.fullmatch(r'Campos?(?:\s+formativos?)?', stripped, re.I)
                or re.fullmatch(rf'(?:{CONTENT}|{PDA})', stripped, re.I))


def _table_lines(lines):
    marked = set()
    for i in range(len(lines) - 2):
        run = [line[2].strip() for line in lines[i:i + 3]]
        if all(_bare_header(line) for line in run) and any(re.match(r'Campos?\b', line, re.I) for line in run):
            marked.update(range(i, i + 3))
    return marked


def _explicit_container_child(line, mentions, quotes):
    """One immediate typed child under a combined heading, not a table row.

    The display container is not a declaration. Child evidence begins at its
    own full typed label; this never splits an unlabeled combined value or
    resolves multiple typed values on one row.
    """
    typed = [mention for mention in mentions if mention.group().endswith(':')]
    if quotes or '|' in line or len(typed) != 2:
        return None
    container, child = typed
    if (not HORIZONTAL_ONLY.fullmatch(line[:container.start()])
            or VERTICAL.search(line[container.start():child.end()])
            or not COMBINED_ONLY.fullmatch(container['label'])
            or not container.group().endswith(':') or not child.group().endswith(':')
            or not HORIZONTAL_ONLY.fullmatch(line[container.end():child.start()])
            or COMBINED_ONLY.fullmatch(child['label'])):
        return None
    return child.start()


def _boundary(line):
    text = line.strip()
    if not text:
        return False
    label = LABEL.match(text)
    standalone_label = label and (text[label.end():].strip() == '' or label.group().endswith(':'))
    return bool(standalone_label or HEADING.match(text) or GENERIC_HEADING.fullmatch(text)
                or SESSION_OR_RESET.match(text) or CONTINUATION.fullmatch(text))


def _unit_data(pages, source):
    units = []
    for segment in scan_session_segments(pages, source):
        a = segment.header_anchor
        units.append({'id': 'session:' + segment.session_id, 'kind': 'session',
                      'anchor': _ref(pages, source, a['page_number'], a['text_start'], a['text_end'], 'unit_anchor'),
                      '_number': segment.session_number})
    for project in project_occurrences(pages, source):
        a = project['anchor']
        # A missing or ambiguous project title does not define a resolved unit.
        if project['title_status'] != 'supported':
            continue
        units.append({'id': f"project:p{a['page_number']}_o{a['occurrence']}", 'kind': 'project',
                      'anchor': _ref(pages, source, a['page_number'], a['text_start'], a['text_end'], 'unit_anchor')})
    barriers = safety_boundary_positions(pages)
    for number, page in enumerate(pages, 1):
        # Any explicit general-data reset cuts this detached conservative scope,
        # without changing the product's separate compound reset grammar.
        barriers[number].extend(m.start() for m in re.finditer(r'(?im)^[ \t]*DATOS\s+GENERALES\b', page))
    return units, barriers


def _scope(pages, source, number, start, units, barriers):
    same_page = [u for u in units if u['anchor']['page_number'] == number and u['anchor']['region']['end'] <= start]
    if same_page:
        current = max(same_page, key=lambda u: u['anchor']['region']['start'])
        if any(current['anchor']['region']['start'] < b <= start for b in barriers[number]):
            return None, None
        return {k: v for k, v in current.items() if not k.startswith('_')}, None
    if number == 1:
        return None, None
    first = next((line for line in _lines(pages[number - 1]) if line[2].strip()), None)
    continuation = CONTINUATION.fullmatch(first[2].strip()) if first else None
    if not continuation or first[1] > start or any(b < start for b in barriers[number]):
        return None, None
    previous = [u for u in units if u['anchor']['page_number'] == number - 1]
    matching = [u for u in previous if u['kind'] == 'session' and u['_number'] == int(continuation[1])]
    if len(matching) != 1:
        return None, None
    current = matching[0]
    if any(u['anchor']['region']['start'] > current['anchor']['region']['start'] for u in previous):
        return None, None
    if any(b > current['anchor']['region']['start'] for b in barriers[number - 1]):
        return None, None
    begin = first[0] + len(first[2]) - len(first[2].lstrip())
    proof = _ref(pages, source, number, begin, first[0] + len(first[2].rstrip()), 'unit_continuation')
    return {k: v for k, v in current.items() if not k.startswith('_')}, proof


def _value_span(page, lines, line_index, label_end):
    end = len(page)
    for begin, _, line in lines[line_index + 1:]:
        if _boundary(line):
            end = begin
            break
    raw = page[label_end:end]
    start = label_end + len(raw) - len(raw.lstrip())
    end = label_end + len(raw.rstrip())
    if start >= end:
        return None, 'empty_value'
    value = page[start:end]
    quotes = []
    _advance_quotes(quotes, value)
    if quotes:
        return None, 'uncertain_boundary'
    nonempty = [line.strip() for line in value.splitlines() if line.strip()]
    for left, right in zip(nonempty, nonempty[1:]):
        if SENTENCE_END.search(left) and not (BULLET.match(left) and BULLET.match(right)):
            return None, 'uncertain_boundary'
    # The supplied window may itself end mid-declaration. Absence of a later
    # supplied page is never proof that a page-final fragment is complete.
    if DANGLING_END.search(value) or end == len(page.rstrip()) and not SENTENCE_END.search(value):
        return None, 'uncertain_boundary'
    if NEGATED.match(value):
        return None, 'negated'
    if CONDITIONAL.match(value):
        return None, 'conditional'
    if NONAFFIRMATIVE.match(value) or UNSPECIFIED.fullmatch(value):
        return None, 'nonaffirmative'
    return (start, end), None


def extract_declarations(pages, *, source_doc_sha256):
    """Return detached proposals; reject malformed/bounded inputs without truncation."""
    if (not isinstance(pages, (list, tuple)) or not pages or any(not isinstance(p, str) for p in pages)
            or not isinstance(source_doc_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', source_doc_sha256)):
        raise ValueError('Invalid source contract')
    pages = tuple(pages)
    if sum(map(len, pages)) > MAX_CHARACTERS:
        raise ValueError('Input exceeds explicit character limit; no silent truncation')
    extraction = snapshot_hash(pages)
    units, barriers = _unit_data(pages, source_doc_sha256)
    records, quotes = [], []
    for number, page in enumerate(pages, 1):
        # An unresolved quotation cannot become a declaration merely because
        # extraction moved to another physical page.
        lines, consumed_until = _lines(page), -1
        tabular = _table_lines(lines)
        for index, (begin, _, line) in enumerate(lines):
            mentions = list(LABEL.finditer(line))
            child_start = _explicit_container_child(line, mentions, quotes)
            row_is_table = ('|' in line or index in tabular or
                            child_start is None and len(mentions) > 1 and (line[:mentions[0].start()].strip() == '' and
                                                  sum(m.group().endswith(':') for m in mentions) > 1
                                                  or re.match(r'^\s*Campos?\b', line, re.I)))
            for mention in mentions:
                if child_start is not None and mention.start() != child_start:
                    continue
                start, end = begin + mention.start(), begin + mention.end()
                if start < consumed_until:
                    continue
                prefix_quotes = list(quotes)
                _advance_quotes(prefix_quotes, line[:mention.start()])
                label = _ref(pages, source_doc_sha256, number, start, end, 'label')
                raw_kind = mention['label']
                kind = 'pda' if re.fullmatch(PDA, raw_kind, re.I) else 'contenido'
                value, reason = None, None
                if prefix_quotes:
                    reason = 'quoted'
                elif COMBINED_ONLY.fullmatch(raw_kind):
                    kind, reason = None, 'combined_label'
                elif row_is_table:
                    reason = 'table_ambiguous'
                elif (re.fullmatch(NUMBERED_PDA, raw_kind, re.I)
                      and (VERTICAL.search(mention.group())
                           or child_start is None and not HORIZONTAL_ONLY.fullmatch(line[:mention.start()]))):
                    reason = 'label_mention'
                elif line[:mention.start()].strip() and mention.start() != child_start:
                    reason = 'label_mention'
                elif not mention.group().endswith(':') and line[mention.end():].strip():
                    reason = 'nonaffirmative' if NONAFFIRMATIVE.match(line[mention.end():].strip(' :')) else 'label_mention'
                else:
                    value, reason = _value_span(page, lines, index, end)
                unit, continuation = _scope(pages, source_doc_sha256, number, start, units, barriers)
                evidence = [label]
                if value:
                    evidence.append(_ref(pages, source_doc_sha256, number, *value, 'value'))
                    consumed_until = value[1]
                    reason = 'unresolved_scope' if unit is None else 'project_scope' if unit['kind'] == 'project' else 'explicit_session'
                if continuation:
                    evidence.append(continuation)
                decision = 'candidate' if reason == 'explicit_session' else 'abstained'
                identity = [VERSION, source_doc_sha256, extraction, number, start, end, kind]
                record_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:16]
                claim = None
                if decision == 'candidate':
                    refs = [SourceReference.from_dict(ev) for ev in evidence + [unit['anchor']]]
                    value_ref = next(ev for ev in evidence if ev['role'] == 'value')
                    claim = AtomicClaim(
                        claim_id=record_id, claim_type='field', subject=unit['id'],
                        predicate=PREDICATES[kind], object_value=page[value[0]:value[1]],
                        source_doc_sha256=source_doc_sha256, page_number=number,
                        region=dict(value_ref['region']), excerpt=value_ref['excerpt'],
                        extraction_method='detached_literal_declarations', extraction_version=MATCHER_VERSION,
                        state='needs_human_review', confidence=None, evidence=refs,
                        metadata={'basis': 'explicit', 'contract_version': VERSION, 'matcher_version': MATCHER_VERSION,
                                  'extraction_sha256': extraction,
                                  'validation': 'literal_declaration_not_SEP_alignment'},
                    ).to_dict()
                records.append({'id': record_id, 'kind': kind, 'decision': decision, 'reason': reason,
                                'unit': unit, 'evidence': evidence, 'claim': claim})
                if len(records) > MAX_RECORDS:
                    raise ValueError('Output exceeds explicit record limit; no silent truncation')
            _advance_quotes(quotes, line)
    return {'version': VERSION, 'source_doc_sha256': source_doc_sha256, 'extraction_sha256': extraction,
            'records': records,
            'limits': ['Matcher implementation: ' + MATCHER_VERSION,
                       'Extracted text only; no PDF/OCR or table reconstruction.',
                       'Page-local values; cross-page scope only with explicit immediate continuation.',
                       'Candidates pending human review; no SEP alignment or pedagogical approval.',
                       'Bounded textual grammar; ambiguous or unrecognized discourse may be omitted or abstained.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='JSON with pages and source_doc_sha256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_bytes())
    result = extract_declarations(data['pages'], source_doc_sha256=data['source_doc_sha256'])
    # Detached output only, and no accidental replacement of a previous run.
    with args.output.open('x', encoding='utf-8', newline='') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
