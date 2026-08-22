from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from health.views import health_page
from curriculum.views import start_student_session, student_activity, student_packages


urlpatterns = [
    path("cms/", include("wagtail.admin.urls")),
    path("documents/", include("wagtail.documents.urls")),
    path("health/", health_page, name="health"),
    path("student/", student_packages, name="student-packages"),
    path(
        "student/snapshots/<int:snapshot_id>/start/",
        start_student_session,
        name="student-session-start",
    ),
    path(
        "student/sessions/<int:session_id>/activity/",
        student_activity,
        name="student-activity",
    ),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
