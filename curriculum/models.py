import hashlib
import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timedelta

from django.contrib.auth.models import Group
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
from wagtail.snippets.views.snippets import CreateView, SnippetViewSet, WorkflowActionView

from curriculum.distribution import calculate_distribution, validate_distribution


EDITORIAL_REVIEWER_GROUP_NAME = "EditorialReviewer"
DIRECTOR_GROUP_NAME = "Director"
PLATFORM_ADMINISTRATOR_GROUP_NAME = "PlatformAdministrator"


def _normalize_datetime(dt):
    """Safely convert naive or aware datetimes to the active timezone, handling None robustly."""
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


def _package_source_upload_to(instance, filename):
    """Store imported PDFs under an opaque, package-owned name."""

    return f"curriculum/package-sources/{instance.pk or 'pending'}/{uuid.uuid4().hex}.pdf"


def _published_source_upload_to(instance, filename):
    """Give each immutable published snapshot its own source object."""

    return f"curriculum/published-sources/{instance.package_id}/{instance.version}/{uuid.uuid4().hex}.pdf"


def _is_platform_administrator(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and user.is_staff
        and (
            user.is_superuser
            or user.groups.filter(name=PLATFORM_ADMINISTRATOR_GROUP_NAME).exists()
        )
    )


class School(models.Model):
    """The single institutional boundary configured for a local installation."""

    MODALITY_PRIMARY = "primary"
    MODALITY_SECONDARY_GENERAL = "secondary_general"
    MODALITY_SECONDARY_TECHNICAL = "secondary_technical"
    MODALITY_TELESECUNDARIA = "telesecundaria"
    MODALITY_CHOICES = (
        (MODALITY_PRIMARY, "Primaria"),
        (MODALITY_SECONDARY_GENERAL, "Secundaria general"),
        (MODALITY_SECONDARY_TECHNICAL, "Secundaria técnica"),
        (MODALITY_TELESECUNDARIA, "Telesecundaria"),
    )

    name = models.CharField("nombre de la School", max_length=160)
    modality = models.CharField(
        "modalidad pedagógica",
        max_length=32,
        choices=MODALITY_CHOICES,
        default=MODALITY_PRIMARY,
    )
    director = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="directed_schools",
        null=True,
        blank=True,
    )
    is_configured = models.BooleanField("School configurada", default=True)
    archived = models.BooleanField("archivada", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "School"
        verbose_name_plural = "Schools"

    @classmethod
    def configured(cls):
        """Return the active configured school, failing closed when absent."""

        return cls.objects.filter(is_configured=True, archived=False).order_by("id").first()

    @classmethod
    def provision(
        cls,
        *,
        name,
        modality=MODALITY_PRIMARY,
        director,
        actor,
        source="manual",
    ):
        """Explicitly provision the sole School and its sole active Director."""

        if not _is_platform_administrator(actor):
            raise ValidationError("La provisión requiere un PlatformAdministrator activo.")
        if director is None or not director.is_active or not director.is_staff:
            raise ValidationError("La provisión requiere una persona Directora activa.")
        if _is_platform_administrator(director):
            raise ValidationError("PlatformAdministrator y Director son funciones separadas.")
        with transaction.atomic():
            if cls.objects.select_for_update().exists():
                raise ValidationError("La instalación ya tiene una School provisionada.")
            school = cls(
                name=name,
                modality=modality,
                director=director,
                is_configured=True,
            )
            school._explicit_provision = True
            school.save(force_insert=True)
            director_group, _ = Group.objects.get_or_create(name=DIRECTOR_GROUP_NAME)
            director.groups.add(director_group)
            InstitutionalAuditEvent.record(
                school=school,
                actor=actor,
                action="school_provisioned",
                object_type="School",
                object_id=school.pk,
                new_state={
                    "director": director.get_full_name().strip() or "Cuenta institucional",
                    "modality": school.modality,
                    "school": school.name,
                },
                source=source,
            )
            return school

    @classmethod
    def bootstrap(cls, *, name, modality=MODALITY_PRIMARY, director=None, actor=None):
        """Compatibility name for explicit, fail-closed provisioning."""

        if director is None or actor is None:
            raise ValidationError("La provisión explícita requiere Director y PlatformAdministrator.")
        return cls.provision(name=name, modality=modality, director=director, actor=actor)

    def handoff_director(self, new_director, *, actor, source="manual"):
        """Atomically replace the sole Director under technical authorization."""

        if not _is_platform_administrator(actor):
            raise ValidationError("El cambio de Dirección requiere PlatformAdministrator.")
        if (
            new_director is None
            or not new_director.is_active
            or not new_director.is_staff
        ):
            raise ValidationError("La nueva persona Directora debe ser una cuenta activa de personal.")
        if _is_platform_administrator(new_director):
            raise ValidationError("PlatformAdministrator y Director son funciones separadas.")
        source = str(source or "").strip()
        if not source:
            raise ValidationError("El cambio de Dirección requiere un origen.")

        with transaction.atomic():
            locked = type(self).objects.select_for_update().select_related("director").get(
                pk=self.pk,
                is_configured=True,
                archived=False,
            )
            previous = locked.director
            director_group, _ = Group.objects.get_or_create(name=DIRECTOR_GROUP_NAME)
            active_directors = list(
                new_director.__class__.objects.select_for_update()
                .filter(is_active=True, groups=director_group)
                .exclude(pk=new_director.pk)
            )
            if previous is not None and previous.pk != new_director.pk:
                new_director.__class__.objects.select_for_update().filter(
                    pk=previous.pk
                ).update(is_active=False)
                if all(item.pk != previous.pk for item in active_directors):
                    active_directors.append(previous)
            for outgoing in active_directors:
                outgoing.groups.remove(director_group)
                if outgoing.is_active:
                    outgoing.is_active = False
                    outgoing.save(update_fields=["is_active"])
            new_director.groups.add(director_group)
            locked.director = new_director
            locked.save(update_fields=["director"])
            InstitutionalAuditEvent.record(
                school=locked,
                actor=actor,
                action="director_handoff",
                object_type="School",
                object_id=locked.pk,
                previous_state={
                    "director": (
                        previous.get_full_name().strip() or "Cuenta institucional"
                    )
                    if previous is not None
                    else None
                },
                new_state={
                    "director": new_director.get_full_name().strip()
                    or "Cuenta institucional"
                },
                source=source,
            )
            return locked

    def set_director(self, director, *, actor=None, source="manual"):
        """Compatibility alias that preserves the authorized handoff boundary."""

        return self.handoff_director(director, actor=actor, source=source)

    def clean(self):
        self.name = str(self.name or "").strip()
        if not self.name:
            raise ValidationError("La School requiere un nombre.")
        if self.director_id and self.director and (
            not self.director.is_active or not self.director.is_staff
        ):
            raise ValidationError("La School requiere una persona Directora activa.")
        super().clean()

    def save(self, *args, **kwargs):
        if self._state.adding and not getattr(self, "_explicit_provision", False):
            raise ValidationError("Use la provisión explícita para crear la School.")
        self.full_clean()
        return super().save(*args, **kwargs)


class InstitutionalAuditEvent(models.Model):
    """Append-only institutional audit record without access credentials."""

    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="institutional_audit_events",
        null=True,
        blank=True,
    )
    actor_display_name = models.CharField("nombre histórico de presentación", max_length=160)
    actor_role = models.CharField("función histórica", max_length=80, blank=True)
    action = models.CharField("acción", max_length=80)
    object_type = models.CharField("tipo de objeto", max_length=80)
    object_id = models.CharField("referencia interna del objeto", max_length=80, blank=True)
    classroom_group = models.ForeignKey(
        "ClassroomGroup",
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    previous_state = models.JSONField(default=dict, blank=True)
    new_state = models.JSONField(default=dict, blank=True)
    source = models.CharField("origen", max_length=80, default="manual")
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "id"]
        verbose_name = "InstitutionalAuditEvent"
        verbose_name_plural = "InstitutionalAuditEvents"

    @classmethod
    def record(cls, *, school=None, actor=None, action, object_type, object_id="", classroom_group=None,
               previous_state=None, new_state=None, source="manual"):
        display_name = "Sistema local"
        role = ""
        if actor is not None:
            display_name = actor.get_full_name().strip() or "Cuenta institucional"
            if _is_platform_administrator(actor):
                role = PLATFORM_ADMINISTRATOR_GROUP_NAME
            elif actor.groups.filter(name=DIRECTOR_GROUP_NAME).exists():
                role = DIRECTOR_GROUP_NAME
            else:
                role = "Personal"
        return cls.objects.create(
            school=school,
            actor=actor,
            actor_display_name=display_name[:160],
            actor_role=role,
            action=action,
            object_type=object_type,
            object_id=str(object_id or ""),
            classroom_group=classroom_group,
            previous_state=previous_state or {},
            new_state=new_state or {},
            source=source,
        )

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("La auditoría institucional es inmutable.")
        if not self.actor_display_name:
            self.actor_display_name = "Sistema local"
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La auditoría institucional no se elimina.")


