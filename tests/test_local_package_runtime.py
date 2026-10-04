"""Installed-script checks using generated responses; never bind a socket."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys

import pytest
from django.test import Client

ROOT = Path(__file__).resolve().parents[1]


def _verifier():
    spec = importlib.util.spec_from_file_location('package_verifier', ROOT / 'scripts/verify_local_package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_server(monkeypatch, module):
    class Server:
        server_port = 8765
        closed = False
        def handle_request(self):
            pass
        def server_close(self):
            self.closed = True
    server = Server()
    monkeypatch.setattr(module, 'make_server', lambda *args: server)
    return server


@pytest.mark.django_db
def test_package_probe_accepts_the_current_student_entrypoint(monkeypatch):
    module = _verifier()
    server = _fake_server(monkeypatch, module)
    page = Client().get('/student/')
    assert page.status_code == 200
    assert b'No hay sesiones activas.' in page.content
    class Response(io.BytesIO):
        status = 200
        reason = 'OK'
    def response(url, timeout):
        assert url == 'http://127.0.0.1:8765/student/' and timeout == 5
        return Response(page.content)
    monkeypatch.setattr(module, 'urlopen', response)
    report = module.probe_wsgi()
    assert report['status'] == '200 OK'
    assert report['body_contains_entrypoint'] is True
    assert server.closed


def test_package_probe_closes_its_server_after_request_failure(monkeypatch):
    module = _verifier()
    server = _fake_server(monkeypatch, module)
    def fail(*args, **kwargs):
        raise OSError('synthetic connection failure')
    monkeypatch.setattr(module, 'urlopen', fail)
    with pytest.raises(OSError, match='synthetic connection failure'):
        module.probe_wsgi()
    assert server.closed


def test_wsgi_launcher_imports_checkout_without_pythonpath_or_package_install(tmp_path):
    # -I removes ambient PYTHONPATH/cwd. The documented script must locate its
    # sibling application itself. A fake make_server stops before any socket.
    script = ROOT / 'scripts/run_wsgi.py'
    code = '''
import runpy,sys,wsgiref.simple_server
script=sys.argv[1]
def no_socket(*args, **kwargs):
    print('APPLICATION_IMPORTED_WITHOUT_SOCKET')
    raise SystemExit(0)
wsgiref.simple_server.make_server=no_socket
sys.argv=[script]
runpy.run_path(script,run_name='__main__')
'''
    env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'aulalista.test_settings',
           'AULALISTA_GEMINI_LIVE_ENABLED': '0'}
    result = subprocess.run([sys.executable, '-I', '-c', code, str(script)],
                            cwd=tmp_path, env=env, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'APPLICATION_IMPORTED_WITHOUT_SOCKET'
