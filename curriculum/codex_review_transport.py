"""Bounded local Codex JSONL transport. No SDK, credentials, model launch or retry on import."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time


def strict_json(raw):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = value
        return result
    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('non_finite_json')
        return number
    def reject(_):
        raise ValueError('non_finite_json')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=finite, parse_constant=reject)


def read_regular(path, limit, *, owner_uid=None, forbid_write_mask=0):
    """Read one bounded regular-file snapshot without following a final symlink."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_size > limit
                or owner_uid is not None and info.st_uid != owner_uid
                or info.st_mode & forbid_write_mask):
            raise ValueError('invalid_bounded_file')
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('invalid_bounded_file')
        return raw


class CodexEvents:
    """Versioned exec envelope, distinct from AGY. Observing tools is not prevention."""
    usage_keys = ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens')

    def __init__(self, model):
        self.model = model
        self.buffer = b''
        self.threads = self.starts = self.completions = 0
        self.last_message = None
        self.usage = {key: None for key in self.usage_keys}
        self.reason = None
        self.usage_invalid = False

    def fail(self, code):
        if code == 'invalid_usage':
            self.usage_invalid = True
        self.reason = self.reason or code

    def feed(self, raw):
        self.buffer += raw
        while b'\n' in self.buffer and not self.reason:
            line, self.buffer = self.buffer.split(b'\n', 1)
            if not line.strip():
                self.fail('invalid_jsonl')
                break
            try:
                event = strict_json(line.decode('utf-8'))
                if not isinstance(event, dict):
                    raise ValueError('invalid_event')
                self.event(event)
            except (ValueError, UnicodeError, RecursionError):
                self.fail('invalid_jsonl')

    def event(self, event):
        kind = event.get('type')
        if event.get('model') not in (None, self.model) or event.get('rerouted_model') is not None:
            self.fail('model_reroute')
        elif kind == 'thread.started':
            self.threads += 1
            if self.threads != 1 or self.starts or self.completions or not isinstance(event.get('thread_id'), str) or not event['thread_id']:
                self.fail('invalid_thread')
        elif kind == 'turn.started':
            self.starts += 1
            if self.threads != 1 or self.starts != 1 or self.completions:
                self.fail('multiple_turns')
        elif kind in ('item.started', 'item.updated', 'item.completed'):
            item = event.get('item')
            if self.threads != 1 or self.starts != 1 or self.completions or not isinstance(item, dict):
                self.fail('invalid_item')
            elif item.get('type') not in ('agent_message', 'reasoning'):
                # Commands, file edits, MCP, web, plans and future unknown items
                # all stop capture. A dispatched action may already have begun.
                self.fail('tool_or_unknown_item')
            elif kind == 'item.completed' and item['type'] == 'agent_message':
                if not isinstance(item.get('text'), str):
                    self.fail('invalid_message')
                else:
                    self.last_message = item['text']
        elif kind == 'turn.completed':
            self.completions += 1
            usage = event.get('usage')
            if self.threads != 1 or self.starts != 1 or self.completions != 1 or not isinstance(usage, dict):
                self.fail('invalid_terminal')
                return
            for key in self.usage_keys:
                value = usage.get(key)
                if value is not None and (type(value) is not int or not 0 <= value <= 2**63 - 1):
                    self.fail('invalid_usage')
                else:
                    self.usage[key] = value
            for part, total in [('cached_input_tokens', 'input_tokens'), ('reasoning_output_tokens', 'output_tokens')]:
                if self.usage[part] is not None and self.usage[total] is not None and self.usage[part] > self.usage[total]:
                    self.fail('invalid_usage')
        elif kind in ('turn.failed', 'error'):
            self.fail('cli_error')
        else:
            self.fail('unknown_or_permission_event')

    def finish(self):
        if self.buffer.strip():
            self.fail('truncated_jsonl')
        if (self.threads, self.starts, self.completions) != (1, 1, 1) or self.last_message is None:
            self.fail('missing_terminal_evidence')

    @property
    def accounting_complete(self):
        # Reasoning is optional; preserve null, do not derive it or billed cost.
        return self.completions == 1 and not self.usage_invalid and all(self.usage[key] is not None for key in self.usage_keys[:3])


def bounded_process(argv, *, cwd, timeout, max_bytes, input_path=None, audit=None):
    """One process, bounded output/time, no shell, no retry and bounded cleanup."""
    if type(timeout) is not int or not 1 <= timeout <= 120 or type(max_bytes) is not int or not 1 <= max_bytes <= 1048576:
        raise ValueError('invalid_process_limits')
    chunks = {'stdout': bytearray(), 'stderr': bytearray()}
    reason = None
    proc = None
    source = None
    selector = selectors.DefaultSelector()
    started = time.monotonic()
    reaped = False
    try:
        if input_path:
            fd = os.open(input_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            source = os.fdopen(fd, 'rb')
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('nonregular_stdin')
        else:
            source = open(os.devnull, 'rb')
        proc = subprocess.Popen(argv, cwd=cwd, stdin=source, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True, umask=0o077)
        for name, stream in [('stdout', proc.stdout), ('stderr', proc.stderr)]:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                reason = 'wall_timeout'
                break
            for key, _ in selector.select(min(0.05, remaining)):
                try:
                    raw = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not raw:
                    selector.unregister(key.fileobj)
                    continue
                retained = raw[:max(0, max_bytes - sum(map(len, chunks.values())))]
                chunks[key.data].extend(retained)
                if len(retained) != len(raw):
                    reason = 'stream_byte_limit'
                if audit and key.data == 'stdout':
                    audit.feed(retained)
                    reason = reason or audit.reason
                if audit and key.data == 'stderr' and re.search(
                    rb'permission denied|approval required|not logged in|unauthorized|authentication failed',
                    bytes(chunks['stderr']), re.I,
                ):
                    reason = reason or 'permission_or_auth_error'
                if reason:
                    break
            if reason:
                break
        if not reason:
            try:
                proc.wait(timeout=max(0.001, timeout - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                reason = 'wall_timeout'
    except Exception:
        reason = 'process_io_error'
    finally:
        if proc is not None:
            # Terminate our process group even after a successful leader exits;
            # an ordinary descendant may have closed both pipes and stayed alive.
            if proc is not None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError:
                    try:
                        proc.kill()
                    except OSError:
                        pass
            try:
                proc.wait(timeout=1)
                reaped = True
            except subprocess.TimeoutExpired:
                reason = reason or 'child_not_reaped'
            for stream in (proc.stdout, proc.stderr):
                if stream:
                    stream.close()
        if source:
            source.close()
        selector.close()
    if audit:
        audit.finish()
        reason = reason or audit.reason
    return {'returncode': proc.returncode if proc is not None else None,
            'reason': reason, 'spawned': proc is not None, 'reaped': reaped,
            'stdout': bytes(chunks['stdout']), 'stderr': bytes(chunks['stderr'])}
