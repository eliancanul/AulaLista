"""Conservative, source-linked proposals; never pedagogical validation/approval.

The model identifies candidate relationships in an existing review call. This
module checks explicit, inspectable conditions. It is not a probability model
and a passing check does not establish semantic entailment.
"""
from __future__ import annotations

import re

from curriculum.verification import normalize_text_for_evidence_check as normalize

RULE = 'A & C & (P | E) & I & S & !X'
MAX_EVIDENCE = 8
MAX_QUOTE = 800
ROLES = frozenset({'action', 'content', 'product', 'assessment'})


def purpose_proposal_has_valid_shape(candidate):
    if not isinstance(candidate, dict) or set(candidate) != {'action', 'content', 'scope_id', 'evidence', 'counterevidence'}:
        return False
    if any(not isinstance(candidate[key], str) or not candidate[key].strip() or len(candidate[key]) > maximum
           for key, maximum in (('action', 40), ('content', 240), ('scope_id', 40))):
        return False
    for key in ('evidence', 'counterevidence'):
        items = candidate[key]
        if not isinstance(items, list) or len(items) > MAX_EVIDENCE:
            return False
        for item in items:
            if (not isinstance(item, dict) or set(item) != {'role', 'page', 'quote'}
                    or not isinstance(item['role'], str) or item['role'] not in ROLES or type(item['page']) is not int or item['page'] < 1
                    or not isinstance(item['quote'], str) or not item['quote'].strip() or len(item['quote']) > MAX_QUOTE):
                return False
    return bool(candidate['evidence'])


def _abstain(issue, *, checks=None):
    return {'decision': 'abstained', 'value': None, 'origin': 'proposed', 'status': 'missing',
            'review': 'pending', 'rule': RULE, 'scope_id': None, 'evidence': [],
            'reason': 'No se propone un propósito con estas evidencias; requiere revisión docente. '
                      'Esto no demuestra que el propósito falte en la fuente.',
            'checks': checks or {}, 'issues': [issue]}


_LEARNER = re.compile(r"\b(?:alumnado|alumn[oa]s?|estudiantes?|nin[oa]s?|participantes?|aprendices)\b")
_TEACHER = re.compile(r"\b(?:docentes?|maestr[oa]s?|profesor(?:a|es|as)?)\b")
_NEGATIVE = re.compile(r"\b(?:no|nunca|sin|quiza|quizas|tal vez|posiblemente|probablemente|podria|podrian|supuesto|hipotetico|excluid\w*|descartad\w*)\b")
_PRODUCTION = {'elaborar', 'realizar', 'hacer', 'crear', 'construir', 'preparar', 'completar', 'presentar'}


def _action_pattern(action):
    # A deliberately conservative Spanish inflection check, not a semantic
    # classifier. Unsupported/irregular formulations abstain for human review.
    if not re.fullmatch(r'[a-z]{3,}(?:ar|er|ir)', action):
        return None
    endings = ('ar|o|a|as|an|amos|ais|e|es|en|emos|eis|aba|aban|aron|ara|aran'
               if action.endswith('ar') else
               'er|ir|o|e|es|en|emos|imos|eis|is|a|as|an|amos|ais|ia|ian|ieron|era|eran|ira|iran')
    return re.compile(r'\b' + re.escape(action[:-2]) + r'(?:' + endings + r')\b')


def _statement(page, quote):
    # Canonical SOURCE assertion, independent of the model's crop/punctuation.
    # A physical wrapped line is not a second assertion. Structural labels,
    # paragraphs, and sentence punctuation cut units; one quote cannot span two.
    start = page.find(quote)
    if start < 0 or page.find(quote, start + 1) >= 0:
        return None
    stop = start + len(quote.rstrip())
    start += len(quote) - len(quote.lstrip())
    boundaries = {0, len(page)}
    boundaries.update(match.end() for match in re.finditer(r'[.!?](?=\s|$)', page))
    boundaries.update(match.end() for match in re.finditer(r'\n[ \t]*\n', page))
    labels = re.compile(r'(?im)^[ \t]*(?:(?:nombre del )?proyecto\b|sesion\b|sesión\b|fase\b|momento\b|'
                        r'(?:actividad|pda|contenidos?|producto|evaluaci[oó]n|criterio|inicio|desarrollo|cierre|'
                        r'materiales|recursos|escenario|grado|campos? formativos?)\s*:)')
    for match in labels.finditer(page):
        boundaries.add(match.start())
        if re.match(r'(?i)(?:nombre del )?proyecto\b|sesion\b|sesión\b|fase\b|momento\b', match.group().strip()):
            end = page.find('\n', match.start())
            boundaries.add(len(page) if end < 0 else end + 1)
    if any(start < boundary < stop and page[start:boundary].strip() and page[boundary:stop].strip()
           for boundary in boundaries):
        return None
    begin = max(boundary for boundary in boundaries if boundary <= start)
    end = min(boundary for boundary in boundaries if boundary >= stop)
    return begin, end, page[begin:end].strip()


