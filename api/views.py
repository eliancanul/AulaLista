"""Authenticated shell; permissions continue to be checked on every API call."""
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from curriculum.views import teacher_required

@teacher_required
@ensure_csrf_cookie
def sprint_shell(request):
    index = Path(settings.BASE_DIR) / "frontend" / "dist" / "index.html"
    if not index.is_file():
        return HttpResponse("Falta construir la interfaz: npm --prefix frontend run build", status=503)
    html = index.read_text().replace("</head>",
        '<meta name="aulalista-can-approve" content="true">'
        f'<meta name="csrf-token" content="{get_token(request)}"></head>')
    return HttpResponse(html, headers={"Cache-Control": "private, no-store"})
