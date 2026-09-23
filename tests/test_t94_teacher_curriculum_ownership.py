"""Issue #94: teacher-owned curriculum never crosses account boundaries."""

import hashlib
import json
import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import Client
from django.urls import reverse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import (  # noqa: E402
    ClassroomSession,
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


def roadmap(owner, package_snapshot, title):
    return PublishedRoadmapSnapshot.objects.create(
        title=title,
        version=PublishedRoadmapSnapshot.objects.count() + 1,
        payload={
            "title": title,
            "units": [{
                "id": "unit-1",
                "title": "Unidad",
                "lessons": [{
                    "id": "lesson-1",
                    "title": "Lección",
                    "activities": [{
                        "id": "activity-1",
                        "title": package_snapshot.payload["title"],
                        "package_snapshot_id": package_snapshot.pk,
                    }],
                }],
            }],
        },
        sha256="computed-by-model",
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
    assert f'data-job-id="{first_job.pk}"' in listing.text
    assert f'data-job-id="{second_job.pk}"' not in listing.text
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


@pytest.mark.parametrize("factory", ["prepare", "start"])
def test_session_factories_reject_cross_owner_snapshot_and_roadmap(factory):
    owner, _ = teacher(f"maestra-factory-{factory}")
    other, _ = teacher(f"maestra-otra-{factory}")
    own_snapshot = snapshot(owner, f"Actividad propia {factory}")
    other_snapshot = snapshot(other, f"Actividad ajena {factory}")
    own_roadmap = roadmap(owner, own_snapshot, f"Roadmap propio {factory}")
    other_roadmap = roadmap(other, other_snapshot, f"Roadmap ajeno {factory}")
    mixed_roadmap = roadmap(owner, other_snapshot, f"Roadmap mixto {factory}")

    def invoke(package_snapshot, published_roadmap):
        if factory == "prepare":
            return ClassroomSession.prepare_from_snapshot(
                package_snapshot,
                1,
                1,
                roadmap_snapshot=published_roadmap,
                teacher=owner,
            )
        return ClassroomSession.start_from_snapshot(
            package_snapshot,
            roadmap_snapshot=published_roadmap,
            teacher=owner,
        )

    with pytest.raises(ValidationError, match="propietaria"):
        invoke(other_snapshot, own_roadmap)
    with pytest.raises(ValidationError, match="propietaria"):
        invoke(own_snapshot, other_roadmap)
    with pytest.raises(ValidationError, match="propietaria"):
        invoke(own_snapshot, mixed_roadmap)
    assert not ClassroomSession.objects.exists()


def test_unowned_draft_cannot_be_claimed_implicitly_by_saving_a_revision():
    first, _ = teacher("maestra-reclamo-uno")
    second, _ = teacher("maestra-reclamo-dos")
    unowned = CurriculumPackage.objects.create(title="Legado sin atribución")

    with pytest.raises(ValidationError, match="atribución explícita"):
        unowned.save_revision(user=first)
    unowned.refresh_from_db()
    assert unowned.created_by_id is None

    owned = CurriculumPackage.objects.create(title="Borrador propio", created_by=first)
    with pytest.raises(ValidationError, match="propietaria"):
        owned.save_revision(user=second)
