import hashlib
import json
import os
import re
import unicodedata
import uuid
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Max
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThanOrEqual
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils import timezone
from wagtail import blocks
from wagtail.admin import messages as wagtail_messages
from wagtail.admin.modal_workflow import render_modal_workflow
from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField
from wagtail.models import (
    DraftStateMixin,
    RevisionMixin,
    TaskState,
    WorkflowMixin,
    WorkflowState,
)
from wagtail.permissions import ModelPermissionPolicy
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, WorkflowActionView

from curriculum.distribution import calculate_distribution, validate_distribution


EDITORIAL_REVIEWER_GROUP_NAME = "EditorialReviewer"


def _parse_cached_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _canonical_payload_sha256(payload):
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_published_payload(payload):
    """Convert Wagtail's serialized StreamField shape to the runtime shape."""

    normalized = dict(payload)
    questions = normalized.get("questions") or []
    if isinstance(questions, str):
        questions = json.loads(questions)

    normalized_questions = []
    for question in questions:
        if not isinstance(question, dict):
            raise ValidationError("El snapshot contiene un reactivo inválido.")
        value = dict(question.get("value") or {})
        value["options"] = [
            dict(option.get("value") or {})
            if isinstance(option, dict) and option.get("type") == "item"
            else option
            for option in value.get("options", []) or []
        ]
        value["hints"] = [
            hint.get("value")
            if isinstance(hint, dict) and hint.get("type") == "item"
            else hint
            for hint in value.get("hints", []) or []
        ]
        normalized_questions.append(
            {"type": question.get("type", "reactivo"), "value": value}
        )
    normalized["questions"] = normalized_questions
    return normalized


class CurriculumOptionBlock(blocks.StructBlock):
    position = blocks.IntegerBlock(
        label="Índice literal de la opción",
        required=False,
    )
    text = blocks.TextBlock(label="Texto de la opción", required=False)
    expected = blocks.BooleanBlock(label="Respuesta esperada", required=False)
    feedback = blocks.TextBlock(label="Retroalimentación de esta opción", required=False)

    class Meta:
        icon = "list-ul"


class CurriculumQuestionBlock(blocks.StructBlock):
    prompt = blocks.TextBlock(label="Enunciado del reactivo", required=False)
    options = blocks.ListBlock(
        CurriculumOptionBlock(),
        label="Opciones ordenadas",
        required=False,
    )
    hints = blocks.ListBlock(
        blocks.TextBlock(label="Pista", required=False),
        label="Pistas autorizadas",
        required=False,
    )

    class Meta:
        icon = "help"


