import os

import django
import pytest
from django.test import Client


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()


pytestmark = pytest.mark.django_db


def test_student_entrypoint_has_viewport_local_styles_and_clear_empty_state():
    response = Client().get("/student/")

    assert response.status_code == 200
    assert 'name="viewport"' in response.text
    assert "/static/curriculum/aulalista.css" in response.text
    assert "No hay sesiones activas." in response.text
    assert "http://" not in response.text
    assert "https://" not in response.text


def test_student_activity_uses_semantic_choices_and_does_not_expose_expected_answer():
    from tests.test_t08_pseudonymous_close import active_question_session

    session = active_question_session()
    assignment = session.device_assignments.get()
    client = Client()
    client.post(
        f"/student/sessions/{session.pk}/devices/{assignment.local_identifier}/turn/start/",
        {"display_name": "Luna"},
    )
    response = client.get(f"/student/sessions/{session.pk}/activity/")

    assert response.status_code == 200
    assert "fieldset" in response.text
    assert "legend" in response.text
    assert 'type="radio"' in response.text
    assert "expected" not in response.text.lower()
    assert "correcta" not in response.text.lower()


def test_local_css_has_focus_targets_and_non_color_feedback():
    from pathlib import Path

    css = (
        Path(__file__).parents[1] / "static" / "curriculum" / "aulalista.css"
    ).read_text(encoding="utf-8")

    assert "focus-visible" in css
    assert "min-block-size: 2.75rem" in css
    assert "outline: 4px solid var(--color-focus)" in css
    assert ".button-secondary" in css
    assert ".button-danger" in css
    assert ".error" in css
    assert "@media" in css
