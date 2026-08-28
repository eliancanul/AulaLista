"""Issue #94: teacher-owned curriculum never crosses account boundaries."""

import hashlib
import json
import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import Client
from django.urls import reverse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import (  # noqa: E402
    CurriculumImportJob,
    CurriculumPackage,
    PublishedPackageSnapshot,
    PublishedRoadmapSnapshot,
)
from curriculum.views import _import_action_convert  # noqa: E402


pytestmark = pytest.mark.django_db


def teacher(username):
    user = get_user_model().objects.create_user(username=username, is_staff=True)
    client = Client()
    client.force_login(user)
    return user, client


def snapshot(owner, title):
    package = CurriculumPackage.objects.create(title=title, created_by=owner)
    revision = package.save_revision(user=owner)
    payload = {"title": title, "objective": "Objetivo", "questions": []}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=digest,
        source_revision=revision,
        published_by=owner,
    )


def test_teacher_curriculum_routes_and_mutations_are_owner_scoped():
    first, first_client = teacher("maestra-uno")
    second, second_client = teacher("maestra-dos")
    first_snapshot = snapshot(first, "Contenido privado uno")
    second_snapshot = snapshot(second, "Contenido privado dos")
    first_job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("uno.pdf", b"%PDF-1.4"),
        created_by=first,
    )
    second_job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("dos.pdf", b"%PDF-1.4"),
        created_by=second,
    )

    listing = first_client.get(reverse("tutor-curriculum"))
    roadmaps = first_client.get(reverse("tutor-roadmaps"))
    assert "Contenido privado uno" in listing.text
    assert "Contenido privado dos" not in listing.text
    assert reverse("tutor-import-detail", args=[first_job.pk]) in listing.text
    assert reverse("tutor-import-detail", args=[second_job.pk]) not in listing.text
    assert "Contenido privado uno" in roadmaps.text
    assert "Contenido privado dos" not in roadmaps.text

    for route in (
        reverse("tutor-package-detail", args=[second_snapshot.pk]),
        reverse("tutor-session-prepare", args=[second_snapshot.pk]),
        reverse("tutor-import-detail", args=[second_job.pk]),
        reverse("tutor-import-wait", args=[second_job.pk]),
        reverse("tutor-import-log-md", args=[second_job.pk]),
        reverse("tutor-import-log-json", args=[second_job.pk]),
    ):
        assert first_client.get(route).status_code == 404

    response = first_client.post(
        reverse("tutor-roadmaps"),
        {"title": "Cruce prohibido", "package": [second_snapshot.pk]},
    )
    assert response.status_code == 200
    assert not PublishedRoadmapSnapshot.objects.filter(title="Cruce prohibido").exists()


def test_import_conversion_preserves_the_teacher_owner():
    owner, _client = teacher("maestra-propuestas")
    job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("curricula.pdf", b"%PDF-1.4"),
        created_by=owner,
        activities=[
            {
                "is_valid": True,
                "proposal": {
                    "title": "Borrador propio",
                    "objective": "Practicar",
                    "micro_lesson": "Explicación",
                    "final_explanation": "Cierre",
                    "questions": [],
                },
            }
        ],
    )
    post = QueryDict("", mutable=True)
    post.setlist("select", ["0"])

    assert _import_action_convert(job, post) == 1
    assert CurriculumPackage.objects.get(title="Borrador propio").created_by == owner


def test_a_teacher_cannot_publish_another_teachers_package():
    owner, _ = teacher("maestra-propietaria")
    other, _ = teacher("maestra-ajena")
    package = CurriculumPackage.objects.create(title="Borrador privado", created_by=owner)

    with pytest.raises(Exception, match="propietaria"):
        package.publish(object(), user=other)