class CurriculumPackage(WorkflowMixin, DraftStateMixin, RevisionMixin, models.Model):
    """A Wagtail-authored DemoPackage with human approval before publication."""

    title = models.CharField("título", max_length=160, blank=True)
    objective = models.TextField("objetivo", blank=True)
    micro_lesson = models.TextField("microlección", blank=True)
    questions = StreamField(
        [("reactivo", CurriculumQuestionBlock())],
        verbose_name="reactivos de opción única",
        blank=True,
    )
    final_explanation = models.TextField("explicación final autorizada", blank=True)
    validation_summary = models.TextField(
        "validación estructural",
        blank=True,
        editable=False,
    )
    is_demo = models.BooleanField("DemoPackage", default=True, editable=False)
    ai_assisted = models.BooleanField(
        "borrador asistido por IA",
        default=False,
        editable=False,
        help_text=(
            "True si el borrador fue generado con asistencia de IA. No implica "
            "validación pedagógica ni autorización de publicación."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        FieldPanel("title"),
        FieldPanel("objective"),
        FieldPanel("micro_lesson"),
        FieldPanel("questions"),
        FieldPanel("final_explanation"),
        FieldPanel("validation_summary", read_only=True),
        FieldPanel("ai_assisted", read_only=True),
    ]

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = "CurriculumPackage"
        verbose_name_plural = "CurriculumPackages"

    def __str__(self):
        return self.title or f"CurriculumPackage {self.pk}"

    def structural_validation(self):
        """Explain structural gaps without blocking draft saves or publishing anything."""

        missing = []
        if not self.title.strip():
            missing.append("Agrega un título.")
        if not self.objective.strip():
            missing.append("Agrega un objetivo.")
        if not self.micro_lesson.strip():
            missing.append("Agrega la microlección.")
        if not self.final_explanation.strip():
            missing.append("Agrega la explicación final.")

        questions = self.questions or []
        if not questions:
            missing.append("Agrega al menos un reactivo de opción única.")
        else:
            for position, question_block in enumerate(questions, start=1):
                if getattr(question_block, "block_type", "reactivo") != "reactivo":
                    continue
                self._validate_question(question_block.value, position, missing)

        return {"is_valid": not missing, "missing": missing}

    @classmethod
    def _validate_question(cls, question, position, missing):
        label = f"El reactivo {position}"
        if not isinstance(question, dict) and not hasattr(question, "get"):
            missing.append(f"{label} necesita una estructura de opción única.")
            return

        if not str(question.get("prompt", "")).strip():
            missing.append(f"{label} necesita un enunciado.")

        try:
            options = list(question.get("options", []) or [])
        except TypeError:
            options = []
        if len(options) < 2:
            missing.append(f"{label} necesita al menos dos opciones ordenadas.")

        literal_positions = []
        expected_count = 0
        for option_position, option in enumerate(options, start=1):
            if not isinstance(option, dict) and not hasattr(option, "get"):
                missing.append(f"{label}, opción {option_position}, necesita una estructura.")
                continue

            literal_index = option.get("position")
            if not isinstance(literal_index, int):
                missing.append(
                    f"{label}, opción {option_position}, necesita conservar su índice literal."
                )
            else:
                literal_positions.append(literal_index)

            if not str(option.get("text", "")).strip():
                missing.append(f"{label}, opción {option_position}, necesita texto.")
            if not str(option.get("feedback", "")).strip():
                missing.append(
                    f"{label}, opción {option_position}, necesita retroalimentación."
                )
            if option.get("expected") is True:
                expected_count += 1

        if literal_positions != sorted(literal_positions):
            missing.append(f"{label} debe conservar el orden de sus índices literales.")
        if len(literal_positions) != len(set(literal_positions)):
            missing.append(f"{label} no puede repetir índices literales.")
        if len(literal_positions) >= 2:
            for literal_index in range(min(literal_positions), max(literal_positions) + 1):
                if literal_index not in literal_positions:
                    missing.append(
                        f"{label}: falta la opción con índice literal {literal_index}; el hueco no se compacta."
                    )

        if expected_count != 1:
            missing.append(f"{label} necesita exactamente una respuesta esperada.")

        try:
            hints = list(question.get("hints", []) or [])
        except TypeError:
            hints = []
        if not hints:
            missing.append(f"{label} necesita al menos una pista autorizada.")
        elif any(not str(hint).strip() for hint in hints):
            missing.append(f"{label} contiene una pista autorizada vacía.")

    def save(self, *args, **kwargs):
        validation = self.structural_validation()
        self.validation_summary = (
            "Validación estructural: completa. La validación estructural no publica ni equivale a aprobación humana."
            if validation["is_valid"]
            else "Validación estructural: incompleta. La validación estructural no publica ni equivale a aprobación humana.\n"
            + "\n".join(validation["missing"])
        )
        super().save(*args, **kwargs)

    @transaction.atomic
    def publish(
        self,
        revision,
        user=None,
        changed=True,
        log_action=True,
        previous_revision=None,
        skip_permission_checks=False,
    ):
        if user is None or not getattr(user, "is_authenticated", False):
            raise ValidationError(
                "La publicación requiere una persona autenticada y aprobación humana."
            )
        if not user.groups.filter(name=EDITORIAL_REVIEWER_GROUP_NAME).exists():
            raise ValidationError(
                "La publicación requiere el grupo EditorialReviewer."
            )
        if not ModelPermissionPolicy(CurriculumPackage).user_has_permission(
            user, "change"
        ):
            raise ValidationError(
                "La publicación requiere permiso change sobre CurriculumPackage."
            )

        approved_task = TaskState.objects.filter(
            workflow_state__base_content_type=self.get_base_content_type(),
            workflow_state__object_id=str(self.pk),
            workflow_state__status=WorkflowState.STATUS_APPROVED,
            revision=revision,
            status=TaskState.STATUS_APPROVED,
            finished_by=user,
        ).first()
        if approved_task is None:
            raise ValidationError(
                "La publicación requiere una aprobación humana autenticada en Wagtail."
            )

        # La aprobación humana no sustituye la validación estructural: ningún
        # snapshot puede originarse de una revisión incompleta. Se valida el
        # contenido exacto de la revisión que se publicará, no el estado actual
        # del borrador.
        revision_validation = revision.as_object().structural_validation()
        if not revision_validation["is_valid"]:
            raise ValidationError(
                [
                    "No se puede publicar un paquete curricular estructuralmente incompleto."
                    " La aprobación humana sigue siendo obligatoria y no declara válido el contenido."
                ]
                + revision_validation["missing"]
            )

        result = super().publish(
            revision,
            user=user,
            changed=changed,
            log_action=log_action,
            previous_revision=previous_revision,
            skip_permission_checks=False,
        )
        payload = _normalize_published_payload(dict(revision.content))
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        version = (
            PublishedPackageSnapshot.objects.filter(package=self).aggregate(
                maximum=Max("version")
            )["maximum"]
            or 0
        ) + 1
        PublishedPackageSnapshot.objects.create(
            package=self,
            version=version,
            payload=payload,
            sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            source_revision=revision,
            published_by=user,
        )
        return result


class PublishedPackageSnapshot(models.Model):
    package = models.ForeignKey(
        CurriculumPackage,
        on_delete=models.PROTECT,
        related_name="snapshots",
    )
    version = models.PositiveIntegerField()
    payload = models.JSONField()
    sha256 = models.CharField(max_length=64, editable=False)
    source_revision = models.OneToOneField(
        "wagtailcore.Revision",
        on_delete=models.PROTECT,
    )
    published_by = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["package_id", "version"]
        constraints = [
            models.UniqueConstraint(
                fields=("package", "version"),
                name="unique_package_snapshot_version",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Un snapshot publicado es inmutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Un snapshot publicado no se elimina.")

    def __str__(self):
        return f"{self.package} v{self.version} ({self.sha256[:8]})"


class PublishedRoadmapSnapshot(models.Model):
    """An immutable, human-published roadmap used by student sessions.

    Every activity carries the id of the PublishedPackageSnapshot that supplies
    its content.  The roadmap is an ordered index, not a second live package.
    """

    title = models.CharField("título", max_length=160, blank=True)
    version = models.PositiveIntegerField()
    payload = models.JSONField("roadmap publicado")
    sha256 = models.CharField(max_length=64, editable=False)
    published_by = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at", "-id"]
        verbose_name = "PublishedRoadmapSnapshot"
        verbose_name_plural = "PublishedRoadmapSnapshots"

    @classmethod
    @transaction.atomic
    def publish(cls, *, title, package_snapshots, teacher):
        """Publish an ordered roadmap after an explicit human decision.

        This is intentionally a small teacher-operated publication boundary;
        no import job or model-generated proposal can call it as an authority.
        """

        if (
            not getattr(teacher, "is_authenticated", False)
            or not teacher.is_staff
            or not teacher.is_active
        ):
            raise ValidationError("La publicación del roadmap requiere una maestra autenticada.")
        snapshots = list(package_snapshots)
        if not snapshots:
            raise ValidationError("Selecciona al menos un paquete publicado.")
        snapshot_ids = [snapshot.pk for snapshot in snapshots]
        if any(snapshot_id is None for snapshot_id in snapshot_ids):
            raise ValidationError("Cada actividad requiere un snapshot publicado existente.")
        existing = {
            snapshot.pk
            for snapshot in PublishedPackageSnapshot.objects.filter(pk__in=snapshot_ids)
        }
        if set(snapshot_ids) != existing:
            raise ValidationError("Cada actividad requiere un snapshot publicado existente.")

        units = []
        for unit_index, snapshot in enumerate(snapshots):
            unit_id = f"u{unit_index}"
            lesson_id = f"{unit_id}:l0"
            units.append(
                {
                    "id": unit_id,
                    "title": snapshot.payload.get("title") or snapshot.package.title,
                    "lessons": [
                        {
                            "id": lesson_id,
                            "title": "Lección",
                            "activities": [
                                {
                                    "id": f"{lesson_id}:a0",
                                    "title": snapshot.payload.get("title") or "Actividad",
                                    "package_snapshot_id": snapshot.pk,
                                }
                            ],
                        }
                    ],
                }
            )
        normalized_title = str(title or "").strip()
        if not normalized_title:
            normalized_title = "Roadmap"
        payload = {"title": normalized_title[:160], "units": units}
        version = (
            cls.objects.aggregate(maximum=Max("version"))["maximum"] or 0
        ) + 1
        return cls.objects.create(
            title=payload["title"],
            version=version,
            payload=payload,
            published_by=teacher,
        )

    def package_snapshot_ids(self):
        from curriculum.roadmap import ordered_activities

        return {
            activity["package_snapshot_id"]
            for activity in ordered_activities(self.payload)
            if activity.get("package_snapshot_id") is not None
        }

    def validate_package_snapshots(self):
        snapshot_ids = {str(value) for value in self.package_snapshot_ids()}
        existing_ids = {
            str(value)
            for value in PublishedPackageSnapshot.objects.filter(
                pk__in=snapshot_ids
            ).values_list("pk", flat=True)
        }
        if snapshot_ids - existing_ids:
            raise ValidationError("El roadmap referencia snapshots de paquete inexistentes.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Un snapshot de roadmap publicado es inmutable.")
        self.sha256 = _canonical_payload_sha256(self.payload)
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Un snapshot de roadmap publicado es inmutable y no se elimina.")

    def __str__(self):
        label = self.title or "Roadmap"
        return f"{label} v{self.version} ({self.sha256[:8]})"


class CurriculumProgress(models.Model):
    """Teacher-confirmed curriculum position, never inferred from activity."""

    STATUS_CURRENT = "current"
    STATUS_WORKED = "worked"
    STATUS_CHOICES = (
        (STATUS_CURRENT, "Actual"),
        (STATUS_WORKED, "Trabajado"),
    )

    roadmap_snapshot = models.ForeignKey(
        PublishedRoadmapSnapshot,
        on_delete=models.PROTECT,
        related_name="curriculum_progress",
    )
    node_id = models.CharField("identificador del tema", max_length=160)
    status = models.CharField(
        "estado confirmado por la maestra",
        max_length=16,
        choices=STATUS_CHOICES,
    )
    confirmed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="confirmed_curriculum_progress",
    )
    confirmed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["node_id"]
        constraints = [
            models.UniqueConstraint(
                fields=("roadmap_snapshot", "node_id"),
                name="unique_curriculum_progress_node",
            )
        ]
        verbose_name = "CurriculumProgress"
        verbose_name_plural = "CurriculumProgress"

    @property
    def topic_id(self):
        """Compatibility vocabulary for teacher-facing topic screens."""

        return self.node_id

    def clean(self):
        self.node_id = str(self.node_id or "").strip()
        if not self.node_id:
            raise ValidationError("El avance curricular requiere un tema.")
        if self.status not in dict(self.STATUS_CHOICES):
            raise ValidationError("El estado curricular no está autorizado.")
        super().clean()

    @classmethod
    def confirm(cls, *, roadmap_snapshot, node_id, status, teacher):
        if (
            not getattr(teacher, "is_authenticated", False)
            or not teacher.is_staff
            or not teacher.is_active
        ):
            raise ValidationError("El avance curricular requiere una maestra autenticada activa.")
        node_id = str(node_id or "").strip()
        if not node_id:
            raise ValidationError("El avance curricular requiere un tema.")
        if status not in dict(cls.STATUS_CHOICES):
            raise ValidationError("El estado curricular no está autorizado.")
        from curriculum.roadmap import ordered_nodes

        allowed_node_ids = {node["id"] for node in ordered_nodes(roadmap_snapshot.payload)}
        if node_id not in allowed_node_ids:
            raise ValidationError("El tema no pertenece al roadmap publicado.")
        progress, _ = cls.objects.update_or_create(
            roadmap_snapshot=roadmap_snapshot,
            node_id=str(node_id).strip(),
            defaults={"status": status, "confirmed_by": teacher},
        )
        return progress


class ClassroomSession(models.Model):
    """An activity and roadmap fixed to immutable published snapshots."""

    STATUS_ACTIVE = "active"
    STATUS_PREPARED = "prepared"
    STATUS_STOPPED = "stopped"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = (
        (STATUS_PREPARED, "Preparada"),
        (STATUS_ACTIVE, "Activa"),
        (STATUS_STOPPED, "Detenida"),
        (STATUS_CLOSED, "Cerrada"),
    )

    snapshot = models.ForeignKey(
        PublishedPackageSnapshot,
        on_delete=models.PROTECT,
        related_name="classroom_sessions",
    )
    roadmap_snapshot = models.ForeignKey(
        PublishedRoadmapSnapshot,
        on_delete=models.PROTECT,
        related_name="classroom_sessions",
        null=True,
        blank=True,
    )
    result_batch_id = models.UUIDField(
        "lote opaco de resultados",
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    status = models.CharField(
        "estado",
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )
    student_count = models.PositiveIntegerField(
        "estudiantes indicados",
        null=True,
        blank=True,
    )
    device_count = models.PositiveIntegerField(
        "dispositivos indicados",
        null=True,
        blank=True,
    )
    confirmed_at = models.DateTimeField(
        "confirmada en",
        null=True,
        blank=True,
    )
    started_at = models.DateTimeField("iniciada en", auto_now_add=True)
    stopped_at = models.DateTimeField("detenida en", null=True, blank=True)
    closed_at = models.DateTimeField("cerrada en", null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        verbose_name = "ClassroomSession"
        verbose_name_plural = "ClassroomSessions"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(student_count__isnull=True) | models.Q(student_count__gt=0),
                name="session_student_count_positive_or_null",
            ),
            models.CheckConstraint(
                condition=models.Q(device_count__isnull=True) | models.Q(device_count__gt=0),
                name="session_device_count_positive_or_null",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(student_count__isnull=True, device_count__isnull=True)
                    | models.Q(
                        student_count__isnull=False,
                        device_count__isnull=False,
                        student_count__gte=models.F("device_count"),
                    )
                ),
                name="session_device_count_not_above_students",
            ),
        ]

    @classmethod
    def start_from_snapshot(cls, snapshot, roadmap_snapshot=None):
        if not snapshot or snapshot.pk is None:
            raise ValidationError("La sesión requiere un snapshot publicado existente.")
        try:
            published_snapshot = PublishedPackageSnapshot.objects.get(pk=snapshot.pk)
            published_roadmap = (
                PublishedRoadmapSnapshot.objects.get(pk=roadmap_snapshot.pk)
                if roadmap_snapshot is not None
                else None
            )
            if published_roadmap is not None:
                published_roadmap.validate_package_snapshots()
        except (PublishedPackageSnapshot.DoesNotExist, PublishedRoadmapSnapshot.DoesNotExist) as error:
            raise ValidationError(
                "La sesión requiere snapshots publicados existentes."
            ) from error
        return cls.objects.create(
            snapshot=published_snapshot,
            roadmap_snapshot=published_roadmap,
        )

    @classmethod
    @transaction.atomic
    def prepare_from_snapshot(
        cls, snapshot, student_count, device_count, roadmap_snapshot=None
    ):
        if not snapshot or snapshot.pk is None:
            raise ValidationError("La sesión requiere un snapshot publicado existente.")
        try:
            published_snapshot = PublishedPackageSnapshot.objects.get(pk=snapshot.pk)
            published_roadmap = (
                PublishedRoadmapSnapshot.objects.get(pk=roadmap_snapshot.pk)
                if roadmap_snapshot is not None
                else None
            )
            capacities = calculate_distribution(student_count, device_count)
            if published_roadmap is not None:
                published_roadmap.validate_package_snapshots()
        except (PublishedPackageSnapshot.DoesNotExist, PublishedRoadmapSnapshot.DoesNotExist) as error:
            raise ValidationError(
                "La sesión requiere snapshots publicados existentes."
            ) from error
        except ValueError as error:
            raise ValidationError(str(error)) from error

        session = cls.objects.create(
            snapshot=published_snapshot,
            roadmap_snapshot=published_roadmap,
            status=cls.STATUS_PREPARED,
            student_count=int(str(student_count).strip()),
            device_count=int(str(device_count).strip()),
        )
        DeviceAssignment.objects.bulk_create(
            [
                DeviceAssignment(
                    session=session,
                    assigned_capacity=capacity,
                    remaining_capacity=capacity,
                )
                for capacity in capacities
            ]
        )
        return session

    @transaction.atomic
    def confirm(self):
        locked = type(self).objects.select_for_update().get(pk=self.pk)
        if locked.status == self.STATUS_ACTIVE:
            return locked
        if locked.status != self.STATUS_PREPARED:
            raise ValidationError("Solo una sesión preparada puede confirmarse.")
        capacities = list(
            locked.device_assignments.order_by("id").values_list(
                "assigned_capacity",
                flat=True,
            )
        )
        try:
            validate_distribution(
                locked.student_count,
                locked.device_count,
                capacities,
            )
        except ValueError as error:
            raise ValidationError(str(error)) from error
        confirmation_time = timezone.now()
        receipt, _ = ClassroomSessionConfirmation.objects.get_or_create(
            session=locked,
            defaults={"confirmed_at": confirmation_time},
        )
        type(self).objects.filter(pk=locked.pk).update(
            status=self.STATUS_ACTIVE,
            confirmed_at=receipt.confirmed_at,
        )
        self.refresh_from_db()
        return self

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).values(
                "snapshot_id", "roadmap_snapshot_id", "status", "closed_at"
            ).first()
            original_snapshot_id = original["snapshot_id"] if original else None
            original_roadmap_snapshot_id = (
                original["roadmap_snapshot_id"] if original else None
            )
            if (
                original_snapshot_id is not None
                and original_snapshot_id != self.snapshot_id
            ):
                raise ValidationError("El snapshot de una ClassroomSession queda fijado.")
            if (
                original_roadmap_snapshot_id != self.roadmap_snapshot_id
            ):
                raise ValidationError(
                    "El snapshot de roadmap de una ClassroomSession queda fijado."
                )
            if (
                original
                and original["status"] == self.STATUS_PREPARED
                and self.status == self.STATUS_ACTIVE
            ):
                raise ValidationError(
                    "Una sesión preparada requiere confirmación explícita para activarse."
                )
            if (
                original
                and original["status"] != self.STATUS_CLOSED
                and self.status == self.STATUS_CLOSED
                and not ClassroomSessionClosure.objects.filter(
                    session_id=self.pk
                ).exists()
            ):
                raise ValidationError(
                    "Una sesión sólo puede cerrarse con su receipt operacional."
                )
            if original and original["status"] == self.STATUS_CLOSED:
                if self.status != self.STATUS_CLOSED:
                    raise ValidationError("Una sesión cerrada no puede reabrirse.")
                if self.closed_at is None:
                    self.closed_at = original["closed_at"]
        elif self.status == self.STATUS_CLOSED:
            raise ValidationError("Una sesión sólo puede cerrarse con su receipt operacional.")
        elif self.status == self.STATUS_ACTIVE and self.student_count is not None:
            raise ValidationError(
                "Una sesión T06 debe confirmarse antes de activarse."
            )
        if (
            self.status == self.STATUS_ACTIVE
            and (self.student_count is not None or self.device_count is not None)
            and self.confirmed_at is None
        ):
            raise ValidationError(
                "Una sesión T06 activa requiere una confirmación registrada."
            )
        return super().save(*args, **kwargs)

    @transaction.atomic
    def stop(self):
        locked = type(self).objects.select_for_update().get(pk=self.pk)
        if locked.status == self.STATUS_STOPPED:
            return locked
        locked.status = self.STATUS_STOPPED
        locked.stopped_at = timezone.now()
        locked.save(update_fields=["status", "stopped_at"])
        return locked

    def close(self):
        """Seal ephemeral turn summaries and destroy temporal classroom links."""

        from curriculum.ephemeral import (
            clear_ephemeral_session_summary,
            clear_practice_cache,
            read_ephemeral_session_summary,
        )

        turn_ids = []
        question_count = 0
        activity_ids = []
        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            if locked.status == self.STATUS_CLOSED:
                ClassroomSessionClosure.objects.get_or_create(
                    session=locked,
                    defaults={"closed_at": locked.closed_at or timezone.now()},
                )
            else:
                if locked.status not in {self.STATUS_ACTIVE, self.STATUS_PREPARED}:
                    raise ValidationError(
                        "Sólo una sesión activa o preparada puede cerrarse explícitamente."
                    )

                closed_at = timezone.now()
                summary = read_ephemeral_session_summary(locked.pk)
                turns = list(
                    StudentTurn.objects.filter(
                        assignment__session_id=locked.pk,
                    ).select_related("assignment")
                )
                turn_ids = [turn.pk for turn in turns]
                question_counts = [len(locked.snapshot.payload.get("questions", []) or [])]
                roadmap_activity_snapshots = {}
                if locked.roadmap_snapshot_id:
                    from curriculum.roadmap import ordered_activities

                    roadmap_activity_snapshots = {
                        activity["id"]: PublishedPackageSnapshot.objects.get(
                            pk=activity["package_snapshot_id"]
                        )
                        for activity in ordered_activities(locked.roadmap_snapshot.payload)
                        if activity.get("package_snapshot_id") is not None
                    }
                    activity_ids = list(roadmap_activity_snapshots)
                    question_counts.extend(
                        len(snapshot.payload.get("questions", []) or [])
                        for snapshot in roadmap_activity_snapshots.values()
                    )
                question_count = max(question_counts, default=0)
                for turn in turns:
                    turn_summary = summary.get("turns", {}).get(str(turn.pk), {})
                    started_at = _parse_cached_datetime(turn_summary.get("started_at"))
                    ended_at = (
                        _parse_cached_datetime(turn_summary.get("completed_at"))
                        or closed_at
                    )
                    duration_seconds = None
                    if started_at is not None:
                        duration_seconds = max(
                            0,
                            int((ended_at - started_at).total_seconds()),
                        )
                    responses = list(turn_summary.get("responses", []) or [])
                    help_requests = list(turn_summary.get("help_requests", []) or [])
                    state = (
                        PseudonymousResult.STATE_COMPLETED
                        if turn_summary.get("state")
                        == PseudonymousResult.STATE_COMPLETED
                        else PseudonymousResult.STATE_ABANDONED
                    )
                    result_snapshots = (
                        list(roadmap_activity_snapshots.items())
                        if roadmap_activity_snapshots
                        else [(None, locked.snapshot)]
                    )
                    for activity_id, result_snapshot in result_snapshots:
                        activity_responses = (
                            [response for response in responses if response.get("activity_id") == activity_id]
                            if activity_id is not None
                            else responses
                        )
                        activity_help = (
                            [request for request in help_requests if request.get("activity_id") == activity_id]
                            if activity_id is not None
                            else help_requests
                        )
                        PseudonymousResult.objects.create(
                            result_batch_id=locked.result_batch_id,
                            snapshot_id=result_snapshot.pk,
                            snapshot_version=result_snapshot.version,
                            snapshot_sha256=result_snapshot.sha256,
                            state=state,
                            duration_seconds=duration_seconds,
                            responses=activity_responses,
                            score=sum(
                                1
                                for response in activity_responses
                                if response.get("is_correct") is True
                            ),
                            help_requests=activity_help,
                            technical_errors=list(
                                turn_summary.get("technical_errors", []) or []
                            ),
                        )

                StudentTurn.objects.filter(assignment__session_id=locked.pk).delete()
                DeviceAssignment.objects.filter(session_id=locked.pk).delete()
                receipt, _ = ClassroomSessionClosure.objects.get_or_create(
                    session=locked,
                    defaults={"closed_at": closed_at},
                )
                locked.status = self.STATUS_CLOSED
                locked.closed_at = receipt.closed_at
                locked.save(update_fields=["status", "closed_at"])

        # The final DB write and transaction exit are complete. Cache cleanup
        # is deliberately last so rollback-prone work leaves evidence retryable.
        for turn_id in turn_ids:
            clear_practice_cache(
                turn_id,
                range(question_count),
                activity_ids=activity_ids or None,
            )
        clear_ephemeral_session_summary(locked.pk)
        return locked