def _teacher_only(statement):
    text = normalize(statement)
    return bool(_TEACHER.search(text) and not _LEARNER.search(text))


def _student_action(statement, pattern):
    text = normalize(statement)
    if _teacher_only(statement) or re.match(r'(?:nombre del )?proyecto\s*:', text):
        return False
    for action in pattern.finditer(text):
        before = text[:action.start()]
        learners, teachers = list(_LEARNER.finditer(before)), list(_TEACHER.finditer(before))
        if teachers and (not learners or teachers[-1].start() > learners[-1].start()):
            continue
        if learners or re.match(pattern, text) or re.search(r'\bpara\s*$', before) or re.match(r'(?:actividad|pda|desarrollo|inicio|cierre)\s*:', text):
            return True
    return False


_UNIT_RE = re.compile(r'(?im)^[ \t]*(?:sesion|sesión|fase|momento)[ \t]*(?:#[ \t]*)?(?:[0-9]+|[ivx]+)\b[^\n]*')


def learning_purpose_scope(source_document):
    """First anchored project only; proximity is still a reviewable scope hint."""
    from curriculum.source_segments import project_occurrences, planning_boundary_positions
    pages = [page.get('text') or '' for page in source_document.get('pages', [])]
    projects = project_occurrences(pages, source_document.get('source_sha256', ''))
    if not projects:
        return None
    anchor = projects[0]['anchor']
    project_page = pages[anchor['page_number'] - 1]
    header_end = project_page.find('\n', anchor['text_start'])
    if header_end < 0:
        return None
    heading = project_page[anchor['text_start']:header_end].strip()
    if not (re.match(r'(?:Nombre\s+del\s+)?Proyecto\s*:\s*\S', heading, re.I)
            or re.match(r'(?:Nombre\s+del\s+)?Proyecto\b.+\bEscenario\b', heading, re.I)):
        return None
    start = (anchor['page_number'], header_end + 1)
    stops = [(p['anchor']['page_number'], p['anchor']['text_start']) for p in projects[1:]]
    stops += [(number, offset) for number, offsets in planning_boundary_positions(pages).items()
              for offset in offsets if (number, offset) > start]
    end = min(stops, default=(len(pages) + 1, 0))
    boundaries = [(number, match.start()) for number, text in enumerate(pages, 1)
                  for match in _UNIT_RE.finditer(text) if start <= (number, match.start()) < end]
    return {'scope_id': 'project-1', 'project_heading': heading,
            'project_page': anchor['page_number'], 'start': list(start), 'end': list(end),
            'unit_boundaries': [list(boundary) for boundary in boundaries],
            'membership': 'source_proximity_requires_human_review'}


def _scope_compatible(candidate, source_document, statements):
    scope = learning_purpose_scope(source_document)
    if not scope or candidate['scope_id'] != scope['scope_id']:
        return False
    start, end = tuple(scope['start']), tuple(scope['end'])
    boundaries = [tuple(boundary) for boundary in scope['unit_boundaries']]
    units, has_overview_intention = set(), False
    for item, (begin, stop, _) in statements:
        position, last = (item['page'], begin), (item['page'], stop)
        if position < start or last > end or any(position <= boundary < last for boundary in boundaries):
            return False
        preceding = [boundary for boundary in boundaries if boundary < position]
        if preceding:
            units.add(max(preceding))
        elif item['role'] == 'action':
            has_overview_intention = True
    # A phase-specific objective is not silently promoted to a project purpose.
    return len(units) <= 1 and has_overview_intention


