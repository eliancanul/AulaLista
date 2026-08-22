from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from health.views import health_page


urlpatterns = [
    path("admin/", admin.site.urls),
    path("cms/", include("wagtail.admin.urls")),
    path("documents/", include("wagtail.documents.urls")),
    path("health/", health_page, name="health"),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
