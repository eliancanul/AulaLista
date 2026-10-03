"""Django session and teacher authorization boundary for the sprint API."""

from io import BytesIO

from django.contrib.auth import get_user
from django.contrib.auth.views import LogoutView
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.handlers.asgi import ASGIRequest
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware

from curriculum.views import teacher_required


teacher_logout = LogoutView.as_view(next_page="wagtailadmin_login")


class AuthenticationError(Exception):
    def __init__(self, status, code, message):
        self.status = status
        self.code = code
        self.message = message
        self.retryable = False
        super().__init__(message)


@teacher_required
def _teacher_gate(request):
    return HttpResponse(status=204)


class _CsrfCheck(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return HttpResponse(status=403)


def require_teacher(request):
    """Resolve a fresh Django user from an ASGI request in a sync dependency.

    Run in FastAPI's worker thread, after django.setup(). Django owns login,
    logout, session storage and cookies. Unsafe API requests must send Django's
    CSRF header; request bodies are neither read nor accepted as credentials.
    """
    django_request = ASGIRequest(request.scope, BytesIO())
    SessionMiddleware(_teacher_gate).process_request(django_request)
    django_request.user = get_user(django_request)
    if not django_request.user.is_authenticated:
        raise AuthenticationError(401, "authentication_required", "Inicia sesión para continuar.")
    if _teacher_gate(django_request).status_code != 204:
        raise AuthenticationError(403, "teacher_required", "Esta acción requiere una cuenta docente autorizada.")

    csrf = _CsrfCheck(_teacher_gate)
    csrf.process_request(django_request)
    if csrf.process_view(django_request, _teacher_gate, (), {}) is not None:
        raise AuthenticationError(403, "csrf_failed", "La sesión de seguridad no es válida. Recarga la página e inténtalo de nuevo.")
    return django_request.user


def get_owned_resource(queryset, teacher, resource_id):
    """Fetch a teacher-authored Django resource without disclosing other owners."""
    if not teacher.is_authenticated or teacher.pk is None:
        raise AuthenticationError(401, "authentication_required", "Inicia sesión para continuar.")
    try:
        return queryset.get(pk=resource_id, created_by_id=teacher.pk)
    except queryset.model.DoesNotExist:
        raise AuthenticationError(404, "not_found", "No se encontró el recurso solicitado.") from None
