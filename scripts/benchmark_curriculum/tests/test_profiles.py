"""Closed comparison profiles, with synthetic fixtures and no comparison history."""
import copy
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.benchmark_curriculum.adapter import adapt
from scripts.benchmark_curriculum.build_release import build_release
from scripts.benchmark_curriculum.common import (
    ROOT, PYTHON, COMMITS, HARNESS_VERSION, Runtime, child_env, comparison_identity, read_json, sha_file, write_json,
)
from scripts.benchmark_curriculum.metrics import score
from scripts.benchmark_curriculum.runner import execute, load_freeze, make_order, validate_config, verify_snapshots
from scripts.benchmark_curriculum.tests.test_portability import SyntheticHarnessFixture
from scripts.benchmark_curriculum.tests import test_portability

PROFILE = 'b0-b3-b4'
EXPECTED_COMMITS = {
    'B0': '2541faf04bda4dad1215a4673e3802567ca7c5c9',
    'B3': 'a4dfe5cf9975d9e9b74a256aff718aec35f11f39',
    'B4': 'bf1ae21eae80ed38ef02179ea5724b7b0aa7b1c7',
}
PAIRS = [['B0', 'B4'], ['B3', 'B4']]


class ProfileTests(SyntheticHarnessFixture, unittest.TestCase):
    def select_new(self):
        self.runtime = Runtime(self.repo, self.runtime.workdir, profile=PROFILE)
        self.config = read_json(ROOT/'config.b0-b3-b4.proposed.json')

    def test_default_comparison_stays_b0_b2_b3(self):
        self.assertEqual(self.runtime.profile, 'b0-b2-b3')
        self.assertEqual(self.runtime.commits, COMMITS)
        validate_config(self.config)
        rows = [{'document_id': name} for name in ('C', 'A', 'B')]
        self.assertEqual([row['version'] for row in make_order(rows)],
                         ['B0', 'B2', 'B3', 'B2', 'B3', 'B0', 'B3', 'B0', 'B2'])

    def test_new_comparison_has_fixed_commits_rotation_and_unchanged_limits(self):
        default = self.config
        self.select_new()
        self.assertEqual(self.runtime.commits, EXPECTED_COMMITS)
        validate_config(self.config, PROFILE)
        identity_fields = {'comparison_profile', 'source_commits', 'comparison_pairs', 'version_order'}
        self.assertEqual({k: v for k, v in default.items() if k not in identity_fields},
                         {k: v for k, v in self.config.items() if k not in identity_fields})
        rows = [{'document_id': name} for name in ('C', 'A', 'B')]
        self.assertEqual(make_order(rows, PROFILE), make_order(rows[::-1], PROFILE))
        self.assertEqual([row['version'] for row in make_order(rows, PROFILE)],
                         ['B0', 'B3', 'B4', 'B3', 'B4', 'B0', 'B4', 'B0', 'B3'])

    def test_unknown_or_arbitrary_profiles_are_rejected(self):
        for profile in ('B4', 'custom', '0'*40, None, {'B4': '0'*40}):
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, 'profile'):
                Runtime(self.repo, self.runtime.workdir, profile=profile)

    def test_configuration_must_identify_selected_profile_and_exact_comparison(self):
        self.select_new()
        for change in ({'comparison_profile': 'b0-b2-b3'}, {'harness_version': '1.1.0-portable'},
                       {'source_commits': {**EXPECTED_COMMITS, 'B4': '0'*40}},
                       {'comparison_pairs': [['B0', 'B3']]},
                       {'version_order': 'rotate_B0_B2_B3_by_document_index'},
                       {'document_order': 'random'}, {'repeat_order': 'shuffle'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_config({**self.config, **change}, PROFILE)
        with self.assertRaises(ValueError):
            validate_config(self.config)
        for key in ('comparison_profile', 'harness_version', 'source_commits', 'comparison_pairs'):
            missing = copy.deepcopy(self.config)
            missing.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError):
                validate_config(missing, PROFILE)

    def test_cli_requires_explicit_new_profile_and_rejects_unknown_before_writing(self):
        command = [str(PYTHON), '-P', str(ROOT/'entrypoint.py'), 'setup', '--repo', str(self.repo),
                   '--workdir', str(self.runtime.workdir), '--profile', 'custom']
        result = subprocess.run(command, cwd=self.runtime.workdir, env=child_env(self.runtime.workdir),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid choice', result.stderr)
        self.assertFalse(self.runtime.snapshots.exists())

    def test_internal_commands_carry_profile_and_unknown_child_profile_fails_closed(self):
        self.select_new()
        for command in ('source', 'worker'):
            args = self.runtime.command(command, '--help')
            self.assertEqual(args[args.index('--profile')+1], PROFILE)
            result = subprocess.run(args, cwd=self.runtime.workdir, env=child_env(self.runtime.workdir),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            args[args.index('--profile')+1] = 'custom'
            result = subprocess.run(args, cwd=self.runtime.workdir, env=child_env(self.runtime.workdir),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)

    def test_cli_selects_profile_configuration_without_inference_from_workdir(self):
        from scripts.benchmark_curriculum.cli import main
        for profile, filename in (('b0-b2-b3', 'config.proposed.json'), (PROFILE, 'config.b0-b3-b4.proposed.json')):
            args = ['benchmark', 'freeze-template', '--repo', str(self.repo), '--workdir', str(self.runtime.workdir),
                    '--protocol', str(self.runtime.workdir/'synthetic-protocol.txt'), '--out', 'release']
            if profile == PROFILE:
                args.extend(['--profile', profile])
            with patch.object(sys, 'argv', args), patch('builtins.print'):
                with patch('scripts.benchmark_curriculum.build_release.build_release', return_value={'status': 'test'}) as build:
                    main()
            runtime, _, _, config_path = build.call_args.args
            self.assertEqual(runtime.profile, profile)
            self.assertEqual(config_path, ROOT/filename)

    def test_setup_exports_only_selected_commits_and_tags_every_snapshot(self):
        from scripts.benchmark_curriculum.setup_snapshots import setup
        self.select_new()
        stream = io.BytesIO()
        data = b'# synthetic lock\n'
        with tarfile.open(fileobj=stream, mode='w') as archive:
            entry = tarfile.TarInfo('requirements.lock')
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        archived = []

        def git(runtime, *args):
            if 'archive' in args:
                archived.append(args[-1])
                return stream.getvalue()
            return b'synthetic-tree\n'

        with patch('scripts.benchmark_curriculum.setup_snapshots.command', side_effect=git):
            with patch('scripts.benchmark_curriculum.setup_snapshots.environment_manifest', return_value={'mismatches': []}):
                report = setup(self.runtime)
        self.assertEqual(archived, list(EXPECTED_COMMITS.values()))
        self.assertEqual(report['comparison_profile'], PROFILE)
        verify_snapshots(self.runtime)
        index = read_json(self.runtime.snapshots/'index.json')
        for version in EXPECTED_COMMITS:
            self.assertEqual(index[version]['comparison_profile'], PROFILE)
            self.assertEqual(index[version]['harness_version'], HARNESS_VERSION)
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            setup(self.runtime)

    def test_worker_receipt_preserves_explicit_profile_on_guard_failure(self):
        self.select_new()
        row = self.input_row()
        snapshot = self.runtime.workdir/'fake snapshot'
        package = snapshot/'curriculum'
        package.mkdir(parents=True)
        (package/'__init__.py').write_text('')
        (package/'source_interpreter.py').write_text('import socket\nsocket.socket()\n')
        out = self.runtime.workdir/'blocked'
        out.mkdir()
        command = self.runtime.command('worker', '--snapshot', snapshot, '--pdf', row['path'],
                                      '--expected-sha', row['file_sha256'], '--out', out,
                                      '--timeout', 10, '--memory', 1073741824)
        completed = subprocess.run(command, cwd=out, env=child_env(out), capture_output=True, text=True)
        self.assertEqual(completed.returncode, 72, completed.stderr)
        status = read_json(out/'worker_status.json')
        self.assertEqual(status['status'], 'offline_violation')
        self.assertEqual(status['comparison_profile'], PROFILE)
        self.assertEqual(status['source_commits'], EXPECTED_COMMITS)
        self.assertEqual(status['comparison_pairs'], PAIRS)

    def test_coordinator_can_reduce_caps_without_changing_time_or_memory_limits(self):
        self.select_new()
        smaller = {**self.config, 'max_documents': 3, 'max_total_pages': 90}
        validate_config(smaller, PROFILE)
        for key in ('timeout_seconds_per_document', 'source_reader_timeout_seconds',
                    'memory_limit_bytes', 'source_reader_memory_limit_bytes'):
            self.assertEqual(smaller[key], self.config[key])

    def test_b4_adapter_changes_only_version_label(self):
        raw = {'dossier': {'general_fields': {'purpose': {'value': ['A'], 'evidence': []}},
                           'sessions': [], 'history': {'timestamp': 'retained'}}, 'claims': []}
        before = adapt(raw, 'B3')
        after = adapt(raw, 'B4')
        self.assertEqual({**before, 'version': 'B4'}, after)

    def test_snapshots_reject_wrong_profile_and_mixed_or_missing_versions(self):
        self.select_new()
        self.snapshots()
        verify_snapshots(self.runtime)
        with self.assertRaisesRegex(ValueError, 'profile|versions'):
            verify_snapshots(Runtime(self.repo, self.runtime.workdir))
        index_path = self.runtime.snapshots/'index.json'
        original = read_json(index_path)
        for index in ({**original, 'B2': original['B3']}, {k: v for k, v in original.items() if k != 'B4'}):
            write_json(index_path, index)
            with self.assertRaisesRegex(ValueError, 'versions'):
                verify_snapshots(self.runtime)
        write_json(index_path, original)
        extra = self.runtime.snapshots/'B2'
        extra.mkdir()
        with self.assertRaisesRegex(ValueError, 'entries|versions'):
            verify_snapshots(self.runtime)

    def test_snapshots_reject_foreign_manifests_even_for_shared_commit(self):
        self.select_new()
        self.snapshots()
        manifest = self.runtime.snapshots/'B0.manifest.json'
        record = read_json(manifest)
        for change in ({'comparison_profile': 'b0-b2-b3'}, {'harness_version': '1.1.0-portable'},
                       {'file_manifest_sha256': '0'*64}):
            write_json(manifest, {**record, **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_snapshots(self.runtime)

    def test_freeze_rejects_profile_mismatch_old_identity_and_missing_selection(self):
        self.select_new()
        path, freeze = self.freeze()
        with self.assertRaisesRegex(ValueError, 'profile'):
            load_freeze(path, Runtime(self.repo, self.runtime.workdir))
        for change in ({'comparison_profile': 'b0-b2-b3'}, {'harness_version': '1.1.0-portable'},
                       {'source_commits': COMMITS}, {'comparison_pairs': [['B0', 'B3']]}):
            write_json(path, {**freeze, **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                load_freeze(path, self.runtime)
        freeze.pop('comparison_profile')
        write_json(path, freeze)
        with self.assertRaisesRegex(ValueError, 'profile'):
            load_freeze(path, self.runtime)

    def test_new_freeze_loads_and_rejects_config_mismatch_even_when_rehashed(self):
        self.select_new()
        path, freeze = self.freeze()
        with patch('scripts.benchmark_curriculum.setup_snapshots.environment_manifest', return_value={'synthetic': True}):
            _, config, rows, order, _ = load_freeze(path, self.runtime)
            self.assertEqual(config['comparison_profile'], PROFILE)
            self.assertEqual(order, make_order(rows, PROFILE))
            config_path = self.runtime.workdir/'run_configuration.json'
            write_json(config_path, read_json(ROOT/'config.proposed.json'))
            freeze['artifacts']['run_configuration']['sha256'] = sha_file(config_path)
            write_json(path, freeze)
            with self.assertRaisesRegex(ValueError, 'profile'):
                load_freeze(path, self.runtime)

    def test_release_template_records_new_profile_and_refuses_wrong_config(self):
        self.select_new()
        self.snapshots()
        protocol = self.runtime.workdir/'protocol.txt'
        protocol.write_text('Synthetic only')
        write_json(self.runtime.workdir/'environment_manifest.json', {'synthetic': True})
        with self.assertRaisesRegex(ValueError, 'profile'):
            build_release(self.runtime, 'wrong-release', protocol, ROOT/'config.proposed.json')
        self.assertFalse((self.runtime.workdir/'wrong-release').exists())
        report = build_release(self.runtime, 'release', protocol, ROOT/'config.b0-b3-b4.proposed.json')
        template = read_json(self.runtime.workdir/'release'/'freeze_record.template.json')
        for artifact in (report, template):
            self.assertEqual(artifact['comparison_profile'], PROFILE)
            self.assertEqual(artifact['source_commits'], EXPECTED_COMMITS)
            self.assertEqual(artifact['comparison_pairs'], PAIRS)
            self.assertEqual(artifact['harness_version'], HARNESS_VERSION)
        self.assertFalse(template['ready_to_run'])

    def test_new_execution_repeats_same_rotated_order_and_records_requested_pairs(self):
        self.select_new()
        self.snapshots()
        row = self.input_row()
        child = test_portability.PortabilityTests.fake_pipeline(self, row, {version: [] for version in EXPECTED_COMMITS})
        with patch('scripts.benchmark_curriculum.runner.bounded', side_effect=child) as launched:
            receipt = execute(self.config, [row], make_order([row], PROFILE), 'new-run', 'preflight', self.runtime)
        self.assertEqual(receipt['comparison_profile'], PROFILE)
        self.assertEqual(receipt['source_commits'], EXPECTED_COMMITS)
        self.assertEqual(receipt['comparison_pairs'], PAIRS)
        self.assertEqual(receipt['harness_version'], HARNESS_VERSION)
        self.assertEqual(receipt['successful_runs'], 6)
        self.assertTrue(receipt['evaluation_completed'])
        calls = [call.args[0] for call in launched.call_args_list]
        self.assertTrue(all(command[command.index('--profile')+1] == PROFILE for command in calls))
        self.assertEqual([Path(command[command.index('--snapshot')+1]).name for command in calls[1:]],
                         ['B0', 'B3', 'B4']*2)
        for repeat in (1, 2):
            pairs = read_json(self.runtime.workdir/'new-run'/f'paired_differences_repeat_{repeat}.json')
            self.assertEqual([pair['comparison'] for pair in pairs], ['B0->B4', 'B3->B4'])
            self.assertTrue(all(pair['metrics']['M1']['before']['denominator'] == 1 for pair in pairs))

    def test_worker_identity_mismatch_aborts_before_scoring_and_retains_artifacts(self):
        self.select_new()
        self.snapshots()
        row = self.input_row()
        valid = {'status': 'completed', **comparison_identity(PROFILE)}
        bad = [
            {'status': 'completed', **comparison_identity('b0-b2-b3')},
            {'status': 'completed'},
            {**valid, 'source_commits': {**EXPECTED_COMMITS, 'B4': '0'*40}},
            {**valid, 'comparison_pairs': [['B0', 'B3']]},
            {**valid, 'harness_version': '1.1.0-portable'},
            {}, [], None,
        ]
        for key in comparison_identity(PROFILE):
            missing = copy.deepcopy(valid)
            missing.pop(key)
            bad.append(missing)
        base_child = test_portability.PortabilityTests.fake_pipeline(
            self, row, {version: [] for version in EXPECTED_COMMITS})
        for i, worker_status in enumerate(bad):
            with self.subTest(worker_status=worker_status):
                def child(command, out, timeout, python):
                    status = base_child(command, out, timeout, python)
                    if 'worker' in command:
                        write_json(Path(out)/'worker_status.json', worker_status)
                    return status

                with patch('scripts.benchmark_curriculum.runner.bounded', side_effect=child) as launched:
                    with patch('scripts.benchmark_curriculum.runner.score', wraps=score) as scored:
                        with self.assertRaisesRegex(ValueError, 'Worker identity'):
                            execute(self.config, [row], make_order([row], PROFILE), f'mismatch-{i}',
                                    'preflight', self.runtime)
                self.assertEqual(launched.call_count, 2)
                scored.assert_not_called()
                out = self.runtime.workdir/f'mismatch-{i}'
                receipt = read_json(out/'run_receipt.json')
                self.assertEqual(receipt['status'], 'instrumentation_failure')
                self.assertFalse(receipt['evaluation_completed'])
                self.assertEqual(receipt['planned_product_runs'], 6)
                self.assertEqual(receipt['product_runs'], 1)
                self.assertEqual(receipt['scored_product_runs'], 0)
                self.assertIn('finished_at_utc', receipt)
                dest = out/'repeat_1'/'SYNTH'/'B0'
                self.assertEqual(read_json(dest/'worker_status.json'), worker_status)
                self.assertTrue((dest/'raw.json').is_file())
                self.assertEqual(read_json(dest/'run_status.json')['outcome'], 'worker_identity_mismatch')
                self.assertFalse((dest/'metrics.json').exists())
                self.assertFalse((out/'aggregates_repeat_1.json').exists())

    def test_missing_worker_status_stays_failed_product_with_original_denominators(self):
        self.select_new()
        self.snapshots()
        row = self.input_row()
        base_child = test_portability.PortabilityTests.fake_pipeline(
            self, row, {version: [] for version in EXPECTED_COMMITS})

        def child(command, out, timeout, python):
            status = base_child(command, out, timeout, python)
            if 'worker' in command:
                (Path(out)/'worker_status.json').unlink()
                (Path(out)/'raw.json').unlink()
                status['returncode'] = 1
            return status

        with patch('scripts.benchmark_curriculum.runner.bounded', side_effect=child):
            receipt = execute(self.config, [row], make_order([row], PROFILE), 'crash', 'preflight', self.runtime)
        self.assertEqual(receipt['status'], 'completed')
        self.assertEqual(receipt['successful_runs'], 0)
        self.assertEqual(receipt['scored_product_runs'], 6)
        for repeat in (1, 2):
            for result in read_json(self.runtime.workdir/'crash'/f'scores_repeat_{repeat}.json'):
                self.assertEqual(result['outcome'], 'worker_crash')
                self.assertEqual(result['metrics']['M1']['numerator'], 0)
                self.assertEqual(result['metrics']['M1']['denominator'], 1)
                self.assertEqual(result['M8']['execution_failure'], 1)


if __name__ == '__main__':
    unittest.main()
