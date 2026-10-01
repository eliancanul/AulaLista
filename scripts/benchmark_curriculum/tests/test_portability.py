"""Public synthetic integration checks, independent of Git history and corpus."""
import copy
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.benchmark_curriculum.common import (
    ROOT, PYTHON, COMMITS, HARNESS_VERSION, Runtime, canonical_bytes,
    child_env, read_json, sha_bytes, sha_file, tree_manifest, write_json,
)
from scripts.benchmark_curriculum.fixtures import build, pdf_bytes
from scripts.benchmark_curriculum.metrics import read_source
from scripts.benchmark_curriculum.runner import (
    bounded, execute, load_freeze, make_order, validate_config, validate_rows,
    verify_snapshots,
)


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root/'checkout with spaces'
        (self.repo/'.git').mkdir(parents=True)
        self.runtime = Runtime(self.repo, self.root/'private with spaces')
        self.runtime.workdir.mkdir()
        self.config = read_json(ROOT/'config.proposed.json')

    def input_row(self):
        path = self.runtime.workdir/'synthetic.pdf'
        path.write_bytes(pdf_bytes([['Proyecto: Ejemplo'], ['Otro texto']]))
        return {'document_id': 'SYNTH', 'family_id': 'synthetic-family', 'split': 'X',
                'path': str(path), 'file_sha256': sha_file(path), 'bytes': path.stat().st_size,
                'page_count': 2, 'selection_status': 'included',
                'rights': {'status': 'approved', 'private_processing_basis': 'Synthetic fixture'},
                'pii': {'status': 'no_detected'}}

    def snapshots(self):
        index = {}
        for version, commit in COMMITS.items():
            dest = self.runtime.snapshots/version
            dest.mkdir(parents=True)
            (dest/'requirements.lock').write_text('# synthetic test lock\n')
            files = tree_manifest(dest)
            digest = sha_bytes(canonical_bytes(files))
            record = {'commit': commit, 'files': files, 'file_manifest_sha256': digest}
            write_json(self.runtime.snapshots/f'{version}.manifest.json', record)
            index[version] = {'commit': commit, 'file_manifest_sha256': digest}
        write_json(self.runtime.snapshots/'index.json', index)
        self.runtime.private_path('requirements.lock').write_text('# synthetic test lock\n')

    def freeze(self):
        self.snapshots()
        row = self.input_row()
        root = self.runtime.workdir
        artifacts = {}
        values = {
            'protocol': {'synthetic': True}, 'candidate_registry': [], 'family_mapping': {},
            'split': {}, 'exposure_ledger': {}, 'panel': {}, 'task_applicability': {},
            'corpus_manifest': [row], 'run_order': make_order([row]),
            'run_configuration': self.config, 'environment_manifest': {'synthetic': True},
            'harness_code_manifest': {name: sha_file(ROOT/name) for name in read_json(ROOT/'code_files.json')},
        }
        for name, value in values.items():
            path = root/f'{name}.json'
            write_json(path, value)
            artifacts[name] = {'path': path.name, 'sha256': sha_file(path)}
        for name, path in {
            'snapshot_index': self.runtime.snapshots/'index.json',
            'scorer': ROOT/'metrics.py', 'output_adapter': ROOT/'adapter.py',
            'mutation_pool': ROOT/'mutation_pool.json',
        }.items():
            artifacts[name] = {'path': str(path), 'sha256': sha_file(path)}
        value = {
            'harness_version': HARNESS_VERSION, 'ready_to_run': True,
            'rights_pii_gate_passed': True, 'source_commits': COMMITS,
            'new_corpus_product_tuning_permitted': False, 'phase': 'M_only',
            'freeze_timestamp_utc': '2000-01-01T00:00:00Z',
            'responsible_custodian': 'Synthetic test custodian',
            'prior_output_exposure': 'Synthetic fixture only',
            'historical_novelty_limitation': 'Synthetic test, no novelty claim',
            'timeout_seconds_per_document': self.config['timeout_seconds_per_document'],
            'memory_limit_bytes': self.config['memory_limit_bytes'], 'artifacts': artifacts,
        }
        path = root/'freeze.json'
        write_json(path, value)
        return path, value

    def test_workdir_cannot_be_inside_or_contain_checkout(self):
        for workdir in (self.repo, self.repo/'private', self.root):
            with self.subTest(workdir=workdir), self.assertRaisesRegex(ValueError, 'external'):
                Runtime(self.repo, workdir)

    def test_workdir_symlink_into_checkout_rejected(self):
        link = self.root/'link'
        link.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'external'):
            Runtime(self.repo, link/'private')

    def test_symlink_and_parent_escape_are_rejected(self):
        outside = self.root/'outside'
        outside.mkdir()
        (self.runtime.workdir/'link').symlink_to(outside, target_is_directory=True)
        for path in ('../escape', 'link/file.json'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'private workdir'):
                self.runtime.private_path(path)

    def test_quarantine_lexical_symlink_is_rejected_before_open(self):
        row = self.input_row()
        link = self.runtime.workdir/'QUARANTINE-link.pdf'
        link.symlink_to(row['path'])
        row['path'] = str(link)
        with self.assertRaisesRegex(ValueError, 'Quarantine'):
            validate_rows([row], self.config, self.runtime)

    def test_environment_is_allowlist_and_does_not_repurpose_home(self):
        with patch.dict(os.environ, {'HARNESS_TEST_SECRET': 'synthetic', 'HTTPS_PROXY': 'synthetic', 'HOME': '/synthetic-home'}):
            env = child_env(self.runtime.workdir)
        for key in ('HARNESS_TEST_SECRET', 'HTTPS_PROXY', 'HOME', 'PYTHONPATH'):
            self.assertNotIn(key, env)
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        self.assertTrue(env['HF_HOME'].startswith(str(self.runtime.workdir)))

    def test_cli_runs_from_unrelated_cwd_with_spaces(self):
        completed = subprocess.run(
            [str(PYTHON), '-P', str(ROOT/'entrypoint.py'), '--help'],
            cwd=self.runtime.workdir, env=child_env(self.runtime.workdir),
            capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('freeze-template', completed.stdout)

    def test_relocated_harness_has_no_original_checkout_dependency(self):
        relocated = self.root/'another checkout'/'scripts'/'benchmark_curriculum'
        shutil.copytree(ROOT, relocated, ignore=shutil.ignore_patterns('__pycache__'))
        row = self.input_row()
        out = self.runtime.workdir/'relocated source.json'
        command = [str(PYTHON), '-P', str(relocated/'entrypoint.py'), 'source',
                   '--pdf', row['path'], '--sha', row['file_sha256'], '--pages', '2',
                   '--out', str(out), '--memory', '1073741824']
        result = subprocess.run(command, cwd=self.runtime.workdir,
                                env=child_env(self.runtime.workdir), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(read_json(out)['page_count'], 2)

    def test_declared_code_manifest_covers_every_public_file(self):
        files = {str(path.relative_to(ROOT)) for path in ROOT.rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts}
        self.assertEqual(set(read_json(ROOT/'code_files.json')), files)

    def test_source_process_reads_synthetic_pdf_from_unrelated_cwd(self):
        row = self.input_row()
        out = self.runtime.workdir/'source result'
        status = bounded(self.runtime.command(
            'source', '--pdf', row['path'], '--sha', row['file_sha256'], '--pages', '2',
            '--out', out/'source.json', '--memory', '1073741824'), out, 10)
        self.assertEqual(status['returncode'], 0, (out/'stderr.log').read_text())
        source = read_json(out/'source.json')
        self.assertEqual(source['page_count'], 2)
        self.assertIn('Ejemplo', source['pages'][0]['text'])

    def test_worker_reports_forbidden_import_without_network(self):
        row = self.input_row()
        snapshot = self.runtime.workdir/'fake snapshot'
        package = snapshot/'curriculum'
        package.mkdir(parents=True)
        (package/'__init__.py').write_text('')
        (package/'source_interpreter.py').write_text('import socket\nsocket.socket()\n')
        out = self.runtime.workdir/'blocked worker'
        status = bounded(self.runtime.command(
            'worker', '--snapshot', snapshot, '--pdf', row['path'],
            '--expected-sha', row['file_sha256'], '--out', out,
            '--timeout', '10', '--memory', '1073741824'), out, 15)
        self.assertEqual(status['returncode'], 72)
        worker = read_json(out/'worker_status.json')
        self.assertEqual(worker['status'], 'offline_violation')
        self.assertEqual(worker['error']['stage'], 'import')
        self.assertTrue(worker['offline_events'])

    def test_default_fixtures_are_synthetic_and_external(self):
        rows = build(self.runtime)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row['synthetic'] for row in rows))
        self.assertTrue(all(Path(row['path']).is_relative_to(self.runtime.workdir) for row in rows))
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            build(self.runtime)

    def test_snapshot_commit_and_byte_drift_rejected(self):
        self.snapshots()
        verify_snapshots(self.runtime)
        index_path = self.runtime.snapshots/'index.json'
        index = read_json(index_path)
        index['B0']['commit'] = '0'*40
        write_json(index_path, index)
        with self.assertRaisesRegex(ValueError, 'commit'):
            verify_snapshots(self.runtime)
        index['B0']['commit'] = COMMITS['B0']
        write_json(index_path, index)
        (self.runtime.snapshots/'B2'/'changed.py').write_text('# altered\n')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            verify_snapshots(self.runtime)

    def test_changed_hash_size_duplicate_id_and_malformed_rows_rejected(self):
        row = self.input_row()
        for rows in ([{**row, 'file_sha256': '0'*64}], [{**row, 'bytes': row['bytes']+1}],
                     [row, row], [True], [], {'documents': [row]}):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validate_rows(rows, self.config, self.runtime)

    def test_uncleared_rights_pii_and_invalid_budgets_rejected(self):
        row = self.input_row()
        for changed in ({'rights': {}}, {'pii': {}}, {'split': 'unknown'}, {'page_count': True}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_rows([{**row, **changed}], self.config, self.runtime)
        for changed in ({'max_documents': True}, {'max_total_pages': 0}, {'parallel_workers': True}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_config({**self.config, **changed})

    def test_existing_run_rejected_before_snapshot_or_input_reads(self):
        out = self.runtime.workdir/'existing'
        out.mkdir()
        (out/'marker').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            execute(self.config, [], [], out, 'preflight', self.runtime)
        self.assertEqual((out/'marker').read_text(), 'keep')

    def test_source_failure_stops_before_any_product_run(self):
        self.snapshots()
        row = self.input_row()
        with patch('scripts.benchmark_curriculum.runner.bounded', return_value={'returncode': 1, 'timeout': False}) as child:
            with self.assertRaisesRegex(RuntimeError, 'source reader failed'):
                execute(self.config, [row], make_order([row]), 'failed', 'preflight', self.runtime)
        self.assertEqual(child.call_count, 1)
        receipt = read_json(self.runtime.workdir/'failed'/'run_receipt.json')
        self.assertEqual(receipt['status'], 'source_reader_failure_before_product_execution')
        self.assertFalse((self.runtime.workdir/'failed'/'repeat_1').exists())

    def test_malformed_raw_bytes_remain_failed_documents_in_both_repetitions(self):
        self.snapshots()
        row = self.input_row()
        source = read_source(row['path'], row['file_sha256'], 2)

        def fake_child(command, out, timeout, python):
            if 'source' in command:
                write_json(Path(out)/'source.json', source)
            else:
                (Path(out)/'raw.json').write_text('{"duplicate": 1, "duplicate": 2}')
                write_json(Path(out)/'worker_status.json', {'status': 'completed'})
            return {'returncode': 0, 'timeout': False, 'wall_seconds': 0.01}

        with patch('scripts.benchmark_curriculum.runner.bounded', side_effect=fake_child):
            receipt = execute(self.config, [row], make_order([row]), 'malformed', 'preflight', self.runtime)
        self.assertEqual(receipt['successful_runs'], 0)
        self.assertEqual(receipt['product_runs'], 6)
        for repetition in (1, 2):
            scores = read_json(self.runtime.workdir/'malformed'/f'scores_repeat_{repetition}.json')
            self.assertEqual(len(scores), 3)
            for result in scores:
                self.assertEqual(result['outcome'], 'malformed_output')
                self.assertEqual(result['metrics']['M1']['denominator'], 1)
                self.assertEqual(result['metrics']['M1']['numerator'], 0)
                self.assertEqual(result['M8']['execution_failure'], 1)
                self.assertIsNone(result['metrics']['M3_citations']['value'])
        reproducibility = read_json(self.runtime.workdir/'malformed'/'reproducibility.json')
        self.assertFalse(reproducibility['reproducibility_established'])
        retained = self.runtime.workdir/'malformed'/'repeat_1'/'SYNTH'/'B0'/'raw.json'
        self.assertIn('duplicate', retained.read_text())

    def fake_pipeline(self, row, histories=None):
        source = read_source(row['path'], row['file_sha256'], row['page_count'])
        histories = histories or {'B0': [], 'B2': [], 'B3': []}

        def child(command, out, timeout, python):
            out = Path(out)
            if 'source' in command:
                write_json(out/'source.json', source)
            else:
                raw = {'dossier': {'source_sha256': row['file_sha256'], 'version': 1,
                                   'page_count': row['page_count'], 'general_fields': {},
                                   'sessions': [], 'history': histories[out.name]},
                       'claims': [], 'verification': {'items': []}}
                write_json(out/'raw.json', raw)
                write_json(out/'worker_status.json', {'status': 'completed'})
            return {'returncode': 0, 'timeout': False, 'wall_seconds': 0.01}
        return child

    def test_unexpected_history_schema_keeps_full_run_and_denominators(self):
        self.snapshots()
        row = self.input_row()
        histories = {'B0': None, 'B2': 7, 'B3': {'timestamp': 'keep'}}
        with patch('scripts.benchmark_curriculum.runner.bounded', side_effect=self.fake_pipeline(row, histories)):
            receipt = execute(self.config, [row], make_order([row]), 'history', 'preflight', self.runtime)
        self.assertEqual(receipt['status'], 'completed')
        self.assertTrue(receipt['evaluation_completed'])
        self.assertEqual(receipt['scored_product_runs'], receipt['planned_product_runs'])
        for repetition in (1, 2):
            scores = read_json(self.runtime.workdir/'history'/f'scores_repeat_{repetition}.json')
            self.assertEqual(len(scores), 3)
            for result in scores:
                self.assertEqual(result['metrics']['M1']['denominator'], 1)
                directory = self.runtime.workdir/'history'/f'repeat_{repetition}'/'SYNTH'/result['version']
                for filename in ('raw.json', 'canonical.json'):
                    self.assertEqual(read_json(directory/filename)['dossier']['history'], histories[result['version']])

    def test_instrumentation_error_closes_receipt_without_claiming_complete_cohort(self):
        self.snapshots()
        row = self.input_row()
        with patch('scripts.benchmark_curriculum.runner.bounded', side_effect=self.fake_pipeline(row)):
            with patch('scripts.benchmark_curriculum.runner.score', side_effect=RuntimeError('Synthetic scorer failure')):
                with self.assertRaisesRegex(RuntimeError, 'Synthetic scorer failure'):
                    execute(self.config, [row], make_order([row]), 'instrument-error', 'preflight', self.runtime)
        out = self.runtime.workdir/'instrument-error'
        receipt = read_json(out/'run_receipt.json')
        self.assertEqual(receipt['status'], 'instrumentation_failure')
        self.assertFalse(receipt['evaluation_completed'])
        self.assertEqual(receipt['planned_document_count'], 1)
        self.assertEqual(receipt['planned_product_runs'], 6)
        self.assertEqual(receipt['product_runs'], 1)
        self.assertEqual(receipt['scored_product_runs'], 0)
        self.assertIn('finished_at_utc', receipt)
        self.assertEqual(receipt['instrumentation_error']['type'], 'RuntimeError')
        self.assertEqual(len(read_json(out/'input_manifest.json')), 1)
        self.assertTrue((out/'repeat_1'/'SYNTH'/'B0'/'raw.json').is_file())
        self.assertFalse((out/'aggregates_repeat_1.json').exists())

    def test_relative_quarantine_names_rejected_before_pdf_read(self):
        path, freeze = self.freeze()
        manifest_path = self.runtime.workdir/'corpus_manifest.json'
        row = read_json(manifest_path)[0]
        pdf = Path(row.pop('path'))
        (self.runtime.workdir/'quarantine').mkdir()
        (self.runtime.workdir/'QUARANTINE-link.pdf').symlink_to(pdf)
        for relative in ('quarantine/../synthetic.pdf', 'QUARANTINE-link.pdf'):
            with self.subTest(relative=relative):
                write_json(manifest_path, [{**row, 'relative_private_path': relative}])
                freeze['artifacts']['corpus_manifest']['sha256'] = sha_file(manifest_path)
                write_json(path, freeze)

                def checked_hash(candidate):
                    if Path(candidate).resolve() == pdf:
                        self.fail('PDF read before quarantine validation')
                    return sha_file(candidate)

                with patch('scripts.benchmark_curriculum.setup_snapshots.environment_manifest', return_value={'synthetic': True}):
                    with patch('scripts.benchmark_curriculum.runner.sha_file', side_effect=checked_hash):
                        with self.assertRaisesRegex(ValueError, 'Quarantine'):
                            load_freeze(path, self.runtime)

    def test_eligible_relative_manifest_path_still_loads(self):
        path, freeze = self.freeze()
        manifest_path = self.runtime.workdir/'corpus_manifest.json'
        row = read_json(manifest_path)[0]
        pdf = Path(row.pop('path'))
        row['relative_private_path'] = pdf.name
        write_json(manifest_path, [row])
        freeze['artifacts']['corpus_manifest']['sha256'] = sha_file(manifest_path)
        write_json(path, freeze)
        with patch('scripts.benchmark_curriculum.setup_snapshots.environment_manifest', return_value={'synthetic': True}):
            _, _, rows, _, _ = load_freeze(path, self.runtime)
        self.assertEqual(rows[0]['path'], str(pdf))

    def test_release_template_is_unready_and_never_overwritten(self):
        from scripts.benchmark_curriculum.build_release import build_release
        self.snapshots()
        protocol = self.runtime.workdir/'synthetic-protocol.txt'
        protocol.write_text('Synthetic release test only. No corpus execution authorized.')
        write_json(self.runtime.workdir/'environment_manifest.json', {'synthetic': True})
        report = build_release(self.runtime, 'release', protocol, ROOT/'config.proposed.json')
        self.assertFalse(report['used_for_original_pilot'])
        template = read_json(self.runtime.workdir/'release'/'freeze_record.template.json')
        self.assertFalse(template['ready_to_run'])
        self.assertFalse(template['rights_pii_gate_passed'])
        self.assertIsNone(template['artifacts']['corpus_manifest']['path'])
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            build_release(self.runtime, 'release', protocol, ROOT/'config.proposed.json')

    def test_complete_synthetic_freeze_loads_without_git_history(self):
        path, _ = self.freeze()
        with patch('scripts.benchmark_curriculum.setup_snapshots.environment_manifest', return_value={'synthetic': True}):
            _, _, rows, order, weak = load_freeze(path, self.runtime)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(order), 3)
        self.assertIsNone(weak)

    def test_freeze_rejects_artifact_tampering(self):
        path, _ = self.freeze()
        (self.runtime.workdir/'corpus_manifest.json').write_text('[]\n')
        with self.assertRaisesRegex(ValueError, 'artifact hash mismatch'):
            load_freeze(path, self.runtime)

    def test_freeze_rejects_different_executable_identity(self):
        path, freeze = self.freeze()
        freeze['harness_version'] = '1.0.0'
        write_json(path, freeze)
        with self.assertRaisesRegex(ValueError, 'portable harness'):
            load_freeze(path, self.runtime)

    def test_freeze_rejects_environment_drift(self):
        path, _ = self.freeze()
        with patch('scripts.benchmark_curriculum.setup_snapshots.environment_manifest', return_value={'changed': True}):
            with self.assertRaisesRegex(ValueError, 'environment drift'):
                load_freeze(path, self.runtime)

    def test_incomplete_harness_manifest_rejected_even_if_artifact_hash_matches(self):
        path, freeze = self.freeze()
        manifest_path = self.runtime.workdir/'harness_code_manifest.json'
        manifest = read_json(manifest_path)
        manifest.pop('metrics.py')
        write_json(manifest_path, manifest)
        freeze['artifacts']['harness_code_manifest']['sha256'] = sha_file(manifest_path)
        write_json(path, freeze)
        with self.assertRaisesRegex(ValueError, 'complete declared harness'):
            load_freeze(path, self.runtime)

    def test_reordered_run_rejected_even_if_artifact_hash_matches(self):
        path, freeze = self.freeze()
        order_path = self.runtime.workdir/'run_order.json'
        write_json(order_path, read_json(order_path)[::-1])
        freeze['artifacts']['run_order']['sha256'] = sha_file(order_path)
        write_json(path, freeze)
        with patch('scripts.benchmark_curriculum.setup_snapshots.environment_manifest', return_value={'synthetic': True}):
            with self.assertRaisesRegex(ValueError, 'Run order'):
                load_freeze(path, self.runtime)


if __name__ == '__main__':
    unittest.main()
