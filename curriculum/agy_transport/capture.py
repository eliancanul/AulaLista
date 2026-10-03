"""Prospective single-attempt transport only. No runnable model CLI or retries.

Derived bounded lifecycle from capture_frozen_v2.py; use only through a newly
reviewed/frozen authorized driver. Synthetic tests inject an in-memory process.
"""
from __future__ import annotations
import os
import math
from pathlib import Path
import selectors
import signal
import subprocess
import time
from .artifact_io import commit
from .audit import StreamAudit, encoded, utc
BASE = Path(__file__).resolve().parent


def capture_attempt(argv, directory, limits, *, cwd=BASE, popen=subprocess.Popen, detector=None):
    """Bounded process transport; fake-process tests never invoke AGY."""
    wall = limits.get('hard_wall_seconds_per_call')
    if type(wall) not in (int, float) or not math.isfinite(wall) or not 0 < wall <= 150:
        raise ValueError('invalid_hard_wall_seconds_per_call')
    for key, maximum in [('max_final_response_bytes', 262272),
                         ('max_stdout_ndjson_bytes_per_call', 2097152),
                         ('max_stderr_bytes_per_call', 1048576)]:
        if type(limits.get(key)) is not int or not 0 < limits[key] <= maximum:
            raise ValueError('invalid_limit:' + key)
    started = utc()
    t0 = time.monotonic()
    guards = []
    sizes = {'stdout': 0, 'stderr': 0}
    observed = dict(sizes)
    proc = None
    exit_code = None
    eof = {'stdout': False, 'stderr': False}
    streams = {}
    selector = None
    spawn_attempted = False
    child_reaped = None
    cleanup_errors = []
    def guard(reason):
        if reason not in guards:
            guards.append(reason)
        if proc is not None and child_reaped is not True:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException as exc:
                cleanup_errors.append('killpg:' + type(exc).__name__ + ':' + str(exc))
                try:
                    proc.kill()
                except BaseException as nested:
                    cleanup_errors.append('kill:' + type(nested).__name__ + ':' + str(nested))
    audit = StreamAudit(limits['max_final_response_bytes'], on_guard=guard, detector=detector)
    try:
        for key in sizes:
            streams[key] = (directory / ('stdout.ndjson' if key == 'stdout' else 'stderr.log')).open('xb')
        selector = selectors.DefaultSelector()
        spawn_attempted = True
        proc = popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        for key, stream in [('stdout', proc.stdout), ('stderr', proc.stderr)]:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, key)
        while selector.get_map():
            if time.monotonic() - t0 >= limits['hard_wall_seconds_per_call']:
                guard('hard_wall_timeout')
                # Close even if an escaped descendant retained a pipe. The
                # deadline bounds us independently of pipe EOF/process exit.
                break
            for key, _ in selector.select(min(0.05, max(0, limits['hard_wall_seconds_per_call'] - (time.monotonic() - t0)))):
                try:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    eof[key.data] = True
                    selector.unregister(key.fileobj)
                    continue
                which = key.data
                observed[which] += len(chunk)
                cap = limits['max_stdout_ndjson_bytes_per_call'] if which == 'stdout' else limits['max_stderr_bytes_per_call']
                retained = chunk[:max(0, cap - sizes[which])]
                streams[which].write(retained)
                streams[which].flush()
                sizes[which] += len(retained)
                if observed[which] > cap:
                    guard(which + '_byte_limit')
                if which == 'stdout':
                    audit.feed_stdout(retained)
                else:
                    audit.feed_stderr(retained)
            if guards:
                # Drain only immediately available bytes within the same
                # deadline and byte bounds, then terminate on pipe closure.
                if proc.poll() is not None and not selector.select(0):
                    break
        audit.finish_stdout()
        try:
            exit_code = proc.wait(timeout=max(0.001, min(0.2, limits['hard_wall_seconds_per_call'] - (time.monotonic() - t0))))
        except subprocess.TimeoutExpired:
            guard('process_not_reaped_at_deadline')
            exit_code = proc.poll()
        if exit_code != 0:
            guard('nonzero_or_unknown_exit')
    except BaseException as exc:
        guard('runner_exception:' + type(exc).__name__ + ':' + str(exc))
        if proc is not None:
            exit_code = proc.poll()
    finally:
        # Bounded cleanup happens on every successfully spawned-child path,
        # including registration, read, timeout and interruption exceptions.
        if proc is not None:
            try:
                running = proc.poll() is None
            except BaseException as exc:
                cleanup_errors.append('poll:' + type(exc).__name__ + ':' + str(exc))
                running = True
            if running:
                guard('cleanup_kill_unreaped_child')
            try:
                exit_code = proc.wait(timeout=1.0)
                child_reaped = True
            except BaseException as exc:
                child_reaped = False
                cleanup_errors.append('wait:' + type(exc).__name__ + ':' + str(exc))
                guard('child_reap_failed')
            for stream in (proc.stdout, proc.stderr):
                if stream:
                    try:
                        stream.close()
                    except BaseException as exc:
                        cleanup_errors.append('pipe_close:' + type(exc).__name__ + ':' + str(exc))
        if selector is not None:
            try:
                selector.close()
            except BaseException as exc:
                cleanup_errors.append('selector_close:' + type(exc).__name__ + ':' + str(exc))
        for output in streams.values():
            try:
                output.flush()
                os.fsync(output.fileno())
            except BaseException as exc:
                cleanup_errors.append('output_sync:' + type(exc).__name__ + ':' + str(exc))
            finally:
                try:
                    output.close()
                except BaseException as exc:
                    cleanup_errors.append('output_close:' + type(exc).__name__ + ':' + str(exc))
        if cleanup_errors:
            guard('resource_cleanup_error')
    artifact_errors = []
    def save_artifact(filename, value, *, json_value=False):
        try:
            commit(directory / filename, encoded(value) if json_value else value)
        except BaseException as exc:
            artifact_errors.append({'path': filename, 'error': type(exc).__name__ + ':' + str(exc)})
            guard('capture_artifact_write_failed')
    if len(audit.results) == 1:
        save_artifact('reported_result_envelope.ndjson', audit.results[0]['raw'])
    for filename, value in [('init_catalogs.json', audit.inits), ('actual_tool_events.json', audit.tools),
                            ('usage_receipts.json', audit.usages), ('ndjson_parse_errors.json', audit.parse_errors)]:
        save_artifact(filename, value, json_value=True)
    metadata = {
        'started_at_utc': started, 'ended_at_utc': utc(), 'duration_seconds': time.monotonic() - t0,
        'spawn_attempted': spawn_attempted, 'spawned': True if proc is not None else (None if spawn_attempted else False),
        'child_reaped': child_reaped, 'cleanup_errors': cleanup_errors, 'artifact_errors': artifact_errors,
        'transmission_status': 'unknown' if spawn_attempted else 'not_started',
        'exit_code': exit_code, 'guard_reasons': guards,
        **audit.integrity_metadata(), 'observed_bytes': observed, 'stream_eof': eof,
        'capture_truncated': {key: observed[key] > sizes[key] for key in sizes},
    }
    # No successful/eligible response artifact exists before every stream and
    # artifact guard has been reconciled. Caller must use this receipt gate.
    return audit.finalize(metadata)


if __name__ == '__main__':
    raise SystemExit('Import-only single-attempt transport; no execution CLI or retries.')