def _source_contradicts(candidate, source_document, pattern):
    scope = learning_purpose_scope(source_document)
    if not scope:
        return True
    content_words = {word for word in normalize(candidate['content']).split() if len(word) > 3}
    # Nominalizations can carry contrary evidence too (comparar/comparación).
    # A prefix match is only a conservative review flag, never entailment.
    concept = re.compile(r'\b' + re.escape(normalize(candidate['action'])[:5]) + r'\w*\b')
    for page in source_document['pages']:
        number = page['page_number']
        if not scope['start'][0] <= number <= scope['end'][0]:
            continue
        text = page.get('text') or ''
        begin = scope['start'][1] if number == scope['start'][0] else 0
        end = scope['end'][1] if number == scope['end'][0] else len(text)
        for statement in re.split(r'[.?!\n]', text[begin:end]):
            normalized = normalize(statement)
            if ((pattern.search(normalized) or concept.search(normalized)) and _NEGATIVE.search(normalized)
                    and content_words.intersection(normalized.split())):
                return True
    return False


def assess_learning_purpose(candidate, source_document):
    """Assess one untrusted candidate against the current literal source."""
    if not purpose_proposal_has_valid_shape(candidate):
        return _abstain('invalid_candidate')
    pages = source_document.get('pages', []) if isinstance(source_document, dict) else []
    if not pages or not isinstance(source_document.get('source_sha256'), str):
        return _abstain('source_unavailable')
    for item in candidate['evidence'] + candidate['counterevidence']:
        number = item['page']
        if (number > len(pages) or pages[number - 1].get('page_number') != number
                or pages[number - 1].get('status') != 'text'
                or not isinstance(pages[number - 1].get('text'), str)
                or item['quote'] not in pages[number - 1]['text']):
            return _abstain('citation_not_verified')
    action = normalize(candidate['action'])
    content = candidate['content'].strip().rstrip('.')
    pattern = _action_pattern(action)
    statements = []
    for item in candidate['evidence']:
        found = _statement(pages[item['page'] - 1]['text'], item['quote'])
        if found is None:
            return _abstain('ambiguous_citation')
        statements.append((item, found))
    ranges = sorted({(item['page'], begin, end) for item, (begin, end, _) in statements})
    if any(page == next_page and next_begin < end
           for (page, _, end), (next_page, next_begin, _) in zip(ranges, ranges[1:])):
        return _abstain('overlapping_assertions')
    if not _scope_compatible(candidate, source_document, statements):
        return _abstain('scope_mismatch', checks={'S': False})
    checks = {
        'A': bool(pattern and any(item['role'] == 'action' and _student_action(statement, pattern)
                                for item, (_, _, statement) in statements)),
        'C': bool(content and any(item['role'] == 'content' and content in item['quote'] for item, _ in statements)
                  and pattern and any(item['role'] == 'action' and content in statement and _student_action(statement, pattern)
                                      for item, (_, _, statement) in statements)),
        'P': any(item['role'] == 'product' and not _teacher_only(statement)
                 and pattern and (pattern.search(normalize(statement)) or content in statement) and re.search(r'\b(?:producto|elabor\w*|constru\w*|realiz\w*|crea\w*)\b', normalize(statement))
                 for item, (_, _, statement) in statements),
        'E': any(item['role'] == 'assessment' and not _teacher_only(statement)
                 and pattern and (pattern.search(normalize(statement)) or content in statement) and re.search(r'\b(?:evalu\w*|criterio\w*|rubrica|lista de cotejo|se observara)\b', normalize(statement))
                 for item, (_, _, statement) in statements),
        'I': len({' '.join(re.findall(r'\w+', normalize(statement))) for item, (_, _, statement) in statements
                  if not _teacher_only(statement) and pattern
                  and (pattern.search(normalize(statement)) or normalize(content) in normalize(statement))}) >= 2,
        'S': True,
        'X': bool(candidate['counterevidence']) or any(_NEGATIVE.search(normalize(statement)) for _, (_, _, statement) in statements)
             or bool(pattern and _source_contradicts(candidate, source_document, pattern)),
    }
    if action in _PRODUCTION and not checks['E']:
        return _abstain('production_without_learning_assessment', checks=checks)
    if not (checks['A'] and checks['C'] and (checks['P'] or checks['E']) and checks['I'] and not checks['X']):
        return _abstain('insufficient_or_conflicting_support', checks=checks)
    labels = {'action': 'Acción del alumnado', 'content': 'Contenido',
              'product': 'Producto', 'assessment': 'Evaluación'}
    supports = {}
    for item, (begin, end, statement) in statements:
        support = supports.setdefault((item['page'], begin, end), {'statement': statement, 'roles': []})
        if item['role'] not in support['roles']:
            support['roles'].append(item['role'])
    citations = [{'document_sha256': source_document['source_sha256'],
                  'page_number': page, 'printed_label': '', 'excerpt': support['statement'],
                  'region': None, 'role': ' · '.join(labels[role] for role in support['roles'])}
                 for (page, _, _), support in supports.items()]
    role_pages = {role: sorted({item['page'] for item, _ in statements if item['role'] == role}) for role in ROLES}
    reason = (f"Propuesta de aprendizaje: acción «{action}» (páginas {role_pages['action']}) y contenido «{content}» "
              f"(páginas {role_pages['content']}) vinculados con "
              f"{'evaluación' if checks['E'] else 'producto'} (páginas {role_pages['assessment' if checks['E'] else 'product']}). "
              "Se aplica A & C & (P | E) & I & S & !X: acción, contenido, demostración, apoyos independientes y ámbito compatible. "
              "Los filtros del prototipo no detectaron contraevidencia. "
              "La relación es una inferencia, no una cita literal del propósito ni validación pedagógica; requiere revisión docente.")
    return {'decision': 'proposed', 'value': action.capitalize() + ' ' + content + '.',
            'origin': 'proposed', 'status': 'ambiguous', 'review': 'pending',
            'rule': RULE, 'scope_id': candidate['scope_id'], 'evidence': citations,
            'reason': reason,
            'checks': checks, 'issues': []}


