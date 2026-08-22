from django.db import models
from wagtail import blocks
from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField
from wagtail.snippets.models import register_snippet


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


@register_snippet
class CurriculumPackage(models.Model):
    """A Wagtail-authored DemoPackage that remains an editorial draft in T02."""

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