class ClassroomSessionConfirmation(models.Model):
    """Operational receipt authorizing one prepared session to become active."""

    session = models.OneToOneField(
        ClassroomSession,
        on_delete=models.CASCADE,
        related_name="confirmation_receipt",
    )
    confirmed_at = models.DateTimeField("confirmada en")
    nonce = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    class Meta:
        verbose_name = "ClassroomSessionConfirmation"
        verbose_name_plural = "ClassroomSessionConfirmations"


class ClassroomSessionClosure(models.Model):
    """Operational receipt proving that a classroom session was closed."""

    session = models.OneToOneField(
        ClassroomSession,
        on_delete=models.CASCADE,
        related_name="closure_receipt",
    )
    closed_at = models.DateTimeField("cerrada en")
    nonce = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    class Meta:
        verbose_name = "ClassroomSessionClosure"
        verbose_name_plural = "ClassroomSessionClosures"


class DeviceAssignment(models.Model):
    """A local, non-semantic device queue prepared before session confirmation."""

    session = models.ForeignKey(
        ClassroomSession,
        on_delete=models.CASCADE,
        related_name="device_assignments",
    )
    local_identifier = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    claimed_at = models.DateTimeField(
        "reclamada en",
        null=True,
        blank=True,
        editable=False,
    )
    assigned_capacity = models.PositiveIntegerField("capacidad asignada")
    remaining_capacity = models.PositiveIntegerField("capacidad restante")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(assigned_capacity__gt=0),
                name="device_assignment_capacity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(remaining_capacity__gte=0),
                name="device_assignment_remaining_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(remaining_capacity__lte=models.F("assigned_capacity")),
                name="device_assignment_remaining_within_capacity",
            ),
            models.UniqueConstraint(
                fields=("session", "local_identifier"),
                name="unique_session_local_device_identifier",
            ),
        ]

    @property
    def queue_capacity(self):
        return self.assigned_capacity

    def reserve_turn(self, display_name):
        """Reserve one participant slot and create its temporary turn."""

        normalized_name = StudentTurn.normalize_display_name(display_name)
        with transaction.atomic():
            assignment_snapshot = type(self).objects.get(pk=self.pk)
            session = ClassroomSession.objects.select_for_update().get(
                pk=assignment_snapshot.session_id,
            )
            assignment = type(self).objects.select_for_update().get(pk=self.pk)
            if session.status != ClassroomSession.STATUS_ACTIVE:
                raise ValidationError(
                    "Solo una sesión activa puede iniciar un turno estudiantil."
                )
            if StudentTurn.objects.filter(
                assignment=assignment,
                status=StudentTurn.STATUS_ACTIVE,
            ).exists():
                raise ValidationError(
                    "Este dispositivo ya tiene un turno activo; continúa o pulsa Listo."
                )
            if assignment.remaining_capacity <= 0:
                raise ValidationError(
                    "La capacidad restante de este dispositivo se agotó."
                )
            return StudentTurn.objects.create(
                assignment=assignment,
                display_name=normalized_name,
            )


