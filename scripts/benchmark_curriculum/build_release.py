"""Hash this portable release and prepare an unready coordinator freeze template."""
import os
from datetime import datetime, timezone
from pathlib import Path
from .common import ROOT, comparison_identity, read_json, write_json, sha_file
from .runner import validate_config, verify_snapshots


def build_release(runtime, out, protocol, config_path):
    out = runtime.private_path(out)
    if out.exists():
        raise ValueError('Refusing to overwrite a release directory')
    config_path = Path(config_path).resolve()
    protocol = Path(protocol).resolve()
    config = read_json(config_path)
    validate_config(config, runtime.profile)
    verify_snapshots(runtime)
    files = read_json(ROOT/'code_files.json')
    manifest = {name: sha_file(ROOT/name) for name in files}
    # No corpus artifact is invented or declared ready by this command.
    artifact_files = {
        'snapshot_index': runtime.snapshots/'index.json', 'protocol': protocol,
        'scorer': ROOT/'metrics.py', 'output_adapter': ROOT/'adapter.py',
        'mutation_pool': ROOT/'mutation_pool.json',
        'environment_manifest': runtime.private_path('environment_manifest.json'),
        'run_configuration': config_path,
    }
    artifacts = {key: {'path': os.path.relpath(path, out), 'sha256': sha_file(path)}
                 for key, path in artifact_files.items()}
    out.mkdir(parents=True)
    write_json(out/'code_manifest.json', manifest)
    artifacts['harness_code_manifest'] = {'path': 'code_manifest.json', 'sha256': sha_file(out/'code_manifest.json')}
    for key in ('candidate_registry', 'corpus_manifest', 'family_mapping', 'split',
                'exposure_ledger', 'panel', 'run_order', 'task_applicability'):
        artifacts[key] = {'path': None, 'sha256': None}
    template = {
        'schema_version': '1.0.1', **comparison_identity(runtime.profile),
        'protocol_version': '1.0.1', 'phase': 'M_only',
        'status': 'pending_coordinator_freeze', 'ready_to_run': False,
        'rights_pii_gate_passed': False, 'freeze_timestamp_utc': None,
        'responsible_custodian': None,
        'new_corpus_product_tuning_permitted': False, 'prior_output_exposure': None,
        'historical_novelty_limitation': None,
        'timeout_seconds_per_document': config['timeout_seconds_per_document'],
        'memory_limit_bytes': config['memory_limit_bytes'],
        'human_reference_sha256': None, 'reference_status': 'no_human_reference_confirmed',
        'weak_reference_ai_outputs_seen_before_freeze': None, 'artifacts': artifacts,
    }
    write_json(out/'freeze_record.template.json', template)
    report = {'status': 'candidate_portable_release', **comparison_identity(runtime.profile),
              'packaged_at_utc': datetime.now(timezone.utc).isoformat(),
              'new_corpus_executed': False, 'used_for_original_pilot': False,
              'code_manifest_sha256': sha_file(out/'code_manifest.json')}
    write_json(out/'release_record.json', report)
    return report
