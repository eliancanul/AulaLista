import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from curriculum.models import CurriculumImportJob, PublishedPackageSnapshot
from test_t15_curriculum_import import make_minimal_pdf


@pytest.mark.django_db(transaction=True)
@pytest.mark.browser
@pytest.mark.usefixtures("legacy_import_routes")
def test_s15_offline_review_keeps_edit_and_retries(live_server, tmp_path, settings):
    chrome = os.environ.get(
        "S15_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    )
    if not Path(chrome).is_file() or not shutil.which("node"):
        if os.environ.get("CI") or os.environ.get("TEACHER_REVIEW_BROWSER_REQUIRED") == "1":
            pytest.fail("Required legacy Chrome/Node acceptance did not run")
        pytest.skip("S15 browser check requires installed Chrome and Node 22+")
    settings.AULALISTA_IMPORT_ASYNC = False
    pdf = tmp_path / 'synthetic-reading.pdf'
    pdf.write_bytes(make_minimal_pdf(['Proyecto: La lectura\nPropósito: Leer el texto.\nMateriales: Papel\nGrado: 3ro\nSESIÓN 1: Leemos\nInicio: Mirar la hoja.\nDesarrollo: Leer el texto.\nCierre: Compartir una observación.']))
    teacher = get_user_model().objects.create_user(
        username="s15-synthetic-teacher", password="s15-local-test-only", is_staff=True
    )
    teacher.user_permissions.add(Permission.objects.get(codename="access_admin"))
    evidence_dir = Path(os.environ.get("S15_EVIDENCE_DIR", tmp_path))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "baseUrl": live_server.url,
        "chrome": chrome,
        "profile": str(tmp_path / "chrome-profile"),
        "pdf": str(pdf),
        "evidenceDir": str(evidence_dir.resolve()),
    }
    result = subprocess.run(
        ["node", str(Path(__file__).with_name("s15_offline_review.mjs"))],
        input=json.dumps(config), text=True, capture_output=True, timeout=120,
    )
    print(result.stdout)
    assert result.returncode == 0, result.stderr + result.stdout
    job = CurriculumImportJob.objects.get()
    dossier = job.get_interpretation_dossier()
    assert dossier.general_fields["proyecto"].value == "Proyecto revisado por S15"
    assert PublishedPackageSnapshot.objects.count() == 0
