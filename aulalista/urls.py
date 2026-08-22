from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from health.views import health_page
from curriculum.views import student_packages


urlpatterns = [
    path("cms/", include("wagtail.admin.urls")),
    path("documents/", include("wagtail.documents.urls")),
    path("health/", health_page, name="health"),
    path("student/", student_packages, name="student-packages"),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