# Compatibility vocabulary for callers that used the shorter domain name.
AuditEvent = InstitutionalAuditEvent


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


class CurriculumSourceBlobQuerySet(models.QuerySet):
    """Immutable, append-only QuerySet for CurriculumSourceBlob."""

    def update(self, **kwargs):
        raise PermissionError("CurriculumSourceBlob is immutable: updates are forbidden.")

    def aupdate(self, **kwargs):
        raise PermissionError("CurriculumSourceBlob is immutable: updates are forbidden.")

    def delete(self):
        raise PermissionError("CurriculumSourceBlob is immutable: deletes are forbidden.")

    def adelete(self):
        raise PermissionError("CurriculumSourceBlob is immutable: deletes are forbidden.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise PermissionError("CurriculumSourceBlob is immutable: bulk updates are forbidden.")

    def abulk_update(self, objs, fields, batch_size=None):
        raise PermissionError("CurriculumSourceBlob is immutable: bulk updates are forbidden.")

    def update_or_create(self, defaults=None, **kwargs):
        raise PermissionError("CurriculumSourceBlob is immutable: update_or_create is forbidden.")

    def aupdate_or_create(self, defaults=None, **kwargs):
        raise PermissionError("CurriculumSourceBlob is immutable: update_or_create is forbidden.")

    @staticmethod
    def _validate_bulk_objects(objs):
        validated = list(objs)
        for blob in validated:
            blob.clean()
        return validated

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        if update_conflicts:
            raise PermissionError(
                "CurriculumSourceBlob is immutable: conflict updates are forbidden."
            )
        return super().bulk_create(
            self._validate_bulk_objects(objs),
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=False,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )

    async def abulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        if update_conflicts:
            raise PermissionError(
                "CurriculumSourceBlob is immutable: conflict updates are forbidden."
            )
        return await super().abulk_create(
            self._validate_bulk_objects(objs),
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=False,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )


class CurriculumSourceBlobManager(models.Manager.from_queryset(CurriculumSourceBlobQuerySet)):
    """Manager enforcing append-only immutability for CurriculumSourceBlob."""

    def update_or_create(self, defaults=None, **kwargs):
        raise PermissionError("CurriculumSourceBlob is immutable: update_or_create is forbidden.")

    def aupdate_or_create(self, defaults=None, **kwargs):
        raise PermissionError("CurriculumSourceBlob is immutable: update_or_create is forbidden.")


class CurriculumSourceBlob(models.Model):
    """Immutable, content-addressed transactional source blob stored directly in the database.

    Eliminates DB+filesystem dual-state impossibility:
    - Guaranteed atomic commit/rollback with CurriculumImportApproval and CurriculumPackage.
    - Zero orphaned files on crash, SystemExit, or transaction abort.
    - Append-only: immutable once written; update/delete/bulk_update/update_or_create are forbidden.
    - Model rejects update, delete, and empty bytes (content_size > 0).
    - Cannot be deleted while referenced by any approval or package (PROTECT / PermissionError).
    """

    sha256 = models.CharField(
        "SHA-256",
        max_length=64,
        unique=True,
        db_index=True,
        editable=False,
    )
    content = models.BinaryField("contenido binario", editable=False)
    content_size = models.PositiveBigIntegerField("tamaño en bytes", editable=False)
    created_at = models.DateTimeField("fecha de creación", auto_now_add=True)

    objects = CurriculumSourceBlobManager()

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "CurriculumSourceBlob"
        verbose_name_plural = "CurriculumSourceBlobs"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(content_size__gt=0),
                name="check_curriculum_source_blob_content_size_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(sha256__regex=r"^[0-9a-f]{64}$"),
                name="check_curriculum_source_blob_sha256_format",
            ),
        ]

    @property
    def size(self) -> int:
        return self.content_size

    def is_valid_blob(self) -> bool:
        """Verify cryptographic and size integrity of the stored content."""
        try:
            if self.content is None:
                return False
            raw = bytes(self.content)
            if len(raw) == 0:
                return False
            if self.content_size is None or int(self.content_size) != len(raw):
                return False
            calc_sha = hashlib.sha256(raw).hexdigest().lower()
            if (self.sha256 or "").lower() != calc_sha:
                return False
            return True
        except Exception:
            return False

    def clean(self):
        super().clean()
        if self.content is None:
            raise ValidationError("CurriculumSourceBlob content cannot be None.")
        raw_content = bytes(self.content)
        if len(raw_content) == 0:
            raise ValidationError("CurriculumSourceBlob content cannot be empty.")
        calc_sha = hashlib.sha256(raw_content).hexdigest().lower()
        calc_size = len(raw_content)
        if self.content_size is not None and int(self.content_size) != calc_size:
            raise ValidationError(
                f"El tamaño especificado ({self.content_size}) no coincide con la longitud del contenido ({calc_size})."
            )
        if self.sha256 and self.sha256.lower() != calc_sha:
            raise ValidationError("El hash SHA-256 no coincide con el contenido del blob.")
        self.sha256 = calc_sha
        self.content_size = calc_size

    def save(self, *args, **kwargs):
        if self.pk is not None:
            if not self._state.adding or CurriculumSourceBlob.objects.filter(pk=self.pk).exists():
                raise PermissionError("CurriculumSourceBlob records are immutable and cannot be updated.")
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("CurriculumSourceBlob records are immutable and cannot be deleted.")

    async def adelete(self, *args, **kwargs):
        raise PermissionError("CurriculumSourceBlob records are immutable and cannot be deleted.")

    def __str__(self):
        return f"CurriculumSourceBlob {self.sha256[:12]} ({self.content_size} bytes)"



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
    source_references = models.JSONField(
        "referencias de fuente",
        default=list,
        blank=True,
        editable=False,
        help_text=(
            "Páginas y recursos de origen conservados para revisión y snapshots; "
            "no son reescritos por la asistencia automática."
        ),
    )
    source_blob = models.ForeignKey(
        CurriculumSourceBlob,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="packages",
        verbose_name="blob fuente inmutable",
    )
    source_pdf = models.FileField(
        "PDF fuente conservado",
        upload_to=_package_source_upload_to,
        null=True,
        blank=True,
        editable=False,
        help_text="Copia inmutable de la fuente usada para este borrador; no se expone sin autorización.",
    )
    source_pdf_sha256 = models.CharField(
        "SHA-256 del PDF fuente",
        max_length=64,
        blank=True,
        editable=False,
    )
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
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="curriculum_packages",
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        FieldPanel("title"),
        FieldPanel("objective"),
        FieldPanel("micro_lesson"),
        FieldPanel("questions"),
        FieldPanel("final_explanation"),
        FieldPanel("source_references", read_only=True),
        FieldPanel("validation_summary", read_only=True),
        FieldPanel("ai_assisted", read_only=True),
    ]

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = "CurriculumPackage"
        verbose_name_plural = "CurriculumPackages"

    def __str__(self):
        return self.title or f"CurriculumPackage {self.pk}"

    def get_source_bytes(self) -> bytes | None:
        """Return source PDF bytes from source_blob with fallback to legacy source_pdf.
        If source_blob is present but invalid/corrupted, fails closed and returns None."""
        if getattr(self, "source_blob_id", None) and self.source_blob:
            blob = self.source_blob
            if not blob.is_valid_blob():
                return None
            if self.source_pdf_sha256 and (blob.sha256 or "").lower() != self.source_pdf_sha256.lower():
                return None
            return bytes(blob.content)
        if self.source_pdf:
            try:
                with self.source_pdf.open("rb") as s:
                    raw = s.read()
                if self.source_pdf_sha256 and hashlib.sha256(raw).hexdigest().lower() != self.source_pdf_sha256.lower():
                    return None
                return raw
            except Exception:
                return None
        return None


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

    def save_revision(self, *args, user=None, **kwargs):
        """Require explicit ownership before an authenticated revision save."""

        if user is not None and getattr(user, "is_authenticated", False):
            if self.created_by_id is None:
                raise ValidationError(
                    "El borrador sin propietaria requiere atribución explícita antes de guardar una revisión."
                )
            if self.created_by_id != user.pk:
                raise ValidationError(
                    "Sólo la maestra propietaria puede guardar una revisión curricular."
                )
        return super().save_revision(*args, user=user, **kwargs)

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
        if self.created_by_id != user.pk:
            raise ValidationError(
                "La publicación requiere a la maestra propietaria de la currícula."
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
            source_pdf=_snapshot_source_file(self, version),
            source_pdf_sha256=self.source_pdf_sha256 or "",
        )
        return result


