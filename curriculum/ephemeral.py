"""Close-only T08 summaries kept outside the educational database."""

from django.core.cache import cache


EPHEMERAL_SUMMARY_TTL = 12 * 60 * 60
EPHEMERAL_SUMMARY_KEY_PREFIX = "aulalista.t08.ephemeral-summary"
HINT_PROGRESS_KEY_PREFIX = "aulalista.practice.hint-progress"


def ephemeral_session_summary_key(session_id):
    return f"{EPHEMERAL_SUMMARY_KEY_PREFIX}:{session_id}"


def _summary(session_id):
    return cache.get(ephemeral_session_summary_key(session_id)) or {"turns": {}}


def ensure_ephemeral_turn_summary(session_id, turn):
    summary = _summary(session_id)
    turn_key = str(turn.pk)
    turn_summary = summary["turns"].setdefault(
        turn_key,
        {
            "state": "active",
            "started_at": turn.started_at.isoformat(),
            "completed_at": None,
            "responses": [],
            "help_requests": [],
            "technical_errors": [],
        },
    )
    cache.set(
        ephemeral_session_summary_key(session_id),
        summary,
        timeout=EPHEMERAL_SUMMARY_TTL,
    )
    return turn_summary


def update_ephemeral_turn_summary(session_id, turn, **updates):
    summary = _summary(session_id)
    turn_summary = ensure_ephemeral_turn_summary(session_id, turn)
    turn_summary.update(updates)
    summary["turns"][str(turn.pk)] = turn_summary
    cache.set(
        ephemeral_session_summary_key(session_id),
        summary,
        timeout=EPHEMERAL_SUMMARY_TTL,
    )


def record_ephemeral_response(session_id, turn, result):
    turn_summary = ensure_ephemeral_turn_summary(session_id, turn)
    responses = [
        response
        for response in turn_summary["responses"]
        if response["question_index"] != result.question_index
    ]
    responses.append(
        {
            "question_index": result.question_index,
            "selected_position": result.selected_position,
            "is_correct": result.is_correct,
        }
    )
    update_ephemeral_turn_summary(session_id, turn, responses=responses)


def record_ephemeral_help(session_id, turn, question_index, assistance):
    turn_summary = ensure_ephemeral_turn_summary(session_id, turn)
    help_request = {"kind": assistance.kind, "question_index": question_index}
    if assistance.hint_index is not None:
        help_request["hint_index"] = assistance.hint_index
    update_ephemeral_turn_summary(
        session_id,
        turn,
        help_requests=[*turn_summary["help_requests"], help_request],
    )


def read_ephemeral_session_summary(session_id):
    return _summary(session_id)


def clear_ephemeral_session_summary(session_id):
    cache.delete(ephemeral_session_summary_key(session_id))


def clear_practice_cache(turn_id, question_indices):
    """Clear all T05/T07 hint progression keys for a temporary turn."""

    for question_index in question_indices:
        progress_key = f"{HINT_PROGRESS_KEY_PREFIX}:{turn_id}:{question_index}"
        consumed_index_key = (
            f"{HINT_PROGRESS_KEY_PREFIX}:consumed-index:{turn_id}:{question_index}"
        )
        consumed_keys = cache.get(consumed_index_key, []) or []
        cache.delete_many([progress_key, consumed_index_key, *consumed_keys])
