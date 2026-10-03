#!/usr/bin/env python3
"""Reproduce the local Django build with disposable state and JSON evidence."""

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
BASE_PACKAGES = ("Django", "Wagtail", "pypdf", "segno", "pytest", "pytest-django")
SERVICE_PACKAGES = ("fastapi", "uvicorn", "httpx", "python-multipart")
ROUTES = """
import django
django.setup()
from django.test import Client
client = Client(enforce_csrf_checks=True)
health = client.get('/health/')
assert health.status_code == 200 and b'healthy' in health.content
student = client.get('/student/')
assert student.status_code == 200
login = client.get('/cms/login/')
assert login.status_code == 200
teacher = client.get('/tutor/')
assert teacher.status_code == 302 and '/cms/login/' in teacher['Location']
assert client.post('/tutor/imports/new/', {}).status_code == 403
print('health=200 student=200 login=200 anonymous_teacher=302 csrf=403')
"""


def run_check(name, arguments, environment, timeout):
    started = time.perf_counter()
    try:
        process = subprocess.run(
            [sys.executable, *arguments], cwd=ROOT, env=environment,
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        result = {
            "returncode": process.returncode,
            "stdout": process.stdout[-12000:], "stderr": process.stderr[-12000:],
        }
    except subprocess.TimeoutExpired:
        result = {"returncode": 124, "stdout": "", "stderr": "Check timed out"}
    except OSError as error:
        result = {"returncode": 1, "stdout": "", "stderr": str(error)}
    return {
        "name": name, "argv": [sys.executable, *arguments],
        "elapsed_seconds": round(time.perf_counter() - started, 4), **result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save JSON evidence as well as stdout")
    parser.add_argument("--service-deps", action="store_true", help="Also require API dependencies")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds allowed per check")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    started = time.perf_counter()
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    versions = {}
    packages = BASE_PACKAGES + (SERVICE_PACKAGES if args.service_deps else ())
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    report = {
        "schema_version": 1, "started_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": sha, "working_tree_dirty": bool(dirty), "python": platform.python_version(),
        "packages": versions, "checks": [], "provider_calls": 0,
        "scope": "Local Django build and in-process HTTP; synthetic tests, no provider evaluation",
        "productive_agent_concurrency": None,
    }
    scratch = os.environ.get("AULALISTA_SCRATCH_DIR")
    with tempfile.TemporaryDirectory(prefix="s20-smoke-", dir=scratch) as temporary:
        environment = dict(os.environ)
        environment.update({
            "AULALISTA_DB_PATH": str(Path(temporary) / "smoke.sqlite3"),
            "AULALISTA_MEDIA_ROOT": str(Path(temporary) / "media"),
            "DJANGO_SETTINGS_MODULE": "aulalista.settings",
            "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": temporary,
        })
        checks = [
            ("django-check", ["manage.py", "check"]),
            ("migrate-empty-db", ["manage.py", "migrate", "--noinput"]),
            ("collectstatic", ["-c", (
                "import django; django.setup(); from django.conf import settings; "
                "from django.core.management import call_command; "
                f"settings.STATIC_ROOT = {str(Path(temporary) / 'static')!r}; "
                "call_command('collectstatic', interactive=False, verbosity=0); "
                "from pathlib import Path; "
                "assert (Path(settings.STATIC_ROOT) / 'health/health.css').is_file(); "
                "print('Static collection and health CSS verified')"
            )]),
            ("http-and-access-boundaries", ["-c", ROUTES]),
            ("human-review-regressions", [
                "-m", "pytest", "-q", "--ds=aulalista.test_settings", "-p", "no:cacheprovider",
                "tests/test_t01_health.py", "tests/test_t21_root_redirect.py",
                "tests/test_t03_publication_snapshot.py",
            ]),
        ]
        if args.service_deps:
            checks.insert(0, ("service-imports", ["-c", (
                "import fastapi, uvicorn, httpx, python_multipart; "
                "print('API dependencies import successfully; application routes not tested')"
            )]))
        for name, arguments in checks:
            result = run_check(name, arguments, environment, args.timeout)
            report["checks"].append(result)
            if result["returncode"] != 0:
                break
    report["passed"] = all(versions.values()) and all(
        check["returncode"] == 0 for check in report["checks"]
    )
    report["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