def _snapshot_source_file(package, version):
    """Return a fresh ContentFile for the snapshot, never a mutable job file."""

    content = None
    if getattr(package, "source_blob_id", None) and package.source_blob:
        content = bytes(package.source_blob.content)
    elif package.source_pdf:
        with package.source_pdf.open("rb") as source:
            content = source.read()

    if content is None:
        return None

    from django.core.files.base import ContentFile

    digest = hashlib.sha256(content).hexdigest()
    if package.source_pdf_sha256 and digest != package.source_pdf_sha256:
        raise ValidationError("El PDF fuente conservado no coincide con su SHA-256.")
    return ContentFile(content, name=f"package-{package.pk}-v{version}.pdf")


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
    source_pdf = models.FileField(
        "PDF fuente publicado",
        upload_to=_published_source_upload_to,
        null=True,
        blank=True,
        editable=False,
        help_text="Copia inmutable de la fuente conservada para auditoría autorizada.",
    )
    source_pdf_sha256 = models.CharField(
        "SHA-256 del PDF publicado",
        max_length=64,
        blank=True,
        editable=False,
    )

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
        if any(snapshot.package.created_by_id != teacher.pk for snapshot in snapshots):
            raise ValidationError("Cada actividad debe pertenecer a la currícula de la maestra.")
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
        from curriculum.roadmap import duplicate_activity_ids

        duplicates = duplicate_activity_ids(self.payload)
        if duplicates:
            joined = ", ".join(duplicates)
            raise ValidationError(
                f"El roadmap contiene IDs de actividad duplicados: {joined}."
            )
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
        if roadmap_snapshot.published_by_id != teacher.pk:
            raise ValidationError("El roadmap debe pertenecer a la maestra autenticada.")
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


class ClassroomGroup(models.Model):
    """An institutional classroom label with no student roster."""

    name = models.CharField("nombre del salón", max_length=80)
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="classroom_groups",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="classroom_groups",
        null=True,
        blank=True,
    )
    # Kept nullable for pre-School rows; new institutional flows use
    # School.director and TeacherAssignment instead of group ownership.
    director = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="legacy_directed_classroom_groups",
        null=True,
        blank=True,
    )
    academic_year = models.CharField("ciclo escolar", max_length=32, blank=True, default="")
    modality = models.CharField("modalidad", max_length=32, blank=True, default="")
    grade = models.PositiveSmallIntegerField("grado", null=True, blank=True)
    group_key = models.CharField("clave de grupo", max_length=80, blank=True, default="")
    shift = models.CharField("turno", max_length=32, blank=True, default="")
    legacy_school_unresolved = models.BooleanField(
        "School histórica no recuperable",
        default=False,
        editable=False,
    )
    archived = models.BooleanField("archivado", default=False)
    archived_at = models.DateTimeField("archivado en", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "ClassroomGroup"
        verbose_name_plural = "ClassroomGroups"
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "school",
                    "academic_year",
                    "modality",
                    "grade",
                    "group_key",
                    "shift",
                ),
                name="unique_school_classroom_identity",
            )
        ]

    def clean(self):
        self.name = str(self.name or "").strip()
        if not self.name:
            raise ValidationError("El salón requiere un nombre corto.")
        if len(self.name) > 80:
            raise ValidationError("El salón no puede superar 80 caracteres.")
        if not self.group_key:
            self.group_key = self.name
        if self.modality not in {"", *dict(School.MODALITY_CHOICES)}:
            raise ValidationError("La modalidad del salón no está autorizada.")
        if self.grade is not None:
            maximum = 6 if self.modality == School.MODALITY_PRIMARY else 3
            if self.grade < 1 or (self.modality and self.grade > maximum):
                raise ValidationError("El grado no corresponde a la modalidad.")
        if self.school_id and self.school and self.school.archived and not self.archived:
            raise ValidationError("No se puede activar un grupo de una School archivada.")
        super().clean()

    def save(self, *args, **kwargs):
        self.name = str(self.name or "").strip()
        if not self.group_key:
            self.group_key = self.name
        if self.school_id is None:
            self.school = School.configured()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def archive(self, *, actor=None, source="manual"):
        if self.archived:
            return self
        self.archived = True
        self.archived_at = timezone.now()
        self.save(update_fields=["archived", "archived_at"])
        InstitutionalAuditEvent.record(
            school=self.school,
            actor=actor,
            action="group_archived",
            object_type="ClassroomGroup",
            object_id=self.pk,
            classroom_group=self,
            new_state={"archived": True},
            source=source,
        )
        return self


