"""S08 tests exercise Django sessions, roles and CSRF without a second identity."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import include, path
from django.utils import timezone

from api.auth import AuthenticationError, get_owned_resource, require_teacher, teacher_logout
from curriculum.models import CurriculumPackage, School


pytestmark = pytest.mark.django_db
urlpatterns = [path("cms/logout/", teacher_logout), path("", include("aulalista.urls"))]


@pytest.fixture
def teacher():
    return get_user_model().objects.create_user(
        username="s08-maestra", password="s08-test-password", is_staff=True,
    )


def signed_in(user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    client.get("/cms/login/")
    return client


def request_for(client=None, *, method="GET", csrf=True, secure=False, headers=None):
    values = {"host": "testserver"}
    if client is not None:
        values["cookie"] = client.cookies.output(header="", sep=";").strip()
        if csrf and settings.CSRF_COOKIE_NAME in client.cookies:
            values["x-csrftoken"] = client.cookies[settings.CSRF_COOKIE_NAME].value
    values.update(headers or {})
    return SimpleNamespace(scope={
        "type": "http", "http_version": "1.1", "method": method,
        "scheme": "https" if secure else "http", "path": "/api/v1/drafts/example",
        "root_path": "", "query_string": b"", "server": ("testserver", 443 if secure else 80),
        "client": ("127.0.0.1", 12345),
        "headers": [(key.encode(), value.encode()) for key, value in values.items()],
    })


def assert_denied(request, status, code):
    with pytest.raises(AuthenticationError) as error:
        require_teacher(request)
    assert (error.value.status, error.value.code, error.value.retryable) == (status, code, False)


@pytest.mark.parametrize("headers", [
    {}, {"cookie": "sessionid=forged"}, {"authorization": "Bearer forged"},
    {"x-user-id": "1", "x-owner-id": "1"},
])
def test_no_client_supplied_identity_authenticates(headers):
    assert_denied(request_for(headers=headers), 401, "authentication_required")


def test_upstream_user_object_does_not_bypass_session(teacher):
    request = request_for()
    request.scope["user"] = teacher
    request.user = teacher
    assert_denied(request, 401, "authentication_required")


def test_existing_session_resolves_same_user(teacher):
    assert require_teacher(request_for(signed_in(teacher))).pk == teacher.pk


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_unsafe_requests_require_matching_csrf(teacher, method):
    client = signed_in(teacher)
    assert_denied(request_for(client, method=method, csrf=False), 403, "csrf_failed")
    assert_denied(request_for(client, method=method, headers={"x-csrftoken": "invalid"}), 403, "csrf_failed")
    assert_denied(request_for(client, method=method, headers={"x-csrftoken": "a" * 32}), 403, "csrf_failed")
    assert require_teacher(request_for(client, method=method)).pk == teacher.pk


def test_csrf_cookie_alone_is_not_sufficient(teacher):
    assert_denied(request_for(signed_in(teacher), method="POST", csrf=False), 403, "csrf_failed")


@pytest.mark.parametrize("headers,secure,accepted", [
    ({"origin": "https://evil.example"}, False, False),
    ({"origin": "http://testserver"}, False, True),
    ({}, True, False),
    ({"referer": "https://evil.example/form"}, True, False),
    ({"referer": "https://testserver/form"}, True, True),
    ({"origin": "https://testserver"}, True, True),
])
def test_django_origin_and_https_referer_rules(teacher, headers, secure, accepted):
    request = request_for(signed_in(teacher), method="POST", headers=headers, secure=secure)
    if accepted:
        assert require_teacher(request).pk == teacher.pk
    else:
        assert_denied(request, 403, "csrf_failed")


@pytest.mark.parametrize("role", ["non_staff", "superuser", "platform", "director"])
def test_existing_teacher_role_boundary_is_preserved(teacher, role):
    if role == "non_staff":
        teacher.is_staff = False
    elif role == "superuser":
        teacher.is_superuser = True
    elif role == "platform":
        teacher.groups.add(Group.objects.create(name="PlatformAdministrator"))
    else:
        administrator = get_user_model().objects.create_user(
            username="s08-admin", is_staff=True, is_superuser=True,
        )
        School.provision(name="Escuela de prueba S08", director=teacher, actor=administrator)
    teacher.save()
    assert_denied(request_for(signed_in(teacher)), 403, "teacher_required")


@pytest.mark.parametrize("change", ["inactive", "password", "expired", "deleted_session", "revoked_staff"])
def test_session_and_permission_changes_take_effect_on_next_request(teacher, change):
    client = signed_in(teacher)
    request = request_for(client)
    assert require_teacher(request).pk == teacher.pk
    if change == "inactive":
        teacher.is_active = False
        teacher.save()
    elif change == "password":
        teacher.set_password("s08-replacement-password")
        teacher.save()
    elif change == "expired":
        Session.objects.filter(session_key=client.session.session_key).update(expire_date=timezone.now() - timedelta(seconds=1))
    elif change == "deleted_session":
        client.session.flush()
    else:
        teacher.is_staff = False
        teacher.save()
    if change == "revoked_staff":
        assert_denied(request, 403, "teacher_required")
    else:
        assert_denied(request, 401, "authentication_required")


def test_actual_wagtail_login_logout_rejects_replayed_session(teacher):
    teacher.user_permissions.add(Permission.objects.get(
        content_type__app_label="wagtailadmin", codename="access_admin",
    ))
    client = Client(enforce_csrf_checks=True)
    assert client.get("/cms/login/").status_code == 200
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    response = client.post("/cms/login/", {
        "username": teacher.username, "password": "s08-test-password",
        "csrfmiddlewaretoken": csrf, "next": "/tutor/",
    })
    assert response.status_code == 302
    assert response["Location"] == "/tutor/"
    request = request_for(client)
    assert require_teacher(request).pk == teacher.pk
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    response = client.post("/cms/logout/", {"csrfmiddlewaretoken": csrf})
    assert response.status_code == 302
    assert_denied(request, 401, "authentication_required")


def test_staff_only_logout_invalidates_session(teacher):
    client = signed_in(teacher)
    request = request_for(client)
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    response = client.post("/tutor/logout/", {"csrfmiddlewaretoken": csrf})
    assert response.status_code == 302
    assert_denied(request, 401, "authentication_required")


def test_two_accounts_cannot_read_or_mutate_foreign_or_unowned_resources(teacher):
    other = get_user_model().objects.create_user(username="s08-otra", is_staff=True)
    first_identity = require_teacher(request_for(signed_in(teacher)))
    second_identity = require_teacher(request_for(signed_in(other)))
    own = CurriculumPackage.objects.create(title="Material de la primera", created_by=teacher)
    foreign = CurriculumPackage.objects.create(title="Material de la segunda", created_by=other)
    unowned = CurriculumPackage.objects.create(title="Material sin atribución")
    packages = CurriculumPackage.objects.all()
    assert get_owned_resource(packages, first_identity, own.pk).title == "Material de la primera"
    assert get_owned_resource(packages, second_identity, foreign.pk).title == "Material de la segunda"
    for user, resource_id in ((first_identity, foreign.pk), (second_identity, own.pk),
                              (first_identity, unowned.pk), (first_identity, 999999)):
        with pytest.raises(AuthenticationError) as error:
            obj = get_owned_resource(packages, user, resource_id)
            obj.title = "No debe escribirse"
            obj.save()
        assert (error.value.status, error.value.code) == (404, "not_found")
    own.refresh_from_db()
    foreign.refresh_from_db()
    assert own.title == "Material de la primera"
    assert foreign.title == "Material de la segunda"


def test_configured_cookie_and_csrf_header_names_are_used(teacher, settings):
    settings.SESSION_COOKIE_NAME = "s08_session"
    settings.CSRF_COOKIE_NAME = "s08_csrf"
    settings.CSRF_HEADER_NAME = "HTTP_X_S08_CSRF"
    client = signed_in(teacher)
    token = client.cookies[settings.CSRF_COOKIE_NAME].value
    assert require_teacher(request_for(client, method="PATCH", headers={"x-s08-csrf": token})).pk == teacher.pk
    assert_denied(request_for(client, method="PATCH"), 403, "csrf_failed")


def test_anonymous_identity_cannot_fetch_unowned_resource():
    unowned = CurriculumPackage.objects.create(title="Sin atribución")
    with pytest.raises(AuthenticationError) as error:
        get_owned_resource(CurriculumPackage.objects.all(), AnonymousUser(), unowned.pk)
    assert error.value.status == 401


def test_csrf_token_must_match_request_cookie(teacher):
    client = signed_in(teacher)
    another_browser = signed_in(teacher)
    token = another_browser.cookies[settings.CSRF_COOKIE_NAME].value
    assert_denied(request_for(client, method="PATCH", headers={"x-csrftoken": token}), 403, "csrf_failed")


def test_teacher_logout_view_works_without_editorial_permission(teacher, settings):
    settings.ROOT_URLCONF = __name__
    client = signed_in(teacher)
    request = request_for(client)
    assert client.get("/cms/logout/").status_code == 405
    assert client.post("/cms/logout/").status_code == 403
    assert require_teacher(request).pk == teacher.pk
    token = client.cookies[settings.CSRF_COOKIE_NAME].value
    response = client.post("/cms/logout/", {"csrfmiddlewaretoken": token})
    assert response.status_code == 302
    assert response["Location"] == "/cms/login/"
    assert client.cookies[settings.SESSION_COOKIE_NAME].value == ""
    assert_denied(request, 401, "authentication_required")
