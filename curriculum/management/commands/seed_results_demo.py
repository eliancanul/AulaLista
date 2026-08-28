"""Create an owner-scoped, repeatable synthetic teacher-results scenario."""

import hashlib
import json
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import (
    ClassroomGroup,
    ClassroomSession,
    CurriculumPackage,
    PublishedPackageSnapshot,
    PublishedRoadmapSnapshot,
    PseudonymousResult,
)


def _digest(payload):
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Command(BaseCommand):
    help = "Carga un escenario sintético local con roadmap, salón y sesiones cerradas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username", default="results-demo-teacher",
            help="Cuenta staff que será dueña del escenario sintético.",
        )

    @staticmethod
    def _namespace(teacher, label):
        """Use an owner-stable key; later foreign rows cannot cause drift."""

        return f"Resultados demo · {teacher.pk} · {label}"[:160]

    def _package_and_snapshot(self, teacher, title):
        payload = {
            "title": title,
            "objective": "Reconocer partes iguales de un todo.",
            "micro_lesson": "El denominador indica cuántas partes iguales hay.",
            "questions": [],
            "final_explanation": "La representación conserva partes iguales.",
        }
        digest = _digest(payload)
        package_title = self._namespace(teacher, title)
        package = CurriculumPackage.objects.filter(
            created_by=teacher, title=package_title
        ).first()
        if package is None:
            package = CurriculumPackage.objects.create(
                title=package_title,
                objective=payload["objective"],
                micro_lesson=payload["micro_lesson"],
                final_explanation=payload["final_explanation"],
                created_by=teacher,
                is_demo=True,
            )
        elif not package.is_demo:
            raise RuntimeError(
                f"El paquete demo existente para {package.title!r} no es sintético; "
                "no se modificó ningún dato."
            )
        elif any(
            getattr(package, field) != payload[field]
            for field in ("objective", "micro_lesson", "final_explanation")
        ):
            raise RuntimeError(
                f"El paquete demo existente para {package.title!r} no coincide; "
                "no se modificó ningún dato."
            )
        snapshot = PublishedPackageSnapshot.objects.filter(
            package=package, version=1
        ).first()
        if snapshot is not None:
            if (
                snapshot.package.created_by_id != teacher.pk
                or snapshot.published_by_id != teacher.pk
                or snapshot.payload != payload
                or snapshot.sha256 != digest
            ):
                raise RuntimeError(
                    f"El snapshot demo existente para {package.title!r} no coincide; "
                    "no se modificó ningún dato."
                )
            return package, snapshot
        revision = package.save_revision(user=teacher)
        snapshot = PublishedPackageSnapshot.objects.create(
            package=package, version=1, payload=payload, sha256=digest,
            source_revision=revision, published_by=teacher,
        )
        return package, snapshot

    def _roadmap(self, teacher, snapshots):
        payload = {
            "units": [{
                "id": "unidad-fracciones", "title": "Fracciones",
                "lessons": [{
                    "id": "leccion-partes", "title": "Partes iguales",
                    "activities": [
                        {
                            "id": "actividad-partes",
                            "title": snapshots[0].payload["title"],
                            "package_snapshot_id": snapshots[0].pk,
                        },
                        {
                            "id": "actividad-denominador",
                            "title": snapshots[1].payload["title"],
                            "package_snapshot_id": snapshots[1].pk,
                        },
                    ],
                }],
            }],
        }
        digest = _digest(payload)
        title = "Roadmap · Fracciones"
        roadmap_title = self._namespace(teacher, title)
        if PublishedRoadmapSnapshot.objects.filter(
            title=roadmap_title, version=1
        ).exclude(published_by=teacher).exists():
            raise RuntimeError(
                "El namespace del roadmap demo pertenece a otra maestra; "
                "no se modificó ningún dato."
            )
        roadmap = PublishedRoadmapSnapshot.objects.filter(
            published_by=teacher, title=roadmap_title, version=1
        ).first()
        if roadmap is not None:
            if roadmap.payload != payload or roadmap.sha256 != digest:
                raise RuntimeError(
                    "El roadmap demo existente no coincide; no se modificó ningún dato."
                )
            return roadmap
        return PublishedRoadmapSnapshot.objects.create(
            title=roadmap_title, version=1, payload=payload, sha256=digest,
            published_by=teacher
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        teacher, _ = User.objects.get_or_create(
            username=options["username"],
            defaults={"is_staff": True, "is_active": True},
        )
        if not teacher.is_staff or not teacher.is_active:
            self.stderr.write("La cuenta del escenario debe ser staff activa.")
            return
        titles = ("Fracciones · partes iguales", "Fracciones · denominador")
        snapshots = [self._package_and_snapshot(teacher, title)[1] for title in titles]
        roadmap = self._roadmap(teacher, snapshots)
        group, _ = ClassroomGroup.objects.get_or_create(
            created_by=teacher, name="Resultados demo"
        )
        sessions = []
        for activity_id, snapshot in zip(
            ("actividad-partes", "actividad-denominador"), snapshots
        ):
            session = ClassroomSession.objects.filter(
                created_by=teacher, snapshot=snapshot, roadmap_snapshot=roadmap
            ).first()
            if session is None:
                session = ClassroomSession.prepare_from_snapshot(
                    snapshot, 2, 2, roadmap_snapshot=roadmap,
                    classroom_group=group, teacher=teacher,
                )
                session.confirm()
                session.close()
            elif session.classroom_group_id != group.pk:
                session.classroom_group = group
                session.save(update_fields=["classroom_group"])
            if not PseudonymousResult.objects.filter(
                result_batch_id=session.result_batch_id
            ).exists():
                PseudonymousResult.objects.create(
                    result_batch_id=session.result_batch_id,
                    participant_key=uuid.uuid4(), activity_id=activity_id,
                    snapshot_id=snapshot.pk, snapshot_version=snapshot.version,
                    snapshot_sha256=snapshot.sha256, state=PseudonymousResult.STATE_COMPLETED,
                    duration_seconds=45,
                    responses=[
                        {
                            "question_index": 0,
                            "selected_position": 1,
                            "is_correct": True,
                        }
                    ],
                    score=1, help_requests=[], technical_errors=[],
                )
            sessions.append(session)
        self.stdout.write(self.style.SUCCESS(
            f"Escenario sintético listo: roadmap, salón y {len(sessions)} sesiones cerradas."
        ))
