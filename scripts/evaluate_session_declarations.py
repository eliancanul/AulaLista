#!/usr/bin/env python3
"""Independent, offline literal-declaration evaluation on authored page spans.

The scorer and reference validator use only the standard library. Only the
explicit ``predict`` adapter imports the experimental matcher. These scores
measure a synthetic text snapshot, never PDF bytes or curricular accuracy.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
KINDS = ('contenido', 'pda')
DECISIONS = ('candidate', 'abstained')
SCOPE_PROOF_ROLES = ('unit_continuation', 'unit_scaffold_tail', 'unit_scaffold_prefix')
ROLES = ('label', 'value', 'unit_anchor', *SCOPE_PROOF_ROLES)
SCOPE_BASES = ('same_page_explicit', 'explicit_continuation', 'structural_scaffold_proposal')
SCAFFOLD_REFERENCE_SHA256 = '3b83730070b9e04859a39af78065dbf70399bdfb3a6d5edbbc3a8941d71f3b09'
PREDICATES = {'contenido': 'contenido_declarado', 'pda': 'pda_declarado'}
CHALLENGE_REASONS = ('combined_label', 'table_ambiguous', 'negated', 'label_mention', 'quoted',
                     'conditional', 'nonaffirmative', 'empty_value', 'uncertain_boundary')


def hash_canonical_pages(pages):
    """SHA256 of exact Unicode page strings, not an original PDF-byte hash."""
    return hashlib.sha256(json.dumps(pages, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _required(value, fields, description):
    if not isinstance(value, dict) or not set(fields) <= value.keys():
        raise ValueError(f'{description}: missing required keys')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _scope_valid(value):
    """A scope is opaque provenance: preserve its JSON structure, never flatten it."""
    if isinstance(value, str):
        return _text(value)
    if not isinstance(value, dict):
        return False
    try:
        # Reject non-JSON values, non-string object keys, cycles and NaN/Infinity.
        # Equality also rejects tuples or integer keys that JSON would coerce.
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False)) == value
    except (TypeError, ValueError, RecursionError):
        return False


def _span_valid(pages, span):
    if not isinstance(span, dict):
        return False
    page, start, end = (span.get(k) for k in ('page', 'start', 'end'))
    return (type(page) is int and 1 <= page <= len(pages)
            and type(start) is int and type(end) is int
            and 0 <= start < end <= len(pages[page - 1])
            and isinstance(span.get('quote'), str)
            and pages[page - 1][start:end] == span['quote'])


def _key(span):
    return tuple(span.get(k) for k in ('page', 'start', 'end', 'quote'))


def _validate_document(document):
    _required(document, ('id', 'pages', 'units', 'declarations', 'challenges', 'absence_expected'), 'Document')
    pages = document['pages']
    if not _text(document['id']) or not isinstance(pages, list) or not pages or any(not isinstance(p, str) for p in pages):
        raise ValueError('Reference requires an ID and original page strings')
    if any(not isinstance(document[k], list) for k in ('units', 'declarations', 'challenges')):
        raise ValueError('Reference collections must be lists')
    seen_ids, seen_anchors = set(), set()

    def identity(item, fields, description):
        _required(item, fields, description)
        if not _text(item['id']) or item['id'] in seen_ids:
            raise ValueError('Duplicate or empty reference ID')
        seen_ids.add(item['id'])

    def span(item):
        if not _span_valid(pages, item):
            raise ValueError('Reference span must reproduce the exact original slice')

    units = {}
    for unit in document['units']:
        identity(unit, ('id', 'kind', 'anchor'), 'Unit')
        span(unit['anchor'])
        if unit['kind'] not in ('session', 'project') or _key(unit['anchor']) in seen_anchors:
            raise ValueError('Invalid or duplicate physical reference unit')
        seen_anchors.add(_key(unit['anchor']))
        units[unit['id']] = unit
    labels = set()
    for declaration in document['declarations']:
        identity(declaration, ('id', 'kind', 'label', 'value', 'unit_id', 'expected_decision', 'reason'), 'Declaration')
        label, value = declaration['label'], declaration['value']
        span(label)
        span(value)
        if declaration['kind'] not in KINDS or declaration['expected_decision'] not in DECISIONS or not _text(declaration['reason']):
            raise ValueError('Invalid declaration type, decision or reason')
        if label['page'] != value['page'] or label['end'] > value['start']:
            raise ValueError('Declaration must have ordered page-local label/value spans')
        if label['quote'] != label['quote'].strip() or value['quote'] != value['quote'].strip():
            raise ValueError('Label/value spans must exclude external whitespace')
        uid = declaration['unit_id']
        if uid is not None and (not isinstance(uid, str) or uid not in units):
            raise ValueError('Unknown reference unit')
        if declaration['expected_decision'] == 'candidate' and (uid is None or units[uid]['kind'] != 'session'):
            raise ValueError('A reference candidate must have a physical session')
        if _key(label) in labels:
            raise ValueError('Duplicate reference opportunity')
        labels.add(_key(label))
    for challenge in document['challenges']:
        identity(challenge, ('id', 'anchor', 'reason'), 'Challenge')
        span(challenge['anchor'])
        if not _text(challenge['reason']) or _key(challenge['anchor']) in labels:
            raise ValueError('Invalid or duplicate challenge')
        labels.add(_key(challenge['anchor']))
    if type(document['absence_expected']) is not bool or document['absence_expected'] != (not document['declarations']):
        raise ValueError('absence_expected must mean no authored declarations')


def validate_reference(reference):
    """Validate a complete reference or one document, without running a parser.

    Denominators are authored opportunities, never inferred from predictions.
    Small independent references are accepted; a missing denominator is N/A.
    """
    if isinstance(reference, dict) and 'documents' not in reference:
        _validate_document(reference)
        return
    _required(reference, ('version', 'reference_kind', 'scope', 'documents'), 'Reference')
    if (reference['version'] != 'session-declarations-reference.v1'
            or not _text(reference['reference_kind']) or not _scope_valid(reference['scope'])
            or not isinstance(reference['documents'], list)):
        raise ValueError('Invalid reference envelope')
    ids = set()
    for document in reference['documents']:
        _validate_document(document)
        if document['id'] in ids:
            raise ValueError('Duplicate document ID')
        ids.add(document['id'])


def _source_span(reference):
    """Read raw coordinates for alignment; validity is checked separately."""
    if not isinstance(reference, dict) or not isinstance(reference.get('region'), dict):
        return {}
    region = reference['region']
    return dict(page=reference.get('page_number'), start=region.get('start'), end=region.get('end'), quote=reference.get('excerpt'))


def _reference_errors(reference, pages, sha, role=None):
    if not isinstance(reference, dict):
        return ['SourceReference must be a dictionary']
    errors = []
    if reference.get('document_sha256') != sha:
        errors.append('SourceReference document hash mismatch')
    if reference.get('role') not in ROLES or (role is not None and reference.get('role') != role):
        errors.append('SourceReference role mismatch')
    if not isinstance(reference.get('region'), dict) or reference['region'].get('kind') != 'text_offsets':
        errors.append('SourceReference requires text_offsets region')
    if not _span_valid(pages, _source_span(reference)):
        errors.append('SourceReference does not reproduce original text')
    return errors


def _evidence_by_role(evidence):
    result = defaultdict(list)
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, dict) and isinstance(item.get('role'), str):
                result[item['role']].append(item)
    return result


def _ref_key(reference):
    return (reference.get('role'), reference.get('document_sha256'), *_key(_source_span(reference)))


def _auxiliary_scope_reference(reference):
    # An altered/unknown proof role must not poison independently exact literal
    # labels and values in the new contract. Legacy record validation is intact.
    return not isinstance(reference, dict) or reference.get('role') not in ('label', 'value', 'unit_anchor')


def _record_errors(record, pages, sha, *, separate_scope=False):
    if not isinstance(record, dict):
        return ['Record must be a dictionary']
    errors = []
    fields = ('id', 'kind', 'decision', 'reason', 'unit', 'evidence', 'claim')
    if not set(fields) <= record.keys():
        errors.append('Missing required record keys')
    if not _text(record.get('id')):
        errors.append('Record ID must be nonempty')
    if record.get('kind') not in (*KINDS, None) or record.get('decision') not in DECISIONS or not _text(record.get('reason')):
        errors.append('Invalid record type, decision or reason')
    evidence = record.get('evidence')
    if not isinstance(evidence, list):
        errors.append('Record evidence must be a list')
        evidence = []
    for ref in evidence:
        if not (separate_scope and _auxiliary_scope_reference(ref)):
            errors.extend(_reference_errors(ref, pages, sha))
    roles = _evidence_by_role(evidence)
    if len(roles['label']) != 1 or len(roles['value']) > 1 or len(roles['unit_anchor']) > 1:
        errors.append('Evidence must have one label and at most one value and unit anchor')
    if roles['label'] and roles['value']:
        label, value = map(_source_span, (roles['label'][0], roles['value'][0]))
        if (_span_valid(pages, label) and _span_valid(pages, value)
                and (label['page'] != value['page'] or label['end'] > value['start'])):
            errors.append('Label/value must be ordered and page-local')
    unit = record.get('unit')
    if unit is not None:
        if not isinstance(unit, dict) or not _text(unit.get('id')) or unit.get('kind') not in ('session', 'project'):
            errors.append('Invalid physical unit')
        else:
            errors.extend(_reference_errors(unit.get('anchor'), pages, sha, 'unit_anchor'))
            if roles['unit_anchor'] and roles['unit_anchor'][0] != unit.get('anchor'):
                errors.append('Record unit anchor contradicts unit')
    elif roles['unit_anchor']:
        errors.append('Null unit contradicts unit-anchor evidence')
    reason, decision = record.get('reason'), record.get('decision')
    if decision == 'candidate' and reason != 'explicit_session':
        errors.append('Candidate requires explicit_session reason')
    if reason == 'explicit_session' and decision != 'candidate':
        errors.append('explicit_session reason requires candidate decision')
    elif reason == 'project_scope' and (decision != 'abstained' or not isinstance(unit, dict) or unit.get('kind') != 'project'):
        errors.append('project_scope requires an abstained project unit')
    elif reason == 'unresolved_scope' and (decision != 'abstained' or unit is not None):
        errors.append('unresolved_scope requires an abstained null unit')
    elif reason in CHALLENGE_REASONS and decision != 'abstained':
        errors.append('Nonaffirmative challenge reason requires abstention')
    elif reason not in ('explicit_session', 'project_scope', 'unresolved_scope', *CHALLENGE_REASONS):
        errors.append('Unknown decision reason')
    claim = record.get('claim')
    if record.get('decision') == 'abstained':
        if claim is not None:
            errors.append('Abstained record must have null claim')
        return errors
    if record.get('decision') != 'candidate':
        return errors
    if record.get('kind') not in KINDS or len(roles['value']) != 1 or not isinstance(unit, dict) or unit.get('kind') != 'session':
        errors.append('Candidate requires a typed literal value and session')
    if not isinstance(claim, dict):
        return errors + ['Candidate requires an AtomicClaim dictionary']
    required = ('claim_id', 'claim_type', 'subject', 'predicate', 'object_value', 'source_doc_sha256', 'state', 'confidence', 'evidence')
    if not set(required) <= claim.keys():
        errors.append('Missing AtomicClaim fields')
    if not _text(claim.get('claim_id')) or claim.get('claim_type') != 'field':
        errors.append('Invalid AtomicClaim identity or type')
    if claim.get('state') != 'needs_human_review' or claim.get('confidence') is not None:
        errors.append('Candidate state must be needs_human_review with null confidence')
    if claim.get('source_doc_sha256') != sha:
        errors.append('AtomicClaim document hash mismatch')
    if isinstance(unit, dict) and claim.get('subject') != unit.get('id'):
        errors.append('AtomicClaim subject contradicts physical unit')
    if claim.get('predicate') != (PREDICATES.get(record.get('kind')) if isinstance(record.get('kind'), str) else None):
        errors.append('AtomicClaim predicate contradicts declaration type')
    value = roles['value'][0] if roles['value'] else None
    if value and claim.get('object_value') != value.get('excerpt'):
        errors.append('AtomicClaim object contradicts literal value')
    claim_evidence = claim.get('evidence')
    if not isinstance(claim_evidence, list):
        errors.append('AtomicClaim evidence must be a list')
        claim_evidence = []
    for ref in claim_evidence:
        if not (separate_scope and _auxiliary_scope_reference(ref)):
            errors.extend(_reference_errors(ref, pages, sha))
    claim_roles = _evidence_by_role(claim_evidence)
    for role in ('label', 'value', 'unit_continuation'):
        if separate_scope and role == 'unit_continuation':
            continue
        if claim_roles[role] != roles[role]:
            errors.append(f'AtomicClaim {role} evidence contradicts record')
    if isinstance(unit, dict) and claim_roles['unit_anchor'] != [unit.get('anchor')]:
        errors.append('AtomicClaim must retain exact physical unit anchor')
    if value:
        for field, expected in (('page_number', value.get('page_number')), ('region', value.get('region')), ('excerpt', value.get('excerpt'))):
            if field in claim and claim[field] != expected:
                errors.append(f'AtomicClaim primary {field} contradicts value evidence')
    return errors


def _asserts_claim(record):
    """Count every raw candidate or non-null claim, even when it is malformed."""
    return isinstance(record, dict) and (record.get('decision') == 'candidate' or record.get('claim') is not None)


def _provenance_invalid(record, pages, sha):
    """Invalid source binding/coordinates, independent of gold span equality.

    Missing/malformed containers remain record-contract errors. This diagnostic
    identifies supplied references that cannot establish literal provenance.
    """
    if not isinstance(record, dict):
        return False
    references = list(record['evidence']) if isinstance(record.get('evidence'), list) else []
    unit, claim = record.get('unit'), record.get('claim')
    if isinstance(unit, dict):
        references.append(unit.get('anchor'))
    if isinstance(claim, dict):
        if claim.get('source_doc_sha256') != sha:
            return True
        if isinstance(claim.get('evidence'), list):
            references.extend(claim['evidence'])
    return any(not isinstance(ref, dict) or ref.get('document_sha256') != sha
               or not isinstance(ref.get('region'), dict) or ref['region'].get('kind') != 'text_offsets'
               or not _span_valid(pages, _source_span(ref)) for ref in references)


def _overlaps(left, right):
    coordinates = [left.get(k) for k in ('page', 'start', 'end')]
    return (all(type(v) is int for v in coordinates)
            and left['page'] == right['page']
            and left['start'] < left['end']
            and left['start'] < right['end'] and right['start'] < left['end'])


def _anchor_identity(document, expected, predicted):
    """Physical identity under the pre-output v1.1 anchor amendment.

    Exact kind/page/start/end/quote equality always suffices. Different ends
    require literal prefixes at the same physical start, both covering the
    COMPLETE identifier read independently from the original source: Spanish
    Sesión/Sesion followed by one integer token, or Proyecto through its colon.
    The longer span must stay before CR/LF in that header line and must not
    cover another annotated unit, declaration label, or challenge. Unsupported
    label forms fall back to exact equality. The checking grammar intentionally
    does not import the matcher, normalize text, or identify new units.
    """
    if not isinstance(predicted, dict) or predicted.get('kind') != expected['kind']:
        return False
    gold, guessed = expected['anchor'], _source_span(predicted.get('anchor'))
    if _key(gold) == _key(guessed):
        return True
    if guessed.get('page') != gold['page'] or guessed.get('start') != gold['start']:
        return False
    page, start = document['pages'][gold['page'] - 1], gold['start']
    if not _span_valid(document['pages'], guessed):
        return False
    longer, shorter = max(gold['end'], guessed['end']), min(gold['end'], guessed['end'])
    line_end = min([p for c in ('\r', '\n') if (p := page.find(c, start)) >= 0] or [len(page)])
    if longer > line_end or (start == 0 and longer == len(page)):
        return False
    grammar = (r'sesi[oó]n[ \t]+[0-9]+(?=$|[ \t:.\-–—])' if expected['kind'] == 'session'
               else r'proyecto[ \t]*:')
    identifier = re.match(grammar, page[start:line_end], re.IGNORECASE)
    if identifier is None or shorter < start + identifier.end():
        return False
    protected = [u['anchor'] for u in document['units'] if u['id'] != expected['id']]
    protected += [d['label'] for d in document['declarations']]
    protected += [c['anchor'] for c in document['challenges']]
    whole = dict(page=gold['page'], start=start, end=longer)
    return not any(_overlaps(whole, span) for span in protected)


def _continuation_errors(document, record):
    """Require explicit named, standalone continuation for cross-page claims.

    This checks a deliberately small independent Spanish grammar and the
    authored/source physical boundaries, not product scanner output. Missing or
    unsupported continuation invalidates scope/candidate credit, not an otherwise
    exact literal declaration. Recognized source resets are deliberately bounded.
    """
    if not isinstance(record, dict) or record.get('decision') != 'candidate':
        return []
    unit = record.get('unit')
    roles = _evidence_by_role(record.get('evidence'))
    if not isinstance(unit, dict) or len(roles['label']) != 1:
        return []  # General record validation already rejects malformed shapes.
    anchor, label = _source_span(unit.get('anchor')), _source_span(roles['label'][0])
    pages = document['pages']
    if not _span_valid(pages, anchor) or not _span_valid(pages, label) or anchor['page'] == label['page']:
        return []
    if anchor['page'] > label['page']:
        return ['Cross-page unit anchor cannot follow the declaration']
    identifier = re.match(r'sesi[oó]n[ \t]+([0-9]+)(?=$|[ \t:.\-–—])', pages[anchor['page'] - 1][anchor['start']:], re.IGNORECASE)
    if identifier is None:
        return ['Unsupported cross-page session identifier']
    number = identifier.group(1)
    evidence = roles['unit_continuation']
    if not evidence:
        return ['Cross-page candidate requires literal unit_continuation evidence']
    named = False
    for reference in evidence:
        span = _source_span(reference)
        if not _span_valid(pages, span) or span['page'] != label['page'] or span['end'] > label['start']:
            continue
        text = pages[span['page'] - 1]
        line_start = max(text.rfind('\n', 0, span['start']), text.rfind('\r', 0, span['start'])) + 1
        line_end = min([i for c in ('\r', '\n') if (i := text.find(c, span['end'])) >= 0] or [len(text)])
        if text[line_start:span['start']].strip() or text[span['end']:line_end].strip():
            continue
        match = re.fullmatch(r'continuaci[oó]n[ \t]+(?:de[ \t]+(?:la[ \t]+)?)?sesi[oó]n[ \t]+([0-9]+)[ \t]*[.:]?', span['quote'], re.IGNORECASE)
        if match and match.group(1) == number:
            named = True
    if not named:
        return ['Continuation must be a standalone literal heading naming the same complete session number']
    start_position, end_position = (anchor['page'], anchor['start']), (label['page'], label['start'])
    for other in document['units']:
        position = (other['anchor']['page'], other['anchor']['start'])
        if start_position < position < end_position:
            return ['Cross-page continuation crosses an authored physical unit']
    preceding_same_number = 0
    for other in document['units']:
        span = other['anchor']
        if other['kind'] != 'session' or (span['page'], span['start']) >= end_position:
            continue
        match = re.match(r'sesi[oó]n[ \t]+([0-9]+)(?=$|[ \t:.\-–—])', pages[span['page'] - 1][span['start']:], re.IGNORECASE)
        preceding_same_number += bool(match and match.group(1) == number)
    if preceding_same_number != 1:
        return ['Continuation session number does not identify one unique preceding physical session']
    # Inspect source lines after the original unit header through the target
    # label, including intermediate pages. This catches unannotated resets too.
    sections = []
    for page_number in range(anchor['page'], label['page'] + 1):
        text = pages[page_number - 1]
        start = anchor['start'] if page_number == anchor['page'] else 0
        end = label['start'] if page_number == label['page'] else len(text)
        lines = text[start:end].splitlines()
        sections.extend(lines[1:] if page_number == anchor['page'] else lines)
    boundary = re.compile(r'^[ \t]*(?:sesi[oó]n[ \t]+[0-9]+(?:$|[ \t:.\-–—])|proyecto[ \t]*:|datos[ \t]+generales[ \t]*:?[ \t]*$)', re.IGNORECASE)
    if any(boundary.match(line) for line in sections):
        return ['Cross-page continuation crosses a source session, project or metadata reset']
    return []


def _scope_basis(record):
    claim = record.get('claim') if isinstance(record, dict) else None
    metadata = claim.get('metadata') if isinstance(claim, dict) else None
    return metadata.get('unit_scope_basis') if isinstance(metadata, dict) else None


def _scope_contract_mode(record, requirements):
    """Keep the legacy path byte-for-byte compatible on historical outputs."""
    # Only candidates have a separate scope-validation route. Abstentions and
    # malformed decisions must keep ordinary validation of every reference.
    if not isinstance(record, dict) or record.get('decision') != 'candidate':
        return False
    if requirements:
        return True
    claim = record.get('claim') if isinstance(record, dict) else None
    metadata = claim.get('metadata') if isinstance(claim, dict) else None
    if isinstance(metadata, dict) and 'unit_scope_basis' in metadata:
        return True
    for owner in (record, claim):
        roles = _evidence_by_role(owner.get('evidence')) if isinstance(owner, dict) else {}
        if roles.get('unit_scaffold_tail') or roles.get('unit_scaffold_prefix'):
            return True
    return False


# This grammar is deliberately local to the evaluator. It discovers the
# structure from original strings, never from product parsers or gold spans.
_SCOPE_SESSION = re.compile(r'^[ \t]*(sesi[oó]n[ \t]+[0-9]+)(?=$|[ \t:.\-–—])', re.I)
_SCOPE_MOMENT = re.compile(r'^[ \t]*(inicio|desarrollo|cierre)(?=[ \t]*:|[ \t]*$)', re.I)
_SCOPE_METADATA = re.compile(
    r'^[ \t]*(?:-[ \t]*)?(?:fecha|tiempo|duraci[oó]n|tema[ \t]+de[ \t]+la[ \t]+sesi[oó]n|'
    r'organizaci[oó]n|campos?)[ \t]*:[ \t]*(.*)$', re.I)
_SCOPE_DECLARATION = re.compile(
    r'^[ \t]*(?:-[ \t]*)?(?P<label>(?:(?:[A-Za-z]{1,4}[0-9]{1,4}[ \t]+)?'
    r'PDA(?:[ \t]*[0-9]+)?|contenidos?(?:[ \t]+curriculares)?)[ \t]*:)'
    r'[ \t]*(?P<value>.*)$', re.I)
_SCOPE_BOUNDARY = re.compile(
    r'^[ \t]*(?:sesi[oó]n[ \t]+[0-9]+(?=$|[ \t:.\-–—])|proyecto[ \t]*:|'
    r'datos[ \t]+generales\b|continuaci[oó]n\b|ejemplo\b)', re.I)
_SCOPE_INLINE_H = r'[ \t\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]'
_SCOPE_INLINE_BOUNDARY = re.compile(
    rf'(?<!\w)(?:(?:inicio|desarrollo|cierre){_SCOPE_INLINE_H}*:|proyecto{_SCOPE_INLINE_H}*:|'
    rf'sesi[oó]n{_SCOPE_INLINE_H}*[0-9]+\b|datos{_SCOPE_INLINE_H}+generales\b)', re.I)
_SCOPE_ACTIVITY = re.compile(rf'^{_SCOPE_INLINE_H}*(?:[-*+•◦]|[0-9]+[.)])')
_TRUNCATED_END = re.compile(r'(?:\b(?:y|e|o|u|de|del|para|con|en|a)|[,;:\-–—])$', re.I)
_UNSUPPORTED_SCAFFOLD_CHAR = re.compile(r'[\v\f\x1c-\x1f\x85\u2028\u2029]')


def _source_lines(text):
    # Only original CR/LF delimit physical lines; Python splitlines would also
    # silently reinterpret vertical separators that the contract does not admit.
    for match in re.finditer(r'[^\r\n]*(?:\r\n|\r|\n|$)', text):
        if match.start() != match.end():
            yield match.start(), match.group().rstrip('\r\n')


def _balanced_quotes(text):
    stack = []
    closing = {'»': '«', '”': '“'}
    for char in text:
        if char == '"':
            if stack and stack[-1] == '"':
                stack.pop()
            else:
                stack.append(char)
        elif char in ('«', '“'):
            stack.append(char)
        elif char in closing:
            if not stack or stack.pop() != closing[char]:
                return False
    return not stack


def _complete_scope_value(text):
    value = text.strip()
    return (bool(value) and not _TRUNCATED_END.search(value) and _balanced_quotes(value)
            and not _UNSUPPORTED_SCAFFOLD_CHAR.search(text))


def _scaffold_geometry(pages, anchor, declaration_page):
    """Return exact whole-page proof spans and source-discovered declarations.

    Gold label/value spans are intentionally not arguments. Discovery happens
    before comparing a supplied literal reference with the discovered blocks.
    """
    errors = []
    if not _span_valid(pages, anchor) or declaration_page != anchor['page'] + 1:
        return None, [], ['Scaffold requires the immediately preceding physical page']
    prior, current = pages[anchor['page'] - 1], pages[declaration_page - 1]
    if _UNSUPPORTED_SCAFFOLD_CHAR.search(prior):
        errors.append('Scaffold prior page contains an unsupported separator or control')
    prior_lines = list(_source_lines(prior))
    sessions = [(offset, line, match) for offset, line in prior_lines
                if (match := _SCOPE_SESSION.match(line))]
    if len(sessions) != 1 or sessions[0][0] + sessions[0][2].start(1) != anchor['start']:
        return None, [], ['Scaffold requires one unique source session on the prior page']
    header_offset, header, identifier = sessions[0]
    if anchor['end'] > header_offset + len(header):
        errors.append('Scaffold anchor must remain within its physical header')
    if _SCOPE_INLINE_BOUNDARY.search(header[identifier.end():]):
        errors.append('Scaffold session header contains an embedded moment, unit or reset')
    entering_context = ''.join(pages[:anchor['page'] - 1]) + prior[:header_offset]
    if not _balanced_quotes(entering_context) or not _balanced_quotes(prior[header_offset:]):
        errors.append('Scaffold prior context contains an unresolved quotation')
    for offset, line in prior_lines:
        if offset <= header_offset or not line.strip():
            continue
        metadata = _SCOPE_METADATA.fullmatch(line)
        if (metadata is None or not _complete_scope_value(metadata.group(1))
                or _SCOPE_INLINE_BOUNDARY.search(metadata.group(1))):
            errors.append('Scaffold tail must contain only complete single-line planning metadata')
            break
    moments = [(offset, match.group(1).lower()) for offset, line in _source_lines(current)
               if (match := _SCOPE_MOMENT.match(line))]
    if not moments or moments[0][1] != 'inicio':
        return None, [], errors + ['Scaffold current page must have Inicio as its first lesson moment']
    prefix_end = moments[0][0]
    prefix = current[:prefix_end]
    if _UNSUPPORTED_SCAFFOLD_CHAR.search(prefix):
        errors.append('Scaffold prefix contains an unsupported separator or control')
    if not _balanced_quotes(prefix):
        errors.append('Scaffold prefix contains an unresolved quotation')
    blocks, active = [], None

    def finish():
        nonlocal active
        if active is not None:
            value = current[active['value_start']:active['value_end']]
            if not _complete_scope_value(value):
                errors.append('Scaffold curricular block has an empty or truncated value')
            if _SCOPE_INLINE_BOUNDARY.search(value):
                errors.append('Scaffold curricular block contains an embedded moment, unit or reset')
            blocks.append(active)
            active = None

    for offset, line in _source_lines(prefix):
        if not line.strip():
            continue
        metadata = _SCOPE_METADATA.fullmatch(line)
        declaration = _SCOPE_DECLARATION.fullmatch(line)
        if metadata:
            finish()
            if (not _complete_scope_value(metadata.group(1))
                    or _SCOPE_INLINE_BOUNDARY.search(metadata.group(1))):
                errors.append('Scaffold prefix requires complete single-line planning metadata')
        elif declaration:
            finish()
            value = declaration.group('value')
            active = dict(label_start=offset + declaration.start('label'),
                          label_end=offset + declaration.end('label'),
                          value_start=offset + declaration.start('value'),
                          value_end=offset + declaration.start('value') + len(value.rstrip()))
        else:
            previous = current[active['value_start']:active['value_end']].rstrip() if active else ''
            # Wrapping is allowed only in a labelled, unfinished curricular
            # block. No display headings, bullets or post-sentence prose.
            if (not active or not previous or re.search(r'[.!?]["»”]?$', previous)
                    or _SCOPE_ACTIVITY.match(line)
                    or line.lstrip().startswith(('"', '«', '“'))
                    or (line.strip().isupper() and any(c.isalpha() for c in line))
                    or ':' in line or _SCOPE_BOUNDARY.match(line)
                    or _SCOPE_MOMENT.match(line)):
                errors.append('Scaffold prefix contains free prose, an activity, heading or reset')
                finish()
            else:
                active['value_end'] = offset + len(line.rstrip())
    finish()
    if not blocks:
        errors.append('Scaffold prefix must contain a complete typed declaration')
    proofs = [dict(role='unit_scaffold_tail', page=anchor['page'], start=anchor['start'],
                   end=len(prior), quote=prior[anchor['start']:]),
              dict(role='unit_scaffold_prefix', page=declaration_page, start=0,
                   end=prefix_end, quote=prefix)]
    return proofs, blocks, errors


def _scope_errors(document, record, requirements=None):
    """Independent scope errors never erase otherwise exact literal evidence."""
    if not isinstance(record, dict) or record.get('decision') != 'candidate':
        return []
    roles = _evidence_by_role(record.get('evidence'))
    claim = record.get('claim')
    claim_roles = _evidence_by_role(claim.get('evidence')) if isinstance(claim, dict) else {}
    basis = _scope_basis(record)
    if not _scope_contract_mode(record, requirements):
        return _continuation_errors(document, record)
    errors, pages = [], document['pages']
    sha = hash_canonical_pages(pages)
    for owner in (record, claim):
        evidence = owner.get('evidence') if isinstance(owner, dict) else None
        for ref in evidence if isinstance(evidence, list) else []:
            if _auxiliary_scope_reference(ref):
                errors.extend(_reference_errors(ref, pages, sha))
    for role in SCOPE_PROOF_ROLES:
        # Comparison ignores evidence ordering, but includes every provenance
        # field and duplicate. Invalid values need not be hashable.
        record_keys = sorted(json.dumps(_ref_key(r), ensure_ascii=False, sort_keys=True) for r in roles[role])
        claim_keys = sorted(json.dumps(_ref_key(r), ensure_ascii=False, sort_keys=True) for r in claim_roles.get(role, []))
        if record_keys != claim_keys:
            errors.append(f'AtomicClaim {role} proof contradicts record')
    if basis not in SCOPE_BASES:
        return errors + ['Candidate requires a recognized claim.metadata.unit_scope_basis']
    expected_roles = {'same_page_explicit': (), 'explicit_continuation': ('unit_continuation',),
                      'structural_scaffold_proposal': ('unit_scaffold_tail', 'unit_scaffold_prefix')}[basis]
    for role in SCOPE_PROOF_ROLES:
        expected_count = int(role in expected_roles)
        if len(roles[role]) != expected_count or len(claim_roles.get(role, [])) != expected_count:
            errors.append(f'{basis} requires exactly {expected_count} {role} proofs')
    unit = record.get('unit')
    anchor = _source_span(unit.get('anchor')) if isinstance(unit, dict) else {}
    label = _source_span(roles['label'][0]) if len(roles['label']) == 1 else {}
    value = _source_span(roles['value'][0]) if len(roles['value']) == 1 else {}
    if not all(_span_valid(pages, span) for span in (anchor, label, value)):
        return errors + ['Scope requires valid anchor, label and value references']
    for declaration in document['declarations']:
        requirement = (requirements or {}).get(declaration['id'])
        if requirement and _overlaps(label, declaration['label']):
            if basis != requirement['unit_scope_basis']:
                errors.append('Candidate unit_scope_basis contradicts its fixed supplemental requirement')
            for role in SCOPE_PROOF_ROLES:
                expected = [_key(p) for p in requirement['proofs'] if p['role'] == role]
                actual = [_key(_source_span(p)) for p in roles[role]]
                if actual != expected:
                    errors.append(f'{role} proof contradicts its fixed supplemental range')
    if basis == 'same_page_explicit':
        if anchor['page'] != label['page'] or anchor['start'] >= label['start']:
            errors.append('same_page_explicit requires a preceding anchor on the declaration page')
    elif basis == 'explicit_continuation':
        if anchor['page'] >= label['page']:
            errors.append('explicit_continuation requires a previous-page anchor')
        errors.extend(_continuation_errors(document, record))
    else:
        expected, blocks, grammar_errors = _scaffold_geometry(pages, anchor, label['page'])
        errors.extend(grammar_errors)
        if expected is not None:
            for proof in expected:
                refs = roles[proof['role']]
                if len(refs) != 1 or _key(_source_span(refs[0])) != _key(proof):
                    errors.append(f"{proof['role']} must reproduce the complete original tail or prefix")
            if (label['page'] != value['page'] or not any(
                    label['start'] == block['label_start'] and label['end'] == block['label_end']
                    and value['start'] == block['value_start'] and value['end'] == block['value_end']
                    for block in blocks)):
                errors.append('Scaffold label/value must equal one complete source-discovered block')
    return errors


def validate_scope_contract(reference, contract, reference_bytes):
    """Bind the frozen supplement to original bytes before any predictions."""
    _required(contract, ('version', 'base_reference', 'candidate_scope_requirements', 'additional_reference'), 'Scope contract')
    if contract['version'] != 'session-declarations-scaffold-supplement.v1':
        raise ValueError('Invalid scope contract envelope')
    binding = contract['base_reference']
    if (not isinstance(binding, dict)
            or binding.get('path') != 'tests/fixtures/interpretation/session_declarations_scaffold_v1.json'
            or binding.get('sha256') != SCAFFOLD_REFERENCE_SHA256
            or not isinstance(reference_bytes, bytes)
            or hashlib.sha256(reference_bytes).hexdigest() != binding['sha256']
            or json.loads(reference_bytes) != reference):
        raise ValueError('Scope contract requires its exact bound base-reference bytes and SHA256')
    validate_reference(reference)
    requirements = contract['candidate_scope_requirements']
    if not isinstance(requirements, list):
        raise ValueError('Scope requirements must be a list')
    candidates = {(doc['id'], declaration['id']): (doc, declaration)
                  for doc in reference['documents'] for declaration in doc['declarations']
                  if declaration['expected_decision'] == 'candidate'}
    seen, counts, result = set(), Counter(), defaultdict(dict)
    for requirement in requirements:
        _required(requirement, ('document_id', 'declaration_id', 'unit_scope_basis', 'proofs'), 'Scope requirement')
        key = (requirement['document_id'], requirement['declaration_id'])
        if key not in candidates or key in seen:
            raise ValueError('Unknown or duplicate candidate scope requirement')
        seen.add(key)
        doc, declaration = candidates[key]
        basis, proofs = requirement['unit_scope_basis'], requirement['proofs']
        if basis not in SCOPE_BASES or not isinstance(proofs, list):
            raise ValueError('Invalid candidate scope basis or proofs')
        expected_roles = {'same_page_explicit': [], 'explicit_continuation': ['unit_continuation'],
                          'structural_scaffold_proposal': ['unit_scaffold_tail', 'unit_scaffold_prefix']}[basis]
        if any(not isinstance(proof, dict) for proof in proofs) or sorted(p.get('role', '') for p in proofs) != sorted(expected_roles):
            raise ValueError('Scope requirement proof roles or multiplicity mismatch')
        if any(not _span_valid(doc['pages'], proof) for proof in proofs):
            raise ValueError('Scope requirement proof does not reproduce original text')
        unit = next(u for u in doc['units'] if u['id'] == declaration['unit_id'])
        if basis == 'same_page_explicit' and unit['anchor']['page'] != declaration['label']['page']:
            raise ValueError('Same-page scope requirement has a cross-page unit')
        if basis == 'explicit_continuation':
            sha = hash_canonical_pages(doc['pages'])
            def source(span, role):
                return dict(role=role, document_sha256=sha, page_number=span['page'], excerpt=span['quote'],
                            region=dict(kind='text_offsets', start=span['start'], end=span['end']))
            probe = dict(decision='candidate', unit=dict(kind='session', anchor=source(unit['anchor'], 'unit_anchor')),
                         evidence=[source(declaration['label'], 'label'), source(proofs[0], 'unit_continuation')])
            if (unit['anchor']['page'] >= declaration['label']['page'] or _continuation_errors(doc, probe)):
                raise ValueError('Named scope requirement must retain a complete literal continuation heading')
        if basis == 'structural_scaffold_proposal':
            expected, _, errors = _scaffold_geometry(doc['pages'], unit['anchor'], declaration['label']['page'])
            if errors or sorted((p['role'], _key(p)) for p in proofs) != sorted((p['role'], _key(p)) for p in (expected or [])):
                raise ValueError('Structural scope requirement violates the independent source grammar')
        counts[basis] += 1
        result[key[0]][key[1]] = deepcopy(requirement)
    if seen != candidates.keys() or counts != Counter(same_page_explicit=7, structural_scaffold_proposal=8, explicit_continuation=2):
        raise ValueError('Scope contract must pin all 17 fixed candidate opportunities')
    additional = contract['additional_reference']
    validate_reference(additional)
    if (len(additional['documents']) != 5 or {d['id'] for d in additional['documents']} & {d['id'] for d in reference['documents']}
            or any(len(d['declarations']) != 1 or d['challenges'] or d['absence_expected']
                   or d['declarations'][0]['unit_id'] is not None
                   or d['declarations'][0]['kind'] != 'pda'
                   or d['declarations'][0]['expected_decision'] != 'abstained'
                   or d['declarations'][0]['reason'] != 'unresolved_scope' for d in additional['documents'])):
        raise ValueError('Additional reference must retain five separate unresolved-scope opportunities')
    return dict(result)


def _metric(expected, *extra):
    return dict(expected=expected, correct=0, incorrect=0, omitted=0, **{key: 0 for key in extra})


def _ratios(metrics):
    result = {name: dict(counts) for name, counts in metrics.items()}
    for name in ('literal_declarations', 'unit_assignment', 'known_unit_assignment',
                 'unresolved_unit_abstentions', 'joint_detection_unit', 'session_candidates', 'scope_abstentions',
                 'strict_session_claims'):
        counts = result[name]
        counts['recall'] = counts['correct'] / counts['expected'] if counts['expected'] else None
    literal = result['literal_declarations']
    literal['precision'] = literal['correct'] / literal['emitted_typed_values'] if literal['emitted_typed_values'] else None
    claims = result['strict_session_claims']
    claims['precision'] = claims['correct'] / claims['emitted_claim_records'] if claims['emitted_claim_records'] else None
    result['strict_session_claim_diagnostics']['wrong_emitted_claim_records'] = claims['emitted_claim_records'] - claims['correct']
    return result


def score(document, output, scope_requirements=None):
    """Score detached predictions without importing or consulting any matcher.

    Alignment uses a unique overlap with an authored physical label, never the
    predicted parent or lexical value. Credit still requires exact type, label,
    and complete value. Multiple attempts poison that opportunity, including an
    invalid attempt alongside a correct one. Unalignable records remain extras.
    """
    validate_reference(document)
    pages, declarations, challenges = document['pages'], document['declarations'], document['challenges']
    sha = hash_canonical_pages(pages)
    output_errors = []
    if not isinstance(output, dict):
        output_errors.append('Output must be a dictionary')
        output = {}
    if output.get('version') != 'session-declarations.v1':
        output_errors.append('Prediction version mismatch')
    for field in ('source_doc_sha256', 'extraction_sha256'):
        if output.get(field) != sha:
            output_errors.append(f'{field} must bind the exact extracted-text snapshot')
    if not isinstance(output.get('limits'), list) or any(not isinstance(v, str) for v in output.get('limits', [])):
        output_errors.append('limits must be a string list')
    records = output.get('records')
    if not isinstance(records, list):
        output_errors.append('records must be a list')
        records = []
    malformed_errors = [_record_errors(r, pages, sha, separate_scope=_scope_contract_mode(r, scope_requirements))
                        for r in records]
    # Legacy diagnostics include duplicate IDs; v1.2 keeps multiplicity apart
    # from the individual record contract and from output-level provenance.
    errors = [list(e) for e in malformed_errors]
    invalid_provenance = [_provenance_invalid(r, pages, sha) for r in records]
    unit_errors = [_scope_errors(document, r, scope_requirements) for r in records]
    ids = Counter(r['id'] for r in records if isinstance(r, dict) and isinstance(r.get('id'), str))
    claim_ids = Counter(r['claim']['claim_id'] for r in records if isinstance(r, dict) and isinstance(r.get('claim'), dict) and isinstance(r['claim'].get('claim_id'), str))
    # Physical IDs must not collapse repeated headings or values. Gold IDs are
    # deliberately not consulted; matcher identities need only be consistent.
    physical_ids = defaultdict(set)
    identities = defaultdict(set)
    for record in records:
        unit = record.get('unit') if isinstance(record, dict) else None
        if isinstance(unit, dict) and _text(unit.get('id')) and isinstance(unit.get('anchor'), dict):
            try:
                identity = (unit.get('kind'), _source_span(unit['anchor']).get('page'), _source_span(unit['anchor']).get('start'))
                physical_ids[unit['id']].add(identity)
                identities[identity].add(unit['id'])
            except TypeError:
                pass  # Already invalid coordinates; retain record-level errors.
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if isinstance(record.get('id'), str) and ids[record['id']] > 1:
            errors[i].append('Duplicate record ID')
        claim = record.get('claim')
        if isinstance(claim, dict) and isinstance(claim.get('claim_id'), str) and claim_ids[claim['claim_id']] > 1:
            errors[i].append('Duplicate AtomicClaim ID')
        unit = record.get('unit')
        if isinstance(unit, dict) and isinstance(unit.get('id'), str) and len(physical_ids[unit['id']]) > 1:
            unit_errors[i].append('One unit ID identifies multiple physical anchors')
        if isinstance(unit, dict) and isinstance(unit.get('anchor'), dict):
            identity = (unit.get('kind'), _source_span(unit['anchor']).get('page'), _source_span(unit['anchor']).get('start'))
            try:
                if len(identities[identity]) > 1:
                    unit_errors[i].append('One physical unit has inconsistent IDs')
            except TypeError:
                pass
    opportunities = [(d['id'], d['label']) for d in declarations] + [(c['id'], c['anchor']) for c in challenges]
    assignments = {oid: [] for oid, _ in opportunities}
    overlaps = {oid: [] for oid, _ in opportunities}
    extras = []
    typed_values = 0
    for i, record in enumerate(records):
        roles = _evidence_by_role(record.get('evidence')) if isinstance(record, dict) else {}
        if isinstance(record, dict) and record.get('kind') is not None and roles.get('value'):
            typed_values += 1
        matched = {oid for oid, span in opportunities for ref in roles.get('label', []) if _overlaps(_source_span(ref), span)}
        for oid in matched:
            overlaps[oid].append(i)
        if len(matched) == 1:
            assignments[next(iter(matched))].append(i)
        else:
            extras.append(i)
    metrics = {
        'literal_declarations': _metric(len(declarations), 'extras', 'duplicates', 'emitted_typed_values'),
        'unit_assignment': {**_metric(len(declarations)), 'expected_anchored': sum(d['unit_id'] is not None for d in declarations), 'anchor_span_exact': 0},
        'known_unit_assignment': _metric(sum(d['unit_id'] is not None for d in declarations)),
        'unresolved_unit_abstentions': _metric(sum(d['unit_id'] is None for d in declarations)),
        'joint_detection_unit': _metric(len(declarations)),
        'session_candidates': _metric(sum(d['expected_decision'] == 'candidate' for d in declarations), 'explicit_abstentions'),
        'scope_abstentions': _metric(sum(d['expected_decision'] == 'abstained' for d in declarations)),
        'strict_session_claims': {**_metric(sum(d['expected_decision'] == 'candidate' for d in declarations), 'explicit_abstentions'),
                                  'emitted_claim_records': sum(_asserts_claim(r) for r in records)},
        'strict_session_claim_diagnostics': dict(wrong_emitted_claim_records=0, response_abstention_opportunities=0),
        'challenges': dict(expected=len(challenges), explicit_abstentions=0, silence_no_claim=0, wrong_candidates=0, duplicates=0, invalid_records=0),
        'challenge_opportunities_v1_2': dict(expected=len(challenges), candidate_or_claim=0, no_claim_safe=0,
                                            no_claim_unknown=0, explicit_abstention=0, silence=0,
                                            label_span_mismatch=0, multiplicity=0, malformed_record=0,
                                            invalid_provenance=0),
        'challenge_records_v1_2': dict(emitted_records=0, candidate_or_claim_records=0, malformed_records=0,
                                      invalid_provenance_records=0, explicit_abstention_records=0,
                                      exact_label_records=0, label_span_mismatch_records=0, duplicate_id_records=0),
        'negative_documents': dict(expected=int(document['absence_expected']), false_candidate_emissions=0, explicit_abstentions=0, clean_silence=0, invalid_or_extra_emissions=0, false_candidate_records=0),
        'output': dict(documents=1, invalid_outputs=int(bool(output_errors)), emitted_records=len(records), invalid_unit_assignments=sum(bool(e) for e in unit_errors), invalid_records=sum(bool(e) or bool(output_errors) for e in errors), extras=len(extras), duplicate_record_ids=sum(n - 1 for n in ids.values() if n > 1)),
    }
    metrics['output'].update(malformed_records=sum(bool(e) for e in malformed_errors),
                             invalid_provenance_records=sum(invalid_provenance))
    metrics['literal_declarations']['extras'] = sum(isinstance(records[i], dict) and records[i].get('kind') is not None and bool(_evidence_by_role(records[i].get('evidence'))['value']) for i in extras)
    metrics['literal_declarations']['emitted_typed_values'] = typed_values
    units = {u['id']: u for u in document['units']}
    details = []
    for declaration in declarations:
        found = assignments[declaration['id']]
        decision_metric = 'session_candidates' if declaration['expected_decision'] == 'candidate' else 'scope_abstentions'
        unit_metric = 'known_unit_assignment' if declaration['unit_id'] is not None else 'unresolved_unit_abstentions'
        group_names = ('literal_declarations', 'unit_assignment', unit_metric, 'joint_detection_unit', decision_metric)
        if declaration['expected_decision'] == 'candidate':
            group_names += ('strict_session_claims',)
            metrics['strict_session_claim_diagnostics']['response_abstention_opportunities'] += any(
                not output_errors and not errors[i] and records[i].get('decision') == 'abstained'
                and records[i].get('claim') is None for i in found)
        if not found:
            for name in group_names:
                metrics[name]['omitted'] += 1
            details.append(dict(id=declaration['id'], outcome='omitted', record_indexes=[]))
            continue
        if len(found) != 1:
            for name in group_names:
                metrics[name]['incorrect'] += 1
            metrics['literal_declarations']['duplicates'] += len(found) - 1
            details.append(dict(id=declaration['id'], outcome='duplicate', record_indexes=found))
            continue
        index = found[0]
        record = records[index]
        roles = _evidence_by_role(record.get('evidence'))
        valid = not errors[index] and not output_errors
        exact = (valid and record.get('kind') == declaration['kind']
                 and len(roles['label']) == len(roles['value']) == 1
                 and _key(_source_span(roles['label'][0])) == _key(declaration['label'])
                 and _key(_source_span(roles['value'][0])) == _key(declaration['value']))
        expected_unit, predicted_unit = units.get(declaration['unit_id']), record.get('unit')
        assignment = (valid and not unit_errors[index] and ((expected_unit is None and predicted_unit is None and record.get('decision') == 'abstained')
                      or (expected_unit is not None and isinstance(predicted_unit, dict)
                          and _anchor_identity(document, expected_unit, predicted_unit))))
        if (valid and not unit_errors[index] and expected_unit is not None and isinstance(predicted_unit, dict)
                and predicted_unit.get('kind') == expected_unit['kind']
                and _key(_source_span(predicted_unit.get('anchor'))) == _key(expected_unit['anchor'])):
            metrics['unit_assignment']['anchor_span_exact'] += 1
        for name, correct in (('literal_declarations', exact), ('unit_assignment', assignment),
                              (unit_metric, assignment), ('joint_detection_unit', exact and assignment)):
            metrics[name]['correct' if correct else 'incorrect'] += 1
        if exact and not unit_errors[index] and record.get('decision') == declaration['expected_decision']:
            metrics[decision_metric]['correct'] += 1
        elif exact and decision_metric == 'session_candidates' and record.get('decision') == 'abstained':
            metrics[decision_metric]['explicit_abstentions'] += 1
        else:
            metrics[decision_metric]['incorrect'] += 1
        if declaration['expected_decision'] == 'candidate':
            if exact and assignment and record.get('decision') == 'candidate':
                strict_outcome = 'correct'
            elif exact and record.get('decision') == 'abstained':
                strict_outcome = 'explicit_abstentions'
            else:
                strict_outcome = 'incorrect'
            metrics['strict_session_claims'][strict_outcome] += 1
        details.append(dict(id=declaration['id'], outcome='exact' if exact else 'incorrect', unit_correct=bool(assignment), record_indexes=found))
    for challenge in challenges:
        found = assignments[challenge['id']]
        if not found:
            outcome = 'invalid_records' if output_errors else 'silence_no_claim'
        elif len(found) > 1:
            outcome = 'duplicates'
        else:
            i = found[0]
            record = records[i]
            labels = _evidence_by_role(record.get('evidence'))['label']
            if errors[i] or output_errors or len(labels) != 1 or _key(_source_span(labels[0])) != _key(challenge['anchor']):
                outcome = 'invalid_records'
            elif record.get('decision') == 'candidate':
                outcome = 'wrong_candidates'
            else:
                outcome = 'explicit_abstentions'
        metrics['challenges'][outcome] += 1
        details.append(dict(id=challenge['id'], outcome=outcome, record_indexes=found))
    # Freeze legacy challenge semantics, including their historically broad
    # invalid_records label. New diagnostics do not rename that old outcome as
    # a malformed record or award positive recall for avoiding a claim.
    metrics['legacy_challenges_v1_1'] = dict(metrics['challenges'])
    # Safety must consider every supplied claim locator, not only the record's
    # preferred label. A contradictory claim can target a challenge even when
    # its enclosing record was aligned to a positive opportunity elsewhere.
    safety_overlaps = {challenge['id']: set(overlaps[challenge['id']]) for challenge in challenges}
    for i, record in enumerate(records):
        claim = record.get('claim') if isinstance(record, dict) else None
        if not isinstance(claim, dict):
            continue
        claim_labels = _evidence_by_role(claim.get('evidence'))['label']
        for challenge in challenges:
            if any(_overlaps(_source_span(ref), challenge['anchor']) for ref in claim_labels):
                safety_overlaps[challenge['id']].add(i)
    challenge_indexes = {i for indexes in safety_overlaps.values() for i in indexes}
    exact_challenge_labels = {}
    for i in challenge_indexes:
        labels = _evidence_by_role(records[i].get('evidence'))['label']
        exact_challenge_labels[i] = {c['id'] for c in challenges if len(labels) == 1
                                    and _key(_source_span(labels[0])) == _key(c['anchor'])}
        diagnostic = metrics['challenge_records_v1_2']
        diagnostic['emitted_records'] += 1
        diagnostic['candidate_or_claim_records'] += _asserts_claim(records[i])
        diagnostic['malformed_records'] += bool(malformed_errors[i])
        diagnostic['invalid_provenance_records'] += invalid_provenance[i]
        diagnostic['explicit_abstention_records'] += (not output_errors and not malformed_errors[i]
                                                       and records[i].get('decision') == 'abstained')
        diagnostic['exact_label_records' if exact_challenge_labels[i] else 'label_span_mismatch_records'] += 1
        diagnostic['duplicate_id_records'] += (isinstance(records[i].get('id'), str)
                                                and ids[records[i]['id']] > 1)
    # Unalignable claims, malformed records and invalid source references can
    # conceal where a claim applies. Valid unalignable no-claim records cannot.
    unknown_unlocalized = any(_asserts_claim(records[i]) or malformed_errors[i] or invalid_provenance[i]
                              for i in extras)
    unknown_unlocalized |= any(_asserts_claim(record) and (malformed_errors[i] or invalid_provenance[i])
                               for i, record in enumerate(records))
    challenge_details = []
    for challenge in challenges:
        found = sorted(safety_overlaps[challenge['id']])
        asserted = any(_asserts_claim(records[i]) for i in found)
        malformed = any(malformed_errors[i] for i in found)
        provenance = bool(output_errors) or any(invalid_provenance[i] for i in found)
        unknown = provenance or malformed or unknown_unlocalized
        safety = 'candidate_or_claim' if asserted else 'no_claim_unknown' if unknown else 'no_claim_safe'
        explicit = any(not output_errors and not malformed_errors[i]
                       and records[i].get('decision') == 'abstained' for i in found)
        mismatch = any(challenge['id'] not in exact_challenge_labels[i] for i in found)
        diagnostic = metrics['challenge_opportunities_v1_2']
        diagnostic[safety] += 1
        diagnostic['explicit_abstention'] += explicit
        diagnostic['silence'] += not found and not unknown
        diagnostic['label_span_mismatch'] += mismatch
        diagnostic['multiplicity'] += len(found) > 1
        diagnostic['malformed_record'] += malformed
        diagnostic['invalid_provenance'] += provenance
        challenge_details.append(dict(id=challenge['id'], safety=safety, explicit_abstention=explicit,
                                      silence=not found and not unknown, label_span_mismatch=mismatch,
                                      multiplicity=len(found) > 1, malformed_record=malformed,
                                      invalid_provenance=provenance,
                                      unknown_unlocalized=unknown_unlocalized, record_indexes=found))
    if document['absence_expected']:
        false_candidates = sum(_asserts_claim(r) for r in records)
        metrics['negative_documents']['false_candidate_records'] = false_candidates
        if false_candidates:
            outcome = 'false_candidate_emissions'
        elif output_errors or any(errors) or extras or metrics['challenges']['duplicates'] or metrics['challenges']['invalid_records']:
            outcome = 'invalid_or_extra_emissions'
        elif records:
            outcome = 'explicit_abstentions'
        else:
            outcome = 'clean_silence'
        metrics['negative_documents'][outcome] = 1
    return {'metrics': _ratios(metrics), 'output_errors': output_errors,
            'record_errors': [{'index': i, 'errors': e} for i, e in enumerate(errors) if e],
            'unit_errors': [{'index': i, 'errors': e} for i, e in enumerate(unit_errors) if e],
            'malformed_record_errors': [{'index': i, 'errors': e} for i, e in enumerate(malformed_errors) if e],
            'extra_record_indexes': extras, 'opportunities': details, 'challenge_diagnostics_v1_2': challenge_details}


def predict(document):
    """Optional matcher adapter; never called from validation or scoring."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.session_declarations import extract_declarations
    return extract_declarations(document['pages'], source_doc_sha256=hash_canonical_pages(document['pages']))


