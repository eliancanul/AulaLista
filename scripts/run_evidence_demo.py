#!/usr/bin/env python3
"""Run the synthetic, offline T12 demonstration and write small artifacts.

The demo uses a temporary SQLite database and a TEST-NET LAN address. It never
contacts a network service and never writes to the checkout's development DB.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_LAN_URL = "http://192.0.2.10:8000/student/"
CLIENT_COUNT = 30
P95_TARGET_MS = 2000


def _run_migrations(database_path: Path) -> dict[str, object]:
    environment = os.environ.copy()
    environment.update(
        {
            "AULALISTA_DB_PATH": str(database_path),
            "AULALISTA_LAN_URL": SYNTHETIC_LAN_URL,
            "DJANGO_SETTINGS_MODULE": "aulalista.settings",
        }
    )
    completed = subprocess.run(
        [sys.executable, str(ROOT / "manage.py"), "migrate", "--noinput"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": "manage.py migrate --noinput",
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stderr": completed.stderr.strip(),
    }


def _valid_package_payload(*, version: int) -> dict[str, object]:
    correction = version == 2
    return {
        "title": "Fracciones sintéticas v2" if correction else "Fracciones sintéticas v1",
        "objective": "Reconocer partes iguales de un todo.",
        "micro_lesson": (
            "Corrección sintética: el denominador indica cuántas partes iguales hay."
            if correction
            else "El denominador indica las partes iguales."
        ),
        "questions": [
            (
                "reactivo",
                {
                    "prompt": "¿Qué indica el denominador?",
                    "options": [
                        {
                            "position": 1,
                            "text": "Las partes iguales",
                            "expected": True,
                            "feedback": "Respuesta sintética correcta.",
                        },
                        {
                            "position": 2,
                            "text": "El color",
                            "expected": False,
                            "feedback": "Revisa la microlección sintética.",
                        },
                    ],
                    "hints": [
                        "Observa el número de abajo.",
                        "Relaciona el denominador con las partes iguales.",
                    ],
                },
            )
        ],
        "final_explanation": "El denominador cuenta las partes iguales.",
    }


def _create_reviewer():
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.get_or_create(name="EditorialReviewer")
    reviewer = get_user_model().objects.create_user(
        username="synthetic-editorial-reviewer",
        password="synthetic-only-password",
        is_staff=True,
    )
    reviewer.groups.add(group)
    reviewer.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="curriculum",
            content_type__model="curriculumpackage",
            codename__in=("add_curriculumpackage", "change_curriculumpackage"),
        ),
        Permission.objects.get(
            content_type__app_label="wagtailadmin",
            codename="access_admin",
        ),
    )
    return reviewer


def _publish_revision(package, reviewer, client, comment):
    from django.urls import reverse
    from curriculum.models import PublishedPackageSnapshot

    revision = package.save_revision(user=reviewer)
    workflow_state = package.get_workflow().start(package, user=reviewer)
    task_state = workflow_state.current_task_state
    action_url = reverse(
        package.snippet_viewset.get_url_name("workflow_action"),
        args=[package.pk, "approve", task_state.pk],
    )
    response = client.post(action_url, {"comment": comment})
    if response.status_code != 302:
        raise RuntimeError(
            f"La aprobación editorial sintética devolvió HTTP {response.status_code}."
        )
    return PublishedPackageSnapshot.objects.get(
        package=package,
        source_revision=revision,
    )


def _hidden_value(response, field_name: str) -> str:
    match = re.search(rf'name="{re.escape(field_name)}" value="([^"]+)"', response.text)
    if not match:
        raise RuntimeError(f"No se encontró la capacidad sintética {field_name}.")
    return match.group(1)


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, (len(ordered) * 95 + 99) // 100 - 1)]


@contextmanager
def _deny_external_network():
    calls = []

    def blocked(*args, **kwargs):
        calls.append({"args": repr(args), "kwargs": repr(kwargs)})
        raise AssertionError("La demo no debe abrir conexiones externas.")

    with (
        patch("socket.create_connection", blocked),
        patch("socket.getaddrinfo", blocked),
        patch("socket.socket.connect", blocked),
        patch("urllib.request.urlopen", blocked),
    ):
        yield calls


def _run_t10_probe(snapshot) -> dict[str, object]:
    from django.test import Client
    from django.urls import reverse
    from curriculum.models import (
        ClassroomSession,
        DeviceAssignment,
        PseudonymousResult,
        StudentTurn,
    )

    session = ClassroomSession.prepare_from_snapshot(snapshot, CLIENT_COUNT, CLIENT_COUNT)
    session.confirm()
    measurements: dict[str, list[float]] = {"start": [], "activity": [], "ready": []}
    errors: list[str] = []
    assignments = list(DeviceAssignment.objects.filter(session=session).order_by("id"))
    for index, assignment in enumerate(assignments, start=1):
        client = Client()
        for operation, method, url_name, data in (
            (
                "start",
                client.post,
                "student-turn-start",
                {"display_name": f"Cliente sintetico {index:02d}"},
            ),
            ("activity", client.get, "student-activity", None),
            ("ready", client.post, "student-turn-ready", None),
        ):
            started = time.perf_counter()
            if operation == "start":
                response = method(
                    reverse(url_name, args=[session.pk, assignment.local_identifier]),
                    data,
                )
            else:
                response = method(reverse(url_name, args=[session.pk]))
            measurements[operation].append(round((time.perf_counter() - started) * 1000, 3))
            expected_status = 302 if operation != "activity" else 200
            if response.status_code != expected_status:
                errors.append(f"{operation}:{response.status_code}")

    active_turns = StudentTurn.objects.filter(
        assignment__session=session,
        status=StudentTurn.STATUS_ACTIVE,
    ).count()
    completed_turns = StudentTurn.objects.filter(
        assignment__session=session,
        status=StudentTurn.STATUS_COMPLETED,
    ).count()
    closed = session.close()
    result_count = PseudonymousResult.objects.filter(
        result_batch_id=session.result_batch_id,
    ).count()
    latency = {
        operation: {"p95_ms": _p95(values), "max_ms": max(values)}
        for operation, values in measurements.items()
    }
    return {
        "clients": CLIENT_COUNT,
        "mode": "controlled-sequence",
        "operations": CLIENT_COUNT * 3,
        "latency": latency,
        "p95_target_ms": P95_TARGET_MS,
        "errors": errors,
        "data_loss": CLIENT_COUNT - result_count,
        "state": {
            "active_turns_before_close": active_turns,
            "completed_turns_before_close": completed_turns,
            "session_after_close": closed.status,
            "results_after_close": result_count,
        },
        "passed": (
            not errors
            and active_turns == 0
            and completed_turns == CLIENT_COUNT
            and result_count == CLIENT_COUNT
            and closed.status == ClassroomSession.STATUS_CLOSED
            and all(item["p95_ms"] <= P95_TARGET_MS for item in latency.values())
        ),
        "concurrency_limit": (
            "No se afirma soporte para 30 escritores simultáneos: T10 documenta "
            "database table is locked como límite exploratorio de SQLite."
        ),
        "physical_test": False,
    }


def _run_demo() -> dict[str, object]:
    import django

    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
    os.environ.setdefault("AULALISTA_LAN_URL", SYNTHETIC_LAN_URL)
    django.setup()

    from django.core.cache import cache
    from django.test import Client
    from django.urls import reverse
    from curriculum.models import (
        ClassroomSession,
        CurriculumPackage,
        DeviceAssignment,
        PseudonymousResult,
        PublishedPackageSnapshot,
        StudentTurn,
    )

    cache.clear()
    reviewer = _create_reviewer()
    editorial_client = Client()
    editorial_client.force_login(reviewer)
    package = CurriculumPackage.objects.create(
        **_valid_package_payload(version=1),
    )
    snapshot_one = _publish_revision(
        package,
        reviewer,
        editorial_client,
        "Aprobación humana sintética de v1.",
    )

    session = ClassroomSession.prepare_from_snapshot(snapshot_one, 1, 1)
    prepared_status = session.status
    confirmation = editorial_client.post(
        reverse("tutor-session-confirm", args=[session.pk])
    )
    session.refresh_from_db()

    student_client = Client()
    assignment = DeviceAssignment.objects.get(session=session)
    started = student_client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Participante sintetico 01"},
    )
    activity = student_client.get(reverse("student-activity", args=[session.pk]))
    answer = student_client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 1},
    )
    help_response = student_client.post(
        reverse("student-question-assistance", args=[session.pk, 0]),
        {
            "kind": "hint",
            "hint_index": 0,
            "hint_capability": _hidden_value(activity, "hint_capability"),
        },
    )
    ready = student_client.post(reverse("student-turn-ready", args=[session.pk]))
    result_count_before_close = PseudonymousResult.objects.count()

    package.title = "Fracciones sintéticas v2"
    package.micro_lesson = _valid_package_payload(version=2)["micro_lesson"]
    package.save()
    snapshot_two = _publish_revision(
        package,
        reviewer,
        editorial_client,
        "Aprobación humana sintética de la corrección v2.",
    )
    session.refresh_from_db()
    session_snapshot_unchanged = session.snapshot_id == snapshot_one.pk
    session_snapshot_version = session.snapshot.version
    export_before_close = editorial_client.post(
        reverse("tutor-session-export", args=[session.pk]),
        {"format": "json"},
    )
    closed = session.close()
    results = list(
        PseudonymousResult.objects.filter(result_batch_id=session.result_batch_id)
    )
    result_fields = {field.name for field in PseudonymousResult._meta.fields}
    forbidden_fields = sorted(
        result_fields.intersection(
            {"display_name", "name", "email", "enrollment", "location", "password"}
        )
    )
    export = editorial_client.post(
        reverse("tutor-session-export", args=[session.pk]),
        {"format": "json"},
    )
    with _deny_external_network() as network_calls:
        access = Client().get(reverse("local-access"))
        student_entrypoint = Client().get(reverse("student-packages"))
    lan_evidence = {
        "configured_url": SYNTHETIC_LAN_URL,
        "access_page_status": access.status_code,
        "qr_contains_url": f'data-qr-value="{SYNTHETIC_LAN_URL}"' in access.text,
        "student_entrypoint_status": student_entrypoint.status_code,
        "wan_requests_made": len(network_calls),
        "external_network_blocked": True,
        "physical_two_device_test": False,
        "note": "192.0.2.10 es TEST-NET; la verificación física requiere la LAN real.",
    }
    t10 = _run_t10_probe(snapshot_two)

    checks = {
        "snapshot_v1_published": snapshot_one.version == 1,
        "session_confirmed": confirmation.status_code == 302,
        "practice_and_help_completed": answer.status_code == 200
        and help_response.status_code == 200,
        "snapshot_v2_published": snapshot_two.version == 2,
        "session_pinned_to_v1": session_snapshot_unchanged,
        "export_blocked_before_close": export_before_close.status_code == 400,
        "closed_and_temporal_links_erased": closed.status == "closed"
        and not StudentTurn.objects.filter(assignment__session=session).exists()
        and not DeviceAssignment.objects.filter(session=session).exists(),
        "results_are_pseudonymous": not forbidden_fields
        and all(field.remote_field is None for field in PseudonymousResult._meta.fields),
        "export_available_after_close": export.status_code == 200,
        "lan_without_external_network": (
            lan_evidence["access_page_status"] == 200
            and lan_evidence["qr_contains_url"]
            and lan_evidence["student_entrypoint_status"] == 200
            and lan_evidence["wan_requests_made"] == 0
        ),
    }

    return {
        "demo": {
            "name": "T12 AulaLista synthetic evidence",
            "synthetic_content": True,
            "real_personal_data": False,
            "pedagogical_impact": "not measured",
            "minor_pilot": False,
            "real_emergency_continuity": False,
        },
        "installation": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "migration": "completed before the scenario",
        },
        "editorial": {
            "reviewer_role": "EditorialReviewer",
            "approval_is_human_workflow": True,
            "snapshot_v1": {
                "id": snapshot_one.pk,
                "version": snapshot_one.version,
                "sha256": snapshot_one.sha256,
            },
            "snapshot_v2": {
                "id": snapshot_two.pk,
                "version": snapshot_two.version,
                "sha256": snapshot_two.sha256,
            },
        },
        "session": {
            "id": session.pk,
            "prepared_status": prepared_status,
            "confirmation_http_status": confirmation.status_code,
            "started_http_status": started.status_code,
            "activity_http_status": activity.status_code,
            "answer_http_status": answer.status_code,
            "help_http_status": help_response.status_code,
            "ready_http_status": ready.status_code,
            "results_before_close": result_count_before_close,
            "snapshot_version_at_close": session_snapshot_version,
            "session_stayed_on_v1_after_v2": session_snapshot_unchanged,
            "closed_status": closed.status,
            "results_after_close": len(results),
            "temporal_turns_after_close": StudentTurn.objects.count(),
            "temporal_assignments_after_close": DeviceAssignment.objects.count(),
            "result_is_pseudonymous": not forbidden_fields
            and all(field.remote_field is None for field in PseudonymousResult._meta.fields),
            "forbidden_personal_fields_found": forbidden_fields,
            "export_http_status": export.status_code,
            "export_before_close_http_status": export_before_close.status_code,
        },
        "lan_without_wan": lan_evidence,
        "t10": t10,
        "checks": checks,
        "known_limits": [
            "No se probó físicamente con teléfonos, Wi-Fi ni WAN desconectada.",
            "La secuencia controlada no equivale a escritores simultáneos.",
            "LocMemCache mantiene el MVP en un solo proceso WSGI.",
            "El contenido es DemoPackage sintético y no tiene aprobación curricular real.",
        ],
    }


def _write_artifacts(report: dict[str, object], output_dir: Path, migration: dict[str, object]):
    output_dir.mkdir(parents=True, exist_ok=True)
    report["installation"]["migration_report"] = migration
    report["passed"] = bool(
        migration["passed"]
        and report["t10"]["passed"]
        and all(report["checks"].values())
    )
    report_json = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (output_dir / "t12-evidence.json").write_text(report_json, encoding="utf-8")
    report_html = """<!doctype html>
