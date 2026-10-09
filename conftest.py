"""Pytest configuration for AulaLista.

Test media isolation is configured early via `aulalista.test_settings` specified in
`pytest.ini` (DJANGO_SETTINGS_MODULE = aulalista.test_settings).
This ensures MEDIA_ROOT is created and isolated under system temp before Django apps
or storages are initialized. Each process cleans up only its own created directory
via atexit with an exact local guard closure.
No late storage resets, PID checks, symlink traversals, or stale directory cleanups
are performed here.
"""

import pytest


@pytest.fixture
def legacy_import_routes(settings):
    """Preserve retired staging/queue invariants without exposing their UI."""
    settings.ROOT_URLCONF = "legacy_import_urls"


@pytest.fixture
def legacy_vue_routes(settings):
    """Retain experimental Vue/API coverage without exposing its retired entry."""
    settings.ROOT_URLCONF = "legacy_vue_urls"
