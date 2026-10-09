"""Offline byte audit of explicitly supplied exported requests; never calls a model.

Run from a checkout with --evidence PATH --output PATH. Input inventory and original
request SHA identities are checked before comparing equivalent representations.
The hypothetical requests retain their historical SYSTEM plus codec instructions;
they are not fresh provider observations or an evaluation of question policy.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import uuid


def dump(value, *, compact=True):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      **({'separators': (',', ':')} if compact else {})).encode('utf-8')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def audit(evidence, output):
    evidence = evidence.resolve()
    codec_path = Path(__file__).resolve().parents[1] / 'curriculum/teacher_review_context.py'
    spec = importlib.util.spec_from_file_location('teacher_context_audit_codec', codec_path)
    codec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codec)
    manifest_bytes = (evidence / 'export-inventory.json').read_bytes()
    inventory = json.loads(manifest_bytes)['files']
    entries = {entry['path']: entry for entry in inventory}
    if len(entries) != len(inventory):
        raise ValueError('duplicate_inventory_entry')
    checked = {}

    def read(relative):
        path = (evidence / relative).resolve()
        if not path.is_relative_to(evidence):
            raise ValueError('input_outside_evidence')
        data = path.read_bytes()
        entry = entries[relative]
        if len(data) != entry['bytes'] or sha(data) != entry['sha256']:
            raise ValueError('export_inventory_mismatch')
        checked[relative] = {'bytes': len(data), 'sha256': sha(data)}
        return data

    summary = json.loads(read('validation-summary.json'))
    provenance = json.loads(read('original-evidence-provenance.json'))
    pdf_sha = sha(read('same-document-synthetic.pdf'))
    rows = []
    for index, call in enumerate(summary['calls'], 1):
        attempt_id = str(uuid.UUID(call['attempt_id']))
        request_rel = f'live-study/attempts/{attempt_id}/request.json'
        context_rel = f'live-study/context-{index}.json'
        exported = read(request_rel)
        request = json.loads(exported)
        original = dump(request, compact=False)
        if (sha(original) != call['request_sha256']
                or sha(original) != provenance[request_rel]['original_sha256']
                or provenance[request_rel]['redacted'] is not False):
            raise ValueError('original_request_identity_mismatch')
        context_bytes = read(context_rel)
        if (sha(context_bytes) != provenance[context_rel]['original_sha256']
                or provenance[context_rel]['redacted'] is not False):
            raise ValueError('original_context_identity_mismatch')
        context = json.loads(context_bytes)
        before, data = request['prompt'].split('\nDATOS:\n', 1)
        label, schema_data = before.split('\n', 1)
        legacy = json.loads(data)
        schema = json.loads(schema_data)
        if codec.canonical_context_bytes(codec.restore_provider_context(legacy)) != codec.canonical_context_bytes(context):
            raise ValueError('legacy_context_does_not_match_export')
        if context['source_document']['source_sha256'] != pdf_sha or context['dossier']['source_sha256'] != pdf_sha:
            raise ValueError('source_identity_mismatch')
        encoded = codec.encode_provider_context(context)
        restored = codec.restore_provider_context(encoded)
        if codec.canonical_context_bytes(restored) != codec.canonical_context_bytes(context):
            raise ValueError('candidate_roundtrip_mismatch')
        compact = copy.deepcopy(request)
        prefix = label + '\n' + dump(schema).decode() + '\nDATOS:\n'
        compact['prompt'] = prefix + dump(legacy).decode()
        candidate = copy.deepcopy(compact)
        candidate['prompt'] = prefix + dump(encoded).decode()
        candidate['system'] += codec.provider_context_instructions(encoded)
        compact_bytes, candidate_bytes = dump(compact), dump(candidate)
        rows.append({
            'call': index, 'attempt_id': attempt_id,
            'exported_request_bytes': len(exported), 'exported_request_sha256': sha(exported),
            'original_request_bytes': len(original), 'original_request_sha256_verified': sha(original),
            'compact_only_request_bytes': len(compact_bytes),
            'codec_request_bytes_including_system_instructions': len(candidate_bytes),
            'codec_request_sha256': sha(candidate_bytes),
            'compact_legacy_context_bytes': len(dump(legacy)), 'shared_context_bytes': len(dump(encoded)),
            'original_context_canonical_sha256': sha(codec.canonical_context_bytes(context)),
            'restored_context_canonical_sha256': sha(codec.canonical_context_bytes(restored)),
            'encoded_context_canonical_sha256': sha(codec.canonical_context_bytes(encoded)),
            'exact_roundtrip_verified': True,
            'source_document_kept_inline': encoded['source_document'] == context['source_document'],
            'shared_values': len(encoded.get('_shared_values', [])),
            'pages': len(context['source_document']['pages']),
            'sessions': len(context['dossier']['sessions']),
            'history_entries': len(context['dossier']['history']),
            'turns': len(context['turns']),
            'answer_versions': sum(len(turn.get('answer_history', [])) for turn in context['turns']),
            'historical_provider_input_tokens_not_a_new_measurement': call['reported_usage']['input'],
        })
    original_total = sum(row['original_request_bytes'] for row in rows)
    compact_total = sum(row['compact_only_request_bytes'] for row in rows)
    codec_total = sum(row['codec_request_bytes_including_system_instructions'] for row in rows)
    result = {
        'scope': 'Offline counterfactual of exact completed synthetic requests; no new inference, no transmission, no model quality evaluation.',
        'representation': 'All original fields, order, source literals, citations, answers, corrections and history retained. Historical SYSTEM extended only with reference instructions.',
        'not_current_question_policy_evaluation': True,
        'tokenizer': {'packages_present': {name: importlib.util.find_spec(name) is not None for name in ('tiktoken', 'transformers', 'tokenizers')}, 'performed': False, 'scope': 'No provider-specific local tokenization was performed; no tokenizer downloaded.', 'estimated_tokens': None},
        'token_warning': 'These are serialized UTF-8 JSON bytes, not provider tokens or wire bytes. Historical input tokens are provenance only; no token or cost saving is asserted.',
        'codec_file_sha256': sha(codec_path.read_bytes()),
        'inventory_sha256': sha(manifest_bytes), 'source_pdf_sha256': pdf_sha,
        'verified_input_files': checked, 'calls': rows,
        'totals': {'original_request_bytes': original_total, 'compact_only_request_bytes': compact_total,
                   'codec_request_bytes_including_system_instructions': codec_total,
                   'bytes_removed_vs_original': original_total - codec_total,
                   'bytes_removed_vs_compact_only': compact_total - codec_total,
                   'percent_bytes_removed_vs_original': 100 * (original_total - codec_total) / original_total,
                   'percent_bytes_removed_vs_compact_only': 100 * (compact_total - codec_total) / compact_total,
                   'measured_token_savings': None, 'measured_cost_savings': None},
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / 'measurements.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.evidence, args.output)['totals'], indent=2))
