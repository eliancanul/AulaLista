"""HTTP input contracts. Interpretation content is owned by S06."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Revision = Annotated[int, Field(strict=True, ge=1)]
Text = Annotated[str, Field(strict=True, max_length=20000)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftChanges(InputModel):
    title: Text | None = None
    objective: Text | None = None
    materials: list[Text] | None = Field(default=None, max_length=200)
    steps: list[Text] | None = Field(default=None, max_length=200)
    assessment: Text | None = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set
        ):
            raise ValueError("Indica al menos un cambio sin valores nulos.")
        return self


class DraftPatch(InputModel):
    expected_revision: Revision
    changes: DraftChanges


class ApprovalRequest(InputModel):
    expected_revision: Revision
    confirm: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def require_confirmation(self):
        if self.confirm is not True:
            raise ValueError("Confirma la revisión del borrador para aprobarlo.")
        return self


class ChatRequest(InputModel):
    interpretation_id: Annotated[str, Field(min_length=1, max_length=200)]
    message: Annotated[str, Field(min_length=1, max_length=4000)]

    @model_validator(mode="after")
    def require_message(self):
        if not self.message.strip():
            raise ValueError("Escribe una pregunta sobre tu planeación.")
        return self


class ChatResponse(BaseModel):
    interpretation_id: str
    message: str
    source_ids: list[str]
    proposals: list[dict] = Field(default_factory=list)
    mode: Literal["source_lookup"] = "source_lookup"
    applies_changes: Literal[False] = False


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    fields: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SourceSegment(BaseModel):
    id: str
    text: str
    page: int = Field(ge=1)


class InterpretationField(BaseModel):
    key: str
    value: str | list[str] | None
    status: Literal["extracted", "suggested", "unknown"]
    evidence_ids: list[str]
    reason: str


class DraftResponse(BaseModel):
    id: str
    title: str
    objective: str
    materials: list[str]
    steps: list[str]
    assessment: str
    source_ids: list[str]
    revision: int = Field(ge=1)
    approval_status: Literal["pending", "approved"]
    status: str


class InterpretationV1Response(BaseModel):
    schema_version: Literal[1]
    document_id: str
    source_segments: list[SourceSegment]
    fields: list[InterpretationField]
    missing_questions: list[str]
    draft: DraftResponse
    diagnostics: dict = Field(default_factory=dict)


class LayoutSourceSegment(SourceSegment):
    kind: Literal["text", "heading_candidate", "table_row_candidate"]
    text_start: int = Field(ge=0)
    text_end: int = Field(ge=1)

    @model_validator(mode="after")
    def require_ordered_offsets(self):
        if self.text_end <= self.text_start:
            raise ValueError("El final del fragmento debe seguir a su inicio.")
        return self


class InterpretationV2Response(InterpretationV1Response):
    schema_version: Literal[2]
    source_segments: list[LayoutSourceSegment]


InterpretationResponse = Annotated[
    InterpretationV1Response | InterpretationV2Response,
    Field(discriminator="schema_version"),
]