class StudentTurn(models.Model):
    """A temporary, non-identifying participant turn on one local device."""

    STATUS_ACTIVE = "active"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Activo"),
        (STATUS_COMPLETED, "Completado"),
    )
    MAX_DISPLAY_NAME_LENGTH = 80

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    assignment = models.ForeignKey(
        DeviceAssignment,
        on_delete=models.CASCADE,
        related_name="student_turns",
    )
    display_name = models.CharField(
        "apodo local",
        max_length=MAX_DISPLAY_NAME_LENGTH,
        blank=True,
    )
    status = models.CharField(
        "estado",
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )
    started_at = models.DateTimeField("iniciado en", auto_now_add=True)
    completed_at = models.DateTimeField("completado en", null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        verbose_name = "StudentTurn"
        verbose_name_plural = "StudentTurns"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["active", "completed"]),
                name="student_turn_status_allowed",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="completed")
                    | (
                        models.Q(status="active")
                        & ~models.Q(display_name="")
                    )
                ),
                name="student_turn_active_name_required",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="completed")
                    | (
                        models.Q(status="active")
                        & GreaterThanOrEqual(Length(Trim("display_name")), 1)
                    )
                ),
                name="student_turn_active_name_length",
            ),
            models.UniqueConstraint(
                fields=("assignment",),
                condition=models.Q(status="active"),
                name="unique_active_student_turn_per_assignment",
            ),
        ]

    @classmethod
    def normalize_display_name(cls, value):
        normalized = str(value or "").strip()
        if not normalized:
            raise ValidationError("El apodo local no puede estar vacío.")
        if len(normalized) > cls.MAX_DISPLAY_NAME_LENGTH:
            raise ValidationError(
                f"El apodo local no puede superar {cls.MAX_DISPLAY_NAME_LENGTH} caracteres."
            )
        return normalized

    def clean(self):
        if self.status == self.STATUS_ACTIVE:
            self.display_name = self.normalize_display_name(self.display_name)
        elif self.status == self.STATUS_COMPLETED:
            self.display_name = ""
        super().clean()

    def save(self, *args, **kwargs):
        if self._state.adding:
            if self.status == self.STATUS_ACTIVE:
                self.display_name = self.normalize_display_name(self.display_name)
            elif self.status == self.STATUS_COMPLETED:
                self.display_name = ""
        else:
            original = type(self).objects.filter(pk=self.pk).values(
                "assignment_id", "status", "display_name"
            ).first()
            if original and original["assignment_id"] != self.assignment_id:
                raise ValidationError("La asignación de un turno queda fijada.")
            if original and original["status"] == self.STATUS_COMPLETED:
                if self.status != self.STATUS_COMPLETED or self.display_name != "":
                    raise ValidationError("Un turno completado no puede reabrirse.")
            if original and original["status"] == self.STATUS_ACTIVE:
                if self.status not in {self.STATUS_ACTIVE, self.STATUS_COMPLETED}:
                    raise ValidationError("La transición del turno no está permitida.")
                if self.status == self.STATUS_ACTIVE:
                    self.display_name = self.normalize_display_name(self.display_name)
                else:
                    self.display_name = ""
        return super().save(*args, **kwargs)

    @transaction.atomic
    def finish(self):
        assignment_snapshot = DeviceAssignment.objects.get(pk=self.assignment_id)
        session = ClassroomSession.objects.select_for_update().get(
            pk=assignment_snapshot.session_id,
        )
        assignment = DeviceAssignment.objects.select_for_update().get(
            pk=assignment_snapshot.pk,
        )
        locked = type(self).objects.select_for_update().get(
            pk=self.pk,
            assignment_id=assignment.pk,
        )
        if session.status != ClassroomSession.STATUS_ACTIVE:
            raise ValidationError("Un turno sólo puede finalizarse en una sesión activa.")
        if locked.status == self.STATUS_COMPLETED:
            return locked
        if locked.status != self.STATUS_ACTIVE:
            raise ValidationError("La transición del turno no está permitida.")
        locked.status = self.STATUS_COMPLETED
        locked.display_name = ""
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "display_name", "completed_at"])
        return locked


