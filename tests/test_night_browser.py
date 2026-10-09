"""Retired Vue regression, isolated test-only shell; not active-flow acceptance."""
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import threading
import time

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from api.persistence import SQLiteRepository
from curriculum.models import PublishedPackageSnapshot, ClassroomSession
from test_t15_curriculum_import import make_minimal_pdf


@pytest.mark.django_db(transaction=True)
@pytest.mark.browser
@pytest.mark.usefixtures("legacy_vue_routes")
def test_compiled_browser_journey(tmp_path, settings):
    chrome = (os.environ.get('NIGHT_CHROME') or shutil.which('google-chrome')
              or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    if not Path(chrome).is_file():
        if os.environ.get('NIGHT_BROWSER_REQUIRED') == '1' or os.environ.get('CI'):
            pytest.fail('Required Chrome is missing; browser acceptance did not run')
        pytest.skip('Requires installed Chrome; set NIGHT_CHROME on CI')
    assert Path('frontend/dist/index.html').is_file(), 'Build frontend first'
    import uvicorn
    from api.local import app
    settings.SPRINT_PERSISTENCE_PATH = str(tmp_path / 'drafts.sqlite3')
    store = SQLiteRepository(settings.SPRINT_PERSISTENCE_PATH)
    teacher = get_user_model().objects.create_user(username='night-synthetic', password='night-test-only', is_staff=True)
    teacher.user_permissions.add(Permission.objects.get(codename='access_admin'))
    pdf = tmp_path / 'synthetic.pdf'
    pdf.write_bytes(make_minimal_pdf(['Proyecto: La lectura\nPropósito: Leer el texto.\nMateriales: Papel\nGrado: 3ro']))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning', lifespan='off'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started
    evidence = Path(os.environ.get('NIGHT_EVIDENCE_DIR', str(tmp_path / 'evidence')))
    evidence.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(['node', 'tests/night_browser.mjs'], input=json.dumps({
            'baseUrl': f'http://127.0.0.1:{port}', 'chrome': chrome,
            'profile': str(tmp_path / 'profile'), 'pdf': str(pdf), 'evidenceDir': str(evidence),
        }), text=True, capture_output=True, timeout=150)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
        assert len(store.list_interpretations(teacher.pk)) == 1
        assert PublishedPackageSnapshot.objects.count() == 0
        assert ClassroomSession.objects.count() == 0
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
