"""Bounded, detached mixed-field hypotheses from saved/synthetic bytes only.

No live provider, network, SDK, production claims or semantic acceptance.
Contract: docs/development/mixed-field-audit-contract-v1.md.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Protocol

VERSION = 'mixed-field-audit.v1.1'
WIRE_VERSION = 'mixed-field-auditor.v1'
REQUEST_VERSION = 'mixed-field-audit-request.v1'
PROFILE_VERSION = 'mixed-field-extraction-profile.v1.1'
RECOVERY_VERSION = 'closed-mixed-fields.v1'
PDA_RECOVERY_VERSION = 'explicit-pda-local-context.v1'
MAX_CHARACTERS = 2_000_000
MAX_RECORDS = 2_000
MAX_PACKETS = 6
MAX_BYTES = 262_272
MAX_SEGMENTS = 128
MAX_SUPPORTS = 16
CODE_PATHS = (
    'curriculum/claims.py', 'curriculum/overview_fields.py',
    'curriculum/source_interpreter.py', 'curriculum/source_segments.py',
    'curriculum/vocabulary.py', 'scripts/anchor_scope_catalogue.py',
    'scripts/mixed_field_recovery.py', 'scripts/pda_context_recovery.py',
    'scripts/session_declarations.py',
)
REQUEST_KEYS = {'contract_version', 'document_id', 'pages', 'pages_sha256',
                'extraction_profile', 'base_output_sha256', 'route', 'packets'}
PROFILE_KEYS = {'contract_version', 'matcher_version', 'extraction_code_sha256',
                'mixed_field_recovery_version', 'pda_context_recovery_version', 'options'}
RESPONSE_KEYS = {'contract_version', 'group_id', 'packet_sha256', 'action',
                 'record_decisions', 'requested_pages', 'reason'}
DECISION_KEYS = {'audit_record_id', 'record_binding_sha256', 'status',
                 'interpretation', 'partition', 'reason'}
SEGMENT_KEYS = {'span', 'disposition', 'proposed_kind', 'basis', 'evidence', 'reason'}
SPAN_KEYS = {'page_number', 'start', 'end', 'excerpt'}
SOURCE_REF_KEYS = {'document_sha256', 'page_number', 'printed_label',
                   'excerpt', 'region', 'role'}
CLASS_STATUS = {'text_generic': 'observed', 'no_resolvable': 'abstained',
                'mixed_preserved': 'observed', 'typed_partition_proposed': 'proposed'}
DISPOSITIONS = {'typed_proposal', 'preserved_untyped', 'unresolved_reference', 'formatting'}
BASIS_ROLE = {'semantic_context': 'semantic_context', 'reported_structure': 'structural_context'}
HASH = re.compile(r'[0-9a-f]{64}\Z')


class MixedFieldAuditError(ValueError):
    """A static machine code only; never source or provider error text."""


@dataclass(frozen=True)
class MixedFieldRecording:
    packet_bytes: bytes
    packet_sha256: str
    response_bytes: bytes
    response_sha256: str
    model_as_recorded: str = 'synthetic-test-only'
    request_hash_timing: str = 'post_run_verification'


class MixedFieldProvider(Protocol):
    kind: str

    def propose(self, packets: tuple[dict, ...]) -> list[MixedFieldRecording]:
        """Return saved/synthetic bytes; trusted local provider, never a live call."""
        ...


@dataclass(frozen=True)
class RecordedMixedFieldProvider:
    recordings: tuple[MixedFieldRecording, ...]
    kind: str = field(default='recorded_replay', init=False)

    def propose(self, packets):
        return list(self.recordings)


@dataclass(frozen=True)
class MixedFieldAuditConfig:
    document_id: str
    provider: MixedFieldProvider | None = None
    enabled: bool = False
    literal_recovery: bool = False
    pda_context: bool = False


def _need(condition, code):
    if not condition:
        raise MixedFieldAuditError(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _same(left, right):
    return canonical(left) == canonical(right)


def _id(value):
    return (isinstance(value, str) and 0 < len(value) <= 128
            and not any(ord(c) < 32 or 127 <= ord(c) <= 159
                        or 0xD800 <= ord(c) <= 0xDFFF for c in value))


def _hash(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _reason(value):
    _need(isinstance(value, str) and bool(value.strip()) and len(value) <= 1000,
          'reason_contract')


def _keys(value, keys, code):
    _need(isinstance(value, dict) and set(value) == keys, code)


def _span(span, pages, supplied=None):
    _keys(span, SPAN_KEYS, 'span_contract')
    p, start, end = span['page_number'], span['start'], span['end']
    _need(type(p) is int and 1 <= p <= len(pages), 'span_page')
    _need(supplied is None or p in supplied, 'evidence_outside_context')
    _need(type(start) is int and type(end) is int and 0 <= start < end <= len(pages[p-1]),
          'span_bounds')
    _need(isinstance(span['excerpt'], str) and span['excerpt'] == pages[p-1][start:end],
          'span_quote')
    return span


def _source_ref(ref, pages, source):
    _keys(ref, SOURCE_REF_KEYS, 'source_reference_contract')
    _need(ref['document_sha256'] == source and isinstance(ref['printed_label'], str)
          and isinstance(ref['role'], str), 'source_reference_binding')
    region = ref['region']
    _keys(region, {'kind', 'start', 'end'}, 'source_region_contract')
    _need(region['kind'] == 'text_offsets', 'source_region_kind')
    return _span({'page_number': ref['page_number'], 'start': region['start'],
                  'end': region['end'], 'excerpt': ref['excerpt']}, pages)


def _code_hash():
    root = Path(__file__).resolve().parents[1]
    try:
        return sha(canonical([{'path': name, 'sha256': sha((root / name).read_bytes())}
                              for name in CODE_PATHS]))
    except (OSError, ValueError):
        raise MixedFieldAuditError('extraction_code_unavailable') from None


def _profile(literal_recovery, pda_context):
    try:
        from scripts.session_declarations import MATCHER_VERSION
    except ImportError:
        raise MixedFieldAuditError('extraction_profile_unavailable') from None
    return {'contract_version': PROFILE_VERSION, 'matcher_version': MATCHER_VERSION,
            'extraction_code_sha256': _code_hash(),
            'mixed_field_recovery_version': RECOVERY_VERSION,
            'pda_context_recovery_version': PDA_RECOVERY_VERSION,
            'options': {'literal_recovery': literal_recovery, 'mixed_fields': True,
                        'pda_context': pda_context}}


def _validate_source(pages, document_id):
    _need(_id(document_id), 'document_id_contract')
    _need(isinstance(pages, (tuple, list)) and 1 <= len(pages) <= MAX_PACKETS
          and all(isinstance(p, str) for p in pages), 'source_window_contract')
    _need(sum(map(len, pages)) <= MAX_CHARACTERS, 'source_limit')
    return sha(json.dumps(list(pages), ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def _fresh_base(pages, source, literal_recovery, pda_context):
    try:
        from scripts.session_declarations import extract_declarations
        # No audit keyword: reconstructing a base cannot recursively audit itself.
        return extract_declarations(pages, source_doc_sha256=source,
                                    literal_recovery=literal_recovery, mixed_fields=True, pda_context=pda_context)
    except ImportError:
        raise MixedFieldAuditError('extraction_profile_unavailable') from None


def _request(pages, declarations, document_id, literal_recovery, pda_context):
    _need(type(literal_recovery) is bool, 'literal_recovery_contract')
    _need(type(pda_context) is bool, 'pda_context_contract')
    source = _validate_source(pages, document_id)
    profile = _profile(literal_recovery, pda_context)
    fresh = _fresh_base(pages, source, literal_recovery, pda_context)
    _need(isinstance(declarations, dict) and _same(declarations, fresh), 'base_output_mismatch')
    _need(fresh.get('source_doc_sha256') == fresh.get('extraction_sha256') == source,
          'source_binding_mismatch')
    if pda_context:
        pda = fresh.get('pda_context')
        _need(isinstance(pda, dict) and pda.get('version') == PDA_RECOVERY_VERSION
              and pda.get('enabled') is True, 'pda_recovery_contract')
    else:
        _need('pda_context' not in fresh, 'unexpected_pda_recovery')
    recovery = fresh.get('mixed_field_recovery')
    _need(isinstance(recovery, dict) and recovery.get('version') == RECOVERY_VERSION,
          'recovery_contract')
    rows = recovery.get('recoveries')
    _need(isinstance(rows, list), 'recovery_contract')
    proofs = {}
    for row in rows:
        _need(isinstance(row, dict) and _id(row.get('record_id'))
              and row['record_id'] not in proofs and row.get('method') == RECOVERY_VERSION,
              'recovery_identity')
        proofs[row['record_id']] = row
    records = fresh.get('records')
    _need(isinstance(records, list) and len(records) <= MAX_RECORDS, 'record_limit')
    profile_sha, base_sha = sha(canonical(profile)), sha(canonical(fresh))
    groups, route, seen, bound_seen = {}, [], set(), set()
    for record in records:
        _keys(record, {'id', 'kind', 'decision', 'reason', 'unit', 'evidence', 'claim'},
              'prior_record_contract')
        rid = record['id']
        _need(_id(rid) and rid not in seen, 'prior_record_identity')
        seen.add(rid)
        entry = {'prior_record_id': rid, 'eligible': False, 'reason': 'not_mixed_record'}
        route.append(entry)
        if not (record['kind'] is None and record['decision'] == 'abstained'
                and record['reason'] == 'combined_label' and record['claim'] is None):
            continue
        ev = record['evidence']
        _need(isinstance(ev, list), 'prior_evidence_contract')
        spans = [_source_ref(ref, pages, source) for ref in ev]
        labels = [s for ref, s in zip(ev, spans) if ref['role'] == 'label']
        values = [s for ref, s in zip(ev, spans) if ref['role'] == 'value']
        proof = proofs.get(rid)
        entry['reason'] = 'missing_complete_value'
        if (len(labels) != 1 or len(values) != 1 or proof is None
                or labels[0]['page_number'] != values[0]['page_number']
                or not values[0]['excerpt'].strip()):
            continue
        label, value = labels[0], values[0]
        _need(label['end'] <= value['start'], 'label_value_order')
        _need(proof.get('label_utf8_sha256') == sha(label['excerpt'].encode('utf-8'))
              and proof.get('value_utf8_sha256') == sha(value['excerpt'].encode('utf-8')),
              'recovery_hash_mismatch')
        boundary = proof.get('boundary')
        context = proof.get('context')
        _need(isinstance(boundary, dict) and boundary.get('role') == 'mixed_field_boundary'
              and isinstance(context, list)
              and all(isinstance(ref, dict) and ref.get('role') == 'mixed_field_context' for ref in context),
              'recovery_evidence_contract')
        support = spans + [_source_ref(ref, pages, source) for ref in [boundary, *context]]
        unit = record['unit']
        if unit is not None:
            _keys(unit, {'id', 'kind', 'anchor'}, 'prior_unit_contract')
            _need(_id(unit['id']) and unit['kind'] in {'session', 'project'}, 'prior_unit_contract')
            support.append(_source_ref(unit['anchor'], pages, source))
        p = value['page_number']
        supplied = {p-1, p} if p > 1 else {p}
        if any(s['page_number'] not in supplied for s in support):
            entry['reason'] = 'prior_evidence_outside_context'
            continue
        entry.update(eligible=True, reason='eligible_mixed_block')
        binding = sha(canonical({'contract_version': 'mixed-field-record-binding.v1',
                                'document_id': document_id, 'pages_sha256': source,
                                'extraction_profile_sha256': profile_sha, 'prior_record': record}))
        audit_id = 'mixed:' + binding
        _need(audit_id not in bound_seen, 'duplicate_record_binding')
        bound_seen.add(audit_id)
        groups.setdefault(p, []).append({'audit_record_id': audit_id,
                                         'record_binding_sha256': binding,
                                         'prior_record': copy.deepcopy(record),
                                         'label_span': label, 'immutable_value_span': value})
    _need(set(proofs) <= seen, 'orphan_recovery')
    packets = []
    for p in sorted(groups):
        numbers = [p-1, p] if p > 1 else [p]
        packet = {'contract_version': WIRE_VERSION, 'profile': 'partition_only',
                  'group_id': f'mixed:p{p}', 'document_id': document_id,
                  'pages_sha256': source, 'extraction_profile_sha256': profile_sha,
                  'base_output_sha256': base_sha, 'records': groups[p],
                  'context_pages': [{'page_number': n, 'text': pages[n-1]} for n in numbers],
                  'allowed_page_numbers': numbers, 'expansion_used': False, 'dictionary': None}
        _need(len(canonical(packet)) <= MAX_BYTES, 'packet_limit')
        packets.append(packet)
    return {'contract_version': REQUEST_VERSION, 'document_id': document_id,
            'pages': list(pages), 'pages_sha256': source, 'extraction_profile': profile,
            'base_output_sha256': base_sha, 'route': route, 'packets': packets}


def build_mixed_audit_request(*, pages, declarations, config):
    """Reconstruct the source route; raise sanitized validation errors on failure."""
    try:
        _need(isinstance(config, MixedFieldAuditConfig) and config.enabled is True,
              'enabled_config_required')
        return _request(pages, declarations, config.document_id, config.literal_recovery, config.pda_context)
    except MixedFieldAuditError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError, OSError, ImportError):
        raise MixedFieldAuditError('malformed_mixed_input') from None


def _validate_request(request):
    _keys(request, REQUEST_KEYS, 'request_contract')
    _need(request['contract_version'] == REQUEST_VERSION, 'request_version')
    profile = request['extraction_profile']
    _keys(profile, PROFILE_KEYS, 'profile_contract')
    _keys(profile['options'], {'literal_recovery', 'mixed_fields', 'pda_context'}, 'profile_options')
    _need(profile['options']['mixed_fields'] is True
          and type(profile['options']['literal_recovery']) is bool
          and type(profile['options']['pda_context']) is bool, 'profile_options')
    source = _validate_source(request['pages'], request['document_id'])
    expected_profile = _profile(profile['options']['literal_recovery'], profile['options']['pda_context'])
    _need(_same(profile, expected_profile), 'profile_binding_mismatch')
    fresh = _fresh_base(request['pages'], source, profile['options']['literal_recovery'],
                        profile['options']['pda_context'])
    expected = _request(request['pages'], fresh, request['document_id'],
                        profile['options']['literal_recovery'], profile['options']['pda_context'])
    _need(_same(request, expected), 'current_request_binding_mismatch')
    return expected


def _empty(status='invalid', request=None):
    verified = request is not None
    return {'version': VERSION, 'status': status,
            'pages_sha256': request['pages_sha256'] if verified else None,
            'extraction_profile_sha256': sha(canonical(request['extraction_profile'])) if verified else None,
            'base_output_sha256': request['base_output_sha256'] if verified else None,
            'route': copy.deepcopy(request['route']) if verified else [],
            'coverage': {'eligible_records': sum(row['eligible'] for row in request['route']) if verified else 0,
                         'expected_packets': len(request['packets']) if verified else 0,
                         'received_packets': 0, 'accepted_records': 0,
                         'typed_proposal_records': 0, 'explicit_abstention_records': 0},
            'results': [], 'errors': [], 'provider_attempts': 0, 'external_calls': 0,
            'semantic_validation': False, 'production_applied': False, 'claim_emitted': False}


def _validate_decision(decision, prior, pages, supplied):
    _keys(decision, DECISION_KEYS, 'decision_contract')
    _need(decision['audit_record_id'] == prior['audit_record_id']
          and decision['record_binding_sha256'] == prior['record_binding_sha256'], 'decision_binding')
    interpretation = decision['interpretation']
    _need(isinstance(interpretation, str) and interpretation in CLASS_STATUS
          and decision['status'] == CLASS_STATUS[interpretation], 'interpretation_status')
    _reason(decision['reason'])
    segments = decision['partition']
    _need(isinstance(segments, list) and 1 <= len(segments) <= MAX_SEGMENTS, 'partition_limit_or_type')
    whole = prior['immutable_value_span']
    cursor, typed, quotes = whole['start'], 0, []
    for segment in segments:
        _keys(segment, SEGMENT_KEYS, 'segment_contract')
        span = _span(segment['span'], pages, supplied)
        _need(span['page_number'] == whole['page_number'] and span['start'] == cursor
              and span['end'] <= whole['end'], 'partition_coverage')
        cursor = span['end']
        quotes.append(span['excerpt'])
        disposition = segment['disposition']
        _need(isinstance(disposition, str) and disposition in DISPOSITIONS, 'segment_disposition')
        _reason(segment['reason'])
        evidence = segment['evidence']
        _need(isinstance(evidence, list), 'support_contract')
        if disposition == 'typed_proposal':
            typed += 1
            _need(isinstance(segment['proposed_kind'], str)
                  and segment['proposed_kind'] in {'contenido', 'pda'}, 'typed_kind')
            basis = segment['basis']
            _need(isinstance(basis, str) and basis in BASIS_ROLE, 'typed_basis')
            _need(1 <= len(evidence) <= MAX_SUPPORTS, 'support_limit')
            ordered, substantive = [], False
            for support in evidence:
                _keys(support, {'role', 'span'}, 'support_contract')
                _need(isinstance(support['role'], str)
                      and support['role'] in {'semantic_context', 'structural_context'}, 'support_role')
                s = _span(support['span'], pages, supplied)
                ordered.append((s['page_number'], s['start'], s['end'], support['role']))
                if support['role'] == BASIS_ROLE[basis] and any(c.isalpha() or c.isnumeric() for c in s['excerpt']):
                    substantive = True
            _need(ordered == sorted(set(ordered)), 'support_order_or_duplicate')
            _need(substantive, 'insubstantial_type_support')
        else:
            _need(segment['proposed_kind'] is None and segment['basis'] == 'none'
                  and evidence == [], 'untyped_segment_contract')
            if disposition == 'formatting':
                _need(all(c in ' \t\r\n' for c in span['excerpt']), 'nonformatting_text')
    _need(cursor == whole['end'] and ''.join(quotes) == whole['excerpt'], 'partition_coverage')
    _need((typed > 0) == (interpretation == 'typed_partition_proposed'), 'typed_class_contradiction')


def _replay_validated(request, recordings):
    from scripts.replay_interpretation import ReplayError, decode_recorded_json
    expected = request['packets']
    _need(isinstance(recordings, (list, tuple)) and len(recordings) == len(expected)
          and len(recordings) <= MAX_PACKETS, 'recording_coverage')
    if not expected:
        return _empty('no_eligible_records', request)
    staged = []
    for packet, recording in zip(expected, recordings):
        _need(isinstance(recording, MixedFieldRecording), 'recording_contract')
        _need(_hash(recording.packet_sha256) and _hash(recording.response_sha256), 'recording_hash_contract')
        _need(_id(recording.model_as_recorded)
              and recording.request_hash_timing in {'pre_run_retained', 'post_run_verification'}, 'recording_metadata')
        try:
            decoded_packet, _ = decode_recorded_json(recording.packet_bytes, recording.packet_sha256,
                                                     allow_fence=False, max_bytes=MAX_BYTES)
            response, transport = decode_recorded_json(recording.response_bytes, recording.response_sha256,
                                                           allow_fence=True, max_bytes=MAX_BYTES)
        except ReplayError as error:
            raise MixedFieldAuditError(str(error)) from None
        _need(recording.packet_bytes == canonical(packet) and _same(decoded_packet, packet), 'packet_binding_mismatch')
        _keys(response, RESPONSE_KEYS, 'response_contract')
        _need(response['contract_version'] == WIRE_VERSION and response['group_id'] == packet['group_id']
              and response['packet_sha256'] == recording.packet_sha256, 'response_binding')
        _need(response['action'] == 'report' and response['requested_pages'] == [], 'expansion_or_action')
        _reason(response['reason'])
        decisions = response['record_decisions']
        _need(isinstance(decisions, list) and len(decisions) == len(packet['records']), 'decision_coverage')
        for decision, prior in zip(decisions, packet['records']):
            _validate_decision(decision, prior, request['pages'], set(packet['allowed_page_numbers']))
            identity = {'audit_record_id': prior['audit_record_id'], 'packet_sha256': recording.packet_sha256,
                        'response_sha256': recording.response_sha256, 'decision': decision}
            staged.append({'proposal_id': 'mixed-result:' + sha(canonical(identity)),
                           'audit_record_id': prior['audit_record_id'],
                           'record_binding_sha256': prior['record_binding_sha256'],
                           'prior_record': copy.deepcopy(prior['prior_record']),
                           'immutable_value_span': copy.deepcopy(prior['immutable_value_span']),
                           'prior_unit': copy.deepcopy(prior['prior_record']['unit']),
                           'unit_policy': 'preserve_prior_metadata_only', 'decision': copy.deepcopy(decision),
                           'state': 'needs_human_review', 'transport_status': 'accepted',
                           'semantic_validation': False, 'production_applied': False, 'claim_emitted': False,
                           'receipt': {'packet_sha256': recording.packet_sha256,
                                       'response_sha256': recording.response_sha256,
                                       'model_as_recorded': recording.model_as_recorded,
                                       'request_hash_timing': recording.request_hash_timing,
                                       'normalization': transport['response_normalization']}})
    result = _empty('review_only_results', request)
    result['results'] = staged
    result['coverage'].update(received_packets=len(recordings), accepted_records=len(staged),
                              typed_proposal_records=sum(r['decision']['status'] == 'proposed' for r in staged),
                              explicit_abstention_records=sum(r['decision']['status'] == 'abstained' for r in staged))
    return result


def _failure(error, request=None, attempts=0, recordings=None):
    result = _empty(request=request)
    result['provider_attempts'] = attempts
    result['coverage']['received_packets'] = (len(recordings) if request is not None
                                               and isinstance(recordings, (tuple, list)) else 0)
    result['errors'] = [str(error) if isinstance(error, MixedFieldAuditError) else 'malformed_mixed_input']
    return result


def replay_mixed_field_audit(*, request, recordings):
    """Public replay independently reconstructs all trusted source/profile inputs."""
    verified = None
    try:
        verified = _validate_request(request)
        return _replay_validated(verified, recordings)
    except (MixedFieldAuditError, ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError, OSError, ImportError) as error:
        return _failure(error, verified, recordings=recordings)


def audit_mixed_fields(*, pages, declarations, config):
    """Produce only an atomic review sidecar; preserve all caller input objects."""
    verified, attempts, recordings = None, 0, None
    try:
        verified = build_mixed_audit_request(pages=pages, declarations=declarations, config=config)
        if not verified['packets']:
            return _empty('no_eligible_records', verified)
        try:
            provider_kind = getattr(config.provider, 'kind', None)
        except Exception:
            raise MixedFieldAuditError('provider_failure') from None
        _need(isinstance(provider_kind, str) and provider_kind in {'synthetic_test', 'recorded_replay'},
              'external_provider_blocked')
        attempts = 1
        try:
            recordings = config.provider.propose(tuple(copy.deepcopy(verified['packets'])))
        except Exception:
            raise MixedFieldAuditError('provider_failure') from None
        result = _replay_validated(verified, recordings)
        result['provider_attempts'] = attempts
        return result
    except (MixedFieldAuditError, ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError, OSError, ImportError) as error:
        return _failure(error, verified, attempts, recordings)
