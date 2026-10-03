"""Transport boundaries for persistent, teacher-owned interpretation drafts."""

import io
import re
import unicodedata
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from api.schemas import (
    ApprovalRequest, ChatRequest, ChatResponse, DraftPatch,
    DraftResponse, InterpretationResponse,
)

router = APIRouter()


class APIError(Exception):
    def __init__(self, status, code, message, *, retryable=False):
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def unavailable():
    return APIError(503, "service_unavailable",
                    "El servicio no está disponible. Inténtalo más tarde.", retryable=True)


def current_teacher(request: Request):
    try:
        from api.auth import require_teacher
    except ImportError:
        raise unavailable() from None
    return require_teacher(request)


def repository(request: Request):
    if getattr(request.app.state, "repository", None) is not None:
        return request.app.state.repository
    try:
        from api.persistence import get_repository
    except ImportError:
        raise unavailable() from None
    return get_repository()


def interpret(source, *, document_id):
    try:
        from curriculum.interpretation_service import interpret_source
    except ImportError:
        raise unavailable() from None
    from curriculum.source_interpreter import (
        CurriculumInterpretationError, InterpretationCancelledError, InterpretationTimeoutError,
    )
    try:
        return interpret_source(source, document_id=document_id)
    except InterpretationCancelledError:
        raise APIError(409, "request_cancelled", "La interpretación fue cancelada.") from None
    except InterpretationTimeoutError:
        raise APIError(504, "interpretation_timeout", "La interpretación tardó demasiado. Inténtalo de nuevo.", retryable=True) from None
    except CurriculumInterpretationError:
        raise APIError(422, "interpretation_failed", "No se pudo interpretar el documento. Revisa el PDF.") from None


def validate_pdf(content, filename):
    if not filename.lower().endswith(".pdf"):
        raise APIError(415, "unsupported_file", "Selecciona un documento PDF (.pdf).")
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted or not reader.pages:
            raise ValueError("unreadable")
    except Exception:
        raise APIError(422, "invalid_pdf", "El PDF está vacío, protegido o dañado. Elige otro archivo.") from None


@router.post(
    "/interpretations", status_code=201, response_model=InterpretationResponse,
    openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {
        "schema": {"type": "object", "required": ["file"], "properties": {
            "file": {"type": "string", "format": "binary"}}, "additionalProperties": False},
    }}}},
)
async def create_interpretation(
    request: Request, teacher=Depends(current_teacher), store=Depends(repository),
):
    from django.conf import settings

    limit = getattr(settings, "CURRICULUM_MAX_UPLOAD_SIZE_BYTES", 25 * 1024 * 1024)
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise APIError(415, "unsupported_content", "Selecciona un documento PDF.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit + 65536:
            raise APIError(413, "upload_too_large", "El archivo supera el tamaño máximo permitido.")
        body.extend(chunk)

    async def receive_body():
        return {"type": "http.request", "body": bytes(body), "more_body": False}

    form_request = Request(request.scope, receive_body)
    async with form_request.form(max_files=1, max_fields=0) as form:
        files = form.getlist("file")
        if len(form) != 1 or len(files) != 1 or not isinstance(files[0], UploadFile):
            raise APIError(422, "invalid_upload", "Elige un solo archivo PDF para continuar.")
        upload = files[0]
        content = await upload.read(limit + 1)
        if len(content) > limit:
            raise APIError(413, "upload_too_large", "El archivo supera el tamaño máximo permitido.")
        await run_in_threadpool(validate_pdf, content, upload.filename or "")
    document_id = str(uuid4())
    if await request.is_disconnected():
        raise APIError(409, "request_cancelled", "La solicitud fue cancelada antes de guardar.")
    result = await run_in_threadpool(interpret, io.BytesIO(content), document_id=document_id)
    if await request.is_disconnected():
        raise APIError(409, "request_cancelled", "La solicitud fue cancelada antes de guardar.")
    saved = await run_in_threadpool(
        store.create_interpretation, teacher.pk, result,
        source_bytes=content, filename=upload.filename,
    )
    return saved


@router.get("/interpretations")
def list_interpretations(teacher=Depends(current_teacher), store=Depends(repository)):
    return store.list_interpretations(teacher.pk)


@router.get("/drafts/{draft_id}/history")
def draft_history(draft_id: str, teacher=Depends(current_teacher), store=Depends(repository)):
    return store.get_history(teacher.pk, draft_id)


@router.get("/interpretations/{interpretation_id}/source")
def original_source(interpretation_id: str, teacher=Depends(current_teacher), store=Depends(repository)):
    from fastapi.responses import Response
    source = store.get_source(teacher.pk, interpretation_id)
    return Response(source["content"], media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="fuente.pdf"',
        "X-Source-SHA256": source["sha256"],
    })


@router.get("/interpretations/{interpretation_id}", response_model=InterpretationResponse)
def get_interpretation(
    interpretation_id: str, teacher=Depends(current_teacher), store=Depends(repository),
):
    return store.get_interpretation(teacher.pk, interpretation_id)


@router.patch("/drafts/{draft_id}", response_model=DraftResponse)
def patch_draft(
    draft_id: str, payload: DraftPatch,
    teacher=Depends(current_teacher), store=Depends(repository),
):
    return store.update_draft(
        teacher.pk, draft_id, payload.expected_revision,
        payload.changes.model_dump(exclude_unset=True),
    )


@router.post("/drafts/{draft_id}/approve", response_model=DraftResponse)
def approve_draft(
    draft_id: str, payload: ApprovalRequest,
    teacher=Depends(current_teacher), store=Depends(repository),
):
    return store.approve_draft(
        teacher.pk, draft_id, payload.expected_revision, confirm=payload.confirm,
    )


@router.post("/interpretations/{interpretation_id}/cancel")
def cancel_interpretation(
    interpretation_id: str, teacher=Depends(current_teacher), store=Depends(repository),
):
    store.get_interpretation(teacher.pk, interpretation_id)
    raise APIError(
        409, "interpretation_finished",
        "La interpretación ya terminó. El borrador guardado se conserva.",
    )


def source_lookup(document, message):
    def tokens(value):
        normalized = unicodedata.normalize("NFKD", value.lower())
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))
        return set(re.findall(r"[a-z0-9]{4,}", normalized))

    question = tokens(message) - {"como", "para", "sobre", "esta", "este", "fuente"}
    ranked = sorted(
        ((len(question & tokens(segment["text"])), index, segment)
         for index, segment in enumerate(document["source_segments"])),
        key=lambda item: (-item[0], item[1]),
    )
    matches = [segment for score, _, segment in ranked if score > 0][:3]
    if not matches:
        return "No encontré un fragmento que responda a esa pregunta. Revisa la fuente o precisa tu pregunta.", []
    answer = "Estos fragmentos de la fuente pueden ayudarte. Revísalos antes de cambiar la actividad.\n\n"
    answer += "\n\n".join(
        f"Página {segment['page']}: {segment['text'][:800]}" for segment in matches
    )
    return answer, [segment["id"] for segment in matches]


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest, teacher=Depends(current_teacher), store=Depends(repository),
):
    document = store.get_interpretation(teacher.pk, payload.interpretation_id)
    message, source_ids = source_lookup(document, payload.message)
    return ChatResponse(interpretation_id=payload.interpretation_id, message=message, source_ids=source_ids)
