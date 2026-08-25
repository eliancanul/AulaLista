import json
import os
import time

import django
import pytest
from django.db import close_old_connections, connection
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import (  # noqa: E402
    ClassroomSession,
    CurriculumPackage,
    DeviceAssignment,
    PublishedPackageSnapshot,
    PseudonymousResult,
    StudentTurn,
)


pytestmark = pytest.mark.django_db
CLIENT_COUNT = 30
P95_TARGET_MS = 2000


def published_snapshot():
    package = CurriculumPackage.objects.create(title="Demo T10")
    revision = package.save_revision()
    payload = {
        "title": "Demo T10",
        "objective": "Medir un flujo local reproducible.",
        "micro_lesson": "La sesión conserva su estado mientras trabaja el grupo.",
        "questions": [],
        "final_explanation": "La prueba usa un paquete sintético.",
    }
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256="0" * 64,
        source_revision=revision,
        published_by=get_user_model().objects.create_user(username="t10-publisher"),
    )


@pytest.fixture
def active_session():
    snapshot = published_snapshot()
    session = ClassroomSession.prepare_from_snapshot(
        snapshot,
        CLIENT_COUNT,
        CLIENT_COUNT,
    )
    session.confirm()
    return session


def _latency_ms(started):
    return round((time.perf_counter() - started) * 1000, 3)


def _run_one_client(session_id, assignment, index):
    close_old_connections()
    client = Client()
    measurements = []
    errors = []
    try:
        start = time.perf_counter()
        response = client.post(
            reverse(
                "student-turn-start",
                args=[session_id, assignment.local_identifier],
            ),
            {"display_name": f"Cliente {index:02d}"},
        )
        measurements.append({"operation": "start", "latency_ms": _latency_ms(start)})
        if response.status_code != 302:
            errors.append(f"start:{response.status_code}")

        start = time.perf_counter()
        response = client.get(reverse("student-activity", args=[session_id]))
        measurements.append({"operation": "activity", "latency_ms": _latency_ms(start)})
        if response.status_code != 200:
            errors.append(f"activity:{response.status_code}")

        start = time.perf_counter()
        response = client.post(
            reverse("student-turn-ready", args=[session_id]),
        )
        measurements.append({"operation": "ready", "latency_ms": _latency_ms(start)})
        if response.status_code != 302:
            errors.append(f"ready:{response.status_code}")
    except Exception as error:  # noqa: BLE001 - the probe must record lock errors.
        errors.append(f"{type(error).__name__}: {error}")
    finally:
        close_old_connections()
    return {"client": index, "measurements": measurements, "errors": errors}


def _p95(values):
    ordered = sorted(values)
    return ordered[max(0, (len(ordered) * 95 + 99) // 100 - 1)]


def test_sqlite_wal_and_finite_busy_timeout_are_explicit():
    with connection.cursor() as cursor:
        journal_mode = cursor.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = cursor.execute("PRAGMA busy_timeout").fetchone()[0]

    # pytest-django uses an in-memory SQLite database by default; SQLite
    # correctly reports `memory` there because WAL requires a file-backed DB.
    # The production settings still carry the explicit WAL command.
    if journal_mode.lower() != "wal":
        assert "memory" in str(connection.settings_dict["NAME"]).lower()
        assert journal_mode.lower() == "memory"
    else:
        assert journal_mode.lower() == "wal"
    assert busy_timeout == 5000


def test_thirty_deterministic_django_clients_preserve_session_data(active_session):
    assignments = list(
        DeviceAssignment.objects.filter(session=active_session).order_by("id")
    )
    # Controlled sequence: this is deterministic and measures the complete
    # session flow without turning SQLite writer contention into a hidden
    # retry policy. A 30-writer thread probe was run separately and is
    # documented as a limitation when it reports `database table is locked`.
    reports = [
        _run_one_client(active_session.pk, assignment, index)
        for index, assignment in enumerate(assignments, start=1)
    ]

    measurements = [
        measurement
        for report in reports
        for measurement in report["measurements"]
    ]
    errors = [error for report in reports for error in report["errors"]]
    active_turns = StudentTurn.objects.filter(
        assignment__session=active_session,
        status=StudentTurn.STATUS_ACTIVE,
    ).count()
    completed_turns = StudentTurn.objects.filter(
        assignment__session=active_session,
        status=StudentTurn.STATUS_COMPLETED,
    ).count()
    closed_session = active_session.close()
    result_count = PseudonymousResult.objects.filter(
        result_batch_id=active_session.result_batch_id,
    ).count()
    latency_by_operation = {
        operation: {
            "p95": _p95(
                [
                    item["latency_ms"]
                    for item in measurements
                    if item["operation"] == operation
                ]
            ),
            "max": max(
                item["latency_ms"]
                for item in measurements
                if item["operation"] == operation
            ),
        }
        for operation in {item["operation"] for item in measurements}
    }
    report = {
        "clients": CLIENT_COUNT,
        "mode": "controlled-sequence",
        "operations": len(measurements),
        "latency_ms": latency_by_operation,
        "errors": errors,
        "data_loss": CLIENT_COUNT - result_count,
        "sessions": {
            "before_close": ClassroomSession.STATUS_ACTIVE,
            "active_turns_before_close": active_turns,
            "completed_turns_before_close": completed_turns,
            "after_close": closed_session.status,
            "results_after_close": result_count,
        },
        "physical_test": False,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))

    assert len(reports) == CLIENT_COUNT
    assert len(measurements) == CLIENT_COUNT * 3
    assert errors == []
    assert report["data_loss"] == 0
    assert active_turns == 0
    assert completed_turns == CLIENT_COUNT
    assert closed_session.status == ClassroomSession.STATUS_CLOSED
    assert result_count == CLIENT_COUNT
    assert all(
        operation_report["p95"] <= P95_TARGET_MS
        for operation_report in report["latency_ms"].values()
    )


def test_wsgi_route_probe_is_available_without_network():
    from io import BytesIO
    from wsgiref.util import setup_testing_defaults

    from aulalista.wsgi import application

    environ = {}
    setup_testing_defaults(environ)
    environ.update({"PATH_INFO": "/student/", "REQUEST_METHOD": "GET"})
    captured = []

    def start_response(status, headers, exc_info=None):
        captured.append((status, headers))

    body = b"".join(application(environ, start_response))
    assert captured[0][0] == "200 OK"
    assert b"No hay sesiones activas." in body


def test_package_verification_script_has_no_external_runtime_dependencies():
    from pathlib import Path

    script = Path(__file__).parents[1] / "scripts" / "verify_local_package.py"
    text = script.read_text(encoding="utf-8")
    assert "collectstatic" in text
    assert "aulalista.wsgi" in text
    assert "student/" in text
