import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import CurriculumPackage


pytestmark = pytest.mark.django_db
WAGTAIL_ADD_URL = "/cms/snippets/curriculum/curriculumpackage/add/"


def editorial_reviewer():
    user = get_user_model().objects.create_user(
        username="editorial-reviewer",
        password="test-password",
        is_staff=True,
    )
    permissions = Permission.objects.filter(
        content_type__app_label="curriculum",
        content_type__model="curriculumpackage",
        codename__in=("add_curriculumpackage", "change_curriculumpackage"),
    )
    user.user_permissions.add(*permissions)
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="wagtailadmin",
            codename="access_admin",
        )
    )
    return user


def test_unauthenticated_people_cannot_open_the_wagtail_curriculum_editor():
    response = Client().get(WAGTAIL_ADD_URL)

    assert response.status_code == 302
    assert "/cms/login/" in response["Location"]


def test_staff_without_wagtail_package_permission_cannot_open_the_editor():
    user = get_user_model().objects.create_user(
        username="unprivileged-editor",
        password="test-password",
        is_staff=True,
    )
    client = Client()
    client.force_login(user)

    response = client.get(WAGTAIL_ADD_URL)

    assert response.status_code in (302, 403)
    assert response.status_code != 200


def test_authorized_editorial_reviewer_uses_wagtail_for_curriculum_authoring():
    client = Client()
    client.force_login(editorial_reviewer())

    response = client.get(WAGTAIL_ADD_URL)

    assert response.status_code == 200
    assert "CurriculumPackage" in response.text
    assert "Microlección" in response.text
    assert "Reactivos de opción única" in response.text
    assert "Guardar" in response.text
    assert "Publicar" not in response.text


def test_authorized_editorial_reviewer_can_save_an_incomplete_draft_in_wagtail():
    client = Client()
    client.force_login(editorial_reviewer())

    response = client.post(
        WAGTAIL_ADD_URL,
        {
            "title": "Fracciones: borrador Wagtail",
            "objective": "Distinguir una fracción de una cantidad entera.",
            "micro_lesson": "Una fracción representa partes iguales de un todo.",
            "final_explanation": "",
            "questions-count": "0",
            "action-save": "Guardar",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert "Fracciones: borrador Wagtail" in response.text


def test_wagtail_editor_can_save_an_incomplete_draft_and_see_structural_missing_fields():
    package = CurriculumPackage.objects.create(
        title="Fracciones: borrador",
        objective="Distinguir una fracción de una cantidad entera.",
        micro_lesson="Una fracción representa partes iguales de un todo.",
    )
    client = Client()
    client.force_login(editorial_reviewer())

    response = client.get(f"/cms/snippets/curriculum/curriculumpackage/edit/{package.pk}/")

    assert response.status_code == 200
    assert "Fracciones: borrador" in response.text
    assert "Agrega al menos un reactivo de opción única." in response.text
    assert "Agrega la explicación final." in response.text
    assert "La validación estructural no publica" in response.text


def test_structural_validation_keeps_literal_option_indexes_and_per_option_feedback():
    package = CurriculumPackage.objects.create(
        title="Fracciones: partes de un todo",
        objective="Reconocer partes iguales de un todo.",
        micro_lesson="El denominador indica en cuántas partes se divide el todo.",
        questions=[
            (
                "reactivo",
                {
                    "prompt": "¿Qué indica el denominador?",
                    "options": [
                        {
                            "position": 1,
                            "text": "Las partes en que se divide el todo",
                            "expected": True,
                            "feedback": "Correcto: indica las partes iguales.",
                        },
                        {
                            "position": 3,
                            "text": "El color del dibujo",
                            "expected": False,
                            "feedback": "Revisa el número de partes.",
                        },
                    ],
                    "hints": ["Observa el número de abajo."],
                },
            )
        ],
        final_explanation="El denominador cuenta las partes iguales.",
    )
    client = Client()
    client.force_login(editorial_reviewer())

    response = client.get(f"/cms/snippets/curriculum/curriculumpackage/edit/{package.pk}/")

    assert response.status_code == 200
    assert "falta la opción con índice literal 2" in response.text
    assert "Correcto: indica las partes iguales." in response.text
    assert "Revisa el" in response.text
    assert "La validación estructural no publica" in response.text


def test_wagtail_editor_shows_a_complete_demo_package_as_pending_human_review():
    package = CurriculumPackage.objects.create(
        title="Fracciones completas",
        objective="Reconocer partes iguales de un todo.",
        micro_lesson="El denominador indica las partes iguales.",
        questions=[
            (
                "reactivo",
                {
                    "prompt": "¿Qué indica el denominador?",
                    "options": [
                        {
                            "position": 1,
                            "text": "Las partes iguales",
                            "expected": True,
                            "feedback": "Correcto.",
                        },
                        {
                            "position": 2,
                            "text": "El color",
                            "expected": False,
                            "feedback": "Revisa la microlección.",
                        },
                    ],
                    "hints": ["Observa el número de abajo."],
                },
            )
        ],
        final_explanation="El denominador cuenta las partes iguales.",
    )
    client = Client()
    client.force_login(editorial_reviewer())

    response = client.get(f"/cms/snippets/curriculum/curriculumpackage/edit/{package.pk}/")

    assert response.status_code == 200
    assert "Validación estructural: completa" in response.text
    assert "La validación estructural no publica" in response.text


def test_student_view_remains_empty_for_a_complete_demo_draft():
    CurriculumPackage.objects.create(title="No publicar este DemoPackage")

    response = Client().get("/student/")

    assert response.status_code == 200
    assert "No publicar este DemoPackage" not in response.text
    assert "No hay paquetes publicados." in response.text
