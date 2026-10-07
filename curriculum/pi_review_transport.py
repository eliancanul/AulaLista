"""AulaLista's own envelope around one Pi 0.84.4 SDK stream, not CLI JSONL."""
from __future__ import annotations

from curriculum.codex_review_transport import strict_json

IDENTITY = {
    'protocol': 'aulalista.pi-text.v1', 'pi_version': '0.84.4',
    'provider': 'openai-codex', 'model': 'gpt-6-luna',
    'api': 'openai-codex-responses', 'base_url': 'https://chatgpt.com/backend-api', 'effort': 'high',
}


def _reported_usage(message):
    """Retain valid reported counters independently of result acceptance.

    These counters alone never establish terminal accounting or an actual cost.
    An identity mismatch must be rejected before calling this function.
    """
    usage = message.get('usage')
    keys = ('input', 'output', 'cacheRead', 'cacheWrite', 'totalTokens')
    if not isinstance(usage, dict) or any(
            type(usage.get(key)) is not int or not 0 <= usage[key] <= 2**53 - 1
            for key in keys):
        return None
    reasoning = usage.get('reasoning')
    if (reasoning is not None and (type(reasoning) is not int or not 0 <= reasoning <= usage['output'])
            or usage['totalTokens'] != sum(usage[key] for key in keys[:4])
            or usage['output'] == 0 or usage['input'] + usage['cacheRead'] + usage['cacheWrite'] == 0):
        return None
    # Pi input excludes cacheRead/cacheWrite; output already includes reasoning.
    # Catalog cost estimates are never retained as actual charges.
    return {key: usage[key] for key in keys} | {'reasoning': reasoning}


class PiEvents:
    """Accept one request/start/result/completion; fail closed on every other event."""
    def __init__(self):
        self.buffer = b''
        self.reason = None
        self.state = 'request'
        self.message = None
        self.text = None
        self.usage = None
        self.observed_model = None
        self.dispatches = 0

    def fail(self, reason):
        self.reason = self.reason or reason

    def feed(self, raw):
        self.buffer += raw
        while b'\n' in self.buffer and not self.reason:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                event = strict_json(line.decode('utf-8'))
                if not isinstance(event, dict):
                    raise ValueError('invalid_event')
                self.event(event)
            except (ValueError, UnicodeError, RecursionError, TypeError):
                self.fail('invalid_jsonl')

    def event(self, event):
        if (self.state == 'request' and type(event.get('dispatch_count')) is int
                and event == {'type': 'pi.request', 'dispatch_count': 1}):
            self.dispatches = 1
            self.state = 'start'
        elif self.state == 'start' and event == {'type': 'pi.start', **IDENTITY}:
            self.state = 'result'
        elif self.state == 'result' and set(event) == {'type', 'message'} and event['type'] == 'pi.result':
            message = event['message']
            if (not isinstance(message, dict) or message.get('role') != 'assistant'
                    or any(message.get(key) != IDENTITY[key] for key in ('provider', 'model', 'api'))
                    or message.get('responseModel') not in (None, IDENTITY['model'])):
                self.fail('model_or_message_mismatch')
                return
            self.usage = _reported_usage(message)
            self.observed_model = message.get('responseModel')
            if message.get('stopReason') != 'stop' or message.get('diagnostics') or message.get('deferred'):
                self.fail('provider_not_completed')
                return
            content = message.get('content')
            if (not isinstance(content, list) or not content or any(
                    not isinstance(block, dict) or block.get('type') not in ('text', 'thinking')
                    or not isinstance(block.get('text' if block['type'] == 'text' else 'thinking'), str)
                    for block in content)):
                self.fail('tool_or_invalid_content')
                return
            self.text = ''.join(block['text'] for block in content if block['type'] == 'text')
            if not self.text or len(self.text.encode()) > 32768:
                self.fail('final_byte_limit')
                return
            if self.usage is None:
                self.fail('invalid_usage')
                return
            self.message = message
            self.state = 'completed'
        elif self.state == 'completed' and event == {'type': 'pi.completed'}:
            self.state = 'done'
        else:
            self.fail('unexpected_event')

    def finish(self):
        if self.buffer.strip() or self.state != 'done':
            self.fail('missing_terminal_evidence')

    @property
    def accounting_complete(self):
        return self.state == 'done' and not self.reason and self.usage is not None