class TeacherAssignment(models.Model):
    """Historical institutional relationship between a teacher and group."""

    STATUS_ACTIVE = "active"
    STATUS_ENDED = "ended"
    STATUS_REJECTED = "rejected"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Activa"),
        (STATUS_ENDED, "Terminada"),
        (STATUS_REJECTED, "Rechazada"),
        (STATUS_ARCHIVED, "Archivada"),
    )

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="teacher_assignments")
    teacher = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT, related_name="teacher_assignments"
    )
    classroom_group = models.ForeignKey(
        ClassroomGroup, on_delete=models.PROTECT, related_name="teacher_assignments"
    )
    function = models.CharField("función", max_length=120, blank=True, default="")
    subject = models.CharField("materia", max_length=120, blank=True, default="")
    valid_from = models.DateField("vigente desde", null=True, blank=True)
    valid_until = models.DateField("vigente hasta", null=True, blank=True)
    status = models.CharField("estado", max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    assigned_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="created_teacher_assignments",
        null=True,
        blank=True,
    )
    source = models.CharField("origen", max_length=80, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField("terminada en", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "TeacherAssignment"
        verbose_name_plural = "TeacherAssignments"

    def clean(self):
        if self.classroom_group_id and self.school_id:
            group_school_id = self.classroom_group.school_id
            if group_school_id != self.school_id:
                raise ValidationError("La adscripción y el grupo deben pertenecer a la misma School.")
        if self.status == self.STATUS_ACTIVE and self.teacher_id and not self.teacher.is_active:
            raise ValidationError("Una maestra inactiva no puede recibir una adscripción activa.")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError("La vigencia de la adscripción no es válida.")
        super().clean()

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        previous = None
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "teacher_id", "classroom_group_id", "status", "function", "subject",
                "valid_from", "valid_until",
            ).first()
        if self.school_id is None and self.classroom_group_id:
            self.school_id = self.classroom_group.school_id
        if self.valid_from is None:
            self.valid_from = timezone.localdate()
        self.full_clean()
        result = super().save(*args, **kwargs)
        if is_new:
            InstitutionalAuditEvent.record(
                school=self.school,
                actor=self.assigned_by,
                action="assignment_created",
                object_type="TeacherAssignment",
                object_id=self.pk,
                classroom_group=self.classroom_group,
                new_state={"teacher": self.teacher_id, "status": self.status, "source": self.source},
                source=self.source,
            )
        elif previous:
            InstitutionalAuditEvent.record(
                school=self.school,
                actor=self.assigned_by,
                action="assignment_changed",
                object_type="TeacherAssignment",
                object_id=self.pk,
                classroom_group=self.classroom_group,
                previous_state={
                    key: value.isoformat() if hasattr(value, "isoformat") else value
                    for key, value in previous.items()
                },
                new_state={
                    "teacher_id": self.teacher_id,
                    "classroom_group_id": self.classroom_group_id,
                    "status": self.status,
                    "function": self.function,
                    "subject": self.subject,
                    "valid_from": self.valid_from.isoformat() if self.valid_from else None,
                    "valid_until": self.valid_until.isoformat() if self.valid_until else None,
                },
                source=self.source,
            )
        return result

    def delete(self, *args, **kwargs):
        raise ValidationError("Una TeacherAssignment histórica no se elimina.")

    @classmethod
    def create_assignment(cls, *, teacher, classroom_group, actor=None, source="manual", **kwargs):
        if teacher == actor:
            raise ValidationError("Dirección no puede adscribirse a sí misma como maestra.")
        if not teacher.is_active or not teacher.is_staff:
            raise ValidationError("La cuenta docente debe estar activa y ser de personal.")
        if classroom_group.school_id is None:
            raise ValidationError("El grupo requiere una School antes de adscribir una maestra.")
        return cls.objects.create(
            school_id=classroom_group.school_id,
            teacher=teacher,
            classroom_group=classroom_group,
            assigned_by=actor,
            source=source,
            **kwargs,
        )

    @transaction.atomic
    def end(self, *, actor=None, source="manual"):
        locked = type(self).objects.select_for_update().get(pk=self.pk)
        if locked.status != self.STATUS_ACTIVE:
            return locked
        old_status = locked.status
        locked.status = self.STATUS_ENDED
        locked.valid_until = locked.valid_until or timezone.localdate()
        locked.ended_at = timezone.now()
        locked.assigned_by = actor or locked.assigned_by
        locked.source = source
        locked.save(update_fields=["status", "valid_until", "ended_at", "assigned_by", "source"])
        InstitutionalAuditEvent.record(
            school=locked.school,
            actor=actor,
            action="assignment_ended",
            object_type="TeacherAssignment",
            object_id=locked.pk,
            classroom_group=locked.classroom_group,
            previous_state={"status": old_status},
            new_state={"status": locked.status},
            source=source,
        )
        return locked


class SupportRequest(models.Model):
    """A teacher-authored, non-nominal request for institutional support."""

    CATEGORY_RESOURCES = "resources"
    CATEGORY_SESSION = "session_operation"
    CATEGORY_FAMILIES = "family_communication"
    CATEGORY_TECHNICAL = "technical_training"
    CATEGORY_CHOICES = (
        (CATEGORY_RESOURCES, "Recursos"),
        (CATEGORY_SESSION, "Operación de sesión"),
        (CATEGORY_FAMILIES, "Comunicación general con familias"),
        (CATEGORY_TECHNICAL, "Apoyo técnico o capacitación"),
    )
    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_NEEDS_CLARIFICATION = "needs_clarification"
    STATUS_RESOLVED = "resolved"
    STATUS_DISMISSED = "dismissed"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pendiente"),
        (STATUS_IN_PROGRESS, "En atención"),
        (STATUS_NEEDS_CLARIFICATION, "Requiere aclaración"),
        (STATUS_RESOLVED, "Resuelta"),
        (STATUS_DISMISSED, "Descartada"),
    )

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="support_requests")
    classroom_group = models.ForeignKey("ClassroomGroup", on_delete=models.PROTECT, related_name="support_requests")
    created_by = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="support_requests")
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    description = models.CharField(max_length=500)
    responsible = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT, related_name="assigned_support_requests", null=True, blank=True
    )
    target_date = models.DateField()
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def clean(self):
        self.description = str(self.description or "").strip()
        if not self.description:
            raise ValidationError("La solicitud requiere una descripción breve.")
        if self.classroom_group_id and self.school_id != self.classroom_group.school_id:
            raise ValidationError("La solicitud debe permanecer en la School del salón.")
        if self.responsible_id and (not self.responsible.is_active or not self.responsible.is_staff):
            raise ValidationError("La persona responsable debe ser personal activo.")

    def close(self, *, status):
        if status not in (self.STATUS_RESOLVED, self.STATUS_DISMISSED):
            raise ValidationError("Sólo se puede cerrar una solicitud como resuelta o descartada.")
        self.status = status
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at", "updated_at"])
        return self


