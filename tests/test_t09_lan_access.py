import os
import socket
import urllib.request
from urllib.parse import urlsplit

import django
import pytest
from django.test import Client, override_settings


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()


LAN_URL = "http://192.168.50.20:8000/student/"


@override_settings(AULALISTA_LAN_URL=LAN_URL, DEBUG=True)
def test_access_page_shows_exact_configured_url_in_text_and_qr():
    response = Client().get("/access/")

    assert response.status_code == 200
    assert LAN_URL in response.text
    assert f'data-qr-value="{LAN_URL}"' in response.text
    assert "Escanea el código" in response.text
    assert "escribe la dirección" in response.text


@pytest.mark.django_db
@override_settings(AULALISTA_LAN_URL=LAN_URL, DEBUG=True)
def test_access_page_uses_only_local_assets_and_does_not_resolve_or_fetch_network(
    monkeypatch,
):
    def network_is_out_of_scope(*args, **kwargs):
        raise AssertionError("la página local no debe usar red externa")

    monkeypatch.setattr(socket, "getaddrinfo", network_is_out_of_scope)
    monkeypatch.setattr(urllib.request, "urlopen", network_is_out_of_scope)
    response = Client().get("/access/")

    assert response.status_code == 200
    assert "/static/health/access.css" in response.text
    assert "cdn" not in response.text.lower()
    assert "fonts.googleapis" not in response.text
    assert urlsplit(LAN_URL).hostname == "192.168.50.20"
    assert response.wsgi_request.META["SERVER_NAME"] == "testserver"

    asset = Client().get("/static/health/access.css")
    assert asset.status_code == 200
    body = b"".join(asset.streaming_content).decode("utf-8")
    assert "http://" not in body
    assert "https://" not in body


@override_settings(AULALISTA_LAN_URL=LAN_URL)
@pytest.mark.django_db
def test_new_clients_can_reach_local_entrypoint_without_a_session_or_dns():
    first = Client().get("/student/")
    second = Client().get("/student/")

    assert first.status_code == second.status_code == 200
    assert "No hay sesiones activas." in first.text
    assert "No hay sesiones activas." in second.text


def test_missing_explicit_lan_url_does_not_invent_an_address():
    response = Client().get("/access/")

    assert response.status_code == 200
    assert "AULALISTA_LAN_URL" in response.text
    assert "data-qr-value" not in response.text
    assert "detecta automáticamente la IP" in response.text


@override_settings(AULALISTA_LAN_URL="javascript:alert(document.cookie)")
def test_access_page_does_not_render_unsafe_url_as_a_link():
    response = Client().get("/access/")

    assert response.status_code == 200
    assert "javascript:" not in response.text
    assert "data-qr-value" not in response.text


def test_qr_generator_uses_correct_rs_generator_and_white_finder_separator():
    from health.qr import _reed_solomon_generator, qr_matrix

    assert _reed_solomon_generator(7) == [1, 127, 122, 154, 164, 11, 68, 117]
    matrix = qr_matrix(LAN_URL)
    assert matrix[3][3] is True
    assert matrix[3][7] is False
