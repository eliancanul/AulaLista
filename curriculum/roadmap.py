"""Deterministic navigation rules for published student roadmaps.

A published roadmap contains the package snapshot id for every activity.  The
roadmap therefore remains an ordered index while each activity keeps the exact
published practice payload it needs.  This module never reads live editorial
content or ephemeral cache state.
"""


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _children(value, *keys):
    value = _as_dict(value)
    for key in keys:
        children = value.get(key)
        if isinstance(children, list):
            return children
    return []


def _activity_snapshot_id(activity, fallback=None):
    activity = _as_dict(activity)
    for key in ("package_snapshot_id", "snapshot_id", "package_id"):
        value = activity.get(key)
        if value is not None:
            return value
    return fallback


def ordered_activities(payload, *, package_snapshot_id=None):
    """Return every activity in its published, deterministic traversal order.

    ``package_snapshot_id`` is retained as a compatibility fallback for old
    one-package payloads.  It is deliberately not a filter: a roadmap may
    contain activities backed by several package snapshots.
    """

    payload = _as_dict(payload)
    units = _children(payload, "units", "unidades")
    found = []
    for unit_index, unit in enumerate(units):
        unit = _as_dict(unit)
        unit_id = str(unit.get("id") or unit.get("unit_id") or f"u{unit_index}")
        lessons = _children(unit, "lessons", "lecciones")
        for lesson_index, lesson in enumerate(lessons):
            lesson = _as_dict(lesson)
            lesson_id = str(
                lesson.get("id")
                or lesson.get("lesson_id")
                or f"{unit_id}:l{lesson_index}"
            )
            activities = _children(lesson, "activities", "actividades")
            for activity_index, activity in enumerate(activities):
                activity = _as_dict(activity)
                activity_id = str(
                    activity.get("id")
                    or activity.get("activity_id")
                    or f"{lesson_id}:a{activity_index}"
                )
                found.append(
                    {
                        "id": activity_id,
                        "title": activity.get("title")
                        or activity.get("titulo")
                        or "Actividad",
                        "unit_title": unit.get("title")
                        or unit.get("titulo")
                        or "Unidad",
                        "lesson_title": lesson.get("title")
                        or lesson.get("titulo")
                        or "Lección",
                        "package_snapshot_id": _activity_snapshot_id(
                            activity, package_snapshot_id
                        ),
                        "unit_id": unit_id,
                        "lesson_id": lesson_id,
                        "unit_index": unit_index,
                        "lesson_index": lesson_index,
                        "activity_index": activity_index,
                    }
                )

    # Keep compatibility with the old flat roadmap payload shape.
    if not found and isinstance(payload.get("activities"), list):
        for index, activity in enumerate(payload["activities"]):
            activity = _as_dict(activity)
            found.append(
                {
                    "id": str(
                        activity.get("id")
                        or activity.get("activity_id")
                        or f"a{index}"
                    ),
                    "title": activity.get("title")
                    or activity.get("titulo")
                    or "Actividad",
                    "unit_title": payload.get("title") or "Unidad",
                    "lesson_title": activity.get("lesson_title") or "Lección",
                    "package_snapshot_id": _activity_snapshot_id(
                        activity, package_snapshot_id
                    ),
                    "unit_id": "u0",
                    "lesson_id": "u0:l0",
                    "unit_index": 0,
                    "lesson_index": 0,
                    "activity_index": index,
                }
            )
    return found


def ordered_nodes(payload):
    """Return selectable unit/lesson/activity nodes for teacher confirmation."""

    payload = _as_dict(payload)
    nodes = []
    units = _children(payload, "units", "unidades")
    for unit_index, unit in enumerate(units):
        unit = _as_dict(unit)
        unit_id = str(unit.get("id") or unit.get("unit_id") or f"u{unit_index}")
        nodes.append(
            {
                "id": unit_id,
                "kind": "unidad",
                "title": unit.get("title") or unit.get("titulo") or "Unidad",
            }
        )
        for lesson_index, lesson in enumerate(_children(unit, "lessons", "lecciones")):
            lesson = _as_dict(lesson)
            lesson_id = str(
                lesson.get("id")
                or lesson.get("lesson_id")
                or f"{unit_id}:l{lesson_index}"
            )
            nodes.append(
                {
                    "id": lesson_id,
                    "kind": "lección",
                    "title": lesson.get("title")
                    or lesson.get("titulo")
                    or "Lección",
                }
            )
            for activity_index, activity in enumerate(
                _children(lesson, "activities", "actividades")
            ):
                activity = _as_dict(activity)
                activity_id = str(
                    activity.get("id")
                    or activity.get("activity_id")
                    or f"{lesson_id}:a{activity_index}"
                )
                nodes.append(
                    {
                        "id": activity_id,
                        "kind": "actividad",
                        "title": activity.get("title")
                        or activity.get("titulo")
                        or "Actividad",
                    }
                )
    return nodes


def ordered_activity_ids(payload, *, package_snapshot_id=None):
    return [
        activity["id"]
        for activity in ordered_activities(
            payload,
            package_snapshot_id=package_snapshot_id,
        )
    ]


def states_for_progress(payload, completed_activity_ids, *, package_snapshot_id=None):
    """Return flat rows with explicit, deterministic roadmap states."""

    activities = ordered_activities(
        payload,
        package_snapshot_id=package_snapshot_id,
    )
    completed = {str(item) for item in completed_activity_ids}
    first_incomplete = next(
        (
            index
            for index, activity in enumerate(activities)
            if activity["id"] not in completed
        ),
        None,
    )
    rows = []
    for index, activity in enumerate(activities):
        if activity["id"] in completed:
            state = "COMPLETADA"
        elif index == first_incomplete:
            state = "ACTUAL"
        elif first_incomplete is not None and index == first_incomplete + 1:
            state = "DISPONIBLE"
        else:
            state = "BLOQUEADA"
        rows.append({**activity, "state": state})
    return rows


def states_for_group_progress(payload, completed_activity_ids, current_activity_id=None):
    """Derive the same navigation state for every client in a session."""
    activities = ordered_activities(payload)
    completed = {str(value) for value in (completed_activity_ids or [])}
    ids = [item["id"] for item in activities]
    current = str(current_activity_id) if current_activity_id in ids else None
    if current is None:
        current = next((item_id for item_id in ids if item_id not in completed), None)
    rows = []
    for index, activity in enumerate(activities):
        if activity["id"] in completed:
            state = "COMPLETADA"
        elif activity["id"] == current:
            state = "ACTUAL"
        elif current is not None and index == ids.index(current) + 1:
            state = "DISPONIBLE"
        else:
            state = "BLOQUEADA"
        rows.append({**activity, "state": state})
    return rows
