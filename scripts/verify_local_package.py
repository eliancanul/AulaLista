#!/usr/bin/env python3
"""Verify the local package's static collection and critical WSGI route."""

import json
import os
import subprocess
import sys
import threading
from urllib.request import urlopen
from pathlib import Path
from wsgiref.simple_server import make_server


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
sys.path.insert(0, str(ROOT))


def run_collectstatic():
    return subprocess.run(
        [sys.executable, str(ROOT / "manage.py"), "collectstatic", "--noinput"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def probe_wsgi():
    from aulalista.wsgi import application

    server = make_server("127.0.0.1", 0, application)
    worker = threading.Thread(target=server.handle_request, daemon=True)
    worker.start()
    with urlopen(
        f"http://127.0.0.1:{server.server_port}/student/", timeout=5
    ) as response:
        status = f"{response.status} {response.reason}"
        body = response.read()
    worker.join(timeout=5)
    server.server_close()
    return {
        "status": status,
        "critical_route": "/student/",
        "body_contains_entrypoint": b"No hay paquetes publicados." in body,
        "transport": "loopback-socket",
    }


def main():
    collectstatic = run_collectstatic()
    wsgi = probe_wsgi() if collectstatic.returncode == 0 else {}
    report = {
        "collectstatic": {
            "returncode": collectstatic.returncode,
            "stdout": collectstatic.stdout.strip(),
            "stderr": collectstatic.stderr.strip(),
        },
        "wsgi": wsgi,
        "passed": (
            collectstatic.returncode == 0
            and wsgi.get("status") == "200 OK"
            and wsgi.get("body_contains_entrypoint") is True
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
