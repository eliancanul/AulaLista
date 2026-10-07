"""Opt-in Pi text transport. Requires a reviewed external isolation launcher.

Offline fixtures are not live readiness. Pi provides no OS sandbox; this module
never falls back to directly running Node/Pi when isolation is absent or fails.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from curriculum.agy_transport.artifact_io import commit, commit_json
from curriculum.codex_review_transport import bounded_process, read_regular, strict_json
from curriculum.pi_review_transport import IDENTITY, PiEvents
from curriculum.teacher_review_task_context import provider_task_payload
from curriculum.teacher_review_provider import RESPONSE_SCHEMA, SYSTEM, ReviewProviderError, review_response_has_valid_shape

DRIVER = Path(__file__).resolve().parents[1] / 'scripts' / 'pi_review_driver.mjs'
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_STREAM_BYTES = 128 * 1024
LIMITATIONS = ['external_review_is_not_machine_attestation', 'transitive_runtime_not_attested',
              'no_server_token_cap', 'remote_stop_not_attested', 'returned_model_may_be_unreported']
CONTRACT = {**IDENTITY, 'node_version': 'v22.22.3', 'tools': [], 'agent_loop': False,
            'resources': [], 'max_dispatches': 1, 'transport': 'sse', 'auth': 'existing_oauth_read_only',
            'isolation_launcher_args': ['--work', '<work>', '--', '<command>'],
            'limits': {'request_bytes': MAX_REQUEST_BYTES, 'stream_bytes': MAX_STREAM_BYTES,
                       'final_bytes': 32768, 'response_wire_bytes': 262144},
            'limitations': LIMITATIONS}
CONTRACT_SHA256 = hashlib.sha256(json.dumps(CONTRACT, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


# Only these fixed, non-sensitive helper diagnostics may survive preflight.
# Arbitrary Node/import/provider stderr is never copied into the preflight record.
PREFLIGHT_DRIVER_STAGES = frozenset({
    'invocation', 'package_manifest', 'ai_manifest', 'runtime_import', 'catalog_read',
    'runtime_create', 'catalog_refresh', 'model_contract', 'auth_check', 'auth_resolution',
})
PREFLIGHT_DRIVER_CODES = frozenset({
    'pi_stage_failed', 'invalid_invocation', 'invalid_file', 'pi_version_unsupported',
    'pi_ai_version_unsupported', 'pi_catalog_contract_mismatch',
    'pi_catalog_model_missing_or_duplicate', 'pi_model_contract_mismatch',
    'pi_refresh_contract_mismatch', 'pi_catalog_refresh_aborted', 'pi_catalog_refresh_failed',
    'pi_oauth_required', 'catalog_is_read_only',
})


def preflight_driver_diagnostic(raw):
    if not isinstance(raw, bytes) or len(raw) > 256:
        return None
    try:
        value = strict_json(raw)
        if (isinstance(value, dict) and set(value) == {'type', 'stage', 'code'}
                and all(type(item) is str for item in value.values())
                and value['type'] == 'pi.error' and value['stage'] in PREFLIGHT_DRIVER_STAGES
                and value['code'] in PREFLIGHT_DRIVER_CODES):
            return value
    except (ValueError, UnicodeError, RecursionError):
        pass
    return None


class PiPreflightStopped(ReviewProviderError):
    def __init__(self, raw):
        super().__init__('pi_runtime_preflight_failed')
        self.driver_diagnostic = preflight_driver_diagnostic(raw)


def digest_file(path, limit=512 * 1024 * 1024, executable=False):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('unsafe_runtime_path')
    raw = read_regular(path, limit, forbid_write_mask=0o022)
    if executable and not os.access(path, os.X_OK):
        raise ValueError('runtime_not_executable')
    return hashlib.sha256(raw).hexdigest()


def unsafe_overrides():
    # Presence only; do not inspect, copy, log, unset or switch credentials.
    names = ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'NODE_OPTIONS',
             'NODE_PATH', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
             'http_proxy', 'https_proxy', 'all_proxy')
    return any(name in os.environ for name in names)


class PiReply(dict):
    def __init__(self, output, receipt):
        super().__init__(output)
        self.provider_receipt = receipt


class PiStopped(ReviewProviderError):
    def __init__(self, code, receipt):
        super().__init__(code)
        self.provider_receipt = receipt


class PiLunaProvider:
    def __init__(self, *, node='', package_dir='', agent_dir='', catalog_file='',
                 isolation_launcher='', runtime_review='', attempt_root,
                 live_enabled=False, timeout=30, runner=bounded_process):
        self.node = Path(node).expanduser() if node else None
        self.package_dir = Path(package_dir).expanduser() if package_dir else None
        self.agent_dir = Path(agent_dir).expanduser() if agent_dir else None
        self.catalog = Path(catalog_file).expanduser() if catalog_file else None
        self.launcher = Path(isolation_launcher).expanduser() if isolation_launcher else None
        self.review = Path(runtime_review).expanduser() if runtime_review else None
        self.attempt_root = Path(attempt_root).expanduser()
        self.live_enabled, self.timeout, self.runner = live_enabled, timeout, runner

    def _identity(self):
        if not all((self.node, self.package_dir, self.agent_dir, self.catalog, self.launcher, self.review)):
            raise ReviewProviderError('pi_route_not_configured')
        try:
            if not self.agent_dir.is_absolute() or any(p.is_symlink() for p in (self.agent_dir, *self.agent_dir.parents)):
                raise ValueError('invalid_agent_dir')
            hashes = {
                'node_sha256': digest_file(self.node, executable=True),
                'isolation_launcher_sha256': digest_file(self.launcher, executable=True),
                'driver_sha256': digest_file(DRIVER, 32768),
                'package_manifest_sha256': digest_file(self.package_dir / 'package.json', 32768),
                'model_runtime_sha256': digest_file(self.package_dir / 'dist/core/model-runtime.js', 1024 * 1024),
                'auth_storage_sha256': digest_file(self.package_dir / 'dist/core/auth-storage.js', 1024 * 1024),
                'catalog_sha256': digest_file(self.catalog, 16 * 1024 * 1024),
            }
            raw = read_regular(self.review, 16384, owner_uid=os.getuid(), forbid_write_mask=0o022)
            review = strict_json(raw)
            keys = {'schema', 'review_id', 'reviewed_at', 'evidence_sha256', 'contract_sha256',
                    'runtime', 'isolation', 'limitations'}
            if not isinstance(review, dict) or set(review) != keys:
                raise ValueError('invalid_review')
            uuid.UUID(review['review_id'])
            date = datetime.datetime.fromisoformat(review['reviewed_at'])
            if (date.tzinfo is None or date > datetime.datetime.now(datetime.timezone.utc)
                    or review['schema'] != 'aulalista.pi-external-review.v1'
                    or review['contract_sha256'] != CONTRACT_SHA256 or review['runtime'] != hashes
                    or review['isolation'] != 'reviewed_external_boundary_no_unrestricted_fallback'
                    or review['limitations'] != LIMITATIONS
                    or not isinstance(review['evidence_sha256'], str)
                    or not re.fullmatch('[0-9a-f]{64}', review['evidence_sha256'])
                    or review['evidence_sha256'] == '0' * 64):
                raise ValueError('review_mismatch')
            return hashes | {'runtime_review_sha256': hashlib.sha256(raw).hexdigest()}
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise ReviewProviderError('pi_runtime_review_required') from None

    def _env(self):
        return {'PATH': '/usr/bin:/bin', 'HOME': str(self.agent_dir.parent.parent),
                'PI_CODING_AGENT_DIR': str(self.agent_dir), 'PI_OFFLINE': '1',
                'PI_SKIP_VERSION_CHECK': '1', 'PI_TELEMETRY': '0', 'LANG': 'C.UTF-8'}

    def _isolated(self, work, command):
        return [str(self.launcher), '--work', str(work), '--', *map(str, command)]

    def _driver(self, mode):
        return [self.node, DRIVER, mode, self.package_dir, self.agent_dir, self.catalog]

    def preflight(self, directory):
        identity = self._identity()
        work = directory / 'work'
        work.mkdir(mode=0o700)
        def probe(command):
            result = self.runner(self._isolated(work, command), cwd=work, timeout=5,
                                 max_bytes=32768, env=self._env())
            if result['reason'] or not result['reaped']:
                raise ReviewProviderError('pi_isolation_preflight_failed')
            return result
        # Paths are verified per runtime, never assume /bin/true exists on macOS.
        if probe(['/usr/bin/true'])['returncode'] != 0:
            raise ReviewProviderError('pi_isolation_preflight_failed')
        allowed, denied, write = work / 'read-canary.txt', directory / 'denied-canary.txt', work / 'write-canary.txt'
        commit(allowed, b'aulalista-pi-allowed\n')
        commit(denied, b'aulalista-pi-denied\n')
        result = probe(['/bin/cat', allowed])
        if result['returncode'] != 0 or result['stdout'] != b'aulalista-pi-allowed\n':
            raise ReviewProviderError('pi_isolation_preflight_failed')
        result = probe(['/bin/cat', denied])
        if result['returncode'] == 0 or b'aulalista-pi-denied' in result['stdout']:
            raise ReviewProviderError('pi_isolation_preflight_failed')
        if probe(['/usr/bin/touch', write])['returncode'] == 0 or write.exists():
            raise ReviewProviderError('pi_isolation_preflight_failed')
        version = probe([self.node, '--version'])
        if version['returncode'] != 0 or version['stdout'].strip() != CONTRACT['node_version'].encode():
            raise ReviewProviderError('pi_node_version_unsupported')
        ready = probe(self._driver('--preflight'))
        expected = {'type': 'pi.ready', **IDENTITY, 'auth_type': 'oauth', 'auth_refresh': False,
                    'tools': 0, 'resources': 0, 'automatic_retries': 0, 'agent_loop': False}
        try:
            actual = strict_json(ready['stdout'])
            valid = (ready['returncode'] == 0 and not ready['stderr']
                     and json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True))
        except (ValueError, UnicodeError, RecursionError):
            valid = False
        if not valid:
            raise PiPreflightStopped(ready['stderr'])
        return identity, work

    def __call__(self, context):
        if not self.live_enabled:
            raise ReviewProviderError('pi_live_not_enabled')
        if type(self.timeout) is not int or not 1 <= self.timeout <= 120:
            raise ReviewProviderError('pi_invalid_timeout')
        if unsafe_overrides():
            raise ReviewProviderError('pi_environment_override_present')
        try:
            system, encoded = provider_task_payload(context)
            request = json.dumps({'protocol': IDENTITY['protocol'], 'system': system,
                'prompt': 'Devuelve únicamente JSON según este esquema:\n' + json.dumps(RESPONSE_SCHEMA, separators=(',', ':'))
                          + '\nDATOS:\n' + json.dumps(encoded, ensure_ascii=False,
                                                       allow_nan=False, separators=(',', ':')),
                'timeout_ms': self.timeout * 1000}, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        except (TypeError, ValueError, RecursionError):
            raise ReviewProviderError('pi_invalid_context') from None
        if len(request) > MAX_REQUEST_BYTES:
            raise ReviewProviderError('pi_full_context_too_large')
        root = self.attempt_root.absolute()
        try:
            if any(p.is_symlink() for p in (root, *root.parents)):
                raise ValueError('symlink_storage')
            root.mkdir(parents=True, mode=0o700, exist_ok=True)
            info = root.stat()
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('nonprivate_storage')
            fd = os.open(root / '.dispatch.lock', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            raise ReviewProviderError('pi_attempt_in_progress') from None
        except (OSError, ValueError):
            raise ReviewProviderError('pi_private_storage_required') from None
        directory = root / str(uuid.uuid4())
        admitted = terminal_saved = False
        receipt = None
        try:
            if (root / 'STOP_REQUIRED.json').exists() or any(p.is_dir() and (p / 'admission.json').exists()
                    and not (p / 'receipt.json').exists() for p in root.iterdir()):
                raise ReviewProviderError('pi_prior_attempt_blocked')
            directory.mkdir(mode=0o700)
            try:
                identity, work = self.preflight(directory)
            except ReviewProviderError as exc:
                record = {'status': 'blocked_before_model_launch', 'code': str(exc)}
                if isinstance(exc, PiPreflightStopped) and exc.driver_diagnostic:
                    record['driver_diagnostic'] = exc.driver_diagnostic
                commit_json(directory / 'preflight.json', record)
                raise
            if unsafe_overrides() or self._identity() != identity:
                raise ReviewProviderError('pi_runtime_review_required')
            request_path = directory / 'request.json'
            commit(request_path, request)
            admission = {'attempt_id': directory.name, 'transport': 'local_pi_sdk',
                **IDENTITY, 'requested_provider': IDENTITY['provider'], 'provider': 'pi_luna',
                'request_sha256': hashlib.sha256(request).hexdigest(),
                'request_bytes': len(request), 'timeout_seconds': self.timeout,
                'transmission': 'unknown', 'consumption': 'unknown', **identity}
            commit_json(directory / 'admission.json', admission)
            admitted = True
            audit = PiEvents()
            result = self.runner(self._isolated(work, self._driver('--generate')), cwd=work,
                timeout=self.timeout, max_bytes=MAX_STREAM_BYTES, input_path=request_path,
                audit=audit, env=self._env())
            audit.finish()
            commit(directory / 'stdout.jsonl', result['stdout'])
            commit(directory / 'stderr.log', result['stderr'])
            reason = result['reason'] or audit.reason
            if result['returncode'] != 0 or not result['reaped'] or result['stderr']:
                reason = reason or 'process_not_cleanly_completed'
            output = None
            if not reason:
                try:
                    output = strict_json(audit.text)
                    if not review_response_has_valid_shape(output):
                        raise ValueError('invalid_schema')
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    reason = 'invalid_structured_response'
            accounted = (not result['reason'] and audit.accounting_complete and result['returncode'] == 0
                         and result['reaped'] and not result['stderr'])
            receipt = {'attempt_id': directory.name, 'provider': 'pi_luna', 'transport': 'local_pi_sdk',
                'pi_version': IDENTITY['pi_version'], 'requested_provider': IDENTITY['provider'],
                'requested_model': IDENTITY['model'], 'requested_effort': IDENTITY['effort'],
                'observed_model': audit.observed_model, 'execution_status': 'stopped' if reason else 'completed',
                'accounting_status': 'terminal_usage_reported' if accounted else 'unknown',
                'usage_complete': accounted, 'reported_usage': audit.usage,
                'usage_source': 'pi_normalized_terminal_usage',
                'request_sha256': admission['request_sha256'],
                'response_sha256': hashlib.sha256(audit.text.encode()).hexdigest() if audit.text is not None else None,
                'automatic_retries': 0, 'provider_dispatch_count': audit.dispatches,
                'provider_dispatch_count_scope': 'local_fetch_invocations_not_backend_work',
                'real_cost_currency': None, 'guard_reason': reason, 'tool_prevention_attested': False,
                'direct_child_reaped': result['reaped'], 'remote_stop_attested': False,
                'runtime_review_sha256': identity['runtime_review_sha256'], 'limitations': LIMITATIONS}
            commit_json(directory / 'receipt.json', receipt)
            if reason:
                commit_json(root / 'STOP_REQUIRED.json', receipt)
                terminal_saved = True
                raise PiStopped('pi_response_rejected' if accounted else 'pi_attempt_unknown', receipt)
            commit(directory / 'final.json', audit.text.encode())
            terminal_saved = True
            return PiReply(output, receipt)
        except ReviewProviderError:
            raise
        except BaseException:
            if admitted:
                try:
                    commit_json(root / 'STOP_REQUIRED.json', {'attempt_id': directory.name,
                        'status': 'unknown', 'reason': 'interrupted_recorder'})
                    terminal_saved = True
                except OSError:
                    pass
            # A recorder failure does not erase independently validated provider
            # usage. The call still fails and its STOP/claim remains blocking.
            if receipt is not None:
                raise PiStopped('pi_attempt_unknown', receipt) from None
            raise ReviewProviderError('pi_attempt_unknown' if admitted else 'pi_preflight_failed') from None
        finally:
            if not admitted or terminal_saved:
                (root / '.dispatch.lock').unlink(missing_ok=True)
