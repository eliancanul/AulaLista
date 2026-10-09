"""Retained browser shells are opt-in regression routes, never public product UI."""
import pytest
from django.urls import resolve, reverse

from helpers import tutor_client

pytestmark = pytest.mark.django_db


def test_product_vue_entry_still_redirects_to_django():
    from api.views import sprint_shell
    assert resolve('/sprint/').func is sprint_shell
    response = tutor_client().get('/sprint/')
    assert response.status_code == 302
    assert response['Location'] == reverse('tutor-curriculum')


@pytest.mark.usefixtures('legacy_vue_routes')
def test_experimental_shell_is_explicit_and_keeps_login_and_csrf(tmp_path, settings):
    from django.test import Client
    from legacy_vue_urls import experimental_vue_shell
    assert resolve('/sprint/').func is experimental_vue_shell
    assert Client().get('/sprint/').status_code == 302
    settings.BASE_DIR = tmp_path
    index = tmp_path / 'frontend/dist/index.html'
    index.parent.mkdir(parents=True)
    index.write_text('<html><head></head><body>synthetic experimental shell</body></html>')
    response = tutor_client().get('/sprint/')
    assert response.status_code == 200
    assert b'csrf-token' in response.content
    assert response['Cache-Control'] == 'private, no-store'


@pytest.mark.usefixtures('legacy_import_routes')
def test_retained_bulk_review_routes_are_test_only():
    from curriculum.views import tutor_import_interpretation
    url = reverse('tutor-import-interpretation', args=[123])
    assert url.startswith('/_test_legacy/')
    assert resolve(url).func is tutor_import_interpretation
