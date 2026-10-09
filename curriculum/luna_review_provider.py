"""Opt-in local Codex CLI adapter. Real readiness is separate from offline adapter tests."""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

from curriculum.agy_transport.artifact_io import commit, commit_json
from curriculum.codex_review_transport import CodexEvents, bounded_process, read_regular, strict_json
from curriculum.teacher_review_task_context import provider_task_payload
from curriculum.teacher_review_provider import RESPONSE_SCHEMA, SYSTEM, ReviewProviderError, review_response_has_valid_shape

MODEL = 'gpt-6-luna'
EFFORT = 'high'
CLI_VERSION = '0.159.2'
PROFILE = 'aulalista_luna_review'
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_FINAL_BYTES = 32 * 1024
MAX_STREAM_BYTES = 128 * 1024
DISABLED_FEATURES = ('shell_tool', 'view_image', 'apps', 'browser_use', 'computer_use',
    'multi_agent', 'code_mode_host', 'image_generation', 'plugins', 'remote_plugin',
    'skill_search', 'sleep_tool', 'hooks', 'tool_suggest', 'unified_exec')
LIMITATIONS = ['event_detection_is_not_prevention', 'no_server_token_cap',
               'returned_model_not_attested', 'internal_retries_not_observed']
PROFILE_CONTRACT = {
    'version': 1, 'model': MODEL, 'effort': EFFORT, 'profile': PROFILE,
    'exec_flags': ['--ignore-user-config', '--strict-config', '--ephemeral', '--json', '--skip-git-repo-check'],
    'disabled_features': list(DISABLED_FEATURES),
    'config': {
        'model_reasoning_effort': EFFORT, 'default_permissions': PROFILE,
        'sqlite_home': '<state>', 'log_dir': '<logs>', 'approval_policy': 'never',
        'allow_login_shell': False, 'shell_environment_policy.inherit': 'none',
        'shell_environment_policy.ignore_default_excludes': False,
        'shell_environment_policy.experimental_use_profile': False,
        'shell_environment_policy.set': {'PATH': '/usr/bin:/bin', 'HOME': '<work>'},
        'web_search': 'disabled', f'permissions.{PROFILE}.network.enabled': False,
        f'permissions.{PROFILE}.filesystem': {
            ':root': 'deny', ':minimal': 'read', '<work>': 'read', '/home': 'deny',
            '/root': 'deny', '/workspace': 'deny', '/tmp': 'deny', '/Users': 'deny'},
    },
}
PROFILE_SHA256 = hashlib.sha256(json.dumps(PROFILE_CONTRACT, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def auth_override_present(environ=None):
    # Inspect names only, never credential values. Do not silently switch a
    # ChatGPT-signed-in CLI to API authentication or another service endpoint.
    environ = os.environ if environ is None else environ
    return any(key in environ for key in ('CODEX_API_KEY', 'OPENAI_API_KEY', 'OPENAI_BASE_URL'))


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class LunaReviewReply(dict):
    def __init__(self, output, receipt):
        super().__init__(output)
        self.provider_receipt = receipt


class LunaAttemptStopped(ReviewProviderError):
    def __init__(self, code, receipt):
        super().__init__(code)
        self.provider_receipt = receipt


def profile_options(work, state, logs):
    """The same normalized security recipe generates argv and its review hash."""
    paths = {'<work>': str(work), '<state>': str(state), '<logs>': str(logs)}
    def materialize(value):
        if isinstance(value, dict):
            return {paths.get(key, key): materialize(item) for key, item in value.items()}
        return paths.get(value, value) if isinstance(value, str) else value
    def toml(value):
        if isinstance(value, dict):
            return '{' + ','.join(json.dumps(key) + '=' + toml(item) for key, item in value.items()) + '}'
        return json.dumps(value)
    result = []
    for key, value in PROFILE_CONTRACT['config'].items():
        # Whole TOML tables avoid unverified quoted-path dotted-key parsing.
        result.extend(['-c', key + '=' + toml(materialize(value))])
    return result


class LunaCodexCliProvider:
    def __init__(self, *, executable='', runtime_review='', attempt_root,
                 live_enabled=False, timeout=30, runner=bounded_process):
        self.executable = Path(executable).expanduser() if executable else None
        self.runtime_review = Path(runtime_review).expanduser() if runtime_review else None
        self.attempt_root = Path(attempt_root).expanduser()
        self.live_enabled = live_enabled
        self.timeout = timeout
        self.runner = runner

    def _reviewed_identity(self):
        if not self.executable or not self.runtime_review:
            raise ReviewProviderError('luna_route_not_configured')
        try:
            if not self.executable.is_absolute() or self.executable.is_symlink():
                raise ValueError('invalid_executable')
            fd = os.open(self.executable, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            digest = hashlib.sha256()
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022
                        or info.st_size > 512 * 1024 * 1024 or not os.access(self.executable, os.X_OK)):
                    raise ValueError('unsafe_executable')
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            raw = read_regular(self.runtime_review, 16384, owner_uid=os.getuid(), forbid_write_mask=0o022)
            review = strict_json(raw)
            expected_keys = {'schema', 'cli_version', 'launcher_sha256', 'profile_contract_sha256',
                'review_id', 'reviewed_at', 'evidence_sha256', 'external_surface_review', 'limitations_acknowledged'}
            if not isinstance(review, dict) or set(review) != expected_keys:
                raise ValueError('invalid_review')
            uuid.UUID(review['review_id'])
            reviewed = datetime.datetime.fromisoformat(review['reviewed_at'])
            if reviewed.tzinfo is None or reviewed > datetime.datetime.now(datetime.timezone.utc):
                raise ValueError('invalid_review_date')
            if (review['schema'] != 'aulalista.codex-local-review.v1'
                    or review['cli_version'] != CLI_VERSION
                    or review['launcher_sha256'] != digest.hexdigest()
                    or review['profile_contract_sha256'] != PROFILE_SHA256
                    or not re.fullmatch('[0-9a-f]{64}', review['evidence_sha256'])
                    or review['evidence_sha256'] == '0' * 64
                    or review['external_surface_review'] != 'reviewed_no_external_surfaces'
                    or review['limitations_acknowledged'] != LIMITATIONS):
                raise ValueError('review_does_not_match_runtime')
            return {'launcher_sha256': digest.hexdigest(), 'runtime_review_sha256': _sha(raw),
                    'profile_contract_sha256': PROFILE_SHA256}
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise ReviewProviderError('luna_runtime_review_required') from None

    def preflight(self, directory):
        """No prompt/model. Metadata and synthetic read/write canaries only.

        The reviewed manifest is operator evidence, not machine attestation of
        zero tools. No secret-bearing config dump is read. Managed rules remain.
        """
        if auth_override_present():
            raise ReviewProviderError('luna_auth_override_present')
        identity = self._reviewed_identity()
        work, state, logs = (directory / name for name in ('work', 'state', 'logs'))
        for path in (work, state, logs):
            path.mkdir(mode=0o700)
        options = profile_options(work, state, logs)
        deadline = time.monotonic() + 30
        def probe(args):
            remaining = math.ceil(deadline - time.monotonic())
            if remaining <= 0:
                raise ReviewProviderError('luna_preflight_failed')
            result = self.runner([str(self.executable), *args], cwd=work,
                                 timeout=min(10, remaining), max_bytes=65536)
            if result['reason'] or not result['reaped']:
                raise ReviewProviderError('luna_preflight_failed')
            return result
        version = probe(['--version'])
        if version['returncode'] != 0 or version['stdout'].decode('utf-8', 'replace').strip() != 'codex-cli ' + CLI_VERSION:
            raise ReviewProviderError('luna_cli_version_unsupported')
        help_result = probe(['exec', '--help'])
        required = (b'--ignore-user-config', b'--strict-config', b'--ephemeral', b'--json',
                    b'--output-schema', b'--output-last-message', b'--skip-git-repo-check')
        if help_result['returncode'] != 0 or not all(flag in help_result['stdout'] for flag in required):
            raise ReviewProviderError('luna_cli_options_unsupported')
        login = probe(['login', 'status'])
        if login['returncode'] != 0 or b'Logged in using ChatGPT' not in login['stdout'] + login['stderr']:
            raise ReviewProviderError('luna_login_required')
        marker = ('synthetic-canary-' + str(uuid.uuid4())).encode()
        commit(work / 'read-canary.txt', marker)
        commit(directory / 'outside-canary.txt', marker)
        base = ['sandbox', '--include-managed-config', '--permission-profile', PROFILE,
                '--cd', str(work), *options, '--']
        allowed = probe([*base, '/bin/true'])
        if allowed['returncode'] != 0:
            raise ReviewProviderError('luna_sandbox_preflight_failed')
        readable = probe([*base, '/bin/cat', str(work / 'read-canary.txt')])
        if readable['returncode'] != 0 or readable['stdout'] != marker:
            raise ReviewProviderError('luna_sandbox_preflight_failed')
        outside = probe([*base, '/bin/cat', str(directory / 'outside-canary.txt')])
        if outside['returncode'] == 0 or marker in outside['stdout']:
            raise ReviewProviderError('luna_sandbox_preflight_failed')
        write = probe([*base, '/usr/bin/touch', str(work / 'write-canary.txt')])
        if write['returncode'] == 0 or (work / 'write-canary.txt').exists():
            raise ReviewProviderError('luna_sandbox_preflight_failed')
        return {**identity, 'cli_version': CLI_VERSION, 'current_read_write_canaries': 'passed',
                'network_policy': 'disabled_in_named_profile',
                'external_surface_evidence': 'operator_review_not_zero_tool_attestation'}, work, options

    def __call__(self, context):
        if not self.executable or not self.runtime_review:
            raise ReviewProviderError('luna_route_not_configured')
        if not self.live_enabled:
            raise ReviewProviderError('luna_live_not_enabled')
        if auth_override_present():
            raise ReviewProviderError('luna_auth_override_present')
        if type(self.timeout) is not int or not 1 <= self.timeout <= 120:
            raise ReviewProviderError('luna_invalid_timeout')
        try:
            system, encoded = provider_task_payload(context)
            request = (system + '\nDATOS:\n' + json.dumps(encoded, ensure_ascii=False,
                       allow_nan=False, separators=(',', ':'))).encode('utf-8')
        except (ValueError, TypeError, UnicodeError):
            raise ReviewProviderError('invalid_target_reference_context') from None
        if len(request) > MAX_REQUEST_BYTES:
            raise ReviewProviderError('luna_full_context_too_large')
        root = self.attempt_root.absolute()
        try:
            if any(part.is_symlink() for part in (root, *root.parents)):
                raise ValueError('symlink_attempt_root')
            root.mkdir(parents=True, mode=0o700, exist_ok=True)
            info = root.stat()
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('non_private_attempt_root')
            if (root / 'STOP_REQUIRED.json').exists() or any(
                    p.is_dir() and (p / 'admission.json').exists() and not (p / 'receipt.json').exists()
                    for p in root.iterdir()):
                raise ReviewProviderError('luna_prior_attempt_blocked')
            fd = os.open(root / '.dispatch.lock', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except ReviewProviderError:
            raise
        except FileExistsError:
            raise ReviewProviderError('luna_attempt_in_progress') from None
        except (OSError, ValueError):
            raise ReviewProviderError('luna_private_storage_required') from None
        directory = root / str(uuid.uuid4())
        admitted = False
        terminal_saved = False
        try:
            # Recheck under the exclusive lock: another completed call may have
            # written its stop record between the initial check and acquisition.
            if (root / 'STOP_REQUIRED.json').exists() or any(
                    p.is_dir() and (p / 'admission.json').exists() and not (p / 'receipt.json').exists()
                    for p in root.iterdir()):
                raise ReviewProviderError('luna_prior_attempt_blocked')
            directory.mkdir(mode=0o700)
            try:
                metadata, work, options = self.preflight(directory)
            except ReviewProviderError as exc:
                commit_json(directory / 'preflight.json', {'status': 'blocked_before_model_launch', 'code': str(exc), 'at': _utc()})
                raise
            if auth_override_present():
                raise ReviewProviderError('luna_auth_override_present')
            if self._reviewed_identity() != {key: metadata[key] for key in ('launcher_sha256', 'runtime_review_sha256', 'profile_contract_sha256')}:
                raise ReviewProviderError('luna_runtime_review_required')
            commit(work / 'response-schema.json', json.dumps(RESPONSE_SCHEMA).encode())
            request_path = directory / 'request.txt'
            final_path = directory / 'final.json'
            commit(request_path, request)
            argv = [str(self.executable), 'exec', *PROFILE_CONTRACT['exec_flags'], '--cd', str(work),
                    '--model', MODEL, '--output-schema', str(work / 'response-schema.json'),
                    '--output-last-message', str(final_path), *options]
            for feature in PROFILE_CONTRACT['disabled_features']:
                argv.extend(['--disable', feature])
            argv.append('-')
            admission = {'attempt_id': directory.name, 'at': _utc(), 'provider': 'luna',
                'transport': 'local_codex_cli', 'requested_model': MODEL, 'requested_effort': EFFORT,
                'observed_model': None, 'request_sha256': _sha(request), 'request_bytes': len(request),
                'timeout_seconds': self.timeout, 'stream_byte_limit': MAX_STREAM_BYTES,
                'final_byte_limit': MAX_FINAL_BYTES, 'max_wrapper_launches': 1,
                'transmission': 'unknown', 'consumption': 'unknown', **metadata}
            commit_json(directory / 'admission.json', admission)
            admitted = True
            audit = CodexEvents(MODEL)
            result = self.runner(argv, cwd=work, timeout=self.timeout, max_bytes=MAX_STREAM_BYTES,
                                 input_path=request_path, audit=audit)
            audit.finish()
            commit(directory / 'stdout.jsonl', result['stdout'])
            commit(directory / 'stderr.log', result['stderr'])
            reason = result['reason'] or audit.reason
            if result['returncode'] != 0 or not result['reaped']:
                reason = reason or 'nonzero_or_unreaped_process'
            final = None
            output = None
            if not reason:
                try:
                    final = read_regular(final_path, MAX_FINAL_BYTES)
                    if final.decode('utf-8').strip() != audit.last_message.strip():
                        raise ValueError('final_message_mismatch')
                    output = strict_json(final.decode('utf-8'))
                    if not review_response_has_valid_shape(output):
                        raise ValueError('invalid_schema')
                except (OSError, ValueError, UnicodeError, RecursionError):
                    reason = 'invalid_structured_response'
            if not audit.accounting_complete:
                reason = reason or 'incomplete_usage'
            accounted = (not result['reason'] and not audit.reason and result['returncode'] == 0
                         and result['reaped'] and audit.accounting_complete)
            safe = {'attempt_id': directory.name, 'provider': 'luna', 'transport': 'local_codex_cli',
                'requested_model': MODEL, 'requested_effort': EFFORT, 'observed_model': None,
                'cli_version': CLI_VERSION, 'execution_status': 'completed' if not reason else 'stopped',
                'accounting_status': 'terminal_usage_reported' if accounted else 'unknown',
                'usage_complete': accounted, 'reported_usage': audit.usage,
                'request_sha256': _sha(request), 'response_sha256': _sha(final) if final is not None else None,
                'automatic_retries': 0, 'automatic_retries_scope': 'wrapper_process_relaunches',
                'transport_internal_retries': None, 'provider_dispatch_count': None, 'real_cost_currency': None,
                'guard_reason': reason, 'tool_prevention_attested': False,
                'direct_child_reaped': result['reaped'], 'all_descendants_termination_verified': False,
                'runtime_review_sha256': metadata['runtime_review_sha256']}
            commit_json(directory / 'receipt.json', safe)
            if reason:
                commit_json(root / 'STOP_REQUIRED.json', safe)
                terminal_saved = True
                code = 'luna_attempt_unknown' if safe['accounting_status'] == 'unknown' else 'luna_response_rejected'
                raise LunaAttemptStopped(code, safe)
            terminal_saved = True
            return LunaReviewReply(output, safe)
        except ReviewProviderError:
            raise
        except BaseException:
            if admitted and not (root / 'STOP_REQUIRED.json').exists():
                try:
                    commit_json(root / 'STOP_REQUIRED.json', {'attempt_id': directory.name,
                                'status': 'unknown', 'at': _utc(), 'reason': 'interrupted_recorder'})
                    terminal_saved = True
                except OSError:
                    pass  # Keep the lock if durable stop evidence could not be written.
            raise ReviewProviderError('luna_attempt_unknown' if admitted else 'luna_preflight_failed') from None
        finally:
            # Only remove the lock created by this call. A crash leaves it for
            # explicit operator inspection, never automatic stale-lock recovery.
            if not admitted or terminal_saved:
                (root / '.dispatch.lock').unlink(missing_ok=True)
