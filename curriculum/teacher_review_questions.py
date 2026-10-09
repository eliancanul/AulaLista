"""Question scope is smaller than the complete source/review context.

This policy selects unresolved blockers, never confirms source facts, and never
writes a dossier. Optional blanks and already-extracted facts remain available
for explicit human review without becoming an automatic questionnaire.
"""
MAX_QUESTION_TARGETS = 3
MAX_QUESTION_CHARACTERS = 500


def _group_key(item):
    scope, name = item["scope"], item["field_name"]
    if scope == "general":
        if name in ("proyecto", "campos_formativos"):
            return (scope, "", "identificacion_curricular")
        if name in ("proposito", "finalidad"):
            return (scope, "", "intencion_pedagogica")
    if scope == "session" and name in ("inicio", "desarrollo", "cierre"):
        return (scope, item["session_id"], "momentos_de_la_sesion")
    # A conflict in another field, or an unlinked annex, deserves its own focus.
    return (scope, item.get("session_id") or "", item["target_id"])


def question_policy(all_targets):
    candidates = [item for item in all_targets
                  if item["priority_state"] == "requires_resolution"]
    groups = {}
    for item in candidates:
        key = _group_key(item)
        groups.setdefault(key, []).append(item["target_id"])
    return {
        "version": 1,
        "candidate_target_ids": [item["target_id"] for item in candidates],
        "max_targets_per_question": MAX_QUESTION_TARGETS,
        "max_question_characters": MAX_QUESTION_CHARACTERS,
        "groups": [{"scope": scope, "session_id": session_id or None,
                    "topic": topic, "target_ids": ids}
                   for (scope, session_id, topic), ids in groups.items()],
        "other_pending_items": "explicit_human_review_not_automatic_questions",
    }


def question_scope_error(question, asked, policy):
    if question is None:
        return None
    if len(question) > MAX_QUESTION_CHARACTERS:
        return "question_too_long"
    if len(asked) > MAX_QUESTION_TARGETS:
        return "question_too_many_targets"
    if policy is not None:
        if any(target not in policy["candidate_target_ids"] for target in asked):
            return "question_has_no_required_gap"
        if not any(set(asked).issubset(group["target_ids"]) for group in policy["groups"]):
            return "question_incoherent_group"
    return None
