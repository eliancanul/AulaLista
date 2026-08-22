import os

import django
import pytest
from django.test import Client
from django.test.utils import override_settings


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()


def test_node_exposes_an_explicit_health_page():
    response = Client().get("/health/")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert "AulaLista" in response.text
    assert "healthy" in response.text


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_health_page_serves_critical_resources_locally():
    client = Client()
    page = client.get("/health/")

    assert page.status_code == 200
    assert "/static/health/font.css" in page.text
    assert "/static/health/health.css" in page.text
    assert "/static/health/health.js" in page.text
    assert "http://" not in page.text
    assert "https://" not in page.text

    for resource in (
        "/static/health/font.css",
        "/static/health/health.css",
        "/static/health/health.js",
    ):
        response = client.get(resource)
        assert response.status_code == 200
        body = b"".join(response.streaming_content).decode("utf-8")
        assert "http://" not in body
        assert "https://" not in body

    font_response = client.get("/static/health/font.css")
    font_body = b"".join(font_response.streaming_content).decode("utf-8")
    assert '@font-face' in font_body
    assert 'font-family: "AulaListaLocal"' in font_body
    assert 'src: local("Arial")' in font_body
    assert "url(" not in font_body
