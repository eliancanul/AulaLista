#!/usr/bin/env python3
"""Offline replay of recorded interpretation experiments, never production apply.

No network, provider SDK, product interpreter or database imports. Validates the
saved source/transport and literal provenance only, not semantic correctness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

VERSION = 'recorded-interpretation.v2'
MAX_CHARACTERS = 2_000_000
MAX_PROPOSALS = 2_000


class ReplayError(ValueError):
    """Sanitized error code; never includes source text or provider output."""


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def source_digest(pages):
    """Hash of exact extracted page strings, not the bytes of a PDF."""
    return digest(json.dumps(pages, ensure_ascii=False, separators=(',', ':')))


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReplayError('duplicate_json_key')
        result[key] = value
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ReplayError('nonfinite_json')))
    except (ValueError, TypeError, RecursionError) as error:
        if isinstance(error, ReplayError):
            raise
        raise ReplayError('invalid_json') from None


def _check(condition, code):
    if not condition:
        raise ReplayError(code)


def _line_span(pages, page, first, last):
    _check(type(page) is int and 1 <= page <= len(pages), 'invalid_page')
    lines = pages[page - 1].splitlines(keepends=True)
    _check(type(first) is int and type(last) is int and 1 <= first <= last <= len(lines), 'invalid_lines')
    start, end = sum(map(len, lines[:first - 1])), sum(map(len, lines[:last]))
    text = pages[page - 1]
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    _check(start < end, 'empty_evidence')
    return dict(page=page, start=start, end=end, quote=text[start:end])


def _quote_span(pages, page, quote, *, within=None):
    _check(type(page) is int and 1 <= page <= len(pages), 'invalid_page')
    _check(isinstance(quote, str) and bool(quote.strip()), 'empty_evidence')
    text = pages[page - 1]
    _check(quote in text, 'quote_not_in_source')
    low, high = 0, len(text)
    if within is not None:
        _check(page == within['page'], 'mention_outside_activity')
        low, high = within['start'], within['end']
    start = text.find(quote, low, high)
    _check(start >= 0, 'mention_outside_activity' if within is not None else 'quote_not_in_source')
    _check(text.find(quote, start + 1, high) < 0, 'ambiguous_quote')
    return dict(page=page, start=start, end=start + len(quote), quote=quote)


def _has_explicit_number(pages, span, number):
    """Check literal label/number provenance, not anaphora or resource necessity.

    This narrow recorded-response contract is independent of product matching.
    Check boundaries in the source too: a cropped `anexo 1` in `anexo 12`
    cannot attest the number 1, nor can `preanexo 1` attest an annex label.
    """
    page = pages[span['page'] - 1]
    pattern = re.compile(r'(?<!\w)anexos?\s+([0-9]+(?:(?:\s*,\s*|\s+(?:y|e)\s+|\s*&\s*)[0-9]+)*)(?!\w|[.:/\-][0-9])', re.I)
    for match in pattern.finditer(page):
        if span['start'] <= match.start() and match.end() <= span['end']:
            # Strip leading zeros without arbitrary-length integer conversion.
            values = {value.lstrip('0') or '0' for value in re.findall(r'[0-9]+', match.group(1))}
            if str(number) in values:
                return True
    return False


def _session(pages, row):
    _check(isinstance(row, dict) and set(row) == {
        'activity_page', 'activity_start_line', 'activity_end_line',
        'session_page', 'session_line', 'abstained'}, 'session_contract')
    _check(type(row['abstained']) is bool, 'invalid_abstention')
    activity = _line_span(pages, row['activity_page'], row['activity_start_line'], row['activity_end_line'])
    if row['abstained']:
        _check(row['session_page'] is None and row['session_line'] is None, 'abstention_with_target')
        context = []
    else:
        context = [_line_span(pages, row['session_page'], row['session_line'], row['session_line'])]
    return dict(predicate='pertenece_a_sesion', activity=activity,
                target=context[0] if context else None, evidence=[activity], context=context,
                basis='abstained' if row['abstained'] else 'explicit_assignment_as_recorded',
                abstained=row['abstained'])


def _annex(pages, row):
    _check(isinstance(row, dict) and set(row) == {
        'activity_page', 'activity_start_line', 'activity_end_line', 'annex_number',
        'basis', 'mention_page', 'mention_quote', 'antecedent_page', 'antecedent_quote', 'abstained'}, 'annex_contract')
    _check(type(row['abstained']) is bool, 'invalid_abstention')
    _check(isinstance(row['basis'], str) and row['basis'] in {'explicit_number', 'contextual_anaphora', 'uncertain'}, 'invalid_basis')
    activity = _line_span(pages, row['activity_page'], row['activity_start_line'], row['activity_end_line'])
    mention = _quote_span(pages, row['mention_page'], row['mention_quote'], within=activity)
    _check(mention['page'] == activity['page'] and activity['start'] <= mention['start'] < mention['end'] <= activity['end'], 'mention_outside_activity')
    if row['abstained']:
        _check(row['annex_number'] is None and row['basis'] == 'uncertain', 'abstention_with_target')
    else:
        _check(type(row['annex_number']) is int and row['annex_number'] >= 0
               and row['basis'] != 'uncertain', 'invalid_annex_number')
    if row['basis'] == 'contextual_anaphora':
        context = [_quote_span(pages, row['antecedent_page'], row['antecedent_quote'])]
        antecedent = context[0]
        _check((antecedent['page'], antecedent['end']) <= (mention['page'], mention['start']), 'antecedent_not_prior')
        _check(_has_explicit_number(pages, antecedent, row['annex_number']), 'antecedent_number_mismatch')
    else:
        _check(row['antecedent_page'] is None and row['antecedent_quote'] is None, 'unexpected_antecedent')
        context = []
        if row['basis'] == 'explicit_number':
            _check(_has_explicit_number(pages, mention, row['annex_number']), 'mention_number_mismatch')
    return dict(predicate='requiere_anexo', activity=activity, target=row['annex_number'],
                evidence=[mention], context=context, basis=row['basis'], abstained=row['abstained'],
                physical_sheet_resolved=False, necessity_validated=False)


def replay(*, kind, document_id, pages, source_sha256, request_text,
           request_sha256, request_hash_timing, stream_text, stream_sha256, model):
    """Return detached, review-only proposals or reject the whole saved response.

    Hashes bind this replay to exact saved inputs. They do not retroactively prove
    a pre-run freeze; request_hash_timing must come from the original protocol.
    """
    _check(isinstance(kind, str) and kind in {'activity_session', 'activity_annex'}, 'unsupported_kind')
    _check(isinstance(document_id, str) and bool(document_id.strip()), 'invalid_document_id')
    _check(isinstance(model, str) and bool(model.strip()), 'invalid_model')
    _check(isinstance(pages, list) and bool(pages) and all(isinstance(p, str) for p in pages), 'invalid_pages')
    _check(isinstance(request_text, str) and isinstance(stream_text, str), 'invalid_transport')
    _check(sum(map(len, pages)) + len(request_text) + len(stream_text) <= MAX_CHARACTERS, 'input_limit')
    _check(source_digest(pages) == source_sha256, 'source_hash_mismatch')
    _check(digest(request_text) == request_sha256, 'request_hash_mismatch')
    _check(digest(stream_text) == stream_sha256, 'stream_hash_mismatch')
    _check(isinstance(request_hash_timing, str) and request_hash_timing in {'pre_run_protocol', 'post_run_verification'}, 'invalid_hash_timing')
    marker = '\nDOCUMENT:\n' if kind == 'activity_session' else 'Sources:\n'
    _check(marker in request_text, 'missing_request_source')
    sent_source = _json(request_text.rsplit(marker, 1)[1])
    expected_source = {'id': document_id, 'pages': [
        {'page': i + 1, 'lines': [{'line': j + 1, 'text': line}
                                for j, line in enumerate(page.splitlines())]}
        for i, page in enumerate(pages)]}
    _check(json.dumps(sent_source, sort_keys=True) == json.dumps(expected_source, sort_keys=True), 'request_source_mismatch')
    events = [_json(line) for line in stream_text.splitlines() if line.strip()]
    _check(all(isinstance(event, dict) for event in events), 'invalid_event')
    results = []
    for event in events:
        if event.get('event') == 'step_update':
            step = event.get('step_update')
            _check(isinstance(step, dict) and isinstance(step.get('step_type'), str) and step.get('step_type') in {'user_input', 'agent_response'}, 'unexpected_tool_step')
        if event.get('event') == 'result':
            results.append(event.get('result'))
    _check(len(results) == 1 and isinstance(results[0], dict), 'missing_or_multiple_results')
    result = results[0]
    _check(result.get('status') == 'SUCCESS' and isinstance(result.get('response'), str), 'unsuccessful_recording')
    raw_response = result['response']
    response = raw_response.strip()
    normalization = None
    if response.startswith('```json') and response.endswith('```') and response.count('```') == 2:
        response = response[7:-3].strip()
        normalization = 'single_outer_json_fence'
    payload = _json(response)
    key = 'relations' if kind == 'activity_session' else 'references'
    _check(isinstance(payload, dict) and set(payload) == {'id', key} and payload['id'] == document_id, 'response_contract')
    _check(isinstance(payload[key], list) and len(payload[key]) <= MAX_PROPOSALS, 'proposal_limit_or_type')
    parser = _session if kind == 'activity_session' else _annex
    proposals, seen = [], set()
    for index, row in enumerate(payload[key]):
        proposal = parser(pages, row)
        activity = proposal['activity']
        identity = (activity['page'], activity['start'], activity['end'])
        if kind == 'activity_annex':
            identity += (proposal['target'],)
        _check(identity not in seen, 'duplicate_proposal')
        seen.add(identity)
        proposal.update(id=f'{document_id}:recorded:{index}', state='insufficient_evidence' if proposal['abstained'] else 'needs_human_review',
                        source_sha256=source_sha256, provenance_validation='literal_only_not_semantic')
        proposals.append(proposal)
    return dict(version=VERSION, status='replayed_for_review', kind=kind,
                document_id=document_id, source_kind='exact_extracted_page_snapshot_not_pdf_bytes',
                source_sha256=source_sha256, request_sha256=request_sha256,
                request_hash_timing=request_hash_timing, recorded_stream_sha256=stream_sha256,
                recording_hash_timing='post_run_verification',
                raw_response_sha256=digest(raw_response), model_as_recorded=model,
                response_normalization=normalization, external_calls=0, production_applied=False,
                semantic_validation=False, proposals=proposals)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='JSON with id and exact extracted pages only')
    parser.add_argument('--kind', choices=['activity_session', 'activity_annex'], required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--request-hash-timing', choices=['pre_run_protocol', 'post_run_verification'], required=True)
    parser.add_argument('--stream', type=Path, required=True)
    parser.add_argument('--stream-sha256', required=True, help='Expected hash of saved stream, independently retained for this replay')
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', type=Path, required=True, help='New PRIVATE replay file, never a public corpus export')
    args = parser.parse_args()
    try:
        for path in [args.source, args.request, args.stream]:
            _check(path.stat().st_size <= 4 * MAX_CHARACTERS, 'file_limit')
        source = _json(args.source.read_text(encoding='utf-8'))
        _check(isinstance(source, dict) and set(source) == {'id', 'pages'}, 'source_contract')
        result = replay(kind=args.kind, document_id=source['id'], pages=source['pages'], source_sha256=args.source_sha256,
                        request_text=args.request.read_bytes().decode('utf-8'), request_sha256=args.request_sha256,
                        request_hash_timing=args.request_hash_timing, stream_text=args.stream.read_bytes().decode('utf-8'), stream_sha256=args.stream_sha256, model=args.model)
        # Exclusive creation preserves existing recordings and primary reports.
        with args.output.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    except (ReplayError, OSError, UnicodeError) as error:
        parser.exit(2, f'Replay rejected: {error if isinstance(error, ReplayError) else "file_io_error"}\n')
    print(json.dumps({'status': result['status'], 'proposals': len(result['proposals']), 'external_calls': 0, 'production_applied': False}))


if __name__ == '__main__':
    main()
