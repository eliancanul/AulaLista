"""Test-only retired Vue shell. Never imported by the product URLconf."""
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie

from aulalista.urls import urlpatterns as active_patterns
from curriculum.views import teacher_required


@teacher_required
@ensure_csrf_cookie
def experimental_vue_shell(request):
    index = Path(settings.BASE_DIR) / "frontend" / "dist" / "index.html"
    if not index.is_file():
        return HttpResponse("Build the retained experimental frontend before testing it.", status=503)
    html = index.read_text().replace("</head>",
        '<meta name="aulalista-can-approve" content="true">'
        f'<meta name="csrf-token" content="{get_token(request)}"></head>')
    return HttpResponse(html, headers={"Cache-Control": "private, no-store"})


urlpatterns = [pattern for pattern in active_patterns
               if getattr(pattern, "name", None) != "sprint-shell"] + [
    path("sprint/", experimental_vue_shell, name="sprint-shell"),
]