def evaluate(reference, predictor=predict, *, scope_contract=None, reference_bytes=None):
    """Reject malformed reference data before invoking any supplied predictor."""
    validate_reference(reference)
    requirements = (validate_scope_contract(reference, scope_contract, reference_bytes)
                    if scope_contract is not None else {})
    documents = [{'id': document['id'], **score(document, predictor(document), requirements.get(document['id']))}
                 for document in reference['documents']]
    # Keep the report schema, including N/A ratios, even for an empty reference.
    empty_document = dict(id='empty', pages=[''], units=[], declarations=[], challenges=[], absence_expected=True)
    empty_output = dict(version='session-declarations.v1', source_doc_sha256=hash_canonical_pages(['']), extraction_sha256=hash_canonical_pages(['']), records=[], limits=[])
    template = score(empty_document, empty_output)['metrics']
    total = {name: {key: 0 for key in counts if key not in ('recall', 'precision')} for name, counts in template.items()}
    for document in documents:
        for name, counts in total.items():
            for key in counts:
                counts[key] += document['metrics'][name][key]
    report = dict(evaluator_version='session-declarations-evaluation.v1.3.3', reference_kind=reference['reference_kind'], scope=deepcopy(reference['scope']),
                total=_ratios(total), documents=documents,
                definitions={
                    'denominators': 'Fixed authored opportunities, separately aggregated; negative documents never enter positive recall.',
                    'literal_detection': 'Exact type, physical label and complete literal value; no normalization, excerpt or partial-span credit.',
                    'unit_assignment': 'Combined scope-decision summary only. Positive physical assignment is known_unit_assignment; unresolved_unit_abstentions reports correctly retained null scopes separately. Exact anchor spans reported separately.',
                    'known_unit_assignment': 'Physical session/project identity under the pre-output v1.1 prefix amendment, over fixed known-unit opportunities only; independent of literal correctness.',
                    'unresolved_unit_abstentions': 'Explicitly abstained unresolved null scope over fixed unresolved-unit opportunities; never counted as positive physical assignment.',
                    'decisions': 'Require valid exact literal detection and coherent unit identities/continuation; wrong but self-consistent parent assignments are reported separately.',
                    'strict_session_claims': 'Fixed positive denominator: declarations with expected_decision=candidate. Correct requires one valid candidate, exact literal detection and correct physical unit, including continuation and identity bijection. Precision denominator is ALL emitted records with decision=candidate OR claim!=null, including extras, duplicates and malformed records. Abstention and silence never earn positive recall.',
                    'strict_session_claim_diagnostics': 'Non-additive diagnostics: wrong_emitted_claim_records=emitted_claim_records minus strict correct under this fixed reference; response_abstention_opportunities counts positive opportunities with a valid localized abstained response, even without complete literal recovery. strict incorrect counts failed reference opportunities, NOT false emitted claims.',
                    'legacy_challenges_v1_1': 'Unchanged v1.1 strict challenge outcomes; challenges is a compatibility alias. Legacy invalid_records includes label-span mismatch and output errors, and is not a malformed-record count.',
                    'challenge_opportunities_v1_2': 'Fixed challenge opportunities. candidate_or_claim, no_claim_safe and no_claim_unknown partition that denominator. Safety uses the conservative union of record and AtomicClaim label locators; any possible overlapping claim defeats safety even if contradictory. Output/provenance errors and malformed or unlocalizable possible claims make no-claim unknown. Other fields are overlapping diagnostics, not recall; reliable silence is separate.',
                    'challenge_records_v1_2': 'Distinct records overlapping any challenge, counted once even when spanning several opportunities. malformed_records means individual record-contract errors only; duplicate IDs, multiplicity and gold label-span mismatch are separate. Explicit abstention records require valid output and record shape/provenance, regardless of gold span equality or multiplicity.',
                    'malformed_records': 'output.malformed_records and malformed_record_errors exclude duplicate IDs and output-level errors; legacy output.invalid_records and record_errors remain unchanged. invalid_provenance_records diagnoses invalid supplied source bindings/spans, independently of gold label-span equality.',
                    'unit_errors': 'ID-to-physical-unit bijection, scope basis and literal scope-proof errors withhold unit/joint/candidate/strict credit without erasing exact literal detection. Legacy outputs without the new basis retain previous checks on previous references.',
                    'scope_contract': 'Optional explicit frozen supplement binds original base-reference bytes by SHA256. All 17 candidate bases and exact proofs are required; its five additional abstention opportunities are reported separately and never enter base positive recall.',
                    'duplicates': 'Additional attempts at the same unique overlapping label invalidate the opportunity; unalignable records remain extras.',
                    'extras': 'output.extras counts every unalignable record; literal_declarations.extras counts their typed-value records. Challenge emissions remain in typed-value precision denominator.',
                    'negative_documents': 'Exclusive document outcomes: false candidate, invalid/extra emission, explicit abstention, or clean silence.',
                    'source_binding': 'SHA256 of canonical UTF-8 JSON original page strings; extracted-text snapshot, not PDF-byte provenance.',
                },
                limits=['Supplied development reference: see reference_kind and scope; not teacher validation or global reliability.',
                        'No SEP catalogue identity, curricular alignment, pedagogical truth or publication authority.',
                        'No OCR/PDF extraction, real API calls, cost or latency measured.'])
    if scope_contract is not None:
        report['scope_contract'] = dict(version=scope_contract['version'],
                                       base_reference=deepcopy(scope_contract['base_reference']),
                                       candidate_requirements=sum(len(r) for r in requirements.values()),
                                       basis_counts=dict(Counter(r['unit_scope_basis']
                                                                for rs in requirements.values() for r in rs.values())))
        report['additional_reference'] = evaluate(scope_contract['additional_reference'], predictor)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=ROOT / 'tests/fixtures/interpretation/session_declarations_v1.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--scope-contract', type=Path,
                        help='Explicit frozen scaffold supplement; additional reference is reported separately')
    args = parser.parse_args(argv)
    raw = args.reference.read_bytes()
    contract_raw = args.scope_contract.read_bytes() if args.scope_contract else None
    report = (evaluate(json.loads(raw), scope_contract=json.loads(contract_raw), reference_bytes=raw)
              if contract_raw is not None else evaluate(json.loads(raw)))
    report['reference_sha256'] = hashlib.sha256(raw).hexdigest()
    if contract_raw is not None:
        report['scope_contract_sha256'] = hashlib.sha256(contract_raw).hexdigest()
    content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(content, encoding='utf-8')
    print(content)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
