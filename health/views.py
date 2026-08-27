from urllib.parse import urlsplit

from django.shortcuts import render

from health.lan import explicit_lan_url
from health.qr import qr_svg


def health_page(request):
    return render(request, "health/health.html", {"health_status": "healthy"})


def local_access(request):
    configured_url = explicit_lan_url()
    parsed_url = urlsplit(configured_url)
    local_url = (
        configured_url
        if parsed_url.scheme in {"http", "https"} and parsed_url.netloc
        else ""
    )
    return render(
        request,
        "health/local_access.html",
        {
            "local_url": local_url,
            "qr_svg": qr_svg(local_url) if local_url else "",
        },
    )