<html lang="es"><meta charset="utf-8"><title>Evidencia T12 | AulaLista</title>
<style>body{font:16px system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;background:#f7f4ee;color:#17202a}pre{white-space:pre-wrap;background:#fff;padding:1rem;border:1px solid #ccd2d8;border-radius:.5rem}h1{color:#144b5f}.ok{color:#176b3a;font-weight:700}</style>
<main><h1>Evidencia técnica T12 — AulaLista</h1>
<p class="ok">Resultado reproducible: %s</p>
<p>Contenido sintético, sin datos personales reales. La prueba física de LAN y WAN queda declarada como pendiente.</p>
<pre>%s</pre></main></html>
""" % ("PASS" if report["passed"] else "FAIL", html.escape(report_json))
    (output_dir / "t12-evidence.html").write_text(report_html, encoding="utf-8")
    return [output_dir / "t12-evidence.json", output_dir / "t12-evidence.html"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "evidence" / "t12",
        help="directorio para JSON y HTML reproducibles",
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aulalista-t12-") as temporary:
        database_path = Path(temporary) / "demo.sqlite3"
        os.environ.update(
            {
                "AULALISTA_DB_PATH": str(database_path),
                "AULALISTA_LAN_URL": SYNTHETIC_LAN_URL,
                "DJANGO_SETTINGS_MODULE": "aulalista.settings",
            }
        )
        migration = _run_migrations(database_path)
        if not migration["passed"]:
            print(json.dumps({"passed": False, "migration": migration}, ensure_ascii=False))
            return 1
        report = _run_demo()
        artifacts = _write_artifacts(report, args.output_dir, migration)
        print(json.dumps({"passed": report["passed"], "artifacts": [str(path) for path in artifacts]}, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
