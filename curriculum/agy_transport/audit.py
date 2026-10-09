"""Offline reconciliation of AGY stream-json v1 observations; never invokes AGY.

Transport completion, exact reported usage and reconciled accounting are distinct.
This validates the known envelope, not response semantics or provider billing.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path
import re

from .artifact_io import commit_json

SCHEMA = 'agy.capture-receipt.v3'
PERMISSION = re.compile(r'permission[ _-]?denied|access[ _-]?denied|authorization[ _-]?denied|not[ _-]?authorized|approval[ _-]?required|permission[ _-]?required|authorization[ _-]?required|permission[ _-]?(?:request|prompt)|approval[ _-]?(?:request|pending)|unauthorized|forbidden', re.I)
PRINT_TIMEOUT = re.compile(r'\[agy\]\s*print\s+time(?:out|d\s+out)\b', re.I)
PARTIAL_OUTPUT = re.compile(r'\[agy\][^\r\n]{0,512}(?:turn\s+in\s+progress|returning\s+partial\s+output)', re.I)
USAGE_FIELDS = ('input_tokens', 'output_tokens', 'total_tokens')
OPTIONAL_USAGE_FIELDS = ('thinking_tokens', 'cache_read_tokens')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate_json_key:' + key)
            result[key] = value
        return result
    def bad_constant(value):
        raise ValueError('non_json_constant:' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def tool_or_permission(event):
    """Init catalogues describe availability; step/call events imply activity."""
    actual, denied = [], []
    is_init = event.get('event', event.get('type')) == 'init' or (
        event.get('event', event.get('type')) == 'system' and event.get('subtype') == 'init')
    def visit(value, path='$'):
        if isinstance(value, dict):
            for key, item in value.items():
                location = path + '.' + key
                if is_init and path in {'$', '$.init'} and key in {
                    'tools', 'available_tools', 'tool_definitions', 'tool_catalog', 'catalog'}:
                    continue
                if key in {'event', 'type', 'subtype', 'event_type', 'step_type'} and isinstance(item, str):
                    kind = item.lower().replace('-', '_')
                    if ('tool' in kind and not any(x in kind for x in ('catalog', 'available', 'definition'))) or kind in {
                        'function_call', 'function_result', 'function_response', 'functioncall', 'functionresponse',
                        'subagent', 'subagent_call', 'invoke_subagent'}:
                        actual.append({'path': location, 'value': item})
                if key in {'tool_calls', 'tool_call', 'tool_name', 'tool_info', 'subagent_info',
                           'function_call', 'functionCall', 'functionResponse', 'function_response'} and item:
                    actual.append({'path': location, 'value': item})
                if key in {'status', 'error', 'code', 'type', 'event', 'message', 'detail'} and isinstance(item, str) and PERMISSION.search(item):
                    denied.append({'path': location, 'value': item})
                visit(item, location)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, path + '[' + str(index) + ']')
    visit(event)
    return actual, denied


def usage_receipts(event, line_number):
    found = []
    if event.get('event', event.get('type')) in {'usage', 'token_usage', 'tokenUsage', 'usageMetadata'}:
        found.append({'line_number': line_number, 'path': '$', 'reported': event})
    def visit(value, path='$'):
        if isinstance(value, dict):
            for key, item in value.items():
                location = path + '.' + key
                if key in {'usage', 'token_usage', 'tokenUsage', 'usageMetadata'}:
                    found.append({'line_number': line_number, 'path': location, 'reported': item})
                else:
                    visit(item, location)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, path + '[' + str(index) + ']')
    visit(event)
    return found


def usage_is_valid(value):
    return (isinstance(value, dict)
            and all(type(value.get(key)) is int and value[key] >= 0 for key in USAGE_FIELDS)
            and all(type(value[key]) is int and value[key] >= 0
                    for key in OPTIONAL_USAGE_FIELDS if key in value))


class StreamAudit:
    def __init__(self, max_response_bytes, on_guard=None, detector=None):
        self.max_response_bytes = max_response_bytes
        self.on_guard = on_guard
        self.detector = detector
        self.guards, self.results, self.usages = [], [], []
        self.tools, self.inits, self.parse_errors = [], [], []
        self.counts = collections.Counter()
        self.line_number = 0
        self.stdout_buffer = b''
        self.stderr_tail = b''
        self.response_delta_bytes = 0
        self.stdout_finished = False
        self.received_bytes = {'stdout': 0, 'stderr': 0}
        self.hashers = {key: hashlib.sha256() for key in self.received_bytes}

    def integrity_metadata(self):
        return {'captured_bytes': dict(self.received_bytes),
                'capture_sha256': {key: value.hexdigest() for key, value in self.hashers.items()}}

    def guard(self, reason):
        if reason not in self.guards:
            self.guards.append(reason)
            if self.on_guard:
                self.on_guard(reason)

    def feed_stdout(self, chunk):
        if self.stdout_finished:
            raise ValueError('stdout_already_finished')
        self.received_bytes['stdout'] += len(chunk)
        self.hashers['stdout'].update(chunk)
        self.stdout_buffer += chunk
        while b'\n' in self.stdout_buffer:
            line, self.stdout_buffer = self.stdout_buffer.split(b'\n', 1)
            self.handle(line + b'\n')

    def finish_stdout(self):
        if not self.stdout_finished and self.stdout_buffer:
            self.handle(self.stdout_buffer)
            self.stdout_buffer = b''
        self.stdout_finished = True

    def feed_stderr(self, chunk):
        self.received_bytes['stderr'] += len(chunk)
        self.hashers['stderr'].update(chunk)
        # Scan the complete new chunk with overlap before retaining its tail.
        # A diagnostic followed by >8192 bytes in one read must not be lost.
        text = (self.stderr_tail + chunk).decode('utf-8', errors='replace')
        if PRINT_TIMEOUT.search(text):
            self.guard('provider_print_timeout')
        elif PARTIAL_OUTPUT.search(text):
            self.guard('provider_partial_output')
        if PERMISSION.search(text):
            self.guard('permission_or_authorization_block')
        self.stderr_tail = (self.stderr_tail + chunk)[-8192:]

    def handle(self, line):
        if not line.strip():
            return
        self.line_number += 1
        if self.results:
            self.guard('event_after_result')
        try:
            event = strict_json(line)
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            self.parse_errors.append({'line_number': self.line_number, 'error': type(exc).__name__ + ':' + str(exc)})
            self.guard('invalid_ndjson')
            return
        if not isinstance(event, dict):
            self.guard('non_object_ndjson')
            return
        name = event.get('event', event.get('type', '<missing>'))
        self.counts[str(name)] += 1
        if not isinstance(name, str):
            self.guard('invalid_event_type')
            return
        if 'event' in event and 'type' in event and event['event'] != event['type']:
            self.guard('contradictory_event_type')
        if name not in {'init', 'step_update', 'result', 'error', 'usage', 'token_usage',
                        'tokenUsage', 'usageMetadata'} and not (name == 'system' and event.get('subtype') == 'init'):
            self.guard('unknown_event_schema')
        if name == 'init' or (name == 'system' and event.get('subtype') == 'init'):
            self.inits.append({'line_number': self.line_number, 'event': event})
        actual, denied = tool_or_permission(event)
        if self.detector:
            extra_actual, extra_denied = self.detector(event)
            actual.extend(extra_actual)
            denied.extend(extra_denied)
        if actual:
            self.tools.append({'line_number': self.line_number, 'event': event, 'detected': actual})
            self.guard('actual_tool_event')
        if denied:
            self.guard('permission_or_authorization_block')
        if 'error' in (event.get('event'), event.get('type'), event.get('subtype')) or event.get('is_error') is True:
            self.guard('error_event')
        step = event.get('step_update')
        if name == 'step_update':
            if not isinstance(step, dict):
                self.guard('invalid_step_envelope')
            elif step.get('step_type') not in ('user_input', 'agent_response'):
                self.guard('unsupported_step_type')
        if isinstance(step, dict) and isinstance(step.get('state'), str) and step['state'] in {'ERROR', 'FAILED', 'CANCELLED', 'CANCELED', 'TIMEOUT'}:
            self.guard('failed_step_event')
        if isinstance(step, dict) and step.get('step_type') == 'agent_response' and isinstance(step.get('text_delta'), str):
            try:
                self.response_delta_bytes += len(step['text_delta'].encode('utf-8'))
            except UnicodeEncodeError:
                self.guard('invalid_response_unicode')
            if self.response_delta_bytes > self.max_response_bytes:
                self.guard('streamed_response_byte_limit')
        self.usages.extend(usage_receipts(event, self.line_number))
        if name == 'result':
            self.results.append({'line_number': self.line_number, 'event': event, 'raw': line})
            result = event.get('result')
            if not isinstance(result, dict) or result.get('status') != 'SUCCESS':
                self.guard('non_success_result')
            if not isinstance(result, dict) or type(result.get('num_turns')) is not int or result['num_turns'] != 1:
                self.guard('unexpected_internal_turn_count')

    def finalize(self, metadata):
        self.finish_stdout()
        for reason in metadata.get('guard_reasons', []):
            self.guard(reason)
        if metadata.get('incomplete_reason'):
            self.guard(metadata['incomplete_reason'])
        if not self.guards and (metadata.get('execution_status') == 'incomplete'
                                or metadata.get('terminal_result_valid') is False):
            self.guard('prior_incomplete_execution')
        if not self.guards and metadata.get('stop_all_calls') is True and metadata.get('accounting_status') != 'unresolved':
            self.guard('prior_stop_all_calls')
        if type(metadata.get('exit_code')) is not int or metadata['exit_code'] != 0:
            self.guard('nonzero_or_unknown_exit')
        if metadata.get('child_reaped') is not True:
            self.guard('child_not_confirmed_reaped')
        truncation = metadata.get('capture_truncated', {})
        if any(truncation.values()):
            self.guard('capture_truncated')
        if any(truncation.get(key) is not False for key in ('stdout', 'stderr')):
            self.guard('capture_integrity_unverified')
        if any(metadata.get('stream_eof', {}).get(key) is not True for key in ('stdout', 'stderr')):
            self.guard('stream_eof_unverified')
        for key in ('stdout', 'stderr'):
            captured = metadata.get('captured_bytes', {}).get(key)
            observed = metadata.get('observed_bytes', {}).get(key)
            digest = metadata.get('capture_sha256', {}).get(key)
            if type(captured) is not int or type(observed) is not int or not isinstance(digest, str):
                self.guard('stream_integrity_unverified')
            else:
                if captured != self.received_bytes[key] or digest != self.hashers[key].hexdigest():
                    self.guard('stream_integrity_mismatch')
                if observed < captured or captured < 0 or (observed > captured) != truncation.get(key):
                    self.guard('capture_metadata_contradiction')
        if metadata.get('cleanup_errors') or metadata.get('artifact_errors'):
            self.guard('capture_or_cleanup_error')
        response = None
        result = self.results[0]['event'].get('result') if len(self.results) == 1 else None
        if len(self.results) != 1:
            self.guard('missing_or_ambiguous_result_event')
        if isinstance(result, dict) and isinstance(result.get('response'), str):
            try:
                response = result['response'].encode('utf-8', errors='strict')
            except UnicodeEncodeError:
                self.guard('invalid_response_unicode')
            if not result['response'].strip():
                self.guard('empty_response')
            if response is not None and len(response) > self.max_response_bytes:
                self.guard('final_response_byte_limit')
        else:
            self.guard('missing_string_response')
        reported = result.get('usage') if isinstance(result, dict) else None
        valid_usage = usage_is_valid(reported)
        complete = not self.guards and response is not None
        accounting_reasons = []
        if not complete:
            accounting_reasons.append('execution_incomplete')
        if not valid_usage:
            accounting_reasons.append('missing_or_invalid_terminal_usage')
        elif reported['total_tokens'] == 0:
            accounting_reasons.append('zero_terminal_usage_unreconciled')
        if not accounting_reasons and (metadata.get('accounting_status') == 'unresolved'
                                       or metadata.get('usage_complete') is False
                                       or metadata.get('consumption_status') == 'unknown'):
            accounting_reasons.append('prior_accounting_unresolved')
        reconciled = complete and not accounting_reasons
        primary = next((reason for reason in ('provider_print_timeout', 'provider_partial_output',
                                              'capture_truncated') if reason in self.guards),
                       self.guards[0] if self.guards else None)
        receipt = dict(metadata)
        # Deliberately no legacy result_usage_exact alias: old callers must migrate.
        receipt.pop('result_usage_exact', None)
        receipt.update({
            'schema': SCHEMA, 'audit_version': 3,
            'execution_status': 'complete' if complete else 'incomplete',
            'incomplete_reason': primary,
            'terminal_result_valid': complete,
            'response_eligible_for_interpretation': complete and reconciled,
            'semantic_evaluation': False,
            'guard_reasons': list(self.guards),
            'stop_all_calls': not (complete and reconciled),
            'event_type_counts': dict(self.counts), 'init_catalog_events': len(self.inits),
            'actual_tool_events': len(self.tools),
            'usage_receipt_available': bool(self.usages),
            'reported_result_usage_exact': reported,
            'reported_terminal_usage_schema_valid': valid_usage,
            'usage_complete': reconciled,
            'accounting_status': 'reconciled_reported_usage' if reconciled else 'unresolved',
            'accounting_unresolved_reasons': accounting_reasons,
            'reconciled_usage_exact': reported if reconciled else None,
            'consumption_status': 'reported_complete' if reconciled else 'unknown',
            'real_cost_currency': None, 'zero_cost_established': False,
            'response_bytes_reported': len(response) if response is not None else None,
            'response_sha256': sha(response) if response is not None else None,
            'automatic_retries': 0,
            'automatic_retries_scope': 'wrapper_process_relaunches',
            'transport_internal_retries': None,
            'provider_dispatch_count': None,
        })
        return receipt, response if receipt['response_eligible_for_interpretation'] else None


def audit_streams(stdout, stderr, metadata, max_response_bytes=262272):
    audit = StreamAudit(max_response_bytes)
    audit.feed_stdout(stdout)
    audit.feed_stderr(stderr)
    return audit.finalize(metadata)[0]


def summarize_receipts(receipts):
    """No cumulative/intermediate usage summing; every admitted attempt counts."""
    if any(item.get('schema') != SCHEMA for item in receipts):
        raise ValueError('v3_receipts_required')
    reported = [r['reported_result_usage_exact'] for r in receipts
                if r['reported_terminal_usage_schema_valid']]
    reconciled = [r['reconciled_usage_exact'] for r in receipts if r['usage_complete']]
    unresolved = len(receipts) - len(reconciled)
    return {'attempt_count': len(receipts),
            'completed_attempt_count': sum(r['terminal_result_valid'] for r in receipts),
            'reported_terminal_usage_attempt_count': len(reported),
            'reported_total_tokens_sum': sum(u['total_tokens'] for u in reported),
            'reconciled_usage_attempt_count': len(reconciled),
            'reconciled_total_tokens_known_part': sum(u['total_tokens'] for u in reconciled),
            'unresolved_consumption_attempt_count': unresolved,
            'reconciled_total_tokens': None if unresolved else sum(u['total_tokens'] for u in reconciled),
            'real_cost_currency': None, 'zero_cost_established': False}


def audit_existing_attempt(source, output, max_response_bytes=262272):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or output.is_relative_to(source):
        raise ValueError('derived_output_must_be_outside_original_attempt')
    files = {}
    for name in ('stdout.ndjson', 'stderr.log', 'receipt.json'):
        path = source / name
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('audit_input_too_large:' + name)
        files[name] = path.read_bytes()
    metadata = strict_json(files['receipt.json'])
    if not isinstance(metadata, dict):
        raise ValueError('receipt_not_object')
    result = audit_streams(files['stdout.ndjson'], files['stderr.log'], metadata, max_response_bytes)
    result['audit_provenance'] = {
        'derived_only': True, 'external_calls': 0, 'source_directory': str(source),
        'inputs': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in files.items()}}
    output.mkdir(parents=True, exist_ok=False)
    commit_json(output / 'derived_receipt.json', result)
    commit_json(output / 'accounting_summary.json', summarize_receipts([result]))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--max-response-bytes', type=int, default=262272)
    args = parser.parse_args()
    if args.max_response_bytes <= 0:
        parser.error('--max-response-bytes must be positive')
    result = audit_existing_attempt(args.attempt_dir, args.output_dir, args.max_response_bytes)
    print(json.dumps({key: result[key] for key in (
        'execution_status', 'incomplete_reason', 'accounting_status', 'usage_complete',
        'terminal_result_valid', 'response_eligible_for_interpretation')}))
