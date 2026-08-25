from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from health.views import health_page, local_access
from curriculum.views import (
    student_activity,
    student_packages,
    student_question_answer,
    student_question_assistance,
    student_session_join,
    student_turn_recover,
    student_turn_ready,
    student_turn_start,
    tutor_session_confirm,
    tutor_session_close,
    tutor_session_export,
    tutor_session_prepare,
    tutor_session_results_delete,
    tutor_session_review,
    tutor_result_delete,
)


urlpatterns = [
    path("cms/", include("wagtail.admin.urls")),
    path("documents/", include("wagtail.documents.urls")),
    path("health/", health_page, name="health"),
    path("access/", local_access, name="local-access"),
    path("student/", student_packages, name="student-packages"),
    path(
        "student/sessions/<int:session_id>/join/",
        student_session_join,
        name="student-session-join",
    ),
    path(
        "student/sessions/<int:session_id>/devices/<uuid:local_identifier>/turn/start/",
        student_turn_start,
        name="student-turn-start",
    ),
    path(
        "student/sessions/<int:session_id>/turn/ready/",
        student_turn_ready,
        name="student-turn-ready",
    ),
    path(
        "student/sessions/<int:session_id>/devices/<uuid:local_identifier>/turn/recover/",
        student_turn_recover,
        name="student-turn-recover",
    ),
    path(
        "tutor/snapshots/<int:snapshot_id>/prepare/",
        tutor_session_prepare,
        name="tutor-session-prepare",
    ),
    path(
        "tutor/sessions/<int:session_id>/review/",
        tutor_session_review,
        name="tutor-session-review",
    ),
    path(
        "tutor/sessions/<int:session_id>/confirm/",
        tutor_session_confirm,
        name="tutor-session-confirm",
    ),
    path(
        "tutor/sessions/<int:session_id>/close/",
        tutor_session_close,
        name="tutor-session-close",
    ),
    path(
        "tutor/sessions/<int:session_id>/results/export/",
        tutor_session_export,
        name="tutor-session-export",
    ),
    path(
        "tutor/sessions/<int:session_id>/results/delete/",
        tutor_session_results_delete,
        name="tutor-session-results-delete",
    ),
    path(
        "tutor/sessions/<int:session_id>/results/<uuid:result_id>/delete/",
        tutor_result_delete,
        name="tutor-result-delete",
    ),
    path(
        "student/sessions/<int:session_id>/activity/",
        student_activity,
        name="student-activity",
    ),
    path(
        "student/sessions/<int:session_id>/questions/<int:question_index>/answer/",
        student_question_answer,
        name="student-question-answer",
    ),
    path(
        "student/sessions/<int:session_id>/questions/<int:question_index>/assistance/",
        student_question_assistance,
        name="student-question-assistance",
    ),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