class GroupRoadmapProgress(models.Model):
    """Shared, ephemeral navigation cursor for one classroom session."""

    session = models.OneToOneField(
        "ClassroomSession", on_delete=models.CASCADE, related_name="group_roadmap_progress"
    )
    roadmap_snapshot = models.ForeignKey(
        PublishedRoadmapSnapshot, on_delete=models.PROTECT, related_name="group_progress"
    )
    completed_activity_ids = models.JSONField(default=list, blank=True)
    current_activity_id = models.CharField(max_length=160, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def for_session(cls, session):
        if session.roadmap_snapshot_id is None:
            return None
        progress, _ = cls.objects.get_or_create(
            session=session,
            defaults={"roadmap_snapshot_id": session.roadmap_snapshot_id},
        )
        if progress.roadmap_snapshot_id != session.roadmap_snapshot_id:
            raise ValidationError("El progreso grupal no corresponde al snapshot de la sesión.")
        from curriculum.roadmap import ordered_activity_ids
        activity_ids = ordered_activity_ids(progress.roadmap_snapshot.payload)
        if not activity_ids:
            return progress
        completed = list(dict.fromkeys(str(value) for value in (progress.completed_activity_ids or [])))
        current = progress.current_activity_id if progress.current_activity_id in activity_ids else ""
        if not current:
            current = next((value for value in activity_ids if value not in completed), "")
            if current != progress.current_activity_id or completed != progress.completed_activity_ids:
                progress.current_activity_id = current
                progress.completed_activity_ids = completed
                progress.save(update_fields=["completed_activity_ids", "current_activity_id", "updated_at"])
        return progress

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).values(
                "session_id", "roadmap_snapshot_id"
            ).first()
            if original and (original["session_id"] != self.session_id or
                             original["roadmap_snapshot_id"] != self.roadmap_snapshot_id):
                raise ValidationError("El progreso grupal y su snapshot quedan fijados.")
        if self.session.roadmap_snapshot_id != self.roadmap_snapshot_id:
            raise ValidationError("El progreso grupal debe usar el snapshot fijado a la sesión.")
        return super().save(*args, **kwargs)

    def states(self):
        from curriculum.roadmap import states_for_group_progress
        return states_for_group_progress(
            self.roadmap_snapshot.payload,
            self.completed_activity_ids,
            self.current_activity_id or None,
        )

    def complete_activity(self, activity_id):
        from curriculum.roadmap import ordered_activity_ids
        activity_id = str(activity_id)
        ids = ordered_activity_ids(self.roadmap_snapshot.payload)
        if activity_id not in ids:
            raise ValidationError("La actividad no existe en el roadmap publicado.")
        completed = list(dict.fromkeys(str(value) for value in self.completed_activity_ids))
        current = self.current_activity_id or next((value for value in ids if value not in completed), "")
        if activity_id != current:
            raise ValidationError("La actividad todavía no es el paso actual del grupo.")
        if activity_id not in completed:
            completed.append(activity_id)
        self.completed_activity_ids = completed
        self.current_activity_id = next((value for value in ids if value not in completed), "")
        self.save(update_fields=["completed_activity_ids", "current_activity_id", "updated_at"])
        return self

    def advance_to(self, activity_id):
        from curriculum.roadmap import ordered_activity_ids
        ids = ordered_activity_ids(self.roadmap_snapshot.payload)
        activity_id = str(activity_id)
        if activity_id not in ids:
            raise ValidationError("La actividad no existe en el roadmap publicado.")
        completed = list(dict.fromkeys(str(value) for value in (self.completed_activity_ids or [])))
        if ids and len(set(completed)) == len(ids):
            raise ValidationError("El roadmap grupal ya está completo.")
        current_id = self.current_activity_id if self.current_activity_id in ids else next(
            (value for value in ids if value not in completed), ""
        )
        if current_id != self.current_activity_id:
            self.current_activity_id = current_id
            self.completed_activity_ids = completed
            self.save(update_fields=["completed_activity_ids", "current_activity_id", "updated_at"])
        current_index = ids.index(current_id) if current_id in ids else -1
        target_index = ids.index(activity_id)
        if target_index <= current_index:
            raise ValidationError("El avance grupal debe seleccionar un paso posterior.")
        self.completed_activity_ids = list(dict.fromkeys([*completed, *ids[:target_index]]))
        self.current_activity_id = activity_id
        self.save(update_fields=["completed_activity_ids", "current_activity_id", "updated_at"])
        return self


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
    classroom_group = models.ForeignKey(
        "ClassroomGroup",
        on_delete=models.PROTECT,
        related_name="sessions",
        null=True,
        blank=True,
    )
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="classroom_sessions",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="classroom_sessions",
        null=True,
        blank=True,
    )
    legacy_owner_unresolved = models.BooleanField(
        "propietaria histórica no recuperable",
        default=False,
        editable=False,
    )
    legacy_school_unresolved = models.BooleanField(
        "School histórica no recuperable",
        default=False,
        editable=False,
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
    def _validate_teacher_snapshot_ownership(
        cls,
        *,
        teacher,
        snapshot,
        roadmap_snapshot,
    ):
        if teacher is None:
            return
        if snapshot.package.created_by_id != teacher.pk:
            raise ValidationError(
                "El snapshot curricular debe pertenecer a la maestra propietaria de la sesión."
            )
        if roadmap_snapshot is None:
            return
        has_foreign_package = PublishedPackageSnapshot.objects.filter(
            pk__in=roadmap_snapshot.package_snapshot_ids()
        ).exclude(package__created_by_id=teacher.pk).exists()
        if roadmap_snapshot.published_by_id != teacher.pk or has_foreign_package:
            raise ValidationError(
                "El roadmap debe pertenecer a la maestra propietaria de la sesión."
            )

    @classmethod
    def start_from_snapshot(
        cls,
        snapshot,
        roadmap_snapshot=None,
        classroom_group=None,
        teacher=None,
    ):
        if not snapshot or snapshot.pk is None:
            raise ValidationError("La sesión requiere un snapshot publicado existente.")
        try:
            published_snapshot = PublishedPackageSnapshot.objects.select_related(
                "package"
            ).get(pk=snapshot.pk)
            published_roadmap = (
                PublishedRoadmapSnapshot.objects.get(pk=roadmap_snapshot.pk)
                if roadmap_snapshot is not None
                else None
            )
            if published_roadmap is not None:
                published_roadmap.validate_package_snapshots()
            cls._validate_teacher_snapshot_ownership(
                teacher=teacher,
                snapshot=published_snapshot,
                roadmap_snapshot=published_roadmap,
            )
        except (PublishedPackageSnapshot.DoesNotExist, PublishedRoadmapSnapshot.DoesNotExist) as error:
            raise ValidationError(
                "La sesión requiere snapshots publicados existentes."
            ) from error
        return cls.objects.create(
            snapshot=published_snapshot,
            roadmap_snapshot=published_roadmap,
            classroom_group=classroom_group,
            school=classroom_group.school if classroom_group is not None else None,
            created_by=teacher,
        )

    @classmethod
    @transaction.atomic
    def prepare_from_snapshot(
        cls,
        snapshot,
        student_count,
        device_count,
        roadmap_snapshot=None,
        classroom_group=None,
        teacher=None,
    ):
        if not snapshot or snapshot.pk is None:
            raise ValidationError("La sesión requiere un snapshot publicado existente.")
        try:
            published_snapshot = PublishedPackageSnapshot.objects.select_related(
                "package"
            ).get(pk=snapshot.pk)
            published_roadmap = (
                PublishedRoadmapSnapshot.objects.get(pk=roadmap_snapshot.pk)
                if roadmap_snapshot is not None
                else None
            )
            capacities = calculate_distribution(student_count, device_count)
            if published_roadmap is not None:
                published_roadmap.validate_package_snapshots()
            cls._validate_teacher_snapshot_ownership(
                teacher=teacher,
                snapshot=published_snapshot,
                roadmap_snapshot=published_roadmap,
            )
        except (PublishedPackageSnapshot.DoesNotExist, PublishedRoadmapSnapshot.DoesNotExist) as error:
            raise ValidationError(
                "La sesión requiere snapshots publicados existentes."
            ) from error
        except ValueError as error:
            raise ValidationError(str(error)) from error

        session = cls.objects.create(
            snapshot=published_snapshot,
            roadmap_snapshot=published_roadmap,
            classroom_group=classroom_group,
            school=classroom_group.school if classroom_group is not None else None,
            created_by=teacher,
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
                "snapshot_id", "roadmap_snapshot_id", "status", "closed_at",
                "classroom_group_id", "school_id",
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
            if original and original["classroom_group_id"] != self.classroom_group_id:
                raise ValidationError("El grupo de una ClassroomSession queda fijado.")
            if original and original["school_id"] != self.school_id:
                raise ValidationError("La School de una ClassroomSession queda fijada.")
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
        if self.school_id is None and self.classroom_group_id:
            self.school_id = self.classroom_group.school_id
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
                            participant_key=turn.participant_key,
                            activity_id=activity_id or "actividad-0",
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
    participant_key = models.UUIDField(
        "clave seudónima del participante",
        default=uuid.uuid4,
        editable=False,
        db_index=True,
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
            # Mint the key at the turn boundary. It is never derived from the
            # temporary apodo, device, or any other user-provided value.
            self.participant_key = uuid.uuid4()
            if self.status == self.STATUS_ACTIVE:
                self.display_name = self.normalize_display_name(self.display_name)
            elif self.status == self.STATUS_COMPLETED:
                self.display_name = ""
        else:
            original = type(self).objects.filter(pk=self.pk).values(
                "assignment_id", "participant_key", "status", "display_name"
            ).first()
            if original and original["participant_key"] != self.participant_key:
                raise ValidationError("La clave seudónima de un turno queda fijada.")
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

    def complete_activity(self, activity_id, *, package_snapshot=None, enforce_current=True):
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
        if enforce_current and activity_id != self.current_activity_id():
            raise ValidationError("La actividad todavía no está habilitada en este recorrido.")
        self.completed_activity_ids = list(dict.fromkeys([*completed_ids, activity_id]))
        self.save(update_fields=["completed_activity_ids", "updated_at"])
        return self

    def record_correct_answer(self, activity_id, question_index, question_count, *, enforce_current=True):
        """Persist a correct response and complete its activity immediately."""

        activity_id = str(activity_id)
        if enforce_current and activity_id != self.current_activity_id():
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
            self.complete_activity(activity_id, enforce_current=enforce_current)
            return True
        return False

    def roadmap_states(self):
        from curriculum.roadmap import states_for_progress

        return states_for_progress(
            self.roadmap_snapshot.payload,
            self.completed_activity_ids,
        )


class PseudonymousResult(models.Model):
    """An erasable result grouped only by a random participant key."""

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
    participant_key = models.UUIDField(
        "clave seudónima del participante",
        db_index=True,
    )
    activity_id = models.CharField(
        "actividad opaca",
        max_length=160,
        blank=True,
        default="",
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

    STATUS_UPLOADED = "uploaded"  # Fuente PDF aceptada y disponible; no significa "sin interpretar".
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

    INTERPRETATION_STATE_NOT_STARTED = "not_started"
    INTERPRETATION_STATE_ORGANIZING = "organizing"
    INTERPRETATION_STATE_READY = "ready"
    INTERPRETATION_STATE_FAILED = "failed"
    INTERPRETATION_STATE_CHOICES = (
        (INTERPRETATION_STATE_NOT_STARTED, "No iniciada"),
        (INTERPRETATION_STATE_ORGANIZING, "Organizando planeación"),
        (INTERPRETATION_STATE_READY, "Planeación organizada/lista para revisar"),
        (INTERPRETATION_STATE_FAILED, "Interpretación interrumpida o fallida"),
    )

    pdf = models.FileField(
        "PDF de la currícula",
        upload_to=curriculum_import_pdf_path,
    )
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="curriculum_import_jobs",
        null=True,
        blank=True,
        editable=False,
    )
    status = models.CharField(
        "estado",
        max_length=24,
        choices=STATUS_CHOICES,
        default=STATUS_UPLOADED,
        help_text=(
            "Estado del pipeline legado de extracción jerárquica y autoría "
            "(temas, subtemas, actividades y conversión). STATUS_UPLOADED indica "
            "únicamente que el PDF fuente fue recibido y aceptado en storage; "
            "el ciclo de interpretación de la fuente es gobernado por 'interpretation_state'."
        ),
    )
    interpretation_state = models.CharField(
        "estado de interpretación",
        max_length=24,
        choices=INTERPRETATION_STATE_CHOICES,
        default=INTERPRETATION_STATE_NOT_STARTED,
        db_index=True,
        help_text=(
            "Estado canónico del ciclo de vida de interpretación V0 de la fuente "
            "(not_started, organizing, ready, failed). Es ortogonal e independiente "
            "del campo 'status' del pipeline legado de temas/subtemas."
        ),
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
    interpretation_dossier = models.JSONField(
        "dossier de interpretación V0",
        default=dict,
        blank=True,
        help_text="Dossier estructurado y versionado de interpretación curricular V0.",
    )
    interpretation_claim_token = models.UUIDField(
        "token de reclamo de interpretación",
        null=True,
        blank=True,
        editable=False,
    )
    interpretation_claimed_at = models.DateTimeField(
        "fecha de reclamo de interpretación",
        null=True,
        blank=True,
        editable=False,
    )
    interpretation_error_message = models.TextField(
        "error de interpretación",
        blank=True,
        default="",
        help_text=(
            "Mensaje de error específico del ciclo de vida de interpretación V0. "
            "Es ortogonal e independiente del campo 'error_message' del pipeline legado."
        ),
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
    progress_finished_at = models.DateTimeField(
        "fin de la etapa",
        null=True,
        blank=True,
        editable=False,
    )
    cancel_requested = models.BooleanField(default=False, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
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

    def get_interpretation_dossier(self):
        """Return the deserialized ImportDossier or None if corrupt/malformed."""
        if not self.interpretation_dossier or not isinstance(self.interpretation_dossier, dict):
            return None
        from curriculum.source_interpreter import ImportDossier
        try:
            return ImportDossier.from_dict(self.interpretation_dossier)
        except (ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
            return None

    def save_interpretation_dossier(self, dossier, explicit_state=None, error_message=None, owner_token=None):
        """Persist a versioned ImportDossier and derive/persist interpretation_state atomically.

        Single source of truth for persisting an interpretation dossier:
        Delegates exclusively to interpretation_commands.save_interpretation_dossier_command
        to enforce the unified CAS and fail-closed concurrency policy.
        """
        from curriculum.interpretation_commands import save_interpretation_dossier_command

        return save_interpretation_dossier_command(
            self,
            dossier,
            explicit_state=explicit_state,
            error_message=error_message,
            owner_token=owner_token,
        )

    def is_stage_stale(self, now=None) -> bool:
        """Check whether the current progress stage or active claim has exceeded timeout (90m)."""
        if now is None:
            now = timezone.now()
        else:
            now = _normalize_datetime(now)

        timeout = timedelta(minutes=90)

        if self.progress_stage and self.progress_started_at:
            started_at = _normalize_datetime(self.progress_started_at)
            if started_at and (now - started_at) > timeout:
                return True

        if self.interpretation_claim_token and self.interpretation_claimed_at:
            claimed_at = _normalize_datetime(self.interpretation_claimed_at)
            if claimed_at and (now - claimed_at) > timeout:
                return True

        return False

    def has_valid_ready_dossier(self, pdf_bytes: bytes | None = None) -> bool:
        """Check if job possesses a valid, active, deserializable ImportDossier matching source PDF."""
        raw = self.interpretation_dossier
        if not raw or not isinstance(raw, dict):
            return False
        # Part B: Strict explicit raw key verification prior to deserialization
        version = raw.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            return False
        if raw.get("status") != "active":
            return False
        source_sha = raw.get("source_sha256")
        if not isinstance(source_sha, str) or not bool(re.fullmatch(r"^[0-9a-fA-F]{64}$", source_sha.strip())):
            return False

        dossier = self.get_interpretation_dossier()
        if dossier is None or getattr(dossier, "version", 0) < 1:
            return False
        if getattr(dossier, "status", "") != "active":
            return False
        if pdf_bytes is None:
            if not self.pdf:
                return False
            try:
                with self.pdf.open("rb") as stream:
                    pdf_bytes = stream.read()
            except (FileNotFoundError, OSError, IOError, ValueError):
                return False

        current_sha = hashlib.sha256(pdf_bytes).hexdigest()
        if current_sha.lower() != source_sha.strip().lower():
            return False

        report = raw.get("verification_report")
        if not isinstance(report, dict) or not report:
            return False

        from curriculum.verification import validate_canonical_verification_report

        if not validate_canonical_verification_report(dossier, pdf_bytes, report):
            return False

        return True

    def get_interpretation_state(self, now=None) -> str:
        """Return the persisted canonical interpretation state."""
        return self.interpretation_state or self.INTERPRETATION_STATE_NOT_STARTED

    def get_active_approval(self, pdf_bytes: bytes | None = None, has_valid_ready_dossier: bool | None = None):
        """Return the active CurriculumImportApproval derived from canonical ready status, version, and SHA match.
        Requires job READY, version+SHA match, valid source blob, and canonical job.has_valid_ready_dossier().
        If current source is missing, or report/blob is invalid/tampered, returns None."""
        if self.interpretation_state != self.INTERPRETATION_STATE_READY:
            return None
        dossier = self.get_interpretation_dossier()
        if not dossier:
            return None
        v = getattr(dossier, "version", None)
        sha = getattr(dossier, "source_sha256", None)
        if not v or not sha:
            return None
        approval = self.approvals.filter(
            dossier_version=v,
            source_sha256=sha,
        ).first()
        if not approval:
            return None
        if not approval.is_active:
            return None
        if has_valid_ready_dossier is None:
            has_valid_ready_dossier = self.has_valid_ready_dossier(pdf_bytes=pdf_bytes)
        if not has_valid_ready_dossier:
            return None
        return approval


    @property
    def is_approved(self) -> bool:
        """True if the job has a currently active and valid approval matching current dossier."""
        return self.get_active_approval() is not None

    def invalidate_approvals(self, reason="Edición o nueva versión del dossier"):
        """No-op: Approval active status is strictly derived from dossier version, SHA, and ready report match.
        Historical records are append-only and never updated."""
        pass


class CurriculumImportApprovalQuerySet(models.QuerySet):
    """QuerySet enforcing append-only invariants and dynamically derived is_active filtering."""

    def update(self, **kwargs):
        raise PermissionError("CurriculumImportApproval records are append-only and cannot be updated.")

    def delete(self):
        raise PermissionError("CurriculumImportApproval records are permanent audit logs and cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise PermissionError("CurriculumImportApproval records are append-only and cannot be updated.")

    def update_or_create(self, defaults=None, **kwargs):
        lookup = {k: v for k, v in kwargs.items() if k != "defaults"}
        if self.filter(**lookup).exists():
            raise PermissionError("CurriculumImportApproval records are append-only and cannot be updated.")
        return super().update_or_create(defaults=defaults, **kwargs)

    async def aupdate(self, **kwargs):
        raise PermissionError("CurriculumImportApproval records are append-only and cannot be updated.")

    async def abulk_update(self, objs, fields, batch_size=None):
        raise PermissionError("CurriculumImportApproval records are append-only and cannot be updated.")

    async def adelete(self):
        raise PermissionError("CurriculumImportApproval records are permanent audit logs and cannot be deleted.")

    def filter(self, *args, **kwargs):
        if "is_active" in kwargs:
            is_active_val = bool(kwargs.pop("is_active"))
            job = kwargs.get("job")
            job_id = kwargs.get("job_id") or (getattr(job, "pk", None) if job else None)
            if job_id is not None:
                job_obj = job if isinstance(job, CurriculumImportJob) else CurriculumImportJob.objects.filter(pk=job_id).first()
                if job_obj:
                    active_approval = job_obj.get_active_approval()
                    if is_active_val:
                        if active_approval:
                            return super().filter(*args, pk=active_approval.pk, **kwargs)
                        return super().none()
                    else:
                        qs = super().filter(*args, **kwargs)
                        if active_approval:
                            return qs.exclude(pk=active_approval.pk)
                        return qs
                else:
                    if is_active_val:
                        return super().none()
                    return super().filter(*args, **kwargs)
            # When job is not specified in filter, filter by comparing is_active on instances
            matched_pks = [
                obj.pk for obj in super().filter(*args, **kwargs)
                if obj.is_active == is_active_val
            ]
            return super().filter(pk__in=matched_pks)
        return super().filter(*args, **kwargs)

    def exclude(self, *args, **kwargs):
        if "is_active" in kwargs:
            is_active_val = not bool(kwargs.pop("is_active"))
            return self.filter(*args, is_active=is_active_val, **kwargs)
        return super().exclude(*args, **kwargs)


class CurriculumImportApproval(models.Model):
    """Auditable teacher approval for an imported curriculum planning job.

    Enforces ADR 0001/0002/0006:
    - Approval is explicit, authenticated, teacher-owned, and bound to an exact canonical dossier snapshot, version, and SHA.
    - Approval DOES NOT publish, DOES NOT create PublishedPackageSnapshot, and DOES NOT activate sessions.
    - Approval creates/updates a draft CurriculumPackage in 'Aprobada para preparar' status.
    - Model is strictly append-only: save() of existing instances, delete(), update(), bulk_update() are rejected with PermissionError.
    - Active status is strictly derived: requires job READY, version+SHA match, and canonical job.has_valid_ready_dossier().
    - FS mutations or missing source files are automatically detected by active guard.
    - No mutable DB flag exists (removed in migration 0041).
    """

    job = models.ForeignKey(
        CurriculumImportJob,
        on_delete=models.CASCADE,
        related_name="approvals",
        verbose_name="trabajo de importación",
    )
    dossier_version = models.PositiveIntegerField("versión del dossier")
    source_sha256 = models.CharField("SHA-256 del PDF fuente", max_length=64)
    dossier_snapshot = models.JSONField("snapshot canónico del dossier", default=dict)
    approved_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="curriculum_import_approvals",
        verbose_name="docente que aprobó",
    )
    approved_at = models.DateTimeField("fecha de aprobación", default=timezone.now)
    package = models.ForeignKey(
        "curriculum.CurriculumPackage",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="import_approvals",
        verbose_name="paquete curricular borrador",
    )
    source_blob = models.ForeignKey(
        CurriculumSourceBlob,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approvals",
        verbose_name="blob fuente inmutable",
    )
    invalidated_at = models.DateTimeField("fecha de invalidación", null=True, blank=True, editable=False)
    invalidation_reason = models.CharField("motivo de invalidación", max_length=255, blank=True, default="", editable=False)
    pending_acknowledged = models.BooleanField("elementos pendientes reconocidos", default=False)
    pending_items_count = models.PositiveIntegerField("elementos opcionales pendientes", default=0)

    objects = CurriculumImportApprovalQuerySet.as_manager()

    class Meta:
        ordering = ["-approved_at", "-id"]
        verbose_name = "CurriculumImportApproval"
        verbose_name_plural = "CurriculumImportApprovals"
        constraints = [
            models.UniqueConstraint(
                fields=["job", "dossier_version"],
                name="unique_curriculum_import_approval_job_version",
            ),
            models.CheckConstraint(
                condition=models.Q(dossier_version__gt=0),
                name="check_approval_dossier_version_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(pending_items_count__gte=0),
                name="check_approval_pending_items_count_gte_zero",
            ),
        ]

    def __init__(self, *args, **kwargs):
        kwargs.pop("is_active", None)
        kwargs.pop("_is_active", None)
        super().__init__(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        """Derived active status: requires job READY, version+SHA match, valid canonical report,
        and valid immutable source blob matching source_sha256.
        If source blob is missing, tampered, or invalid, returns False (fail closed)."""
        if not self.job_id:
            return False
        try:
            job = CurriculumImportJob.objects.filter(pk=self.job_id).first()
            if not job:
                return False
            if job.interpretation_state != job.INTERPRETATION_STATE_READY:
                return False
            dossier = job.get_interpretation_dossier()
            if not dossier:
                return False
            v = getattr(dossier, "version", None)
            sha = getattr(dossier, "source_sha256", None)
            if self.dossier_version != v or (self.source_sha256 or "").lower() != (sha or "").lower():
                return False
            if not job.has_valid_ready_dossier():
                return False
            # Strict blob validation: must be present, valid, and match source_sha256 exactly
            if not self.source_blob_id:
                return False
            blob = self.source_blob
            if blob is None or not blob.is_valid_blob():
                return False
            if (blob.sha256 or "").lower() != (self.source_sha256 or "").lower():
                return False
            return True
        except Exception:
            return False

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            raise PermissionError("CurriculumImportApproval records are append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("CurriculumImportApproval records are permanent audit logs and cannot be deleted.")

    async def asave(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            raise PermissionError("CurriculumImportApproval records are append-only and cannot be updated.")
        await super().asave(*args, **kwargs)

    async def adelete(self, *args, **kwargs):
        raise PermissionError("CurriculumImportApproval records are permanent audit logs and cannot be deleted.")

    def __str__(self):
        status = "vigente" if self.is_active else "histórica"
        return f"Aprobación job {self.job_id} v{self.dossier_version} ({status})"

    def get_source_bytes(self) -> bytes | None:
        """Return source PDF bytes from source_blob with fallback to job PDF.
        If source_blob is present but invalid/corrupted, fails closed and returns None."""
        if getattr(self, "source_blob_id", None) and self.source_blob:
            blob = self.source_blob
            if not blob.is_valid_blob() or (blob.sha256 or "").lower() != (self.source_sha256 or "").lower():
                return None
            return bytes(blob.content)
        if self.job and self.job.pdf:
            try:
                with self.job.pdf.open("rb") as s:
                    raw = s.read()
                if (self.source_sha256 or "").lower() != hashlib.sha256(raw).hexdigest().lower():
                    return None
                return raw
            except Exception:
                return None
        return None



class PseudonymousSurveyResponse(models.Model):
    """An erasable group survey rating with no participant relationship."""

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
    rating = models.PositiveSmallIntegerField("calificación de estrellas")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        verbose_name = "PseudonymousSurveyResponse"
        verbose_name_plural = "PseudonymousSurveyResponses"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="survey_rating_between_one_and_five",
            )
        ]

    def clean(self):
        try:
            rating = int(self.rating)
        except (TypeError, ValueError):
            rating = None
        if rating is None or not 1 <= rating <= 5:
            raise ValidationError("La calificación debe estar entre 1 y 5 estrellas.")
        super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

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


class CurriculumPackageCreateView(CreateView):
    """Assign new Wagtail drafts explicitly before their first revision."""

    def save_instance(self):
        self.form.instance.created_by = self.request.user
        return super().save_instance()


class CurriculumPackageViewSet(SnippetViewSet):
    model = CurriculumPackage
    add_view_class = CurriculumPackageCreateView
    workflow_action_view_class = EditorialReviewerWorkflowActionView
    permission_policy = None


class CurriculumPackagePermissionPolicy(ModelPermissionPolicy):
    """Keep Wagtail snippet reads and writes within the teacher owner."""

    def user_has_permission_for_instance(self, user, action, instance):
        owns_instance = user.is_superuser or instance.created_by_id == user.pk
        return owns_instance and super().user_has_permission_for_instance(
            user, action, instance
        )

    def instances_user_has_any_permission_for(self, user, actions):
        queryset = super().instances_user_has_any_permission_for(user, actions)
        if user.is_superuser:
            return queryset
        return queryset.filter(created_by=user)

    def users_with_any_permission_for_instance(self, actions, instance):
        queryset = super().users_with_any_permission_for_instance(actions, instance)
        if instance.created_by_id is None:
            return queryset.filter(is_superuser=True)
        return queryset.filter(models.Q(pk=instance.created_by_id) | models.Q(is_superuser=True))


CurriculumPackageViewSet.permission_policy = CurriculumPackagePermissionPolicy(
    CurriculumPackage
)


register_snippet(CurriculumPackageViewSet)


class CurriculumTeacherReview(models.Model):
    """Durable, bounded clarification conversation; never an editorial approval."""

    job = models.OneToOneField(
        CurriculumImportJob, on_delete=models.PROTECT, related_name="teacher_review"
    )
    revision = models.PositiveIntegerField(default=1)
    dossier_version = models.PositiveIntegerField()
    source_sha256 = models.CharField(max_length=64)
    state = models.JSONField(default=dict)
    draft_state = models.JSONField(default=dict)
    draft_epoch = models.PositiveIntegerField(default=0)
    generation_token = models.UUIDField(null=True, blank=True, editable=False)
    generation_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
