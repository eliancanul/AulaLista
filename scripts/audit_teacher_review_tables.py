"""Verified offline v1->v2 replay of the five completed real-case requests.

No authentication, network, inference, output prediction or token estimation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from curriculum.teacher_review_context import canonical_context_bytes
from curriculum.teacher_review_task_context import build_task_context
from curriculum.teacher_review_table_context import encode_table_context, restore_table_context, TABLE_SYSTEM


def raw(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def audit(evidence, output):
    evidence = evidence.resolve()
    inventory_raw = (evidence / 'export-inventory.json').read_bytes()
    inventory = json.loads(inventory_raw)['files']
    entries = {row['path']: row for row in inventory}
    if len(entries) != len(inventory): raise ValueError('duplicate_inventory_entry')
    checked = {}
    def read(relative):
        path = (evidence / relative).resolve()
        if not path.is_relative_to(evidence): raise ValueError('unsafe_evidence_path')
        data = path.read_bytes(); expected = entries[relative]
        if len(data) != expected['bytes'] or sha(data) != expected['sha256']:
            raise ValueError('evidence_inventory_mismatch')
        checked[relative] = {'bytes': len(data), 'sha256': sha(data)}
        return data
    summary = json.loads(read('validation-summary.json'))
    provenance = json.loads(read('original-evidence-provenance.json'))
    source_sha = sha(read('same-document-synthetic.pdf'))
    rows = []
    for number, call in enumerate(summary['calls'], 1):
        attempt = str(uuid.UUID(call['attempt_id']))
        request_path = f'live-study/attempts/{attempt}/request.json'
        request = json.loads(read(request_path))
        original = raw(request)
        if sha(original) != call['request_sha256'] or sha(original) != provenance[request_path]['original_sha256']:
            raise ValueError('original_request_sha_mismatch')
        if provenance[request_path].get('private_paths_redacted') is not False:
            raise ValueError('request_was_redacted')
        full = json.loads(read(f'live-study/context-{number}.json'))
        prefix, payload = request['prompt'].split('\nDATOS:\n', 1)
        semantic = json.loads(payload)
        if canonical_context_bytes(build_task_context(full)) != canonical_context_bytes(semantic):
            raise ValueError('v1_runtime_projection_mismatch')
        if semantic['source_document']['source_sha256'] != source_sha:
            raise ValueError('source_identity_mismatch')
        encoded = encode_table_context(semantic)
        restored = restore_table_context(encoded, max_expanded_bytes=len(canonical_context_bytes(semantic)))
        if canonical_context_bytes(restored) != canonical_context_bytes(semantic):
            raise ValueError('v2_roundtrip_mismatch')
        candidate = {**request, 'system': TABLE_SYSTEM,
                     'prompt': prefix + '\nDATOS:\n' + raw(encoded).decode()}
        data = raw(candidate)
        request_out = output / 'fixed-panel' / f'request-{number}-semantic-v2.json'
        request_out.parent.mkdir(parents=True, exist_ok=True)
        request_out.write_bytes(data)
        rows.append({'call': number, 'attempt_id': attempt, 'v1_request_bytes': len(original),
                     'v2_request_bytes': len(data), 'v1_request_sha256_verified': sha(original),
                     'v2_request_sha256': sha(data), 'v1_semantic_sha256': sha(canonical_context_bytes(semantic)),
                     'restored_v1_semantic_sha256': sha(canonical_context_bytes(restored)),
                     'v2_context_sha256': sha(canonical_context_bytes(encoded)),
                     'exact_semantic_roundtrip': True, 'source_document_unchanged': encoded['source_document'] == semantic['source_document'],
                     'v1_dossier_bytes': len(raw(semantic['dossier'])), 'v2_dossier_bytes': len(raw(encoded['dossier'])),
                     'recorded_v1_usage_not_v2_measurement': call['reported_usage']})
    total_v1 = sum(row['v1_request_bytes'] for row in rows)
    total_v2 = sum(row['v2_request_bytes'] for row in rows)
    result = {'scope': 'Five frozen historical contexts; exact v1 semantic restoration; no new live journey or token estimate.',
              'inventory_sha256': sha(inventory_raw), 'source_pdf_sha256': source_sha,
              'checked_files': checked, 'calls': rows,
              'totals': {'v1_request_bytes': total_v1, 'v2_request_bytes': total_v2,
                         'request_byte_reduction_fraction': 1 - total_v2 / total_v1,
                         'historical_v1_total_tokens': sum(call['reported_usage']['totalTokens'] for call in summary['calls']),
                         'original_baseline_total_tokens': 67743, 'target_total_tokens_at_most': 20322,
                         'new_v2_tokens_measured': None, 'token_goal_met': None},
              'new_runtime_sha256': sha((ROOT / 'curriculum/teacher_review_table_context.py').read_bytes()),
              'v1_mode_remains_unchanged': True}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'measurements.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.evidence, args.output)['totals'], indent=2))
