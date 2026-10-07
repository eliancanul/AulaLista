"""Offline preparation/scoring for explicit teacher-review A/B runs.

This tool NEVER invokes a model, opens authentication, or grants a run budget.
Preparation is a fixed historical-context panel, not a simulated live journey.
Scoring counts terminal tokens for the complete supplied journey, including all
its attempts; missing/unknown accounting is inconclusive, not zero usage.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from curriculum.teacher_review_context import canonical_context_bytes, encode_provider_context, provider_context_instructions
from curriculum.teacher_review_task_context import TASK_SYSTEM, build_task_context
from curriculum.teacher_review_provider import SYSTEM, RESPONSE_SCHEMA
from curriculum.teacher_review_questions import question_policy


def raw(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def prepare(evidence, output):
    from scripts.audit_teacher_context import audit
    # The predecessor auditor verifies export inventory, original request hashes,
    # full context restoration and PDF identity before any candidate preparation.
    verified = audit(evidence, output / 'verified-historical-input')
    rows = []
    for row in verified['calls']:
        number = row['call']
        context_path = evidence / f'live-study/context-{number}.json'
        data = context_path.read_bytes()
        identity = verified['verified_input_files'][f'live-study/context-{number}.json']
        if len(data) != identity['bytes'] or digest(data) != identity['sha256']:
            raise ValueError('context_changed_after_verification')
        context = json.loads(data)
        context['question_policy'] = question_policy(context['all_targets'])
        if not context['question_policy']['candidate_target_ids']:
            context['questions_remaining'] = 0
        for mode in ('complete', 'semantic-v1'):
            if mode == 'semantic-v1':
                system, encoded = TASK_SYSTEM, build_task_context(context)
            else:
                encoded = encode_provider_context(context)
                system = SYSTEM + provider_context_instructions(encoded)
            request = {'protocol': 'aulalista.pi-text.v1', 'system': system,
                       'prompt': 'Devuelve únicamente JSON según este esquema:\n' + raw(RESPONSE_SCHEMA).decode()
                                 + '\nDATOS:\n' + raw(encoded).decode(), 'timeout_ms': 30000}
            path = output / 'fixed-panel' / f'request-{number}-{mode}.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw(request))
            rows.append({'call': number, 'mode': mode, 'request_path': str(path.relative_to(output)),
                         'request_bytes': path.stat().st_size, 'request_sha256': digest(path.read_bytes()),
                         'full_context_sha256': digest(canonical_context_bytes(context)),
                         'source_document_sha256': digest(canonical_context_bytes(context['source_document'])),
                         'source_literal_exact': encoded['source_document'] == context['source_document'],
                         'context_bytes': len(raw(encoded))})
    report = {'scope': 'Fixed-panel offline bytes, not total live journey tokens or model quality.',
              'historical_baseline_total_tokens': 67743, 'target_total_tokens_at_most': 20322,
              'token_savings_measured': None, 'calls_are_not_new_provider_calls': True,
              'rows': rows, 'totals_request_bytes': {mode: sum(x['request_bytes'] for x in rows if x['mode'] == mode)
                                                   for mode in ('complete', 'semantic-v1')}}
    (output / 'preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def semantic_outcome(dossier):
    # Times/version/audit/UI prose can differ with call count; every actual value,
    # origin, uncertainty, reference and association remains compared exactly.
    result = copy.deepcopy(dossier)
    for key in ('history', 'version', 'created_at', 'updated_at', 'source_name'):
        result.pop(key, None)
    if isinstance(result.get('verification_report'), dict):
        result['verification_report'].pop('dossier_version', None)
    def field(value):
        return {key: copy.deepcopy(child) for key, child in value.items()
                if key not in ('action_required', 'current_action')}
    result['general_fields'] = {name: field(value) for name, value in result['general_fields'].items()}
    for session in result['sessions']:
        session['fields'] = {name: field(value) for name, value in session['fields'].items()}
        session['annex_references'] = [field(value) for value in session.get('annex_references', [])]
    return result


def _answer_scope(run):
    """This frozen case permits only bank values, optionally labelled by target.

    Preserve raw responses in their original files; this check only establishes
    that no extra human facts were introduced to make a smaller run easier.
    An unknown/free-form response makes comparison inconclusive.
    """
    bank = run['plan']['allowed_invented_answers']
    if not isinstance(bank, dict) or any(not isinstance(value, str) or not value for value in bank.values()):
        raise ValueError('unsupported_answer_bank')
    values = set(bank.values())
    labelled = {f"{target['human_label']}: {bank[target['field_name']]}": bank[target['field_name']]
                for target in run['first_context'].get('all_targets', [])
                if target.get('field_name') in bank and isinstance(target.get('human_label'), str)}
    supplied = set()
    for turn in run['state']['turns']:
        history = turn.get('answer_history')
        if not isinstance(history, list) or not history or turn.get('answer') != history[-1].get('answer'):
            raise ValueError('incomplete_answer_history')
        for version in history:
            answer = version.get('answer')
            if not isinstance(answer, str):
                raise ValueError('incomplete_answer_history')
            if version.get('skipped'):
                if answer.strip():
                    raise ValueError('unapproved_skipped_answer_text')
                continue
            if answer.strip() in values:
                supplied.add(answer.strip())
                continue
            lines = [line.strip() for line in answer.splitlines() if line.strip()]
            if not lines or any(line not in values and line not in labelled for line in lines):
                raise ValueError('answer_outside_frozen_bank')
            supplied.update(labelled.get(line, line) for line in lines)
    return sorted(supplied)


def _load_run(directory):
    """Read the existing case-export layout; reject incomplete/hidden attempts."""
    def read(name):
        return json.loads((directory / name).read_bytes())
    summary = read('validation-summary.json')
    plan = read('validation/real-validation-plan.json')
    initial, final = read('live-study/initial-dossier.json'), read('live-study/final-dossier.json')
    state = read('live-study/final-review-state.json')
    first_context = read('live-study/context-1.json')
    calls = summary['calls']
    ids = [call['attempt_id'] for call in calls]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('missing_or_duplicate_attempts')
    disk_ids = {p.name for p in (directory / 'live-study/attempts').iterdir() if p.is_dir()}
    if set(ids) != disk_ids:
        raise ValueError('unaccounted_attempt_directory')
    observed = []
    totals = {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0, 'totalTokens': 0}
    for call in calls:
        receipt = read(f"live-study/attempts/{call['attempt_id']}/receipt.json")
        if (receipt.get('execution_status') != 'completed' or receipt.get('usage_complete') is not True
                or receipt.get('accounting_status') != 'terminal_usage_reported'):
            raise ValueError('inconclusive_usage_do_not_count_as_zero')
        observed.append(receipt.get('observed_model'))
        usage = receipt['reported_usage']
        if any(type(usage.get(key)) is not int or usage[key] < 0 for key in totals):
            raise ValueError('invalid_or_unknown_usage')
        if usage['totalTokens'] != sum(usage[key] for key in ('input', 'output', 'cacheRead', 'cacheWrite')):
            raise ValueError('inconsistent_usage_total')
        if receipt.get('reported_usage') != call.get('reported_usage'):
            raise ValueError('summary_receipt_usage_mismatch')
        route = {'requested_provider': summary.get('provider'), 'requested_model': summary.get('requested_model'),
                 'requested_effort': summary.get('effort'), 'pi_version': summary.get('pi_version')}
        for key, expected in route.items():
            if not expected or receipt.get(key) != call.get(key) or receipt.get(key) != expected:
                raise ValueError('summary_receipt_identity_mismatch')
        if receipt.get('observed_model') not in (None, route['requested_model']):
            raise ValueError('observed_model_mismatch')
        for key in totals:
            totals[key] += usage[key]
    if summary.get('usage_totals_pi_normalized', {}).get('totalTokens') != totals['totalTokens']:
        raise ValueError('summary_total_mismatch')
    pdf = (directory / 'same-document-synthetic.pdf').read_bytes()
    if digest(pdf) != initial['source_sha256'] or initial['source_sha256'] != final['source_sha256']:
        raise ValueError('source_identity_mismatch')
    if len(state['turns']) > 6 or state.get('status') not in ('complete', 'limited'):
        raise ValueError('unfinished_or_unbounded_journey')
    return {'summary': summary, 'plan': plan, 'initial': initial, 'final': final,
            'state': state, 'first_context': first_context, 'observed_models': observed, 'totals': totals, 'calls': len(calls)}


def compare(baseline, candidate):
    old, new = _load_run(baseline), _load_run(candidate)
    same_source = old['initial']['source_sha256'] == new['initial']['source_sha256']
    same_answers = old['plan']['allowed_invented_answers'] == new['plan']['allowed_invented_answers']
    same_supplied_answers = _answer_scope(old) == _answer_scope(new)
    same_initial = canonical_context_bytes(semantic_outcome(old['initial'])) == canonical_context_bytes(semantic_outcome(new['initial']))
    def initial_authority(run):
        dossier = run['initial']
        return {'version': dossier.get('version'),
                'history': [{key: value for key, value in event.items() if key != 'timestamp'}
                            for event in dossier.get('history', [])],
                'turns': run['first_context'].get('turns'),
                'questions_asked': run['first_context'].get('questions_asked'),
                'questions_remaining': run['first_context'].get('questions_remaining'),
                'source_document': run['first_context'].get('source_document')}
    same_authority = canonical_context_bytes(initial_authority(old)) == canonical_context_bytes(initial_authority(new))
    same_result = canonical_context_bytes(semantic_outcome(old['final'])) == canonical_context_bytes(semantic_outcome(new['final']))
    same_route = all(old['summary'].get(key) == new['summary'].get(key)
                     for key in ('provider', 'requested_model', 'effort', 'pi_version'))
    observed_models = [old['observed_models'], new['observed_models']]
    all_reported = all(model == run['summary']['requested_model']
                       for run in (old, new) for model in run['observed_models'])
    old_total, new_total = old['totals']['totalTokens'], new['totals']['totalTokens']
    if old_total <= 0:
        raise ValueError('invalid_zero_baseline')
    comparable = same_source and same_answers and same_supplied_answers and same_initial and same_authority and same_result and same_route
    return {'same_source': same_source, 'same_answer_bank': same_answers, 'same_answer_facts_supplied': same_supplied_answers, 'same_initial_state': same_initial,
            'same_initial_authority_and_source_text': same_authority, 'same_semantic_result': same_result, 'same_requested_route': same_route,
            'observed_models_from_receipts': observed_models, 'remote_model_reported_by_all_receipts': all_reported,
            'remote_model_attested': False,
            'baseline_calls': old['calls'], 'candidate_calls': new['calls'],
            'baseline_total_tokens': old_total, 'candidate_total_tokens': new_total,
            'target_total_tokens_at_most': old_total * 3 // 10,
            'observed_total_token_reduction_fraction': 1 - new_total / old_total,
            'comparable_case_and_result': comparable,
            'token_goal_on_same_semantic_result': comparable and new_total <= old_total * 3 // 10,
            'model_quality_acceptance': 'Requires independent question/source/correction assessment; value equality alone is insufficient.',
            'reasoning_not_added_again': True, 'real_cost_measured': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    preparation = commands.add_parser('prepare')
    preparation.add_argument('--evidence', type=Path, required=True)
    preparation.add_argument('--output', type=Path, required=True)
    comparison = commands.add_parser('compare')
    comparison.add_argument('--baseline', type=Path, required=True)
    comparison.add_argument('--candidate', type=Path, required=True)
    comparison.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.evidence, args.output)
    else:
        result = compare(args.baseline, args.candidate)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
