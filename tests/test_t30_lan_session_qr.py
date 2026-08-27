import hashlib
import json
import os
import re
from xml.etree import ElementTree

import django
import pytest
from PIL import Image, ImageDraw
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse
import zxingcpp

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import ClassroomSession, CurriculumPackage, PublishedPackageSnapshot  # noqa: E402
from helpers import tutor_client  # noqa: E402


pytestmark = pytest.mark.django_db
LAN_BASE = "http://192.168.50.20:8000"


def active_session():
    package = CurriculumPackage.objects.create(title="QR LAN")
    revision = package.save_revision()
    payload = {"title": "QR LAN", "questions": []}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    snapshot = PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(username=f"qr-editor-{package.pk}"),
    )
    session = ClassroomSession.prepare_from_snapshot(snapshot, 2, 1)
    session.confirm()
    return session


def decode_generated_svg(svg):
    """Rasterize our simple module SVG and decode it with an independent reader."""

    root = ElementTree.fromstring(svg)
    dimension = int(root.attrib["width"])
    image = Image.new("L", (dimension, dimension), 255)
    draw = ImageDraw.Draw(image)
    for element in root.iter():
        if not element.tag.endswith("rect") or element.attrib.get("fill") == "white":
            continue
        x = int(element.attrib["x"])
        y = int(element.attrib["y"])
        width = int(element.attrib["width"])
        height = int(element.attrib["height"])
        draw.rectangle((x, y, x + width - 1, y + height - 1), fill=0)
    decoded = zxingcpp.read_barcode(image, is_pure=True)
    assert decoded is not None, "el SVG generado no se puede decodificar"
    return decoded.text, root


@override_settings(AULALISTA_LAN_URL=LAN_BASE)
def test_all_production_session_surfaces_encode_exact_lan_join_url():
    session = active_session()
    expected = f"{LAN_BASE}{reverse('student-session-join', args=[session.pk])}"
    surfaces = (
        (tutor_client(), reverse("tutor-session-review", args=[session.pk])),
        (tutor_client(), reverse("tutor-session-active", args=[session.pk])),
        (Client(), reverse("session-projection", args=[session.pk])),
    )

    for client, path in surfaces:
        response = client.get(path)
        assert response.status_code == 200
        assert response.text.count("<svg") == 1
        assert expected in response.text
        svg_markup = re.search(r"<svg.*?</svg>", response.text, re.DOTALL).group(0)
        payload, svg = decode_generated_svg(svg_markup)
        assert payload == expected
        assert svg.attrib["data-qr-error"] == "M"
        assert svg.attrib["data-qr-border"] == "4"


@override_settings(AULALISTA_LAN_URL="")
def test_session_surfaces_degrade_to_visible_current_host_link_without_qr():
    session = active_session()
    expected = f"http://testserver{reverse('student-session-join', args=[session.pk])}"

    for client, path in (
        (tutor_client(), reverse("tutor-session-review", args=[session.pk])),
        (tutor_client(), reverse("tutor-session-active", args=[session.pk])),
        (Client(), reverse("session-projection", args=[session.pk])),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert expected in response.text
        assert "data-session-join-url" in response.text
        assert "data-qr-value" not in response.text
        assert "AULALISTA_LAN_URL" in response.text
