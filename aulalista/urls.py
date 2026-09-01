from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.shortcuts import redirect

from health.views import health_page, local_access
from curriculum.views import (
    director_dashboard,
    director_export,
    director_group_assign,
    director_import_apply,
    director_import_preview,
    platform_director_handoff,
    student_activity,
    student_roadmap,
    student_roadmap_complete,
    student_packages,
    student_question_answer,
    student_question_assistance,
    student_session_join,
    student_session_survey,
    student_turn_recover,
    student_turn_ready,
    student_turn_start,
    tutor_import_detail,
    tutor_import_log_json,
    tutor_import_log_md,
    tutor_import_upload,
    tutor_import_wait,
    tutor_import_status,
    tutor_home,
    tutor_curriculum,
    tutor_package_detail,
    tutor_results,
    tutor_groups,
    tutor_group_results,
    tutor_group_close_year,
    tutor_session_results,
    tutor_session_confirm,
    tutor_session_close,
    tutor_session_export,
    tutor_session_prepare,
    tutor_session_results_delete,
    tutor_session_review,
    tutor_session_active,
    tutor_session_roadmap_advance,
    tutor_roadmaps,
    tutor_roadmap_progress,
    tutor_session_projection,
    tutor_sessions,
    tutor_result_delete,
)


urlpatterns = [
    path("", lambda request: redirect("student-packages")),
    path("cms/", include("wagtail.admin.urls")),
    path("documents/", include("wagtail.documents.urls")),
    path("health/", health_page, name="health"),
    path("access/", local_access, name="local-access"),
    path("director/", director_dashboard, name="director-dashboard"),
    path(
        "director/salones/<int:group_id>/asignar/",
        director_group_assign,
        name="director-group-assign",
    ),
    path("director/export/", director_export, name="director-export"),
    path("director/importar/", director_import_preview, name="director-import-preview"),
    path("director/importar/aplicar/", director_import_apply, name="director-import-apply"),
    path(
        "platform/director/handoff/",
        platform_director_handoff,
        name="platform-director-handoff",
    ),
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
    path("tutor/", tutor_home, name="tutor-home"),
    path("tutor/curricula/", tutor_curriculum, name="tutor-curriculum"),
    path(
        "tutor/curricula/<int:snapshot_id>/",
        tutor_package_detail,
        name="tutor-package-detail",
    ),
    path("tutor/autoria/", tutor_curriculum, name="tutor-authoring"),
    path("tutor/resultados/", tutor_results, name="tutor-results"),
    path("tutor/salones/", tutor_groups, name="tutor-groups"),
    path(
        "tutor/salones/<int:group_id>/resultados/",
        tutor_group_results,
        name="tutor-group-results",
    ),
    path(
        "tutor/salones/<int:group_id>/cerrar-ano/",
        tutor_group_close_year,
        name="tutor-group-close-year",
    ),
    path(
        "tutor/sessions/<int:session_id>/results/",
        tutor_session_results,
        name="tutor-session-results",
    ),
    path(
        "tutor/imports/new/",
        tutor_import_upload,
        name="tutor-import-upload",
    ),
    path(
        "tutor/imports/<int:job_id>/",
        tutor_import_detail,
        name="tutor-import-detail",
    ),
    path(
        "tutor/imports/<int:job_id>/espera/",
        tutor_import_wait,
        name="tutor-import-wait",
    ),
    path(
        "tutor/imports/<int:job_id>/estado/",
        tutor_import_status,
        name="tutor-import-status",
    ),
    path(
        "tutor/imports/<int:job_id>/bitacora.md",
        tutor_import_log_md,
        name="tutor-import-log-md",
    ),
    path(
        "tutor/imports/<int:job_id>/bitacora.json",
        tutor_import_log_json,
        name="tutor-import-log-json",
    ),
    path(
        "tutor/sesiones/",
        tutor_sessions,
        name="tutor-sessions",
    ),
    path(
        "tutor/roadmaps/",
        tutor_roadmaps,
        name="tutor-roadmaps",
    ),
    path(
        "tutor/roadmaps/<int:snapshot_id>/progress/",
        tutor_roadmap_progress,
        name="tutor-roadmap-progress",
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
        "tutor/sessions/<int:session_id>/active/",
        tutor_session_active,
        name="tutor-session-active",
    ),
    path(
        "tutor/sessions/<int:session_id>/roadmap/advance/",
        tutor_session_roadmap_advance,
        name="tutor-session-roadmap-advance",
    ),
    path(
        "sessions/<int:session_id>/projection/",
        tutor_session_projection,
        name="session-projection",
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
        "student/sessions/<int:session_id>/roadmap/",
        student_roadmap,
        name="student-roadmap",
    ),
    path(
        "student/sessions/<int:session_id>/activities/<str:activity_id>/complete/",
        student_roadmap_complete,
        name="student-roadmap-complete",
    ),
    path(
        "student/sessions/<int:session_id>/encuesta/",
        student_session_survey,
        name="student-session-survey",
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
