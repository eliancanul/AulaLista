import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Max
from django.http import HttpResponseForbidden
from wagtail import blocks
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


EDITORIAL_REVIEWER_GROUP_NAME = "EditorialReviewer"


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        FieldPanel("title"),
        FieldPanel("objective"),
        FieldPanel("micro_lesson"),
        FieldPanel("questions"),
        FieldPanel("final_explanation"),
        FieldPanel("validation_summary", read_only=True),
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

        result = super().publish(
            revision,
            user=user,
            changed=changed,
            log_action=log_action,
            previous_revision=previous_revision,
            skip_permission_checks=False,
        )
        payload = dict(revision.content)
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


class EditorialReviewerWorkflowActionView(WorkflowActionView):
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
