"""Explicit LAN URL handling shared by local access surfaces."""

from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.urls import reverse


def explicit_lan_url(raw_url=None):
    """Return the operator-supplied LAN base URL when it is valid.

    The value may be an origin (``http://192.168.1.20:8000``) or the existing
    ``/student/`` base used by the local access page.  It must not contain
    credentials, a query, or a fragment: this setting is a route base, not a
    place to smuggle arbitrary browser destinations.
    """

    value = (
        getattr(settings, "AULALISTA_LAN_URL", "")
        if raw_url is None
        else raw_url
    )
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        # Accessing hostname/port performs additional validation for malformed
        # bracketed IPv6 addresses and ports.
        hostname = parsed.hostname
        parsed.port
    except (TypeError, ValueError):
        return ""
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return value


def session_join_url(request, session_id):
    """Build the session join URL from the explicit LAN base when available.

    Without configuration, the current request host is returned only as a
    visible manual fallback.  Callers must not generate a QR from that
    fallback because localhost or a non-LAN hostname may not be reachable by
    students.
    """

    route = reverse("student-session-join", args=[session_id])
    configured = explicit_lan_url()
    if configured:
        parsed = urlsplit(configured)
        base_path = parsed.path.rstrip("/")
        # Support both the documented origin and the historical /student/
        # value without duplicating a deployment path prefix.
        path = route if base_path and route.startswith(base_path + "/") else base_path + route
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")), True
    return request.build_absolute_uri(route), False


def lan_url_notice(configured):
    """Human-readable state for a missing or invalid explicit LAN setting."""

    raw = str(getattr(settings, "AULALISTA_LAN_URL", "") or "").strip()
    if raw and not configured:
        return (
            "AULALISTA_LAN_URL no es válida. Verifica una URL http(s) de la "
            "LAN sin consulta ni fragmento; por ahora sólo se muestra el host actual."
        )
    return (
        "Configura AULALISTA_LAN_URL con la URL LAN verificada para habilitar "
        "el QR; por ahora sólo se muestra el host actual."
    )
