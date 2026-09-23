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
from helpers import tutor_client, tutor_client_for_sessions  # noqa: E402


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


from bs4 import BeautifulSoup


def try_decode_svg_as_qr(svg_markup):
    """Attempt to decode an arbitrary SVG as a QR code.

    Returns (decoded_text, root_element) if decodable, or None if the SVG
    is not a valid QR code or cannot be decoded.
    """
    try:
        root = ElementTree.fromstring(svg_markup)
        if "width" not in root.attrib:
            return None
        dimension = int(root.attrib["width"])
        image = Image.new("L", (dimension, dimension), 255)
        draw = ImageDraw.Draw(image)
        has_rects = False
        for element in root.iter():
            if not element.tag.endswith("rect") or element.attrib.get("fill") == "white":
                continue
            has_rects = True
            x = int(element.attrib["x"])
            y = int(element.attrib["y"])
            width = int(element.attrib["width"])
            height = int(element.attrib["height"])
            draw.rectangle((x, y, x + width - 1, y + height - 1), fill=0)
        if not has_rects:
            return None
        decoded = zxingcpp.read_barcode(image, is_pure=True)
        if decoded and decoded.text:
            return decoded.text, root
        return None
    except Exception:
        return None


def find_and_decode_all_qr_svgs(html_content):
    """Inspect every <svg> in the HTML, decode candidates as QR codes, and return list of (svg_tag, decoded_text, xml_root)."""
    soup = BeautifulSoup(html_content, "html.parser")
    all_svgs = soup.find_all("svg")
    decodable_qrs = []
    for s in all_svgs:
        res = try_decode_svg_as_qr(str(s))
        if res is not None:
            text, root = res
            decodable_qrs.append((s, text, root))
    return decodable_qrs, soup


@override_settings(AULALISTA_LAN_URL=LAN_BASE)
def test_all_production_session_surfaces_encode_exact_lan_join_url():
    session = active_session()
    expected = f"{LAN_BASE}{reverse('student-session-join', args=[session.pk])}"
    assert "localhost" not in expected
    assert "127.0.0.1" not in expected
    assert expected.startswith("http://192.168.")

    teacher = tutor_client_for_sessions(session)
    surfaces = (
        (teacher, reverse("tutor-session-review", args=[session.pk])),
        (teacher, reverse("tutor-session-active", args=[session.pk])),
        (Client(), reverse("session-projection", args=[session.pk])),
    )

    for client, path in surfaces:
        response = client.get(path)
        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert expected in html
        assert "data:image" not in html
        assert "data:text" not in html
        assert "localhost" not in html
        assert "127.0.0.1" not in html

        # 1. Inspect ALL SVGs on page and decode them as QR codes (content-based, not attribute-based)
        decodable_qrs, soup = find_and_decode_all_qr_svgs(html)

        # EXACTLY one decodable QR SVG must exist on the entire page
        assert len(decodable_qrs) == 1, (
            f"Expected exactly 1 decodable QR SVG on {path}, found {len(decodable_qrs)}"
        )
        qr_svg_elem, decoded_payload, svg_root = decodable_qrs[0]
        assert decoded_payload == expected

        # 2. Verify attributes on production QR
        assert svg_root.attrib["data-qr-error"] == "M"
        assert svg_root.attrib["data-qr-border"] == "4"
        assert svg_root.attrib.get("data-qr-value") == expected

        # 3. Locate the stable semantic container (.qr)
        qr_containers = soup.find_all(class_="qr")
        assert len(qr_containers) == 1, f"Expected exactly 1 .qr container on {path}, found {len(qr_containers)}"
        qr_container = qr_containers[0]

        # 4. The decodable QR SVG is inside the semantic container
        assert qr_svg_elem in qr_container.find_all("svg")

        # 5. Non-decodable decorative SVGs (such as navigation icons) outside .qr are permitted
        non_qr_svgs = [s for s in soup.find_all("svg") if s != qr_svg_elem]
        for extra in non_qr_svgs:
            assert try_decode_svg_as_qr(str(extra)) is None, f"Non-container SVG must not decode as QR on {path}"

        # 6. Displayed join link matches expected LAN URL
        join_link = soup.find(attrs={"data-session-join-url": True})
        assert join_link is not None, f"data-session-join-url link not found on {path}"
        assert join_link.get("href") == expected


@override_settings(AULALISTA_LAN_URL=LAN_BASE)
def test_qr_duplicate_detector_fails_on_unadorned_cloned_qr():
    """Causal probe: a second decodable QR SVG stripped of all data-qr-* attributes and placed
    outside .qr causes the detector to find 2 decodable QRs, proving detection is content-based
    and non-tautological.
    """
    import copy

    session = active_session()
    teacher = tutor_client_for_sessions(session)
    response = teacher.get(reverse("tutor-session-review", args=[session.pk]))
    assert response.status_code == 200
    html = response.content.decode("utf-8")

    # Baseline: exactly 1 decodable QR on normal page
    initial_qrs, soup = find_and_decode_all_qr_svgs(html)
    assert len(initial_qrs) == 1

    # Clone the valid QR SVG and strip all data-qr-* attributes
    original_qr_svg = initial_qrs[0][0]
    cloned_svg = copy.copy(original_qr_svg)
    for attr in list(cloned_svg.attrs.keys()):
        if attr.startswith("data-qr"):
            del cloned_svg.attrs[attr]

    # Verify attributes were stripped
    assert not cloned_svg.get("data-qr-value")
    assert not cloned_svg.get("data-qr-error")
    assert not cloned_svg.get("data-qr-border")

    # Insert cloned QR SVG outside .qr container (in main)
    main_el = soup.find("main")
    main_el.append(cloned_svg)

    # Re-inspect modified HTML
    modified_html = str(soup)
    duplicated_qrs, _ = find_and_decode_all_qr_svgs(modified_html)

    # Content-based detector finds 2 decodable QRs even without data-qr-* attributes
    assert len(duplicated_qrs) == 2, f"Expected 2 decodable QRs, found {len(duplicated_qrs)}"

    # The requirement of exactly 1 decodable QR fails causally
    with pytest.raises(AssertionError):
        assert len(duplicated_qrs) == 1, "Expected exactly 1 decodable QR"


@override_settings(AULALISTA_LAN_URL="")
def test_session_surfaces_degrade_to_visible_current_host_link_without_qr():
    session = active_session()
    expected = f"http://testserver{reverse('student-session-join', args=[session.pk])}"
    teacher = tutor_client_for_sessions(session)

    for client, path in (
        (teacher, reverse("tutor-session-review", args=[session.pk])),
        (teacher, reverse("tutor-session-active", args=[session.pk])),
        (Client(), reverse("session-projection", args=[session.pk])),
    ):
        response = client.get(path)
        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert expected in html
        assert "data-session-join-url" in html
        assert "data-qr-value" not in html
        assert "AULALISTA_LAN_URL" in html

        decodable_qrs, soup = find_and_decode_all_qr_svgs(html)
        assert len(decodable_qrs) == 0, f"Expected 0 decodable QRs in degraded mode on {path}"
        assert len(soup.find_all(class_="qr")) == 0


def test_session_surfaces_security_and_auth_boundaries():
    """Tutor review and active surfaces require authentication; projection is public."""
    session = active_session()
    anon = Client()
    assert anon.get(reverse("tutor-session-review", args=[session.pk])).status_code == 302
    assert anon.get(reverse("tutor-session-active", args=[session.pk])).status_code == 302
    assert anon.get(reverse("session-projection", args=[session.pk])).status_code == 200
