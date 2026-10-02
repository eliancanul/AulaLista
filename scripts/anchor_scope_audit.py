"""Opt-in offline scope candidates for values already extracted literally.

No production import, value extraction, provider SDK, network or dossier writes.
Transport lives in the existing recorded-interpretation.v2 replay channel.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
import re
from typing import Protocol

from scripts.anchor_scope_catalogue import (
    CUT_LINE, H, SESSION_SIMPLE, VERSION, canonical, catalogue_from_sources, document_hash,
    example_context, lines, quote_open, route_record, sha,
)

MAX_CHARACTERS = 2_000_000
MAX_RECORDINGS = 6
PACKET_KEYS = {'contract_version', 'group_id', 'document_id', 'document_sha256',
               'catalog_sha256', 'records', 'context_pages', 'allowed_page_numbers', 'expansion_used'}
RESPONSE_KEYS = {'contract_version', 'group_id', 'catalog_sha256', 'action',
                 'record_decisions', 'requested_pages', 'reason'}
DECISION_KEYS = {'record_id', 'status', 'anchor_id', 'value_quote', 'reason'}
RECORD_KEYS = ('record_id', 'mode', 'kind', 'prior_reason', 'prior_decision',
               'prior_unit', 'label_span', 'immutable_value_span')


@dataclass(frozen=True)
class ScopeRecording:
    packet_text: str
    packet_sha256: str
    response_bytes: bytes
    response_sha256: str
    model_as_recorded: str = 'synthetic-test-only'
    request_hash_timing: str = 'post_run_verification'


@dataclass(frozen=True)
class ScopeRequest:
    document_id: str
    pages: tuple[str, ...]
    source_sha256: str
    extraction_sha256: str
    catalogue: dict
    groups: dict[int, list[dict]]
    source_windows_text: str | None = None
    source_windows_sha256: str | None = None


class ScopeProvider(Protocol):
    kind: str

    def propose(self, request: ScopeRequest) -> list[ScopeRecording]:
        """Return bounded saved recordings; never issue an external call."""
        ...


@dataclass(frozen=True)
class RecordedScopeProvider:
    recordings: tuple[ScopeRecording, ...]
    kind: str = field(default='recorded_replay', init=False)

    def propose(self, request):
        return list(self.recordings)


@dataclass(frozen=True)
class ScopeAuditConfig:
    document_id: str
    provider: ScopeProvider | None = None
    enabled: bool = False
    source_windows_text: str | None = None
    source_windows_sha256: str | None = None


class ScopeAuditError(ValueError):
    """Sanitized machine code; never source/provider free text."""


def _need(condition, code):
    if not condition:
        raise ScopeAuditError(code)


def _same(left, right):
    # JSON identity distinguishes bool/int and avoids normalization.
    return canonical(left) == canonical(right)


def _reason(value):
    _need(isinstance(value, str) and bool(value.strip()) and len(value) <= 1000, 'reason_contract')


def _packet(request, packet):
    _need(isinstance(packet, dict) and set(packet) == PACKET_KEYS, 'packet_contract')
    _need(packet['contract_version'] == VERSION, 'packet_version')
    _need(isinstance(packet['group_id'], str) and 0 < len(packet['group_id']) <= 128, 'group_id_contract')
    _need(packet['document_id'] == request.document_id, 'foreign_document')
    _need(packet['document_sha256'] == request.source_sha256, 'source_hash_mismatch')
    _need(packet['catalog_sha256'] == sha(canonical(request.catalogue)), 'catalog_hash_mismatch')
    _need(packet['expansion_used'] is False, 'expansion_not_supported')
    _need(_same(packet['allowed_page_numbers'], list(range(1, len(request.pages) + 1))), 'allowed_pages_mismatch')
    records = packet['records']
    _need(isinstance(records, list) and bool(records), 'missing_records')
    _need(isinstance(records[0], dict) and isinstance(records[0].get('label_span'), dict), 'record_contract')
    number = records[0]['label_span'].get('page_number')
    _need(type(number) is int and number in request.groups, 'foreign_group_page')
    _need(_same(records, request.groups[number]), 'current_record_binding_mismatch')
    context_numbers = [number - 1, number] if number > 1 else [number]
    expected_context = [{'page_number': n, 'text': request.pages[n - 1]} for n in context_numbers]
    _need(_same(packet['context_pages'], expected_context), 'context_source_mismatch')
    return number, set(context_numbers)



def _supplied_prefix(request, supplied, number, offset):
    """Grammar-only history; source evidence offsets are never changed.

    Preserve every supplied page byte/string. If a page has no final CR/LF,
    insert one virtual line boundary for quote/paragraph safety only.
    """
    history = ''
    for n in sorted(supplied):
        if n > number:
            break
        if history and not history.endswith(('\r', '\n')):
            history += '\n'
        history += request.pages[n - 1][:offset] if n == number else request.pages[n - 1]
    return history

def _anchor(request, anchor_id, record, supplied):
    _need(isinstance(anchor_id, str), 'anchor_id_contract')
    matches = [a for a in request.catalogue['entries'] if a['anchor_id'] == anchor_id]
    _need(len(matches) == 1, 'unknown_or_duplicate_anchor_id')
    anchor = matches[0]
    _need(anchor['document_id'] == request.document_id, 'foreign_anchor_document')
    _need(anchor['document_sha256'] == request.source_sha256, 'anchor_source_mismatch')
    _need(anchor['eligibility'] == 'selectable', 'anchor_not_selectable')
    _need(not re.search(r'[\x00-\x09\x0b\x0c\x0e-\x1f\x7f-\x9f\u2028\u2029]', anchor['excerpt']), 'anchor_control_or_vertical_separator')
    _need(set(anchor['support_pages']) <= supplied, 'anchor_support_not_supplied')
    _need(not anchor['repeated_literal'], 'repeated_anchor_requires_review')
    anchor_prefix = _supplied_prefix(request, supplied, anchor['page_number'], anchor['start'])
    _need(not quote_open(anchor_prefix) and not example_context(anchor_prefix, len(anchor_prefix)), 'quoted_or_example_anchor_context')
    if anchor['kind'] == 'session' and not SESSION_SIMPLE.fullmatch(anchor['excerpt']):
        positive_moment = False
        for n in anchor['support_pages']:
            page = request.pages[n - 1]
            low = anchor['end'] if n == anchor['page_number'] else 0
            cuts = [m.start() for m in CUT_LINE.finditer(page, low)]
            high = min(cuts) if cuts else len(page)
            for begin, _, line in lines(page[low:high]):
                offset = low + begin
                history = _supplied_prefix(request, supplied, n, offset)
                if (re.match(rf'{H}*(?:Inicio|Desarrollo|Cierre){H}*(?::|$)', line, re.I)
                        and not quote_open(history) and not example_context(history, len(history))):
                    positive_moment = True
        _need(positive_moment, 'quoted_or_example_session_support')
    label = record['label_span']
    start, end = (anchor['page_number'], anchor['start']), (label['page_number'], label['start'])
    _need(start < end and (anchor['page_number'], anchor['end']) <= end, 'anchor_not_prior')
    _need(anchor['page_number'] in supplied, 'anchor_outside_context')
    # Contradictions only, never nearest-unit assignment or project correction.
    for other in request.catalogue['entries']:
        if other['document_id'] == request.document_id and start < (other['page_number'], other['start']) < end:
            raise ScopeAuditError('intervening_or_ambiguous_unit')
    for n in supplied:
        if not anchor['page_number'] <= n <= label['page_number']:
            continue
        low = anchor['end'] if n == anchor['page_number'] else 0
        high = label['start'] if n == label['page_number'] else len(request.pages[n - 1])
        if low < high:
            prior_line = ''
            for _, _, line in lines(request.pages[n - 1][low:high]):
                metadata_continuation = bool(re.fullmatch(rf'{H}*(?:Fecha{H}*:{H}*(?:(?:Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes){H}+)?(?:0?[1-9]|[12][0-9]|3[01]){H}+)?Tema{H}+de{H}+la{H}*', prior_line, re.I)
                                             and re.match(rf'{H}*sesi[oó]\u0301?n{H}*:', line, re.I))
                _need(not re.match(rf'{H}*DATOS{H}+GENERALES\b', line, re.I), 'reset_barrier')
                _need(metadata_continuation or not re.match(rf'{H}*(?:(?:(?:Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes){H}*[-–—]?{H}*)?SESI[OÓ]\u0301?N\b|(?:Nombre{H}+del{H}+)?Proyecto\b|P\.{H}*Integrador\b)', line, re.I), 'unresolved_scope_barrier')
                prior_line = line
    return anchor



def _validate_current_request(request):
    """Public replay entry never trusts caller/provider catalogue or groups."""
    from scripts.replay_interpretation import decode_recorded_json
    from scripts.session_declarations import extract_declarations
    _need(isinstance(request, ScopeRequest), 'scope_request_contract')
    _need(isinstance(request.document_id, str) and 0 < len(request.document_id) <= 128, 'document_id_contract')
    _need(isinstance(request.pages, tuple) and 0 < len(request.pages) <= 6
          and all(isinstance(p, str) for p in request.pages), 'source_window_contract')
    _need(sum(map(len, request.pages)) <= MAX_CHARACTERS, 'input_limit')
    _need(request.source_sha256 == request.extraction_sha256 == document_hash(request.pages), 'current_source_binding')
    source = {'documents': [{'id': request.document_id, 'pages': list(request.pages)}]}
    if request.source_windows_text is not None:
        _need(isinstance(request.source_windows_text, str) and len(request.source_windows_text) <= MAX_CHARACTERS, 'source_windows_limit')
        source, _ = decode_recorded_json(request.source_windows_text.encode('utf-8'), request.source_windows_sha256,
                                         allow_fence=False, max_bytes=4 * MAX_CHARACTERS)
    else:
        _need(request.source_windows_sha256 is None, 'unexpected_source_windows_hash')
    rebuilt = catalogue_from_sources(source, source_windows_sha256=request.source_windows_sha256)
    _need(sum(len(p) for d in source['documents'] for p in d['pages']) <= MAX_CHARACTERS, 'source_windows_limit')
    current = [d for d in source['documents'] if d['id'] == request.document_id]
    _need(len(current) == 1 and _same(current[0]['pages'], list(request.pages)), 'source_windows_current_mismatch')
    _need(_same(request.catalogue, rebuilt), 'catalogue_source_reconstruction_mismatch')
    baseline = extract_declarations(request.pages, source_doc_sha256=request.source_sha256)
    groups = {}
    for record in baseline['records']:
        row = route_record(current[0], record)
        if row['eligible'] and record.get('claim') is None:
            groups.setdefault(row['label_span']['page_number'], []).append({k: copy.deepcopy(row[k]) for k in RECORD_KEYS})
    _need(_same(request.groups, groups) and list(request.groups) == list(groups), 'current_route_reconstruction_mismatch')

def validate_scope_recordings(*, request, recordings):
    """Atomic current-state validation; all candidates remain review-only."""
    from scripts.replay_interpretation import decode_recorded_json
    _validate_current_request(request)
    _need(isinstance(recordings, (list, tuple)) and 0 < len(recordings) <= MAX_RECORDINGS, 'recording_coverage_or_limit')
    candidates, ledgers, seen_pages, seen_groups = [], [], set(), set()
    for recording in recordings:
        _need(isinstance(recording, ScopeRecording), 'recording_contract')
        _need(isinstance(recording.packet_text, str), 'packet_transport')
        packet, packet_ledger = decode_recorded_json(recording.packet_text.encode('utf-8'), recording.packet_sha256, allow_fence=False)
        number, supplied = _packet(request, packet)
        _need(number not in seen_pages and packet['group_id'] not in seen_groups, 'duplicate_group')
        _need(number == list(request.groups)[len(seen_pages)], 'group_order_mismatch')
        seen_pages.add(number); seen_groups.add(packet['group_id'])
        _need(recording.request_hash_timing in {'pre_run_protocol', 'post_run_verification'}, 'hash_timing_contract')
        _need(isinstance(recording.model_as_recorded, str) and bool(recording.model_as_recorded.strip()), 'model_contract')
        response, transport = decode_recorded_json(recording.response_bytes, recording.response_sha256)
        _need(isinstance(response, dict) and set(response) == RESPONSE_KEYS, 'response_contract')
        _need(response['contract_version'] == VERSION and response['group_id'] == packet['group_id'], 'response_binding')
        _need(response['catalog_sha256'] == packet['catalog_sha256'], 'response_catalog_hash_mismatch')
        _need(response['requested_pages'] == [], 'expansion_not_supported')
        _reason(response['reason'])
        action = response['action']
        _need(action in {'propose', 'abstain'}, 'unsupported_action')
        decisions = response['record_decisions']
        _need(isinstance(decisions, list), 'decisions_contract')
        ledgers.append({'group_id': packet['group_id'], 'packet': packet_ledger, 'response': transport,
                        'request_hash_timing': recording.request_hash_timing,
                        'model_as_recorded': recording.model_as_recorded})
        if action == 'abstain':
            _need(decisions == [], 'abstain_with_decisions')
            continue
        records = packet['records']
        _need(len(decisions) == len(records), 'record_coverage_mismatch')
        proposed = 0
        for decision, record in zip(decisions, records):
            _need(isinstance(decision, dict) and set(decision) == DECISION_KEYS, 'decision_contract')
            _need(decision['record_id'] == record['record_id'], 'record_order_or_identity_mismatch')
            _reason(decision['reason'])
            _need(decision['value_quote'] is None, 'immutable_value_modified')
            if decision['status'] == 'abstained':
                _need(decision['anchor_id'] is None, 'abstention_has_anchor')
                continue
            _need(decision['status'] == 'proposed', 'unsupported_status')
            anchor = _anchor(request, decision['anchor_id'], record, supplied)
            proposed += 1
            candidates.append({'record_id': record['record_id'], 'decision': 'candidate',
                               'state': 'needs_human_review', 'transport_status': 'accepted',
                               'anchor_id': anchor['anchor_id'], 'anchor_kind': anchor['kind'],
                               'anchor': copy.deepcopy(anchor), 'label_span': copy.deepcopy(record['label_span']),
                               'immutable_value_span': copy.deepcopy(record['immutable_value_span']),
                               'source_sha256': request.source_sha256,
                               'extraction_sha256': request.extraction_sha256,
                               'value_basis': 'unchanged_prior_literal', 'claim_emitted': False,
                               'semantic_validation': False, 'production_applied': False})
        _need(proposed > 0, 'propose_without_proposals')
    _need(seen_pages == set(request.groups), 'group_coverage_mismatch')
    return {'status': 'candidates_for_review' if candidates else 'abstained',
            'candidates': candidates, 'errors': [], 'recordings': ledgers}


def audit_scopes(*, pages, declarations, config):
    """Disabled by default, no mutation; provider errors release no candidates."""
    if config is None or isinstance(config, ScopeAuditConfig) and config.enabled is False:
        return {'status': 'disabled', 'candidates': [], 'errors': [], 'external_calls': 0}
    attempts = 0
    try:
        _need(isinstance(config, ScopeAuditConfig) and config.enabled is True, 'config_contract')
        _need(getattr(config.provider, 'kind', None) in {'synthetic_test', 'recorded_replay'}, 'external_provider_blocked')
        _need(isinstance(config.document_id, str) and 0 < len(config.document_id) <= 128, 'document_id_contract')
        _need(isinstance(pages, (tuple, list)) and 0 < len(pages) <= 6 and all(isinstance(p, str) for p in pages), 'source_window_contract')
        _need(sum(map(len, pages)) <= MAX_CHARACTERS, 'input_limit')
        dsha = document_hash(pages)
        _need(declarations['source_doc_sha256'] == declarations['extraction_sha256'] == dsha, 'current_source_binding')
        source = {'documents': [{'id': config.document_id, 'pages': list(pages)}]}
        source_windows_hash = None
        if config.source_windows_text is not None:
            from scripts.replay_interpretation import decode_recorded_json
            _need(isinstance(config.source_windows_text, str) and len(config.source_windows_text) <= MAX_CHARACTERS, 'source_windows_limit')
            source, _ = decode_recorded_json(config.source_windows_text.encode('utf-8'), config.source_windows_sha256, allow_fence=False, max_bytes=4 * MAX_CHARACTERS)
            source_windows_hash = config.source_windows_sha256
        catalogue = catalogue_from_sources(source, source_windows_sha256=source_windows_hash)
        _need(sum(len(p) for d in source['documents'] for p in d['pages']) <= MAX_CHARACTERS, 'source_windows_limit')
        current = [d for d in source['documents'] if d['id'] == config.document_id]
        _need(len(current) == 1 and _same(current[0]['pages'], list(pages)), 'source_windows_current_mismatch')
        groups, seen = {}, set()
        for record in declarations['records']:
            _need(isinstance(record, dict) and isinstance(record.get('id'), str) and record['id'] not in seen, 'record_identity_contract')
            seen.add(record['id'])
            row = route_record(current[0], record)
            if row['eligible'] and record.get('claim') is None:
                groups.setdefault(row['label_span']['page_number'], []).append({k: copy.deepcopy(row[k]) for k in RECORD_KEYS})
        if not groups:
            return {'status': 'no_eligible_records', 'candidates': [], 'errors': [], 'external_calls': 0, 'provider_attempts': 0}
        request = ScopeRequest(config.document_id, tuple(pages), dsha, dsha, catalogue, groups,
                               config.source_windows_text, config.source_windows_sha256)
        try:
            attempts = 1
            recordings = config.provider.propose(copy.deepcopy(request))
        except Exception:
            raise ScopeAuditError('provider_failure') from None
        from scripts.replay_interpretation import replay_scope_audit
        result = replay_scope_audit(request=request, recordings=recordings)
        result.update(external_calls=0, provider_attempts=1)
        return result
    except (ScopeAuditError, ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError) as error:
        code = str(error) if isinstance(error, ScopeAuditError) else 'malformed_scope_input'
        return {'status': 'invalid', 'candidates': [], 'errors': [code], 'external_calls': 0,
                'semantic_validation': False, 'production_applied': False, 'provider_attempts': attempts}
