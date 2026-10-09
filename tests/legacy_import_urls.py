"""Test-only routes for retained staging/queue regression contracts.

These views are not exposed by the active product URLconf. Tests opt in through
legacy_import_routes; current teacher-review tests keep the real public routes.
"""
from django.urls import path

from aulalista.urls import urlpatterns as active_patterns
from curriculum.views import tutor_import_detail, tutor_import_interpretation

_REPLACED_NAMES = {"tutor-import-detail", "tutor-import-interpretation"}
urlpatterns = [pattern for pattern in active_patterns
               if getattr(pattern, "name", None) not in _REPLACED_NAMES] + [
    path("_test_legacy/tutor/imports/<int:job_id>/", tutor_import_detail,
         name="tutor-import-detail"),
    path("_test_legacy/tutor/imports/<int:job_id>/interpretacion/", tutor_import_interpretation,
         name="tutor-import-interpretation"),
]
