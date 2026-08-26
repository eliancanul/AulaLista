"""Deterministic navigation rules for published student roadmaps.

This module has no AI or live-editorial dependencies. Its inputs are immutable
snapshot payloads and the pseudonymous completion list, so the same inputs
always produce the same next step.
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


def ordered_activities(payload, *, package_snapshot_id=None):
    """Return activities in their published, deterministic traversal order."""

    payload = _as_dict(payload)
    units = _children(payload, "units", "unidades")
    found = []
    for unit_index, unit in enumerate(units):
        unit = _as_dict(unit)
        lessons = _children(unit, "lessons", "lecciones")
        for lesson_index, lesson in enumerate(lessons):
            lesson = _as_dict(lesson)
            activities = _children(lesson, "activities", "actividades")
            for activity_index, activity in enumerate(activities):
                activity = _as_dict(activity)
                activity_package_id = activity.get("package_snapshot_id")
                if activity_package_id is None:
                    activity_package_id = activity.get("snapshot_id")
                if activity_package_id is None:
                    activity_package_id = activity.get("package_id")
                if (
                    package_snapshot_id is not None
                    and activity_package_id is not None
                    and str(activity_package_id) != str(package_snapshot_id)
                ):
                    continue
                activity_id = activity.get("id") or activity.get("activity_id")
                if activity_id is None:
                    activity_id = f"u{unit_index}:l{lesson_index}:a{activity_index}"
                found.append(
                    {
                        "id": str(activity_id),
                        "title": activity.get("title") or activity.get("titulo") or "Actividad",
                        "unit_title": unit.get("title") or unit.get("titulo") or "Unidad",
                        "lesson_title": lesson.get("title") or lesson.get("titulo") or "Lección",
                        "unit_index": unit_index,
                        "lesson_index": lesson_index,
                        "activity_index": activity_index,
                    }
                )

    # A package snapshot may represent one activity while an older roadmap
    # payload has not yet been expanded to units and lessons.
    if not found and payload.get("activities"):
        for index, activity in enumerate(payload["activities"]):
            activity = _as_dict(activity)
            activity_package_id = (
                activity.get("package_snapshot_id")
                or activity.get("snapshot_id")
                or activity.get("package_id")
            )
            if (
                package_snapshot_id is not None
                and activity_package_id is not None
                and str(activity_package_id) != str(package_snapshot_id)
            ):
                continue
            found.append(
                {
                    "id": str(activity.get("id") or activity.get("activity_id") or f"a{index}"),
                    "title": activity.get("title") or activity.get("titulo") or "Actividad",
                    "unit_title": payload.get("title") or "Unidad",
                    "lesson_title": activity.get("lesson_title") or "Lección",
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
        nodes.append({"id": unit_id, "kind": "unidad", "title": unit.get("title") or unit.get("titulo") or "Unidad"})
        for lesson_index, lesson in enumerate(_children(unit, "lessons", "lecciones")):
            lesson = _as_dict(lesson)
            lesson_id = str(lesson.get("id") or lesson.get("lesson_id") or f"{unit_id}:l{lesson_index}")
            nodes.append({"id": lesson_id, "kind": "lección", "title": lesson.get("title") or lesson.get("titulo") or "Lección"})
            for activity_index, activity in enumerate(_children(lesson, "activities", "actividades")):
                activity = _as_dict(activity)
                activity_id = str(activity.get("id") or activity.get("activity_id") or f"{lesson_id}:a{activity_index}")
                nodes.append({"id": activity_id, "kind": "actividad", "title": activity.get("title") or activity.get("titulo") or "Actividad"})
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
    """Return flat display rows with explicit textual roadmap states.

    Only the first incomplete activity is ``ACTUAL`` and only the immediate
    following activity is ``DISPONIBLE``. Later activities remain ``BLOQUEADA``
    until the deterministic sequence reaches them. Completion says nothing
    about mastery, approval, grading or curriculum progress.
    """

    activities = ordered_activities(
        payload,
        package_snapshot_id=package_snapshot_id,
    )
    completed = {str(item) for item in completed_activity_ids}
    first_incomplete = next(
        (index for index, activity in enumerate(activities) if activity["id"] not in completed),
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
