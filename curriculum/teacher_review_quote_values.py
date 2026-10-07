"""Conservative labelled-answer boundary, never a value rewriter.

Only a complete block of exact display-label entries is treated as structured
metadata. Everything else remains free prose for the existing semantic checks.
The original answer, quote, punctuation and whitespace are never modified.
"""
import re

VALUE_QUOTE_INSTRUCTIONS = """For labelled replies (<asked display label>: <value>), quote only VALUE, excluding
the label and delimiter. Match the FULL label, which may contain colons. Preserve
labels/colons inside quoted or literal content. Never strip prose prefixes by
heuristic. If the label, value or target association is ambiguous, do not update.
"""


class AmbiguousLabelledAnswer(ValueError):
    """Known labels exist but cannot be assigned to one value per target."""


def _quote_state(text, state):
    pairs = {'"': '"', "'": "'", '`': '`', '«': '»', '“': '”', '‘': '’'}
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        previous = text[index - 1] if index else ''
        following = text[index + 1] if index + 1 < len(text) else ''
        # Apostrophes within words (l'élève, don't, l’élève) are not quote marks.
        if char in ("'", '’') and previous.isalnum() and following.isalnum():
            index += 1
            continue
        if state == '```':
            if text.startswith('```', index):
                state = None; index += 3; continue
        elif state is not None:
            if char == state: state = None
        elif text.startswith('```', index):
            state = '```'; index += 3; continue
        elif char in pairs:
            state = pairs[char]
        index += 1
    return state


def labelled_value_spans(answer, turn, all_targets):
    """Exact per-target ranges, None for prose, or explicit label ambiguity.

    The first nonblank line must start with an exact asked display label and a
    colon (case-insensitive, no fuzzy aliases or Unicode normalization). A new
    known label outside quoted content starts the next field. Other lines are
    literal continuations. Duplicated/overlapping labels reject assignment.
    """
    if not isinstance(answer, str) or not isinstance(turn, dict):
        return None
    records = {record['target_id']: record for record in all_targets}
    patterns = []
    for target_id in turn.get('targets', []):
        record = records.get(target_id)
        label = record.get('human_label') if record else None
        if not isinstance(label, str) or not label or '\n' in label or '\r' in label:
            return None
        patterns.append((target_id, re.compile(r'^[ \t]*' + re.escape(label) + r'[ \t]*:[ \t]*', re.IGNORECASE)))
    if not patterns:
        return None
    spans, offset, active, quote = {}, 0, None, None
    for physical in answer.splitlines(keepends=True):
        line = physical.rstrip('\r\n')
        if not line.strip() and active is None:
            offset += len(physical)
            continue
        matches = [(target_id, pattern.match(line)) for target_id, pattern in patterns] if quote is None else []
        matches = [(target_id, match) for target_id, match in matches if match is not None]
        if len(matches) > 1:
            raise AmbiguousLabelledAnswer('ambiguous_answer_labels')
        if matches:
            target_id, match = matches[0]
            if target_id in spans:
                raise AmbiguousLabelledAnswer('duplicate_answer_label')
            active = target_id
            spans[active] = [offset + match.end(), offset + len(line)]
            quote = _quote_state(line[match.end():], None)
        elif active is None:
            return None  # The answer begins as prose/quotation, not a field block.
        else:
            spans[active][1] = offset + len(line)
            quote = _quote_state(line, quote)
        offset += len(physical)
    if quote is not None:
        raise AmbiguousLabelledAnswer('unclosed_answer_quotation')
    return {target: tuple(span) for target, span in spans.items()} or None


def quote_matches_labelled_value(quote, target_id, turn, all_targets):
    """No rewriting: reject metadata/cross-field quotes in unambiguous blocks."""
    try:
        spans = labelled_value_spans(turn.get('answer'), turn, all_targets)
    except AmbiguousLabelledAnswer:
        return False
    if spans is None:
        return True  # Free prose; this helper makes no semantic claim about it.
    if target_id not in spans:
        return False
    start, end = spans[target_id]
    return isinstance(quote, str) and bool(quote.strip()) and quote in turn['answer'][start:end]
