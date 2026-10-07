"""The offline audit accepts only inventory- and original-hash-verified bytes."""
import hashlib
import json

import pytest

from scripts.audit_teacher_context import audit, dump
from test_teacher_review_shared_context import repeated_context


def synthetic_export(root):
    root.mkdir()
    pdf = b'Invented local source bytes; this fixture does not claim PDF extraction.'
    source_sha = hashlib.sha256(pdf).hexdigest()
    context = repeated_context()
    context['source_document']['source_sha256'] = source_sha
    context['dossier']['source_sha256'] = source_sha
    legacy = dict(context)
    legacy['missing_target_ids'] = [t['target_id'] for t in legacy.pop('missing_fields')]
    attempt = '00000000-0000-4000-8000-000000000001'
    request_rel = f'live-study/attempts/{attempt}/request.json'
    context_rel = 'live-study/context-1.json'
    request = {'protocol': 'synthetic', 'system': 'Synthetic system rules.\n',
               'prompt': 'Synthetic schema:\n{}\nDATOS:\n' + dump(legacy, compact=False).decode(),
               'timeout_ms': 30000}
    original = dump(request, compact=False)
    files = {
        'same-document-synthetic.pdf': pdf,
        request_rel: json.dumps(request, ensure_ascii=False, indent=2).encode(),
        context_rel: dump(context),
        'validation-summary.json': dump({'calls': [{'attempt_id': attempt,
            'request_sha256': hashlib.sha256(original).hexdigest(), 'reported_usage': {'input': 123}}]}),
        'original-evidence-provenance.json': dump({
            request_rel: {'original_sha256': hashlib.sha256(original).hexdigest(), 'redacted': False},
            context_rel: {'original_sha256': hashlib.sha256(dump(context)).hexdigest(), 'redacted': False}}),
    }
    for path, data in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (root / 'export-inventory.json').write_bytes(dump({'files': [
        {'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        for path, data in files.items()]}))
    return request_rel


def test_audit_verifies_identity_and_roundtrip_without_provider(tmp_path):
    evidence = tmp_path / 'evidence'
    synthetic_export(evidence)
    result = audit(evidence, tmp_path / 'out')
    assert result['calls'][0]['exact_roundtrip_verified'] is True
    assert result['calls'][0]['original_context_canonical_sha256'] == result['calls'][0]['restored_context_canonical_sha256']
    assert result['totals']['codec_request_bytes_including_system_instructions'] < result['totals']['compact_only_request_bytes']
    assert result['totals']['measured_token_savings'] is None


def test_audit_rejects_mutated_export(tmp_path):
    evidence = tmp_path / 'evidence'
    request = synthetic_export(evidence)
    (evidence / request).write_bytes(b'{}')
    with pytest.raises(ValueError, match='export_inventory_mismatch'):
        audit(evidence, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()
