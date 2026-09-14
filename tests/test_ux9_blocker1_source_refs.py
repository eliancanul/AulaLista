import pytest
from django.template.loader import render_to_string
from django.urls import NoReverseMatch

pytestmark = pytest.mark.django_db

class MockPackage:
    title = "Mock Package"
    get_absolute_url = lambda self: "/mock-url/"

class MockSnapshot:
    pk = 123
    version = 1
    sha256 = "abcd"
    package = MockPackage()
    
def test_tutor_package_detail_source_refs_format():
    # Old broken format
    source_refs = [{
        "session_id": "sess-1",
        "session_number": 1,
        "pages": [1, 2],
    }]
    
    snapshot = MockSnapshot()
    payload = {"source_references": source_refs}
    
    with pytest.raises(NoReverseMatch):
        render_to_string("curriculum/tutor_package_detail.html", {
            "snapshot": snapshot,
            "payload": payload,
        })

def test_tutor_package_detail_source_refs_format_pass():
    # New working format
    source_refs = [{
        "session_id": "sess-1",
        "session_number": 1,
        "source_pages": [1, 2],
        "source_pdf_sha256": "abcd",
        "source_anchor": "Test Title",
        "source_text": "Sample text",
        "source_urls": ["http://example.com"],
    }]
    
    snapshot = MockSnapshot()
    payload = {"source_references": source_refs}
    
    rendered = render_to_string("curriculum/tutor_package_detail.html", {
        "snapshot": snapshot,
        "payload": payload,
    })
    
    assert "Test Title" in rendered
    assert "http://example.com" in rendered
    assert "Sample text" in rendered