PURPOSE_INSTRUCTIONS = """
purpose_proposal=null unless purpose_policy.eligible. In this SAME response, infer
only a pending learner purpose satisfying A & C & (P | E) & I & S & !X:
A=student action, C=linked content, P/E=linked product/assessment, I=two independent
assertions, S=first-project intention plus at most one phase/moment/session,
X=contradiction/uncertainty. This heuristic is not probability or pedagogical proof.
Use purpose_policy.source_scope.scope_id; action=Spanish infinitive, content=literal source
phrase. Quotes must be EXACT complete source assertions including subject/negation;
include counterevidence, or []. Crops/repetitions, decorative titles, teacher-only
intentions and unrelated products do not support learning. Never replace existing
or human-corrected purpose. The server composes action+content as PROPOSED, requiring
human review. Subtract its target from questions only when the rule passes;
otherwise return null and ask a focused remaining gap within the existing budget.
"""


def purpose_proposal_schema():
    """Small additive output contract; no repeated source or generated essay."""
    citation = {'type': 'object', 'properties': {
        'role': {'type': 'string', 'enum': sorted(ROLES)},
        'page': {'type': 'integer', 'minimum': 1},
        'quote': {'type': 'string', 'minLength': 1, 'maxLength': MAX_QUOTE}},
        'required': ['role', 'page', 'quote'], 'additionalProperties': False}
    return {'anyOf': [{'type': 'null'}, {'type': 'object', 'properties': {
        'action': {'type': 'string', 'minLength': 1, 'maxLength': 40},
        'content': {'type': 'string', 'minLength': 1, 'maxLength': 240},
        'scope_id': {'type': 'string', 'minLength': 1, 'maxLength': 40},
        'evidence': {'type': 'array', 'items': citation, 'minItems': 1, 'maxItems': MAX_EVIDENCE},
        'counterevidence': {'type': 'array', 'items': citation, 'maxItems': MAX_EVIDENCE}},
        'required': ['action', 'content', 'scope_id', 'evidence', 'counterevidence'],
        'additionalProperties': False}]}
