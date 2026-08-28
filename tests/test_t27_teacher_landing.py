import hashlib
import json
import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from curriculum.models import ClassroomSession, CurriculumPackage, PublishedPackageSnapshot
from helpers import tutor_client, tutor_client_for_sessions

pytestmark = pytest.mark.django_db


def snapshot(title, version=1, owner=None):
    owner = owner or get_user_model().objects.create_user(
        username=f"editor-{CurriculumPackage.objects.count() + 1}"
    )
    package = CurriculumPackage.objects.create(title=title, created_by=owner)
    revision = package.save_revision(user=owner)
    payload = {"title": title, "questions": []}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=version,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        source_revision=revision,
        published_by=owner,
    )


def test_landing_is_authorized_and_offers_recent_published_choices():
    client = tutor_client()
    owner = get_user_model().objects.get(pk=client.session["_auth_user_id"])
    published = snapshot("Actividad publicada", version=4, owner=owner)
    response = client.get(reverse("tutor-sessions"))

    assert response.status_code == 200
    assert "Actividad publicada" in response.text
    assert "versión 4" in response.text
    assert published.sha256[:8] in response.text
    assert reverse("tutor-session-prepare", args=[published.pk]) in response.text
    assert "Importar currícula" in response.text
    assert "EditorialReviewer" in response.text
    assert "IA" in response.text
    assert "activa" in response.text.lower()

    anonymous = Client().get(reverse("tutor-sessions"))
    assert anonymous.status_code == 302
    assert "login" in anonymous["Location"].lower()


def test_landing_has_state_actions_and_participant_waiting_language():
    published = snapshot("Estados de aula")
    prepared = ClassroomSession.prepare_from_snapshot(published, 2, 1)
    active_waiting = ClassroomSession.prepare_from_snapshot(published, 2, 1)
    active_waiting.confirm()
    active_progress = ClassroomSession.prepare_from_snapshot(published, 2, 1)
    active_progress.confirm()
    active_progress.device_assignments.get().reserve_turn("alias")
    closed = ClassroomSession.prepare_from_snapshot(published, 2, 1)
    closed.confirm()
    closed.close()
    stopped = ClassroomSession.prepare_from_snapshot(published, 2, 1)
    stopped.stop()

    text = tutor_client_for_sessions(
        prepared, active_waiting, active_progress, closed, stopped
    ).get(reverse("tutor-sessions")).text
    assert text.count("Revisar y activar") == 1
    assert text.count("Esperando participantes") == 1
    assert text.count("Actividad en progreso") == 1
    assert text.count("Revisar resultados y exportar") == 1
    assert text.count(">Revisar</a>") == 1
    assert reverse("tutor-session-active", args=[active_waiting.pk]) in text
    assert reverse("session-projection", args=[active_waiting.pk]) in text
    assert reverse("tutor-session-active", args=[active_progress.pk]) in text
    assert reverse("session-projection", args=[active_progress.pk]) in text
    assert "1 participante" in text
    assert "0 participantes" in text
    assert "capacidad" not in text.lower()
    assert "puntuación" not in text.lower()
    assert "local_identifier" not in text
    assert "Estados de aula" in text
    assert str(prepared.pk) not in re.findall(r"Sesión\s+\d+", text)


def test_landing_css_contract_is_local_responsive_touch_and_reduced_motion():
    html = tutor_client().get(reverse("tutor-sessions")).text
    assert 'static "curriculum/teacher_landing.css"' in html or "teacher_landing.css" in html
    css = open("static/curriculum/teacher_landing.css", encoding="utf-8").read()
    assert "prefers-reduced-motion" in css
    assert "min-width: 44px" in css or "min-block-size: 44px" in css
    assert "@media" in css
    assert ":focus-visible" in css
    assert "grid-template-columns" in css
    assert "http://" not in css and "https://" not in css