class StudentRoadmapProgress(models.Model):
    """An erasable, pseudonymous activity path for one classroom turn.

    This row is intentionally tied to the temporary ``StudentTurn``. Closing
    the session deletes the turn and therefore this progress; there is no
    student account, name, grade or identity relationship to retain.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ClassroomSession,
        on_delete=models.CASCADE,
        related_name="student_roadmap_progress",
    )
    turn = models.OneToOneField(
        StudentTurn,
        on_delete=models.CASCADE,
        related_name="roadmap_progress",
        null=True,
        blank=True,
    )
    student_key = models.UUIDField(default=uuid.uuid4, editable=False)
    roadmap_snapshot = models.ForeignKey(
        PublishedRoadmapSnapshot,
        on_delete=models.PROTECT,
        related_name="student_progress",
    )
    package_snapshot = models.ForeignKey(
        PublishedPackageSnapshot,
        on_delete=models.PROTECT,
        related_name="student_progress",
    )
    completed_activity_ids = models.JSONField(
        "actividades completadas en el recorrido",
        default=list,
        blank=True,
    )
    correct_question_indices = models.JSONField(
        "reactivos correctos persistidos por actividad",
        default=dict,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("session", "student_key"),
                name="unique_session_student_roadmap_key",
            )
        ]
        verbose_name = "StudentRoadmapProgress"
        verbose_name_plural = "StudentRoadmapProgress"

    @classmethod
    def for_turn(cls, turn):
        session = turn.assignment.session
        if session.roadmap_snapshot_id is None:
            return None
        progress, _ = cls.objects.get_or_create(
            turn=turn,
            defaults={
                "session": session,
                "student_key": uuid.uuid4(),
                "roadmap_snapshot_id": session.roadmap_snapshot_id,
                "package_snapshot_id": session.snapshot_id,
            },
        )
        if (
            progress.session_id != session.pk
            or progress.roadmap_snapshot_id != session.roadmap_snapshot_id
            or progress.package_snapshot_id != session.snapshot_id
        ):
            raise ValidationError("El progreso no corresponde a los snapshots de la sesión.")
        return progress

    def _assert_session_snapshots(self):
        session = self.session
        if (
            self.roadmap_snapshot_id != session.roadmap_snapshot_id
            or self.package_snapshot_id != session.snapshot_id
        ):
            raise ValidationError("El progreso debe usar los snapshots fijados a la sesión.")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).values(
                "session_id", "turn_id", "student_key", "roadmap_snapshot_id", "package_snapshot_id"
            ).first()
            if original and any(
                original[field] != getattr(self, field)
                for field in ("session_id", "turn_id", "student_key", "roadmap_snapshot_id", "package_snapshot_id")
            ):
                raise ValidationError("El progreso pseudónimo y sus snapshots quedan fijados.")
        self._assert_session_snapshots()
        return super().save(*args, **kwargs)

    def available_activity_ids(self):
        from curriculum.roadmap import ordered_activity_ids

        return ordered_activity_ids(self.roadmap_snapshot.payload)

    @property
    def completed_activities(self):
        """Human-readable alias for the persisted opaque activity ids."""

        return list(self.completed_activity_ids)

    def current_activity_id(self):
        activities = self.available_activity_ids()
        completed = {str(item) for item in self.completed_activity_ids}
        return next((activity_id for activity_id in activities if activity_id not in completed), None)

    def package_snapshot_for_activity(self, activity_id=None):
        from curriculum.roadmap import ordered_activities

        activity_id = activity_id or self.current_activity_id()
        activity = next(
            (item for item in ordered_activities(self.roadmap_snapshot.payload) if item["id"] == str(activity_id)),
            None,
        )
        snapshot_id = activity and activity.get("package_snapshot_id")
        snapshot_id = snapshot_id or self.package_snapshot_id
        return PublishedPackageSnapshot.objects.get(pk=snapshot_id)

    def complete_activity(self, activity_id, *, package_snapshot=None):
        """Complete one eligible activity without touching CurriculumProgress."""

        self._assert_session_snapshots()
        activity_id = str(activity_id)
        completed_ids = list(dict.fromkeys(str(item) for item in self.completed_activity_ids))
        if activity_id in completed_ids:
            self.completed_activity_ids = completed_ids
            self.save(update_fields=["completed_activity_ids", "updated_at"])
            return self
        if package_snapshot is not None:
            expected_snapshot = self.package_snapshot_for_activity(activity_id)
            if package_snapshot.pk != expected_snapshot.pk:
                raise ValidationError("La actividad no pertenece al snapshot publicado del roadmap.")
        activities = self.available_activity_ids()
        if activity_id not in activities:
            raise ValidationError("La actividad no existe en el roadmap publicado.")
        if activity_id != self.current_activity_id():
            raise ValidationError("La actividad todavía no está habilitada en este recorrido.")
        self.completed_activity_ids = list(dict.fromkeys([*completed_ids, activity_id]))
        self.save(update_fields=["completed_activity_ids", "updated_at"])
        return self

    def record_correct_answer(self, activity_id, question_index, question_count):
        """Persist a correct response and complete its activity immediately."""

        activity_id = str(activity_id)
        if activity_id != self.current_activity_id():
            raise ValidationError("La actividad todavía no está habilitada en este recorrido.")
        try:
            question_index = int(question_index)
            question_count = int(question_count)
        except (TypeError, ValueError) as error:
            raise ValidationError("El reactivo no es válido.") from error
        if question_index < 0 or question_index >= question_count:
            raise ValidationError("El reactivo no es válido.")
        correct = dict(self.correct_question_indices or {})
        indices = {int(index) for index in correct.get(activity_id, [])}
        indices.add(question_index)
        correct[activity_id] = sorted(indices)
        self.correct_question_indices = correct
        self.save(update_fields=["correct_question_indices", "updated_at"])
        if len(indices) == question_count:
            self.complete_activity(activity_id)
            return True
        return False

    def roadmap_states(self):
        from curriculum.roadmap import states_for_progress

        return states_for_progress(
            self.roadmap_snapshot.payload,
            self.completed_activity_ids,
        )


class PseudonymousResult(models.Model):
    """An erasable result that has no relationship to a classroom participant."""

    STATE_COMPLETED = "completed"
    STATE_ABANDONED = "abandoned"
    STATE_CHOICES = (
        (STATE_COMPLETED, "Completado"),
        (STATE_ABANDONED, "Interrumpido"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    result_batch_id = models.UUIDField(
        "lote opaco de resultados",
        db_index=True,
    )
    snapshot_id = models.PositiveBigIntegerField("id del snapshot")
    snapshot_version = models.PositiveIntegerField("versión del snapshot")
    snapshot_sha256 = models.CharField("sha256 del snapshot", max_length=64)
    state = models.CharField("estado", max_length=16, choices=STATE_CHOICES)
    duration_seconds = models.PositiveIntegerField("duración en segundos", null=True, blank=True)
    responses = models.JSONField("respuestas", default=list)
    score = models.IntegerField("puntuación", default=0)
    help_requests = models.JSONField("ayudas solicitadas", default=list)
    technical_errors = models.JSONField("errores técnicos", default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "PseudonymousResult"
        verbose_name_plural = "PseudonymousResults"


# Filesystem limits are per-path-component (~255 bytes on common Linux/macOS
# filesystems); stay well below it so long teacher-supplied names never fail.
CURRICULUM_IMPORT_PDF_MAX_STEM_BYTES = 120


def _truncate_utf8(text, max_bytes):
    """Truncate text to at most max_bytes of UTF-8, respecting char boundaries."""
    return text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def curriculum_import_pdf_path(instance, filename):
    """Sanitize the teacher's PDF filename before it reaches the filesystem.

    Real curriculum PDFs arrive with very long names, accents, emojis or
    repeated spaces; several of those break the upload outright. The server
    must never require the teacher to rename a file by hand.
    """
    stem = os.path.splitext(filename)[0]
    stem = unicodedata.normalize("NFKC", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    # Keep letters/digits (including accented ones), dots, dashes and spaces;
    # drop everything else (invalid chars, emojis, control characters).
    stem = re.sub(r"[^\w .\-]", "", stem, flags=re.UNICODE)
    stem = stem.strip(" .-").replace(" ", "_")
    stem = _truncate_utf8(stem, CURRICULUM_IMPORT_PDF_MAX_STEM_BYTES)
    if not stem:
        stem = "curriculo"
    return f"curriculum_imports/{stem}.pdf"


class CurriculumImportJob(models.Model):
    """Staging area for the local-LLM curriculum import pipeline.

    Holds the extracted PDF text and the LLM-proposed topic/subtopic
    hierarchy awaiting human confirmation. Nothing here creates or modifies
    CurriculumPackage, revisions or snapshots: conversion to drafts is a
    separate, human-approved step.
    """

    STATUS_UPLOADED = "uploaded"
    STATUS_TOPICS_PROPOSED = "topics_proposed"
    STATUS_SUBTOPICS_PROPOSED = "subtopics_proposed"
    STATUS_ACTIVITIES_PROPOSED = "activities_proposed"
    STATUS_COMPLETED = "completed"
    STATUS_CONVERTED = "converted"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_UPLOADED, "PDF cargado"),
        (STATUS_TOPICS_PROPOSED, "Temas propuestos; en revisión docente"),
        (STATUS_SUBTOPICS_PROPOSED, "Subtemas propuestos; en revisión docente"),
        (STATUS_ACTIVITIES_PROPOSED, "Actividades propuestas; en revisión docente"),
        (STATUS_COMPLETED, "Jerarquía confirmada"),
        (STATUS_CONVERTED, "Borradores generados"),
        (STATUS_FAILED, "Procesamiento fallido"),
    )

    pdf = models.FileField(
        "PDF de la currícula",
        upload_to=curriculum_import_pdf_path,
    )
    status = models.CharField(
        "estado",
        max_length=24,
        choices=STATUS_CHOICES,
        default=STATUS_UPLOADED,
    )
    source_text = models.TextField(
        "texto extraído del PDF",
        blank=True,
        editable=False,
    )
    page_count = models.PositiveIntegerField(
        "páginas detectadas",
        null=True,
        blank=True,
        editable=False,
    )
    topics = models.JSONField(
        "jerarquía propuesta",
        default=list,
        blank=True,
    )
    activities = models.JSONField(
        "actividades propuestas",
        default=list,
        blank=True,
    )
    progress_stage = models.CharField(
        "etapa en curso",
        max_length=24,
        blank=True,
        editable=False,
    )
    progress_done = models.PositiveIntegerField(
        "elementos procesados",
        default=0,
        editable=False,
    )
    progress_total = models.PositiveIntegerField(
        "elementos totales",
        default=0,
        editable=False,
    )
    progress_started_at = models.DateTimeField(
        "inicio de la etapa",
        null=True,
        blank=True,
        editable=False,
    )
    llm_trace = models.JSONField(
        "bitácora técnica del modelo local",
        default=list,
        blank=True,
        editable=False,
    )
    llm_log = models.JSONField(
        "bitácora del modelo local",
        default=list,
        blank=True,
        editable=False,
    )
    error_message = models.TextField("error", blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "CurriculumImportJob"
        verbose_name_plural = "CurriculumImportJobs"

    def __str__(self):
        return f"Import {self.pk} ({self.get_status_display()})"

    def extract_text(self):
        """Stage A: pull per-page text out of the uploaded PDF."""

        from curriculum.curriculum_import import chunk_pages, extract_pdf_pages

        pages = extract_pdf_pages(self.pdf)
        self.source_text = "\n\n".join(
            f"[página {number}]\n{text}"
            for number, text in enumerate(pages, start=1)
        )
        self.page_count = len(pages)
        self._chunks = chunk_pages(pages)
        return self._chunks


class PseudonymousSurveyResponse(models.Model):
    """An erasable survey answer with no relationship to any participant.

    Like PseudonymousResult, it carries only opaque batch/snapshot references;
    it never stores turn ids, device identifiers or display names, and no
    database key connects it to who submitted it.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    result_batch_id = models.UUIDField(
        "lote opaco de resultados",
        db_index=True,
    )
    snapshot_id = models.PositiveBigIntegerField("id del snapshot")
    snapshot_version = models.PositiveIntegerField("versión del snapshot")
    answers = models.JSONField("respuestas de la encuesta", default=list)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        verbose_name = "PseudonymousSurveyResponse"
        verbose_name_plural = "PseudonymousSurveyResponses"

    def __str__(self):
        return f"Survey {self.pk} (batch {str(self.result_batch_id)[:8]})"


class EditorialReviewerWorkflowActionView(WorkflowActionView):
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except ValidationError as error:
            # La transacción de publicación ya hizo rollback: ni la tarea queda
            # aprobada ni se crea snapshot. Se informan los faltantes concretos.
            for message in error.messages:
                wagtail_messages.error(request, message)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return render_modal_workflow(
                    request,
                    "",
                    None,
                    {},
                    json_data={"step": "success", "redirect": self.redirect_url},
                )
            return redirect(self.redirect_url)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        if not request.user.has_perm("wagtailadmin.access_admin"):
            return HttpResponseForbidden()
        if not ModelPermissionPolicy(CurriculumPackage).user_has_permission(
            request.user, "change"
        ):
            return HttpResponseForbidden()
        if not request.user.groups.filter(
            name=EDITORIAL_REVIEWER_GROUP_NAME
        ).exists():
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)


class CurriculumPackageViewSet(SnippetViewSet):
    model = CurriculumPackage
    workflow_action_view_class = EditorialReviewerWorkflowActionView


register_snippet(CurriculumPackageViewSet)
