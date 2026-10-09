"""FastAPI entrypoint; the existing Django ASGI application remains separate."""

from importlib import import_module

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from api.routes import APIError, router
from api.schemas import ErrorResponse


SAFE_HTTP_MESSAGES = {
    400: "No se pudo leer la solicitud.",
    401: "Inicia sesión para continuar.",
    403: "No tienes permiso para realizar esta acción.",
    404: "No se encontró el recurso solicitado.",
    405: "Esta acción no está disponible en esta dirección.",
    413: "El archivo supera el tamaño máximo permitido.",
    415: "Selecciona un documento PDF.",
    422: "Revisa los datos de la solicitud.",
    503: "El servicio no está disponible. Inténtalo más tarde.",
}


def error_response(status, code, message, *, retryable=False, fields=None):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message,
                           "retryable": retryable, "fields": fields or []}},
        headers={"Cache-Control": "private, no-store"},
    )


def create_app() -> FastAPI:
    import os
    import django
    from django.apps import apps

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
    if not apps.ready:
        django.setup()

    application = FastAPI(
        title="AulaLista API", version="1.0.0",
        description="Borradores docentes con revisión humana. No publica actividades.",
        responses={status: {"model": ErrorResponse} for status in
                   (400, 401, 403, 404, 409, 413, 415, 422, 503, 504)},
    )

    @application.exception_handler(APIError)
    async def handle_api_error(request, exc):
        return error_response(exc.status, exc.code, exc.message, retryable=exc.retryable)

    for module_name, error_name in (
        ("api.auth", "AuthenticationError"),
        ("api.persistence", "PersistenceError"),
    ):
        try:
            module = import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
        else:
            application.add_exception_handler(getattr(module, error_name), handle_api_error)

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(request, exc):
        return error_response(
            422, "invalid_request", "Revisa los datos de la solicitud.",
            fields=[
                ".".join(str(part) for part in (
                    error["loc"][:-1] if error["type"] == "extra_forbidden" else error["loc"]
                )) for error in exc.errors()
            ],
        )

    @application.exception_handler(HTTPException)
    async def handle_http_error(request, exc):
        return error_response(
            exc.status_code, f"http_{exc.status_code}",
            SAFE_HTTP_MESSAGES.get(exc.status_code, "No se pudo completar la solicitud."),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request, exc):
        return error_response(500, "internal_error", "No se pudo completar la solicitud. Inténtalo más tarde.")

    @application.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    application.include_router(router, prefix="/api/v1")
    return application


app = create_app()
