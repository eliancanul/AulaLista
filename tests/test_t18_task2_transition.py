"""Tests for Task 2: Happy path automatic transition after curriculum upload.

Contratos:
- POST válido a /tutor/imports/new/ crea el job una sola vez y dispara inmediatamente
  el pipeline de interpretación V0 existente sin lanzar extracción legacy.
- Redirección 302 a Location de espera (tutor-import-wait), nunca a tutor-import-detail.
- tutor-import-wait ofrece/lleva a 'Revisar planeación' (tutor-import-interpretation) sin parpadeo de detail técnico.
- GET refresh en wait es byte-identical y no reejecuta la interpretación.
- Llamada repetida a trigger_job_interpretation sobre el mismo job es idempotente (no duplica dossier/historial/versión).
- Control de acceso: otro docente recibe 404 en wait.
- Upload inválido mantiene T1 (HTTP 400 sin crear job ni iniciar interpretación).
- CSRF y source_sha256 preservados.
"""

import hashlib
import uuid
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from curriculum.models import CurriculumImportJob
from helpers import MINIMAL_VALID_PDF_BYTES, tutor_client

pytestmark = pytest.mark.django_db(transaction=True)

C01_PATH = Path("output/pdf/prueba-issue-96-paginas-4-a-8.pdf")


def _c01_upload():
    assert C01_PATH.exists(), f"Fixture C01 missing at {C01_PATH}"
    return SimpleUploadedFile(
        "prueba-semana-01.pdf",
        C01_PATH.read_bytes(),
        content_type="application/pdf",
    )


_CACHED_C01_DOSSIER = None


def _valid_c01_dossier_dict():
    global _CACHED_C01_DOSSIER
    if _CACHED_C01_DOSSIER is None:
        import copy
        from curriculum.source_interpreter import CurriculumSourceInterpreter
        d = CurriculumSourceInterpreter.prepare(C01_PATH)
        _CACHED_C01_DOSSIER = d.to_dict()
    import copy
    return copy.deepcopy(_CACHED_C01_DOSSIER)


def test_task2_valid_post_c01_redirects_to_wait_and_interprets_once():
    """Valid POST with C01 creates job once, starts interpretation, and redirects to wait."""
    client = tutor_client("t2-c01-teacher")
    upload_url = reverse("tutor-import-upload")

    initial_job_count = CurriculumImportJob.objects.count()
    resp = client.post(upload_url, {"pdf": _c01_upload()})

    # 1. Redirect to wait (never detail)
    assert resp.status_code in (302, 303)
    assert CurriculumImportJob.objects.count() == initial_job_count + 1

    job = CurriculumImportJob.objects.latest("id")
    expected_wait_url = reverse("tutor-import-wait", args=[job.pk])
    assert resp["Location"] == expected_wait_url
    assert "/espera/" in resp["Location"]
    assert "/tutor/imports/" in resp["Location"]
    assert not resp["Location"].endswith(f"/tutor/imports/{job.pk}/")

    # 2. Interpretation was executed and persisted on the job
    job.refresh_from_db()
    assert job.interpretation_dossier is not None
    dossier = job.get_interpretation_dossier()
    assert dossier is not None
    assert dossier.version == 1
    assert len(dossier.history) == 1
    assert dossier.history[0]["action"] == "prepare"
    assert len(dossier.sessions) == 2

    # 3. Source SHA matches uploaded file
    c01_bytes = C01_PATH.read_bytes()
    expected_sha = hashlib.sha256(c01_bytes).hexdigest()
    assert dossier.source_sha256 == expected_sha


def test_task2_wait_page_offers_review_planning_and_refresh_is_byte_identical():
    """GET on wait page shows 'Estamos organizando tu planeación', offers review, and refresh is byte-identical."""
    client = tutor_client("t2-wait-teacher")
    upload_url = reverse("tutor-import-upload")
    client.post(upload_url, {"pdf": _c01_upload()})

    job = CurriculumImportJob.objects.latest("id")
    wait_url = reverse("tutor-import-wait", args=[job.pk])

    # First GET
    resp1 = client.get(wait_url)
    assert resp1.status_code == 200
    html1 = resp1.content.decode("utf-8")

    # Contains coherent state: organizing / ready for review
    assert "Estamos organizando tu planeación" in html1
    assert "Revisar planeación" in html1
    interp_url = reverse("tutor-import-interpretation", args=[job.pk])
    assert interp_url in html1

    import re
    # Second GET: byte-identical excluding dynamic CSRF token, no re-execution, no state modification
    resp2 = client.get(wait_url)
    assert resp2.status_code == 200
    strip_csrf = lambda h: re.sub(r'name="csrfmiddlewaretoken" value="[^"]*"', '', h)
    assert strip_csrf(resp1.content.decode("utf-8")) == strip_csrf(resp2.content.decode("utf-8"))

    job.refresh_from_db()
    assert job.interpretation_dossier["version"] == 1
    assert len(job.interpretation_dossier["history"]) == 1


def test_task2_repeated_trigger_is_idempotent_no_duplicate_dossier():
    """Calling trigger_job_interpretation repeatedly on same job does not duplicate history or version."""
    from curriculum.views import trigger_job_interpretation

    client = tutor_client("t2-idempotency-teacher")
    upload_url = reverse("tutor-import-upload")
    client.post(upload_url, {"pdf": _c01_upload()})

    job = CurriculumImportJob.objects.latest("id")
    job.refresh_from_db()
    initial_version = job.interpretation_dossier["version"]
    initial_history_len = len(job.interpretation_dossier["history"])

    # Trigger again explicitly on the same job
    result_dossier = trigger_job_interpretation(job)
    assert result_dossier is not None

    job.refresh_from_db()
    assert job.interpretation_dossier["version"] == initial_version
    assert len(job.interpretation_dossier["history"]) == initial_history_len


def test_task2_ownership_other_teacher_gets_404_on_wait():
    """A teacher cannot access the wait page of another teacher's job."""
    owner_client = tutor_client("t2-owner")
    owner_client.post(reverse("tutor-import-upload"), {"pdf": _c01_upload()})
    job = CurriculumImportJob.objects.latest("id")

    other_client = tutor_client("t2-other")
    wait_url = reverse("tutor-import-wait", args=[job.pk])
    resp_other = other_client.get(wait_url)
    assert resp_other.status_code == 404


def test_task2_invalid_upload_rejects_and_does_not_create_job_or_dossier():
    """Invalid upload returns 400 without creating job or starting interpretation."""
    client = tutor_client("t2-invalid-tester")
    upload_url = reverse("tutor-import-upload")

    initial_job_count = CurriculumImportJob.objects.count()

    # Fake PDF bytes
    resp = client.post(
        upload_url,
        {"pdf": SimpleUploadedFile("fake.pdf", b"not a pdf", content_type="application/pdf")},
    )
    assert resp.status_code == 400
    assert CurriculumImportJob.objects.count() == initial_job_count


def test_task2_legacy_detail_endpoint_preserved_for_dependencies():
    """Legacy tutor-import-detail route remains accessible with existing controls."""
    client = tutor_client("t2-legacy-tester")
    client.post(reverse("tutor-import-upload"), {"pdf": _c01_upload()})
    job = CurriculumImportJob.objects.latest("id")

    detail_url = reverse("tutor-import-detail", args=[job.pk])
    resp_detail = client.get(detail_url)
    assert resp_detail.status_code == 200
    assert "Importación de currícula" in resp_detail.content.decode("utf-8")
    assert "Asistente de planeación · Interpretación de guía docente (V0)" in resp_detail.content.decode("utf-8")


from django.test import TransactionTestCase


class TestTask2InterpretationConcurrency(TransactionTestCase):
    """B1 concurrency validation: Multi-connection SQLite testing using TransactionTestCase."""

    databases = "__all__"

    def test_concurrent_trigger_single_prepare_and_no_operational_error(self):
        """Two concurrent threads on same job execute prepare once without locks."""
        import threading
        import time
        from unittest.mock import patch
        from curriculum.source_interpreter import CurriculumSourceInterpreter
        from curriculum.views import trigger_job_interpretation
        from django.db import connections

        # Stability verification: repeat 3 iterations to confirm robustness
        for iteration in range(3):
            client = tutor_client(f"t2-concurrent-user-{iteration}")
            job = CurriculumImportJob.objects.create(
                created_by=client.user if hasattr(client, "user") else None,
                pdf=_c01_upload(),
                status=CurriculumImportJob.STATUS_UPLOADED,
            )

            real_prepare = CurriculumSourceInterpreter.prepare
            prepare_calls = 0
            prepare_lock = threading.Lock()

            def slow_prepare(*args, **kwargs):
                nonlocal prepare_calls
                with prepare_lock:
                    prepare_calls += 1
                time.sleep(0.1)
                return real_prepare(*args, **kwargs)

            barrier = threading.Barrier(2)
            results = [None, None]
            errors = [None, None]

            def worker(idx):
                connections.close_all()
                try:
                    barrier.wait(timeout=5.0)
                    j = CurriculumImportJob.objects.get(pk=job.pk)
                    results[idx] = trigger_job_interpretation(j, wait_timeout=5.0, poll_interval=0.02)
                except Exception as exc:
                    errors[idx] = exc
                finally:
                    connections.close_all()

            with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=slow_prepare):
                t1 = threading.Thread(target=worker, args=(0,))
                t2 = threading.Thread(target=worker, args=(1,))
                t1.start()
                t2.start()
                t1.join(timeout=10.0)
                t2.join(timeout=10.0)

            # 1. No OperationalError or lock errors on either thread
            for idx, err in enumerate(errors):
                assert err is None, f"Iteration {iteration}, Worker {idx} failed with: {err!r}"

            # 2. Both callers received the valid dossier
            assert results[0] is not None
            assert results[1] is not None
            assert results[0].version == 1
            assert results[1].version == 1

            # 3. prepare() was called exactly once
            assert prepare_calls == 1

            # 4. Dossier in DB has version 1 and history length 1
            job.refresh_from_db()
            assert job.interpretation_dossier["version"] == 1
            assert len(job.interpretation_dossier["history"]) == 1
            assert job.progress_stage == ""

            # 5. Secuencial listo no compute: calling trigger on ready job does not compute
            with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=slow_prepare):
                seq_result = trigger_job_interpretation(job)
                assert seq_result is not None
                assert seq_result.version == 1
                assert prepare_calls == 1, "Sequential trigger on ready job must not call prepare"

    def test_concurrent_trigger_owner_error_propagates_to_waiter_no_retry_no_deadlock(self):
        """B1 owner error: When owner encounters an error during prepare, claim is released consistently."""
        import threading
        import time
        from unittest.mock import patch
        from curriculum.source_interpreter import (
            CurriculumInterpretationError,
            CurriculumSourceInterpreter,
            SourcePdfReadError,
        )
        from curriculum.views import trigger_job_interpretation
        from django.db import connections

        client = tutor_client("t2-err-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        prepare_calls = 0
        prepare_lock = threading.Lock()

        def failing_slow_prepare(*args, **kwargs):
            nonlocal prepare_calls
            with prepare_lock:
                prepare_calls += 1
            time.sleep(0.1)
            raise SourcePdfReadError("Simulated extraction error for testing owner failure")

        barrier = threading.Barrier(2)
        results = [None, None]
        errors = [None, None]

        def worker(idx):
            connections.close_all()
            try:
                barrier.wait(timeout=5.0)
                j = CurriculumImportJob.objects.get(pk=job.pk)
                results[idx] = trigger_job_interpretation(j, wait_timeout=5.0, poll_interval=0.02)
            except Exception as exc:
                errors[idx] = exc
            finally:
                connections.close_all()

        with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=failing_slow_prepare):
            t1 = threading.Thread(target=worker, args=(0,))
            t2 = threading.Thread(target=worker, args=(1,))
            t1.start()
            t2.start()
            t1.join(timeout=10.0)
            t2.join(timeout=10.0)

        # Prepare must have been called exactly once (no retry by waiter)
        assert prepare_calls == 1

        # Both threads got an exception:
        # Owner got SourcePdfReadError (or re-raised error)
        # Waiter got CurriculumInterpretationError containing the error message
        assert errors[0] is not None
        assert errors[1] is not None
        for err in errors:
            assert isinstance(err, (SourcePdfReadError, CurriculumInterpretationError))
            assert "Simulated extraction error" in str(err)

        # Job in DB has interpretation_error_message recorded and progress_stage cleared
        job.refresh_from_db()
        assert "Simulated extraction error" in (job.interpretation_error_message or job.error_message)
        assert job.progress_stage == ""

    def test_prepare_clears_progress_stage_before_success_still_persists_dossier(self):
        """Red test 1: prepare() internally clears progress_stage before success.
        Ownership is decoupled via interpretation_claim_token:
        - prepare_calls == 1.
        - Dossier is correctly persisted in DB despite progress_stage having been cleared.
        """
        import threading
        import time
        from unittest.mock import patch
        from curriculum.source_interpreter import CurriculumSourceInterpreter
        from curriculum.views import trigger_job_interpretation
        from django.db import connections

        client = tutor_client("t2-clear-stage-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        real_prepare = CurriculumSourceInterpreter.prepare
        prepare_calls = 0
        prepare_lock = threading.Lock()

        def prepare_clearing_stage(*args, **kwargs):
            nonlocal prepare_calls
            with prepare_lock:
                prepare_calls += 1
            # real_prepare internally clears progress_stage before returning (source_interpreter.py:1843)
            return real_prepare(*args, **kwargs)

        barrier = threading.Barrier(2)
        results = [None, None]
        errors = [None, None]

        def worker(idx):
            connections.close_all()
            try:
                barrier.wait(timeout=5.0)
                j = CurriculumImportJob.objects.get(pk=job.pk)
                results[idx] = trigger_job_interpretation(j, wait_timeout=5.0, poll_interval=0.02)
            except Exception as exc:
                errors[idx] = exc
            finally:
                connections.close_all()

        with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=prepare_clearing_stage):
            t1 = threading.Thread(target=worker, args=(0,))
            t2 = threading.Thread(target=worker, args=(1,))
            t1.start()
            t2.start()
            t1.join(timeout=10.0)
            t2.join(timeout=10.0)

        for err in errors:
            assert err is None, f"Unexpected error: {err!r}"

        assert prepare_calls == 1
        assert results[0] is not None
        assert results[1] is not None
        assert results[0].version == 1
        assert results[1].version == 1

        job.refresh_from_db()
        assert job.interpretation_dossier["version"] == 1
        assert len(job.interpretation_dossier["history"]) == 1
        assert job.interpretation_claim_token is None

    def test_prepare_clears_stage_and_fails_persists_error_no_second_prepare(self):
        """Red test 2: prepare() clears stage and fails.
        Waiter detects active claim_token, does not attempt a second prepare.
        Error is persisted in DB and claim is cleanly released.
        """
        import threading
        import time
        from unittest.mock import patch
        from curriculum.source_interpreter import (
            CurriculumInterpretationError,
            CurriculumSourceInterpreter,
            SourcePdfReadError,
        )
        from curriculum.views import trigger_job_interpretation
        from django.db import connections

        client = tutor_client("t2-clear-stage-err-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        prepare_calls = 0
        prepare_lock = threading.Lock()

        def prepare_clearing_and_failing(*args, **kwargs):
            nonlocal prepare_calls
            with prepare_lock:
                prepare_calls += 1
            # Simulate internal clearing of progress_stage before raising
            from curriculum.views import _execute_with_db_lock_retry
            _execute_with_db_lock_retry(lambda: CurriculumImportJob.objects.filter(pk=job.pk).update(progress_stage=""))
            time.sleep(0.05)
            raise SourcePdfReadError("Fallo interno con stage limpio")

        barrier = threading.Barrier(2)
        results = [None, None]
        errors = [None, None]

        def worker(idx):
            connections.close_all()
            try:
                barrier.wait(timeout=5.0)
                j = CurriculumImportJob.objects.get(pk=job.pk)
                results[idx] = trigger_job_interpretation(j, wait_timeout=5.0, poll_interval=0.02)
            except Exception as exc:
                errors[idx] = exc
            finally:
                connections.close_all()

        with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=prepare_clearing_and_failing):
            t1 = threading.Thread(target=worker, args=(0,))
            t2 = threading.Thread(target=worker, args=(1,))
            t1.start()
            t2.start()
            t1.join(timeout=10.0)
            t2.join(timeout=10.0)

        assert prepare_calls == 1
        assert errors[0] is not None
        assert errors[1] is not None

        job.refresh_from_db()
        assert "Fallo interno con stage limpio" in (job.interpretation_error_message or job.error_message)
        assert job.interpretation_claim_token is None

    def test_forced_token_loss_before_final_update_raises_error_no_false_success(self):
        """Red test 3: Forced token loss before final persist.
        Owner must NOT return unpersisted local dossier (no false success);
        must raise CurriculumInterpretationError.
        """
        import uuid
        from unittest.mock import patch
        from curriculum.source_interpreter import (
            CurriculumInterpretationError,
            CurriculumSourceInterpreter,
        )
        from curriculum.views import trigger_job_interpretation

        client = tutor_client("t2-lost-token-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        real_prepare = CurriculumSourceInterpreter.prepare

        def prepare_with_token_theft(*args, **kwargs):
            res = real_prepare(*args, **kwargs)
            # Simulate external flow stealing or clearing the claim token
            CurriculumImportJob.objects.filter(pk=job.pk).update(
                interpretation_claim_token=uuid.uuid4()
            )
            return res

        with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=prepare_with_token_theft):
            with pytest.raises(CurriculumInterpretationError) as exc_info:
                trigger_job_interpretation(job)

            assert "Se perdió el reclamo de interpretación" in str(exc_info.value)

        job.refresh_from_db()
        assert not job.interpretation_dossier, "Dossier must not be persisted on lost claim"

    def test_takeover_stale_token_old_worker_rows_zero_new_worker_persists(self):
        """Takeover stale token: old worker gets rows=0 and does not overwrite, new worker persists.
        - Old worker has stale claim_token (claimed_at older than threshold).
        - New worker takes over atomically without GET.
        - New worker prepares and persists dossier.
        - Old worker final save matches rows=0, does NOT overwrite, and returns new worker's persisted dossier.
        - ABA protection: new worker's token is not cleared by old worker.
        """
        import uuid
        from datetime import timedelta
        from django.utils import timezone
        from curriculum.views import trigger_job_interpretation

        client = tutor_client("t2-stale-takeover-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        old_token = uuid.uuid4()
        stale_time = timezone.now() - timedelta(minutes=20)
        CurriculumImportJob.objects.filter(pk=job.pk).update(
            interpretation_claim_token=old_token,
            interpretation_claimed_at=stale_time,
            progress_stage="reading_pdf",
        )

        # 1. New worker triggers interpretation with 10min stale threshold -> takes over atomically
        new_dossier = trigger_job_interpretation(job, stale_threshold=timedelta(minutes=10))
        assert new_dossier is not None
        assert new_dossier.version == 1

        # 2. Database contains new worker's persisted dossier and claim is cleared
        job.refresh_from_db()
        assert job.interpretation_dossier["version"] == 1
        assert job.interpretation_claim_token is None

        # 3. Old worker tries to execute its final conditional update with old_token
        # It must match rows=0 and NOT overwrite anything in DB
        old_dossier_dict = {"version": 999, "history": [{"action": "stale_write"}]}
        rows = CurriculumImportJob.objects.filter(
            pk=job.pk,
            interpretation_claim_token=old_token,
        ).update(
            interpretation_dossier=old_dossier_dict,
        )
        assert rows == 0, "Old worker with stale token must match rows=0"

        # Verify DB was NOT overwritten
        job.refresh_from_db()
        assert job.interpretation_dossier["version"] == 1

    def test_claimant_muerto_stale_recupera(self):
        """Claimant muerto stale recupera:
        - Job has abandoned claim (stale claimed_at, no active worker).
        - Calling trigger_job_interpretation recovers by atomically replacing token and computing.
        """
        import uuid
        from datetime import timedelta
        from django.utils import timezone
        from curriculum.views import trigger_job_interpretation

        client = tutor_client("t2-dead-claimant-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        dead_token = uuid.uuid4()
        CurriculumImportJob.objects.filter(pk=job.pk).update(
            interpretation_claim_token=dead_token,
            interpretation_claimed_at=timezone.now() - timedelta(minutes=30),
            progress_stage="reading_pdf",
        )

        dossier = trigger_job_interpretation(job, stale_threshold=timedelta(minutes=10))
        assert dossier is not None
        assert dossier.version == 1

        job.refresh_from_db()
        assert job.interpretation_dossier["version"] == 1
        assert job.interpretation_claim_token is None

    def test_token_vigente_no_takeover(self):
        """Token vigente no takeover:
        - Job has an active claim (claimed_at is recent, within stale threshold).
        - Competing caller CANNOT take over; bounded waiter waits and does NOT compute.
        """
        import uuid
        from datetime import timedelta
        from unittest.mock import patch
        from django.utils import timezone
        from curriculum.source_interpreter import (
            CurriculumInterpretationError,
            CurriculumSourceInterpreter,
        )
        from curriculum.views import trigger_job_interpretation

        client = tutor_client("t2-active-token-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        active_token = uuid.uuid4()
        now_dt = timezone.now()
        CurriculumImportJob.objects.filter(pk=job.pk).update(
            interpretation_claim_token=active_token,
            interpretation_claimed_at=now_dt,
            progress_stage="reading_pdf",
        )

        # Competing caller with small wait_timeout to avoid test delay
        with patch.object(CurriculumSourceInterpreter, "prepare") as mock_prep:
            with pytest.raises(CurriculumInterpretationError) as exc_info:
                trigger_job_interpretation(
                    job,
                    wait_timeout=0.1,
                    poll_interval=0.02,
                    stale_threshold=timedelta(minutes=10),
                )
            assert "Tiempo de espera agotado" in str(exc_info.value)
            mock_prep.assert_not_called()

        # Token was not taken over
        job.refresh_from_db()
        assert job.interpretation_claim_token == active_token

    def test_ready_secuencial_no_compute(self):
        """Ready secuencial:
        - Calling trigger_job_interpretation on already interpreted job returns immediately
          without executing prepare or modifying database.
        """
        from unittest.mock import patch
        from curriculum.source_interpreter import CurriculumSourceInterpreter
        from curriculum.views import trigger_job_interpretation

        client = tutor_client("t2-ready-sec-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        # First trigger executes prepare once
        dossier1 = trigger_job_interpretation(job)
        assert dossier1 is not None

        # Sequential trigger on ready job does not compute
        with patch.object(CurriculumSourceInterpreter, "prepare") as mock_prep:
            dossier2 = trigger_job_interpretation(job)
            assert dossier2 is not None
            assert dossier2.version == 1
            mock_prep.assert_not_called()

    def test_rows_zero_with_foreign_persisted_dossier_returns_foreign_dossier(self):
        """Red test 5: rows=0 when foreign owner already persisted valid dossier returns foreign dossier."""
        from unittest.mock import patch
        from curriculum.source_interpreter import CurriculumSourceInterpreter
        from curriculum.views import trigger_job_interpretation

        client = tutor_client("t2-foreign-dossier-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        real_prepare = CurriculumSourceInterpreter.prepare

        def prepare_with_foreign_persist(*args, **kwargs):
            res = real_prepare(*args, **kwargs)
            foreign_dossier = real_prepare(*args, **kwargs)
            # Mutate to distinguish foreign dossier
            foreign_dict = foreign_dossier.to_dict()
            foreign_dict["version"] = 99
            foreign_dict["history"].append({"action": "foreign_save", "version": 99})
            CurriculumImportJob.objects.filter(pk=job.pk).update(
                interpretation_dossier=foreign_dict,
                interpretation_claim_token=None,
                interpretation_claimed_at=None,
            )
            return res

        with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=prepare_with_foreign_persist):
            returned_dossier = trigger_job_interpretation(job)

        assert returned_dossier is not None
        assert returned_dossier.version == 99, "Must return foreign persisted dossier from DB"

        job.refresh_from_db()
        assert job.interpretation_dossier["version"] == 99

    def test_migration_0036_consistency_check(self):
        """Red test 6: Verify migration 0036 depends on 0035 and no pending migrations exist."""
        from django.core.management import call_command
        import io

        out = io.StringIO()
        call_command("makemigrations", "--check", "--dry-run", stdout=out)
        output = out.getvalue()
        assert "No changes detected" in output or not output.strip()

    def test_retry_under_atomic_transaction_preserves_usable_connection_no_programming_error(self):
        """TDD: Calling _execute_with_db_lock_retry inside transaction.atomic()
        with transient OperationalError must NOT close connection when in_atomic_block.
        The transaction must remain usable for subsequent queries and writes.
        """
        from unittest.mock import patch
        from django.db import connection, transaction
        from django.db.utils import OperationalError
        from curriculum.views import _execute_with_db_lock_retry

        client = tutor_client("t2-atomic-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        attempts = 0

        def flaky_query():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OperationalError("database is locked")
            return CurriculumImportJob.objects.filter(pk=job.pk).count()

        with patch.object(connection, "close", wraps=connection.close) as mock_close:
            with transaction.atomic():
                res = _execute_with_db_lock_retry(flaky_query)
                assert res == 1
                assert attempts == 2
                # CRITICAL: connection.close() must NEVER be called while in an atomic block
                mock_close.assert_not_called()

                # Subsequent query/write in the same transaction block must succeed
                # without django.db.utils.ProgrammingError: Cannot operate on a closed database.
                job.error_message = "transacción-activa-ok"
                job.save(update_fields=["error_message", "updated_at"])

                fresh_count = CurriculumImportJob.objects.filter(pk=job.pk, error_message="transacción-activa-ok").count()
                assert fresh_count == 1

        job.refresh_from_db()
        assert job.error_message == "transacción-activa-ok"

        # Safe cleanup outside atomic: connection.close() IS called between retries
        attempts_out = 0

        def flaky_outside():
            nonlocal attempts_out
            attempts_out += 1
            if attempts_out == 1:
                raise OperationalError("database is locked")
            return 99

        with patch.object(connection, "close", wraps=connection.close) as mock_close_outside:
            assert _execute_with_db_lock_retry(flaky_outside) == 99
            assert attempts_out == 2
            assert mock_close_outside.called, "Outside atomic, connection.close() must be called to refresh lock"

    def test_file_based_sqlite_atomic_retry_prevents_programming_error(self):
        """Exact Luna probe: on a real file-based SQLite database (is_in_memory_db() is False),
        calling _execute_with_db_lock_retry inside transaction.atomic() must NOT close
        the database connection, which would cause ProgrammingError: Cannot operate on a closed database.
        """
        import os
        import subprocess
        import sys

        probe_code = """
import os, tempfile, django
django.setup()
from django.db import connection, transaction
from django.db.utils import OperationalError
from curriculum.views import _execute_with_db_lock_retry

with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as f:
    db_path = f.name

connection.close()
connection.settings_dict['NAME'] = db_path

try:
    with connection.cursor() as cur:
        cur.execute('CREATE TABLE probe (id INT PRIMARY KEY, val TEXT);')

    attempts = 0
    def flaky_action():
        global attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError('database table is locked')
        with connection.cursor() as cur:
            cur.execute("INSERT INTO probe VALUES (1, 'saved-in-atomic');")
        return True

    with transaction.atomic():
        _execute_with_db_lock_retry(flaky_action)
        with connection.cursor() as cur:
            cur.execute('SELECT val FROM probe WHERE id=1;')
            assert cur.fetchone() == ('saved-in-atomic',)

    with connection.cursor() as cur:
        cur.execute('SELECT val FROM probe WHERE id=1;')
        assert cur.fetchone() == ('saved-in-atomic',)
finally:
    connection.close()
    if os.path.exists(db_path):
        os.unlink(db_path)
"""
        result = subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True,
            text=True,
            env={"DJANGO_SETTINGS_MODULE": "aulalista.settings", **dict(os.environ)},
        )
        assert result.returncode == 0, f"Probe failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"

    def test_permanent_lock_is_not_masked_and_raises(self):
        """Permanent database lock must NOT be swallowed or hidden; raises OperationalError."""
        from django.db.utils import OperationalError
        from curriculum.views import _execute_with_db_lock_retry

        def permanently_locked():
            raise OperationalError("database is locked")

        with pytest.raises(OperationalError) as exc_info:
            _execute_with_db_lock_retry(permanently_locked, max_attempts=3, base_delay=0.001, max_delay=0.005)
        assert "locked" in str(exc_info.value).lower()

    def test_trigger_job_interpretation_inside_atomic_remains_usable_afterwards(self):
        """TDD: trigger_job_interpretation wrapped in transaction.atomic()
        completes and caller can continue querying/writing without ProgrammingError.
        """
        from django.db import transaction
        from curriculum.views import trigger_job_interpretation

        client = tutor_client("t2-atomic-trigger-user")
        job = CurriculumImportJob.objects.create(
            created_by=client.user if hasattr(client, "user") else None,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        with transaction.atomic():
            dossier = trigger_job_interpretation(job)
            assert dossier is not None
            assert dossier.version == 1

            # Caller continues in the same transaction:
            job.error_message = "caller-atomic-write-confirmed"
            job.save(update_fields=["error_message", "updated_at"])
            count = CurriculumImportJob.objects.filter(pk=job.pk, error_message="caller-atomic-write-confirmed").count()
            assert count == 1

        job.refresh_from_db()
        assert job.error_message == "caller-atomic-write-confirmed"


def _model_field_snapshot(instance):
    """Capture snapshot of all database column values of a model instance."""
    instance.refresh_from_db()
    return {
        field.name: getattr(instance, field.name)
        for field in instance._meta.fields
    }


def _tutor_client_and_user(username):
    from django.contrib.auth import get_user_model
    client = tutor_client(username)
    user = get_user_model().objects.get(pk=int(client.session["_auth_user_id"]))
    return client, user


class TestTask2GetWaitStatusNoMutation(TransactionTestCase):
    """B2 validation: GET wait/status are pure read operations that never mutate persistence.

    Contracts verified:
    - Stale job with progress_stage='reading_pdf', claim_token and timestamps:
      GET wait (2x) and GET status (2x) leave DB snapshot 100% byte/field identical.
    - Responses report derived error state with honest message without modifying DB.
    - Claim token and claimed_at remain intact in DB (no release by GET).
    - Neither save() nor update() is ever called during GET wait/status.
    - Repeated status calls produce deterministic JSON.
    - Repeated wait calls produce identical HTML (excluding dynamic CSRF token).
    - Ready path and organizing normal path retain labels/redirects without mutating DB.
    - Other teacher receives 404 with zero DB mutation.
    """

    def test_stale_reading_pdf_get_wait_twice_does_not_mutate_persistence_and_shows_derived_error(self):
        """Stale job GET wait (2x): DB snapshot remains 100% identical; derived error rendered."""
        import re
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b2-wait-teacher")
        stale_time = timezone.now() - timedelta(minutes=120)
        claim_token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=stale_time,
            interpretation_claim_token=claim_token,
            interpretation_claimed_at=stale_time,
        )

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        snapshot_initial = _model_field_snapshot(job)

        # First GET
        resp1 = client.get(wait_url)
        assert resp1.status_code == 200
        html1 = resp1.content.decode("utf-8")
        assert "Estamos organizando tu planeación" in html1
        assert "Está tardando más de lo esperado; aún puede terminar" in html1
        assert 'data-assistant-state="delayed"' in html1
        assert "se detuvo" not in html1
        assert '<p class="error" role="alert">' not in html1

        snapshot_after_1 = _model_field_snapshot(job)
        assert snapshot_after_1 == snapshot_initial, "First GET wait mutated database fields!"

        # Second GET (meta-refresh / reload simulation)
        resp2 = client.get(wait_url)
        assert resp2.status_code == 200
        html2 = resp2.content.decode("utf-8")

        # HTML is byte-identical excluding dynamic CSRF token
        strip_csrf = lambda h: re.sub(r'name="csrfmiddlewaretoken" value="[^"]*"', '', h)
        assert strip_csrf(html1) == strip_csrf(html2)

        snapshot_after_2 = _model_field_snapshot(job)
        assert snapshot_after_2 == snapshot_initial, "Second GET wait mutated database fields!"

        # Specific field verification: claim token and progress stage intact
        job.refresh_from_db()
        assert job.progress_stage == "reading_pdf"
        assert job.interpretation_claim_token == claim_token
        assert job.interpretation_claimed_at == stale_time
        assert job.progress_finished_at is None
        assert job.error_message == ""
        assert not job.interpretation_dossier

    def test_stale_reading_pdf_get_status_twice_does_not_mutate_persistence_and_returns_derived_json(self):
        """Stale job GET status (2x): DB snapshot remains 100% identical; deterministic JSON."""
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b2-status-teacher")
        stale_time = timezone.now() - timedelta(minutes=120)
        claim_token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=stale_time,
            interpretation_claim_token=claim_token,
            interpretation_claimed_at=stale_time,
        )

        status_url = reverse("tutor-import-status", args=[job.pk])
        snapshot_initial = _model_field_snapshot(job)

        # First GET
        resp1 = client.get(status_url)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["state"] == "delayed"
        assert data1["label"] == "Está tardando más de lo esperado; aún puede terminar"
        assert data1["error"] == ""
        assert data1["stage"] == "reading_pdf"
        assert data1["finished_at"] is not None

        snapshot_after_1 = _model_field_snapshot(job)
        assert snapshot_after_1 == snapshot_initial, "First GET status mutated database fields!"

        # Second GET (polling simulation)
        resp2 = client.get(status_url)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data1 == data2, "Repeated GET status responses must be deterministic!"

        snapshot_after_2 = _model_field_snapshot(job)
        assert snapshot_after_2 == snapshot_initial, "Second GET status mutated database fields!"

        # Claim token remains intact in DB
        job.refresh_from_db()
        assert job.interpretation_claim_token == claim_token
        assert job.progress_stage == "reading_pdf"

    def test_model_save_and_update_never_called_on_get_wait_and_status(self):
        """Seam verification: CurriculumImportJob.save() is never called during GET wait/status."""
        import uuid
        from datetime import timedelta
        from unittest.mock import patch
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b2-spy-teacher")
        stale_time = timezone.now() - timedelta(minutes=120)
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=stale_time,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=stale_time,
        )

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        status_url = reverse("tutor-import-status", args=[job.pk])

        with patch.object(CurriculumImportJob, "save") as mock_save:
            client.get(wait_url)
            client.get(status_url)
            mock_save.assert_not_called()

    def test_ready_job_get_wait_and_status_do_not_mutate_and_retain_labels(self):
        """Ready job with interpretation dossier: GET wait and status retain labels and do not mutate DB."""
        client, user = _tutor_client_and_user("t2-b2-ready-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            page_count=5,
        )

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        status_url = reverse("tutor-import-status", args=[job.pk])
        snapshot_initial = _model_field_snapshot(job)

        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html_wait = resp_wait.content.decode("utf-8")
        assert "Estamos organizando tu planeación" in html_wait
        assert "Revisar planeación" in html_wait
        interp_url = reverse("tutor-import-interpretation", args=[job.pk])
        assert interp_url in html_wait

        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data_status = resp_status.json()
        assert data_status["state"] == "finished"
        assert data_status["label"] == "Planeación organizada/lista para revisar"
        assert data_status["redirect_url"] == interp_url

        snapshot_after = _model_field_snapshot(job)
        assert snapshot_after == snapshot_initial, "Ready GET mutated database fields!"

    def test_organizing_normal_get_wait_and_status_do_not_mutate_and_retain_labels(self):
        """Active non-stale job: GET wait and status retain normal labels and do not mutate DB."""
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b2-normal-teacher")
        recent_time = timezone.now() - timedelta(minutes=2)
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=recent_time,
        )

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        status_url = reverse("tutor-import-status", args=[job.pk])
        snapshot_initial = _model_field_snapshot(job)

        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html_wait = resp_wait.content.decode("utf-8")
        assert "Estamos organizando tu planeación" in html_wait
        assert "Esperando al asistente" in html_wait
        assert 'data-assistant-state="waiting"' in html_wait

        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data_status = resp_status.json()
        assert data_status["state"] == "waiting"
        assert data_status["label"] == "Esperando al asistente"
        assert data_status["stage"] == "reading_pdf"

        snapshot_after = _model_field_snapshot(job)
        assert snapshot_after == snapshot_initial, "Normal organizing GET mutated database fields!"

    def test_other_teacher_get_wait_and_status_returns_404_no_mutation(self):
        """Other teacher GET wait and status returns 404 and does not mutate owner's job."""
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        owner_client, owner_user = _tutor_client_and_user("t2-b2-owner-teacher")
        stale_time = timezone.now() - timedelta(minutes=120)
        job = CurriculumImportJob.objects.create(
            created_by=owner_user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=stale_time,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=stale_time,
        )

        other_client = tutor_client("t2-b2-stranger-teacher")
        wait_url = reverse("tutor-import-wait", args=[job.pk])
        status_url = reverse("tutor-import-status", args=[job.pk])
        snapshot_initial = _model_field_snapshot(job)

        resp_wait = other_client.get(wait_url)
        assert resp_wait.status_code == 404

        resp_status = other_client.get(status_url)
        assert resp_status.status_code == 404

        snapshot_after = _model_field_snapshot(job)
        assert snapshot_after == snapshot_initial, "Unauthorized GET mutated database fields!"

    def test_b2_active_claim_with_empty_stage_derives_waiting_and_does_not_redirect_to_detail(self):
        """B2-2: Active claim token + empty dossier + progress_stage='' derives waiting; wait does not redirect to detail."""
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b22-active-teacher")
        recent_time = timezone.now() - timedelta(minutes=1)
        claim_token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="",
            interpretation_claim_token=claim_token,
            interpretation_claimed_at=recent_time,
            error_message="",
        )

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        status_url = reverse("tutor-import-status", args=[job.pk])
        snapshot_initial = _model_field_snapshot(job)

        # GET status must report waiting, never finished
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data_status = resp_status.json()
        assert data_status["state"] == "waiting"
        assert data_status["label"] == "Esperando al asistente"
        assert data_status["stage"] == ""
        assert data_status["finished_at"] is None
        assert data_status["started_at"] == recent_time.isoformat()

        # GET wait must render waiting shell, NEVER 302 redirect to detail
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html_wait = resp_wait.content.decode("utf-8")
        assert "Estamos organizando tu planeación" in html_wait
        assert 'data-assistant-state="waiting"' in html_wait
        assert reverse("tutor-import-detail", args=[job.pk]) not in resp_wait.get("Location", "")

        # Pure read: zero mutation
        snapshot_after = _model_field_snapshot(job)
        assert snapshot_after == snapshot_initial, "Active claim GET mutated database fields!"

    def test_b2_naive_and_none_timestamps_normalized_without_type_error(self):
        """B2-3: Naive datetimes and None timestamps are safely normalized without TypeError."""
        from datetime import datetime
        from django.utils import timezone
        from curriculum.views import _is_import_stage_stale, _get_derived_import_presentation

        client, user = _tutor_client_and_user("t2-b23-naive-teacher")
        naive_started = datetime(2026, 9, 12, 10, 0, 0)
        naive_claimed = datetime(2026, 9, 12, 10, 0, 0)
        naive_finished = datetime(2026, 9, 12, 10, 5, 0)

        job_naive = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
        )
        job_naive.progress_started_at = naive_started
        job_naive.interpretation_claimed_at = naive_claimed
        job_naive.progress_finished_at = naive_finished

        # Direct function calls with naive datetimes and naive now
        assert not _is_import_stage_stale(job_naive, now=datetime(2026, 9, 12, 10, 10, 0))
        assert _is_import_stage_stale(job_naive, now=datetime(2026, 9, 12, 12, 0, 0))

        pres = _get_derived_import_presentation(job_naive)
        assert pres["state"] in ("waiting", "delayed", "working")
        assert timezone.is_aware(pres["finished_at"])

        # Endpoints execute cleanly
        resp_status = client.get(reverse("tutor-import-status", args=[job_naive.pk]))
        assert resp_status.status_code == 200
        resp_wait = client.get(reverse("tutor-import-wait", args=[job_naive.pk]))
        assert resp_wait.status_code == 200

        # None timestamps handled robustly
        job_none = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=None,
            interpretation_claimed_at=None,
            progress_finished_at=None,
        )
        assert not _is_import_stage_stale(job_none)
        pres_none = _get_derived_import_presentation(job_none)
        assert pres_none["finished_at"] is None
        assert pres_none["state"] == "waiting"

    def test_b2_stale_delayed_does_not_assert_stopped_and_does_not_show_retry_button(self):
        """B2-1: Stale stage/claim derives delayed state with honest message and no retry prompt."""
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b21-delayed-teacher")
        stale_time = timezone.now() - timedelta(minutes=120)
        claim_token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=stale_time,
            interpretation_claim_token=claim_token,
            interpretation_claimed_at=stale_time,
            error_message="",
        )

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        status_url = reverse("tutor-import-status", args=[job.pk])

        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "delayed"
        assert data["label"] == "Está tardando más de lo esperado; aún puede terminar"
        assert data["error"] == ""

        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html = resp_wait.content.decode("utf-8")
        assert "Está tardando más de lo esperado; aún puede terminar" in html
        assert 'data-assistant-state="delayed"' in html
        assert "se detuvo" not in html
        assert '<p class="error" role="alert">' not in html

    def test_b2_real_cancellation_signal_derives_error(self):
        """B2-1: Real cancellation signals (cancel_requested / cancelled_at) derive error state."""
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b21-cancel-teacher")
        now = timezone.now()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            cancel_requested=True,
            cancelled_at=now,
            interpretation_error_message="Cancelado por el docente.",
        )

        status_url = reverse("tutor-import-status", args=[job.pk])
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "error"
        assert data["error"] == "Cancelado por el docente."

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html = resp_wait.content.decode("utf-8")
        assert "Cancelado por el docente." in html

    def test_b2_dossier_present_derives_ready_even_with_residual_claim_token(self):
        """B2-2: Dossier present derives ready/finished even if residual claim token is present."""
        import uuid

        client, user = _tutor_client_and_user("t2-b22-dossier-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_claim_token=uuid.uuid4(),
        )

        status_url = reverse("tutor-import-status", args=[job.pk])
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "finished"
        assert data["label"] == "Planeación organizada/lista para revisar"
        assert data["redirect_url"] == reverse("tutor-import-interpretation", args=[job.pk])

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html = resp_wait.content.decode("utf-8")
        assert "Revisar planeación" in html

    def test_exact_luna_probe_stale_reading_pdf_before_after_equality_including_updated_at(self):
        """Exact Luna probe verification:
        In Luna review B2:
          before=('reading_pdf', None, '')
          after=('', <timestamp>, 'El asistente virtual tardó demasiado...')
        Here we assert that GET wait and GET status in ANY order leave:
          after == before (100% equality including updated_at),
        while HTML and JSON render derived, coherent recovery presentation.
        """
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b2-exact-luna-teacher")
        stale_time = timezone.now() - timedelta(minutes=120)
        claim_token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=stale_time,
            interpretation_claim_token=claim_token,
            interpretation_claimed_at=stale_time,
            error_message="",
        )

        job.refresh_from_db()
        before_tuple = (job.progress_stage, job.progress_finished_at, job.error_message, job.updated_at)
        snapshot_before = _model_field_snapshot(job)

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        status_url = reverse("tutor-import-status", args=[job.pk])

        # Execute requests in mixed order: wait -> status -> status -> wait
        r_wait1 = client.get(wait_url)
        assert r_wait1.status_code == 200
        html1 = r_wait1.content.decode("utf-8")
        assert "Está tardando más de lo esperado" in html1
        assert "Estamos organizando tu planeación" in html1

        r_status1 = client.get(status_url)
        assert r_status1.status_code == 200
        j1 = r_status1.json()
        assert j1["state"] == "delayed"
        assert j1["stage"] == "reading_pdf"
        assert "Está tardando más de lo esperado" in j1["label"]

        r_status2 = client.get(status_url)
        assert r_status2.status_code == 200
        assert r_status1.json() == r_status2.json()

        r_wait2 = client.get(wait_url)
        assert r_wait2.status_code == 200

        # After all GETs: verify absolute DB equality, including updated_at
        job.refresh_from_db()
        after_tuple = (job.progress_stage, job.progress_finished_at, job.error_message, job.updated_at)
        snapshot_after = _model_field_snapshot(job)

        assert after_tuple == before_tuple, f"Tuple mutated! Before: {before_tuple}, After: {after_tuple}"
        assert snapshot_after == snapshot_before, "Database fields mutated during GET requests!"

    def test_pure_derived_presentation_helper_deterministic_with_injected_now(self):
        """Pure query helper is deterministic, does not mutate instance, and accepts injected now."""
        from datetime import timedelta
        from django.utils import timezone
        from curriculum.views import (
            _get_derived_import_presentation,
            _is_import_stage_stale,
            IMPORT_STAGE_TIMEOUT,
            STALE_STAGE_DELAYED_MESSAGE,
        )

        fixed_start = timezone.now() - timedelta(hours=2)
        job = CurriculumImportJob(
            progress_stage="reading_pdf",
            progress_started_at=fixed_start,
            interpretation_claim_token="fake-claim-token",
            interpretation_claimed_at=fixed_start,
            error_message="",
        )

        # 1. Injected now before timeout -> not stale
        now_fresh = fixed_start + IMPORT_STAGE_TIMEOUT - timedelta(seconds=10)
        assert not _is_import_stage_stale(job, now=now_fresh)
        pres_fresh = _get_derived_import_presentation(job, now=now_fresh)
        assert pres_fresh["is_stale"] is False
        assert pres_fresh["state"] == "waiting"
        assert pres_fresh["label"] == "Esperando al asistente"

        # 2. Injected now after timeout -> stale / delayed
        now_stale = fixed_start + IMPORT_STAGE_TIMEOUT + timedelta(seconds=10)
        assert _is_import_stage_stale(job, now=now_stale)
        pres_stale = _get_derived_import_presentation(job, now=now_stale)
        assert pres_stale["is_stale"] is True
        assert pres_stale["state"] == "delayed"
        assert pres_stale["label"] == STALE_STAGE_DELAYED_MESSAGE
        assert pres_stale["finished_at"] == fixed_start + IMPORT_STAGE_TIMEOUT

        # 3. Instance remains 100% unmutated
        assert job.progress_stage == "reading_pdf"
        assert job.progress_started_at == fixed_start
        assert job.error_message == ""
        assert job.progress_finished_at is None

    def test_b2c_valid_dossier_with_active_claim_derives_ready_and_no_mutation(self):
        """T2-B2c: Valid dossier + active claim derives ready/finished, offering review, no mutation."""
        import uuid
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b2c-active-teacher")
        now = timezone.now()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=now,
        )

        snapshot_before = _model_field_snapshot(job)

        status_url = reverse("tutor-import-status", args=[job.pk])
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "finished"
        assert data["label"] == "Planeación organizada/lista para revisar"
        assert data["redirect_url"] == reverse("tutor-import-interpretation", args=[job.pk])

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html = resp_wait.content.decode("utf-8")
        assert "Revisar planeación" in html
        assert 'id="review-planning-btn"' in html
        assert reverse("tutor-import-interpretation", args=[job.pk]) in html

        snapshot_after = _model_field_snapshot(job)
        assert snapshot_after == snapshot_before, "Database mutated during GET wait/status with active claim!"

    def test_b2c_valid_dossier_with_stale_claim_and_stale_stage_derives_ready_and_no_mutation(self):
        """T2-B2c blocker resolution: Valid dossier + stale claim + stale stage derives ready, not delayed."""
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b2c-stale-teacher")
        stale_time = timezone.now() - timedelta(minutes=120)
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=stale_time,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=stale_time,
            error_message="",
        )

        snapshot_before = _model_field_snapshot(job)

        # GET status must derive 'finished' (not 'delayed') and point to interpretation
        status_url = reverse("tutor-import-status", args=[job.pk])
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "finished"
        assert data["label"] == "Planeación organizada/lista para revisar"
        assert data["redirect_url"] == reverse("tutor-import-interpretation", args=[job.pk])

        # GET wait must render review button and URL (not delayed notice)
        wait_url = reverse("tutor-import-wait", args=[job.pk])
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html = resp_wait.content.decode("utf-8")
        assert "Revisar planeación" in html
        assert 'id="review-planning-btn"' in html
        assert reverse("tutor-import-interpretation", args=[job.pk]) in html
        assert "Está tardando más de lo esperado" not in html

        # Persistence remains 100% byte-identical, no cleanup during GET
        snapshot_after = _model_field_snapshot(job)
        assert snapshot_after == snapshot_before, "Database mutated during GET wait/status with stale claim!"

    def test_b2c_valid_dossier_with_residual_error_message_derives_ready(self):
        """T2-B2c: Valid dossier + residual error_message derives ready, preserves error_message in DB."""
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b2c-error-teacher")
        stale_time = timezone.now() - timedelta(minutes=120)
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=stale_time,
            error_message="Worker timeout anterior no limpiado.",
        )

        snapshot_before = _model_field_snapshot(job)

        # Presentation derives finished and suppresses residual error in UI
        status_url = reverse("tutor-import-status", args=[job.pk])
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "finished"
        assert data["error"] == ""
        assert data["redirect_url"] == reverse("tutor-import-interpretation", args=[job.pk])

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html = resp_wait.content.decode("utf-8")
        assert "Revisar planeación" in html
        assert 'id="review-planning-btn"' in html

        # Persistence maintains the error_message in DB unmutated
        snapshot_after = _model_field_snapshot(job)
        assert snapshot_after == snapshot_before
        job.refresh_from_db()
        assert job.error_message == "Worker timeout anterior no limpiado."

    def test_b2c_corrupt_non_deserializable_dossier_does_not_derive_ready_and_no_500(self):
        """T2-B2c: Corrupt/non-deserializable dossier does not derive ready and NEVER causes HTTP 500."""
        from helpers import MINIMAL_VALID_PDF_BYTES

        client, user = _tutor_client_and_user("t2-b2c-corrupt-teacher")

        # Test corrupt payloads: invalid type, missing version, non-dict
        corrupt_payloads = [
            "corrupt string",
            {"version": "invalid_not_an_int"},
            {"version": 0},
            {"general_fields": "not-a-dict"},
            {"sessions": ["not-a-dict"]},
        ]

        for idx, payload in enumerate(corrupt_payloads):
            job = CurriculumImportJob.objects.create(
                created_by=user,
                pdf=SimpleUploadedFile(f"c_{idx}.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf"),
                status=CurriculumImportJob.STATUS_UPLOADED,
                interpretation_dossier=payload,
            )

            status_url = reverse("tutor-import-status", args=[job.pk])
            resp_status = client.get(status_url)
            assert resp_status.status_code == 200, f"Payload {idx} caused status code {resp_status.status_code}"
            data = resp_status.json()
            assert data["state"] != "finished", f"Corrupt payload {idx} derived finished!"
            assert data["redirect_url"] == reverse("tutor-import-wait", args=[job.pk])

            wait_url = reverse("tutor-import-wait", args=[job.pk])
            resp_wait = client.get(wait_url)
            assert resp_wait.status_code in (200, 302), f"Payload {idx} caused wait code {resp_wait.status_code}"
            if resp_wait.status_code == 200:
                html = resp_wait.content.decode("utf-8")
                assert "Revisar planeación" not in html
                assert 'id="review-planning-btn"' not in html

    def test_b2c_tampered_source_pdf_with_valid_dossier_does_not_derive_ready(self):
        """T2-B2c: Valid dossier whose source PDF SHA does not match file does not derive ready."""
        client, user = _tutor_client_and_user("t2-b2c-tampered-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_dossier={
                "version": 1,
                "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                "history": [{"action": "prepare"}],
            },
        )

        status_url = reverse("tutor-import-status", args=[job.pk])
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "error"
        assert "alterado" in data["error"] or "integridad" in data["error"]
        assert data["redirect_url"] == reverse("tutor-import-wait", args=[job.pk])

        wait_url = reverse("tutor-import-wait", args=[job.pk])
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html = resp_wait.content.decode("utf-8")
        assert "Revisar planeación" not in html
        assert 'id="review-planning-btn"' not in html

    def test_b2c_empty_dossier_maintains_delayed_and_working_rules(self):
        """T2-B2c: Empty dossier maintains delayed, working, waiting rules, never ready prematurely."""
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b2c-empty-teacher")
        now = timezone.now()

        # 1. Fresh claim + empty dossier -> waiting
        job_fresh = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier={},
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=now,
        )
        r_status = client.get(reverse("tutor-import-status", args=[job_fresh.pk]))
        assert r_status.json()["state"] == "waiting"
        assert r_status.json()["redirect_url"] == reverse("tutor-import-wait", args=[job_fresh.pk])
        r_wait = client.get(reverse("tutor-import-wait", args=[job_fresh.pk]))
        assert "Revisar planeación" not in r_wait.content.decode("utf-8")

        # 2. Stale claim + empty dossier -> delayed
        stale_time = now - timedelta(minutes=120)
        job_stale = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier={},
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=stale_time,
        )
        r_status_stale = client.get(reverse("tutor-import-status", args=[job_stale.pk]))
        assert r_status_stale.json()["state"] == "delayed"
        assert r_status_stale.json()["redirect_url"] == reverse("tutor-import-wait", args=[job_stale.pk])
        r_wait_stale = client.get(reverse("tutor-import-wait", args=[job_stale.pk]))
        assert "Está tardando más de lo esperado" in r_wait_stale.content.decode("utf-8")
        assert "Revisar planeación" not in r_wait_stale.content.decode("utf-8")

    def test_luna_table_exact_label_equality_across_all_four_states(self):
        """Luna table TDD: HTML #assistant-status-label and JSON status label are 100% equal across all 4 states."""
        import re
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-luna-table-teacher")
        now = timezone.now()

        def extract_html_label(html_str):
            m = re.search(r'<p id="assistant-status-label">\s*([^<]+?)\s*</p>', html_str)
            assert m, f"#assistant-status-label not found in HTML:\n{html_str[:400]}"
            return m.group(1).strip()

        # 1. State: stale/delayed
        stale_time = now - timedelta(minutes=120)
        job_stale = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=stale_time,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=stale_time,
        )
        snap_stale_before = _model_field_snapshot(job_stale)
        r_wait_stale = client.get(reverse("tutor-import-wait", args=[job_stale.pk]))
        r_status_stale = client.get(reverse("tutor-import-status", args=[job_stale.pk]))
        label_html_stale = extract_html_label(r_wait_stale.content.decode("utf-8"))
        label_json_stale = r_status_stale.json()["label"]
        assert label_html_stale == label_json_stale == "Está tardando más de lo esperado; aún puede terminar"
        assert _model_field_snapshot(job_stale) == snap_stale_before

        # 2. State: normal/waiting
        recent_time = now - timedelta(minutes=2)
        job_normal = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="reading_pdf",
            progress_started_at=recent_time,
        )
        snap_normal_before = _model_field_snapshot(job_normal)
        r_wait_normal = client.get(reverse("tutor-import-wait", args=[job_normal.pk]))
        r_status_normal = client.get(reverse("tutor-import-status", args=[job_normal.pk]))
        label_html_normal = extract_html_label(r_wait_normal.content.decode("utf-8"))
        label_json_normal = r_status_normal.json()["label"]
        assert label_html_normal == label_json_normal == "Esperando al asistente"
        assert _model_field_snapshot(job_normal) == snap_normal_before

        # 3. State: ready/finished
        job_ready = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            page_count=5,
        )
        snap_ready_before = _model_field_snapshot(job_ready)
        r_wait_ready = client.get(reverse("tutor-import-wait", args=[job_ready.pk]))
        r_status_ready = client.get(reverse("tutor-import-status", args=[job_ready.pk]))
        label_html_ready = extract_html_label(r_wait_ready.content.decode("utf-8"))
        label_json_ready = r_status_ready.json()["label"]
        assert label_html_ready == label_json_ready == "Planeación organizada/lista para revisar"
        assert _model_field_snapshot(job_ready) == snap_ready_before

        # 4. State: error
        job_error = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            progress_stage="",
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
            interpretation_error_message="Error persistido de prueba",
            error_message="Error persistido de prueba",
        )
        snap_error_before = _model_field_snapshot(job_error)
        r_wait_error = client.get(reverse("tutor-import-wait", args=[job_error.pk]))
        r_status_error = client.get(reverse("tutor-import-status", args=[job_error.pk]))
        label_html_error = extract_html_label(r_wait_error.content.decode("utf-8"))
        label_json_error = r_status_error.json()["label"]
        assert label_html_error == label_json_error == "La generación se interrumpió"
        assert _model_field_snapshot(job_error) == snap_error_before

    def test_b2d_luna_invalid_matrix_never_ready_or_500(self):
        """T2-B2d: Exact Luna matrix: empty, corrupt, version0, inactive, sha missing/wrong,
        invalidated, missing file, no-pdf, tamper => never ready, redirect to detail, no 500.
        """
        import hashlib
        from pathlib import Path
        from helpers import MINIMAL_VALID_PDF_BYTES

        client, user = _tutor_client_and_user("t2-b2d-matrix-teacher")
        c01_sha = hashlib.sha256(C01_PATH.read_bytes()).hexdigest()
        other_sha = hashlib.sha256(MINIMAL_VALID_PDF_BYTES).hexdigest()

        def make_raw(*, sha=c01_sha, version=1, status="active"):
            return {
                "source_sha256": sha,
                "source_name": "prueba-semana-01.pdf",
                "page_count": 5,
                "version": version,
                "status": status,
                "history": [{"action": "prepare"}],
            }

        cases = [
            ("empty", {}),
            ("corrupt", "not-a-dict"),
            ("version-invalid", make_raw(version=0)),
            ("inactive", make_raw(status="inactive")),
            ("sha-missing", make_raw(sha="")),
            ("sha-wrong", make_raw(sha=other_sha)),
            ("tampered-status", make_raw(status="invalidated_source_tampered")),
            ("missing-file", make_raw()),
        ]

        for name, dossier in cases:
            job = CurriculumImportJob.objects.create(
                created_by=user,
                pdf=_c01_upload(),
                status=CurriculumImportJob.STATUS_UPLOADED,
                interpretation_dossier=dossier,
            )
            if name == "missing-file":
                Path(job.pdf.path).unlink()

            snap_before = _model_field_snapshot(job)
            status_resp = client.get(reverse("tutor-import-status", args=[job.pk]))
            assert status_resp.status_code == 200, f"Case {name} returned status {status_resp.status_code}"
            payload = status_resp.json()
            assert payload["state"] != "finished", f"Case {name} derived finished!"
            assert payload["redirect_url"] == reverse("tutor-import-wait", args=[job.pk])

            wait_resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
            assert wait_resp.status_code in (200, 302), f"Case {name} returned wait {wait_resp.status_code}"
            if wait_resp.status_code == 200:
                html = wait_resp.content.decode("utf-8")
                assert "review-planning-btn" not in html, f"Case {name} showed review button!"
                assert "Revisar planeación" not in html
            assert _model_field_snapshot(job) == snap_before

        # Case: no-pdf
        no_pdf_job = CurriculumImportJob.objects.create(
            created_by=user,
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=make_raw(),
        )
        status_resp = client.get(reverse("tutor-import-status", args=[no_pdf_job.pk]))
        assert status_resp.status_code == 200
        assert status_resp.json()["state"] != "finished"
        assert status_resp.json()["redirect_url"] == reverse("tutor-import-wait", args=[no_pdf_job.pk])
        wait_resp = client.get(reverse("tutor-import-wait", args=[no_pdf_job.pk]))
        assert wait_resp.status_code in (200, 302)
        if wait_resp.status_code == 200:
            assert "review-planning-btn" not in wait_resp.content.decode("utf-8")

        # Case: tampered file bytes on disk
        tampered_job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_dossier=make_raw(),
        )
        Path(tampered_job.pdf.path).write_bytes(b"tampered source bytes")
        status_resp = client.get(reverse("tutor-import-status", args=[tampered_job.pk]))
        assert status_resp.status_code == 200
        assert status_resp.json()["state"] == "error"
        assert status_resp.json()["redirect_url"] == reverse("tutor-import-wait", args=[tampered_job.pk])
        wait_resp = client.get(reverse("tutor-import-wait", args=[tampered_job.pk]))
        assert wait_resp.status_code == 200
        assert "review-planning-btn" not in wait_resp.content.decode("utf-8")

    def test_b2d_runtime_error_and_operational_error_propagate_not_hidden(self):
        """T2-B2d: get_interpretation_dossier and _is_valid_ready_interpretation_dossier
        propagate RuntimeError and OperationalError without swallowing them.
        """
        import pytest
        from unittest.mock import patch
        from django.db import OperationalError
        from curriculum.views import _is_valid_ready_interpretation_dossier

        _, user = _tutor_client_and_user("t2-b2d-errors-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        )

        # 1. RuntimeError must propagate
        with patch("curriculum.source_interpreter.ImportDossier.from_dict", side_effect=RuntimeError("programming-sentinel")):
            with pytest.raises(RuntimeError, match="programming-sentinel"):
                job.get_interpretation_dossier()
            with pytest.raises(RuntimeError, match="programming-sentinel"):
                _is_valid_ready_interpretation_dossier(job)

        # 2. OperationalError must propagate
        with patch("curriculum.source_interpreter.ImportDossier.from_dict", side_effect=OperationalError("db-sentinel")):
            with pytest.raises(OperationalError, match="db-sentinel"):
                job.get_interpretation_dossier()
            with pytest.raises(OperationalError, match="db-sentinel"):
                _is_valid_ready_interpretation_dossier(job)


class TestTask2B3InterpretationContract:
    """TDD for Task 2 - B3 contract: `uploaded` vs `interpretation_state` ready.

    Contracts:
    - CurriculumImportJob.status continues governing legacy topics/subtopics/completed.
    - Orthogonal canonical interpretation_state property (not_started, organizing, ready, failed).
    - Ready requires valid persisted dossier, NOT status==uploaded.
    - topics_proposed + dossier => ready (status != uploaded, wait offers review).
    - uploaded + active claim => organizing.
    - error without dossier => failed.
    - uploaded empty => not_started.
    - dossier + residual error => ready (persisted dossier wins).
    - Roundtrip DB (reload) preserves canonical derivation identically without mutation.
    - Happy path upload ends in interpretation ready and status uploaded intact.
    """

    def test_b3_matrix_uploaded_with_dossier_derives_ready(self):
        """Matrix 1: status=uploaded + valid dossier + interpretation_state=ready => wait/status offer review."""
        client, user = _tutor_client_and_user("t2-b3-uploaded-ready")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        )

        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.has_valid_ready_dossier() is True

        # Wait page offers review
        wait_resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert wait_resp.status_code == 200
        html = wait_resp.content.decode("utf-8")
        assert "Revisar planeación" in html
        assert 'id="review-planning-btn"' in html
        assert reverse("tutor-import-interpretation", args=[job.pk]) in html

        # Status JSON reports finished and redirects to interpretation
        status_resp = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["state"] == "finished"
        assert data["interpretation_state"] == "ready"
        assert data["label"] == "Planeación organizada/lista para revisar"
        assert data["redirect_url"] == reverse("tutor-import-interpretation", args=[job.pk])

    def test_b3_matrix_topics_proposed_with_dossier_derives_ready(self):
        """Matrix 2: status=topics_proposed + valid dossier + interpretation_state=ready => ready (status != uploaded, wait offers review)."""
        client, user = _tutor_client_and_user("t2-b3-topics-ready")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_TOPICS_PROPOSED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        )

        # Interpretation state is ready despite status != uploaded
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.status == CurriculumImportJob.STATUS_TOPICS_PROPOSED

        # Wait page offers review without requiring status == STATUS_UPLOADED
        wait_resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert wait_resp.status_code == 200
        html = wait_resp.content.decode("utf-8")
        assert "Revisar planeación" in html
        assert 'id="review-planning-btn"' in html
        assert reverse("tutor-import-interpretation", args=[job.pk]) in html

        # Status JSON points to interpretation
        status_resp = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["state"] == "finished"
        assert data["interpretation_state"] == "ready"
        assert data["redirect_url"] == reverse("tutor-import-interpretation", args=[job.pk])

    def test_b3_matrix_uploaded_with_active_claim_derives_organizing(self):
        """Matrix 3: status=uploaded + active claim token + interpretation_state=organizing."""
        import uuid
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b3-claim-organizing")
        now = timezone.now()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=now,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        )

        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING

        # Wait page shows organizing indicator, not review
        wait_resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert wait_resp.status_code == 200
        html = wait_resp.content.decode("utf-8")
        assert "Estamos organizando tu planeación" in html
        assert "Revisar planeación" not in html
        assert 'id="review-planning-btn"' not in html

        # Status JSON reports waiting and redirects to detail if polled
        status_resp = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["state"] == "waiting"
        assert data["interpretation_state"] == "organizing"
        assert data["redirect_url"] == reverse("tutor-import-wait", args=[job.pk])

    def test_b3_matrix_error_without_dossier_derives_failed(self):
        """Matrix 4: explicit error without dossier => failed."""
        client, user = _tutor_client_and_user("t2-b3-error-failed")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_error_message="Error durante la interpretación del PDF.",
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        )

        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED

        # Wait page shows failure, not review
        wait_resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert wait_resp.status_code == 200
        html = wait_resp.content.decode("utf-8")
        assert "La generación se interrumpió" in html
        assert "Revisar planeación" not in html

        # Status JSON reports error and redirects to wait
        status_resp = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["state"] == "error"
        assert data["interpretation_state"] == "failed"
        assert data["error"] == "Error durante la interpretación del PDF."
        assert data["redirect_url"] == reverse("tutor-import-wait", args=[job.pk])

    def test_b3_matrix_uploaded_empty_derives_not_started(self):
        """Matrix 5: status=uploaded with no dossier, no claim, no error => not_started."""
        client, user = _tutor_client_and_user("t2-b3-uploaded-empty")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED

        # Wait page renders safely without review button
        wait_resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert wait_resp.status_code in (200, 302)
        if wait_resp.status_code == 200:
            html = wait_resp.content.decode("utf-8")
            assert "Revisar planeación" not in html

        # Status JSON reports not_started / waiting and redirects to wait
        status_resp = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["state"] in ("not_started", "waiting")
        assert data["interpretation_state"] == "not_started"
        assert data["redirect_url"] == reverse("tutor-import-wait", args=[job.pk])

    def test_b3_matrix_contradictory_dossier_and_error_derives_ready(self):
        """Matrix 6: Valid dossier + residual error_message + residual claim => ready (persisted dossier wins)."""
        import uuid
        from datetime import timedelta
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b3-contradictory")
        stale_time = timezone.now() - timedelta(hours=2)
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=stale_time,
            error_message="Worker timeout residual no limpiado.",
        )

        # Persisted valid dossier strictly wins over residual error and residual claim
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.has_valid_ready_dossier() is True

        # Wait page offers review
        wait_resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert wait_resp.status_code == 200
        html = wait_resp.content.decode("utf-8")
        assert "Revisar planeación" in html
        assert 'id="review-planning-btn"' in html

        # Status JSON reports finished
        status_resp = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert status_resp.status_code == 200
        assert status_resp.json()["state"] == "finished"
        assert status_resp.json()["interpretation_state"] == "ready"
        assert status_resp.json()["redirect_url"] == reverse("tutor-import-interpretation", args=[job.pk])

    def test_b3_matrix_roundtrip_reload_preserves_interpretation_state(self):
        """Matrix 7: Roundtrip DB reload preserves canonical interpretation_state identically."""
        import uuid
        from django.utils import timezone

        _, user = _tutor_client_and_user("t2-b3-roundtrip")
        now = timezone.now()

        # Create all 4 states
        job_ready = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        )
        job_organizing = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=now,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        )
        job_failed = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            error_message="Error persistido",
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        )
        job_not_started = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
        )

        # Before reloads
        assert job_ready.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job_organizing.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        assert job_failed.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert job_not_started.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED

        # Refresh from DB
        job_ready.refresh_from_db()
        job_organizing.refresh_from_db()
        job_failed.refresh_from_db()
        job_not_started.refresh_from_db()

        # After reloads: exact match
        assert job_ready.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job_organizing.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        assert job_failed.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert job_not_started.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED

        # Query fresh instances
        assert CurriculumImportJob.objects.get(pk=job_ready.pk).interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert CurriculumImportJob.objects.get(pk=job_organizing.pk).interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        assert CurriculumImportJob.objects.get(pk=job_failed.pk).interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert CurriculumImportJob.objects.get(pk=job_not_started.pk).interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED

    def test_b3_happy_upload_ends_in_ready_and_status_uploaded(self):
        """Matrix 8: Happy path upload ends in interpretation ready and status uploaded intact."""
        from curriculum.views import trigger_job_interpretation

        client = tutor_client("t2-b3-happy-teacher")
        upload_url = reverse("tutor-import-upload")

        resp = client.post(upload_url, {"pdf": _c01_upload()})
        assert resp.status_code == 302

        job = CurriculumImportJob.objects.order_by("-id").first()
        assert job.status == CurriculumImportJob.STATUS_UPLOADED
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.has_valid_ready_dossier() is True

        # Idempotent trigger returns persisted dossier without mutating or recomputing
        dossier_first = job.get_interpretation_dossier()
        dossier_second = trigger_job_interpretation(job)
        assert dossier_first.source_sha256 == dossier_second.source_sha256
        assert dossier_first.version == dossier_second.version
        assert job.status == CurriculumImportJob.STATUS_UPLOADED
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY

    def test_b3_inconsistent_matrix_ready_state_with_invalid_dossier_never_offers_review(self):
        """T2-B3: Inconsistent matrix (interpretation_state == READY in DB without valid dossier).
        Must fail closed: state='error', NEVER offer 'Revisar planeación' button, redirect to detail.
        """
        import hashlib
        from pathlib import Path

        client, user = _tutor_client_and_user("t2-b3-inconsistent-teacher")
        c01_sha = hashlib.sha256(C01_PATH.read_bytes()).hexdigest()

        cases = [
            ("empty-dict", {}),
            ("corrupt-payload", "not-a-dict"),
            ("tampered-status", {
                "source_sha256": c01_sha,
                "source_name": "prueba-semana-01.pdf",
                "page_count": 5,
                "version": 1,
                "status": "invalidated_source_tampered",
                "history": [],
            }),
            ("tampered-disk-file", {
                "source_sha256": c01_sha,
                "source_name": "prueba-semana-01.pdf",
                "page_count": 5,
                "version": 1,
                "status": "active",
                "history": [],
            }),
            ("missing-file", {
                "source_sha256": c01_sha,
                "source_name": "prueba-semana-01.pdf",
                "page_count": 5,
                "version": 1,
                "status": "active",
                "history": [],
            }),
        ]

        for name, dossier in cases:
            job = CurriculumImportJob.objects.create(
                created_by=user,
                pdf=_c01_upload(),
                status=CurriculumImportJob.STATUS_UPLOADED,
                interpretation_dossier=dossier,
                interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            )
            if name == "tampered-disk-file":
                Path(job.pdf.path).write_bytes(b"tampered content bytes")
            elif name == "missing-file":
                Path(job.pdf.path).unlink()

            snap_before = _model_field_snapshot(job)

            # Verification: has_valid_ready_dossier MUST be False
            assert job.has_valid_ready_dossier() is False, f"Case {name} reported valid dossier!"

            # GET status: reports error, NEVER finished, redirects to wait
            status_resp = client.get(reverse("tutor-import-status", args=[job.pk]))
            assert status_resp.status_code == 200
            data = status_resp.json()
            assert data["state"] == "error", f"Case {name} derived state {data['state']}"
            assert data["interpretation_state"] == "ready"
            assert data["redirect_url"] == reverse("tutor-import-wait", args=[job.pk])

            # GET wait: renders without review button
            wait_resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
            assert wait_resp.status_code == 200
            html = wait_resp.content.decode("utf-8")
            assert "review-planning-btn" not in html, f"Case {name} rendered review button!"
            assert "Revisar planeación" not in html

            # Read-only persistence guarantee
            assert _model_field_snapshot(job) == snap_before

    def test_b3_organizing_without_dossier_never_finished(self):
        """T2-B3: ORGANIZING without dossier never finished, never offers review button."""
        import uuid
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b3-organizing-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=timezone.now(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            interpretation_dossier={},
        )

        snap_before = _model_field_snapshot(job)

        status_resp = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["state"] == "waiting"
        assert data["interpretation_state"] == "organizing"
        assert data["redirect_url"] == reverse("tutor-import-wait", args=[job.pk])

        wait_resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert wait_resp.status_code == 200
        html = wait_resp.content.decode("utf-8")
        assert "review-planning-btn" not in html
        assert "Revisar planeación" not in html

        assert _model_field_snapshot(job) == snap_before

    def test_b3_status_json_exposes_interpretation_state_for_all_states(self):
        """T2-B3: Status JSON exposes interpretation_state for all 4 states."""
        import uuid
        from django.utils import timezone

        client, user = _tutor_client_and_user("t2-b3-json-teacher")

        states = [
            (CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED, {}),
            (CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING, {"interpretation_claim_token": uuid.uuid4(), "interpretation_claimed_at": timezone.now()}),
            (CurriculumImportJob.INTERPRETATION_STATE_READY, {"interpretation_dossier": _valid_c01_dossier_dict()}),
            (CurriculumImportJob.INTERPRETATION_STATE_FAILED, {"error_message": "Fallo explícito"}),
        ]

        for expected_state, extra_kwargs in states:
            job = CurriculumImportJob.objects.create(
                created_by=user,
                pdf=_c01_upload(),
                status=CurriculumImportJob.STATUS_UPLOADED,
                interpretation_state=expected_state,
                **extra_kwargs,
            )
            resp = client.get(reverse("tutor-import-status", args=[job.pk]))
            assert resp.status_code == 200
            data = resp.json()
            assert "interpretation_state" in data
            assert data["interpretation_state"] == expected_state

    def test_b3_cas_trigger_lifecycle_transitions(self):
        """T2-B3: CAS trigger transitions:
        - Claim establishes ORGANIZING
        - Success persists dossier + READY
        - Failure persists FAILED
        - Lost ownership does not alter foreign state
        - Re-trigger on ready job preserves READY idempotently
        """
        import uuid
        from unittest.mock import patch
        from django.utils import timezone
        from curriculum.views import trigger_job_interpretation

        _, user = _tutor_client_and_user("t2-b3-cas-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
        )

        # 1. Success transition: NOT_STARTED -> ORGANIZING (during prepare) -> READY
        dossier = trigger_job_interpretation(job)
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.status == CurriculumImportJob.STATUS_UPLOADED
        assert job.interpretation_claim_token is None
        assert job.interpretation_claimed_at is None
        assert job.error_message == ""
        assert dossier is not None

        # 2. Re-trigger on READY preserves READY idempotently
        dossier2 = trigger_job_interpretation(job)
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert dossier2.source_sha256 == dossier.source_sha256

        # 3. Failure transition: error during prepare sets FAILED
        job_fail = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
        )
        with patch("curriculum.source_interpreter.CurriculumSourceInterpreter.prepare", side_effect=ValueError("Fallo simulado")):
            with pytest.raises(ValueError, match="Fallo simulado"):
                trigger_job_interpretation(job_fail)

        job_fail.refresh_from_db()
        assert job_fail.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert job_fail.interpretation_claim_token is None
        assert "Fallo simulado" in (job_fail.interpretation_error_message or job_fail.error_message)

        # 4. Lost ownership does not overwrite foreign READY
        job_foreign = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
        )
        foreign_dossier = _valid_c01_dossier_dict()

        def steal_ownership_during_prepare(*args, **kwargs):
            CurriculumImportJob.objects.filter(pk=job_foreign.pk).update(
                interpretation_claim_token=uuid.uuid4(),
                interpretation_claimed_at=timezone.now(),
                interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
                interpretation_dossier=foreign_dossier,
            )
            from curriculum.source_interpreter import ImportDossier
            return job_foreign.get_interpretation_dossier() or ImportDossier.from_dict(foreign_dossier)

        with patch("curriculum.source_interpreter.CurriculumSourceInterpreter.prepare", side_effect=steal_ownership_during_prepare):
            returned = trigger_job_interpretation(job_foreign)

        job_foreign.refresh_from_db()
        # Foreign state must remain READY and not be wiped or altered
        assert job_foreign.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert returned.source_sha256 == foreign_dossier["source_sha256"]
        assert returned.version == foreign_dossier["version"]

    def test_b3_migration_0037_data_backfill_logic(self):
        """T2-B3: Verify migration 0037 backfill function correctly classifies existing jobs."""
        import importlib
        from unittest.mock import MagicMock
        import uuid
        from django.utils import timezone

        mig_0037 = importlib.import_module("curriculum.migrations.0037_curriculumimportjob_interpretation_state_and_more")
        migrate_interpretation_states = mig_0037.migrate_interpretation_states
        reverse_interpretation_states = mig_0037.reverse_interpretation_states

        _, user = _tutor_client_and_user("t2-b3-mig-teacher")

        # Create 5 rows with different legacy states
        job_ready = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
        )
        job_corrupt = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier={"corrupt": True},
        )
        job_claim = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=timezone.now(),
        )
        job_failed = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            error_message="Error persistido",
            progress_stage="",
        )
        job_empty = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        # Reset all interpretation_state to empty
        CurriculumImportJob.objects.filter(pk__in=[
            job_ready.pk, job_corrupt.pk, job_claim.pk, job_failed.pk, job_empty.pk
        ]).update(interpretation_state="")

        # Build mock apps for migration
        mock_apps = MagicMock()
        mock_apps.get_model.return_value = CurriculumImportJob

        # Run forward migration logic
        migrate_interpretation_states(mock_apps, None)

        job_ready.refresh_from_db()
        job_corrupt.refresh_from_db()
        job_claim.refresh_from_db()
        job_failed.refresh_from_db()
        job_empty.refresh_from_db()

        assert job_ready.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job_corrupt.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
        assert job_claim.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        assert job_failed.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED, (
            "Legacy error_message must not be classified as FAILED (origin is ambiguous; fail closed to NOT_STARTED)"
        )
        assert job_empty.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED

        # Run reverse migration logic
        reverse_interpretation_states(mock_apps, None)
        for j in (job_ready, job_corrupt, job_claim, job_failed, job_empty):
            j.refresh_from_db()
            assert j.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED

    def test_b3b_migration_0037_strict_fail_closed_checks(self):
        """B3b-1: Migration 0037 fail-closed checks against physical storage and SHA bytes."""
        import importlib
        from unittest.mock import MagicMock
        import uuid
        from django.core.files.base import ContentFile

        mig_0037 = importlib.import_module("curriculum.migrations.0037_curriculumimportjob_interpretation_state_and_more")
        migrate_interpretation_states = mig_0037.migrate_interpretation_states
        reverse_interpretation_states = mig_0037.reverse_interpretation_states

        _, user = _tutor_client_and_user("t2-b3b-strict-mig-teacher")

        c01_bytes = C01_PATH.read_bytes()
        valid_sha = hashlib.sha256(c01_bytes).hexdigest()

        # 1. Exact match with physical file on disk/storage -> READY
        job_exact = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier={
                "version": 1,
                "status": "active",
                "source_sha256": valid_sha,
                "source_name": "exact.pdf",
            },
        )

        # 2. Valid dossier metadata but physical file missing in storage -> NOT_STARTED
        job_missing_file = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=None,
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier={
                "version": 1,
                "status": "active",
                "source_sha256": valid_sha,
                "source_name": "missing.pdf",
            },
        )

        # 3. File exists but content SHA does NOT match dossier source_sha256 -> NOT_STARTED
        job_mismatch = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=SimpleUploadedFile("mismatch.pdf", b"tampered content differing from sha", content_type="application/pdf"),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier={
                "version": 1,
                "status": "active",
                "source_sha256": valid_sha,
                "source_name": "mismatch.pdf",
            },
        )

        # 4. Fake 64 non-hex string in source_sha256 -> NOT_STARTED
        fake_non_hex = "g" * 64
        job_fake_sha = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier={
                "version": 1,
                "status": "active",
                "source_sha256": fake_non_hex,
                "source_name": "fake.pdf",
            },
        )

        # 5. Missing explicit version or status keys -> NOT_STARTED
        job_missing_keys = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier={
                "source_sha256": valid_sha,
                "source_name": "no_version.pdf",
            },
        )

        # 6. Ambiguous legacy error message -> NOT_STARTED
        job_legacy_error = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            error_message="legacy extraction worker failed: timeout",
        )

        # 7. Active claim token -> ORGANIZING
        job_claim = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=timezone.now(),
        )

        CurriculumImportJob.objects.filter(pk__in=[
            job_exact.pk, job_missing_file.pk, job_mismatch.pk, job_fake_sha.pk,
            job_missing_keys.pk, job_legacy_error.pk, job_claim.pk,
        ]).update(interpretation_state="")

        mock_apps = MagicMock()
        mock_apps.get_model.return_value = CurriculumImportJob

        migrate_interpretation_states(mock_apps, None)

        job_exact.refresh_from_db()
        job_missing_file.refresh_from_db()
        job_mismatch.refresh_from_db()
        job_fake_sha.refresh_from_db()
        job_missing_keys.refresh_from_db()
        job_legacy_error.refresh_from_db()
        job_claim.refresh_from_db()

        assert job_exact.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job_missing_file.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
        assert job_mismatch.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
        assert job_fake_sha.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
        assert job_missing_keys.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
        assert job_legacy_error.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
        assert job_claim.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING

        # Reverse check
        reverse_interpretation_states(mock_apps, None)
        for j in (job_exact, job_missing_file, job_mismatch, job_fake_sha, job_missing_keys, job_legacy_error, job_claim):
            j.refresh_from_db()
            assert j.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED

    def test_b3b_real_path_upload_happy_and_exception(self):
        """B3b-2: Real upload POST transition to READY on success and FAILED on trigger crash."""
        from unittest.mock import patch

        client, user = _tutor_client_and_user("t2-b3b-upload-teacher")
        upload_url = reverse("tutor-import-upload")

        # 1. Happy path: upload PDF -> trigger succeeds -> DB row is READY
        resp_happy = client.post(upload_url, {"pdf": _c01_upload()})
        assert resp_happy.status_code in (302, 303)
        job_happy = CurriculumImportJob.objects.filter(created_by=user).latest("id")
        assert job_happy.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job_happy.has_valid_ready_dossier() is True
        assert job_happy.error_message == ""

        # 2. Exception path: trigger raises -> catch updates interpretation_state=FAILED
        with patch("curriculum.views.trigger_job_interpretation", side_effect=RuntimeError("Worker crashed unexpectedly")):
            resp_crash = client.post(upload_url, {"pdf": _c01_upload()})
            assert resp_crash.status_code in (302, 303)
            job_crashed = CurriculumImportJob.objects.filter(created_by=user).latest("id")
            assert job_crashed.pk != job_happy.pk
            assert job_crashed.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
            assert "Worker crashed unexpectedly" in (job_crashed.interpretation_error_message or job_crashed.error_message)

    def test_b3b_real_path_initial_get_prepare_in_interpretation_view(self):
        """Task 4 B1: GET tutor_import_interpretation when NOT_READY redirects to wait without mutating DB."""
        client, user = _tutor_client_and_user("t2-b3b-getprep-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
        )
        assert job.interpretation_dossier == {} or job.interpretation_dossier is None

        interp_url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.get(interp_url)
        assert resp.status_code == 302
        assert resp.headers["Location"] == reverse("tutor-import-wait", args=[job.pk])

        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
        assert job.interpretation_dossier == {} or job.interpretation_dossier is None
        assert job.interpretation_claim_token is None

    def test_b3b_real_path_mutating_actions_and_tamper_invalidation(self):
        """B3b-2: Mutating actions keep state READY, while tamper invalidation sets FAILED."""
        client, user = _tutor_client_and_user("t2-b3b-mutate-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
        )
        from curriculum.source_interpreter import CurriculumSourceInterpreter
        dossier = CurriculumSourceInterpreter.prepare(job, timeout_seconds=30.0)
        job.save_interpretation_dossier(dossier)

        interp_url = reverse("tutor-import-interpretation", args=[job.pk])
        # Initial visit on valid READY returns 200
        resp_get = client.get(interp_url)
        assert resp_get.status_code == 200
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        dossier = job.get_interpretation_dossier()
        assert dossier is not None

        # 1. Action confirm_all preserves READY
        resp_confirm = client.post(interp_url, {
            "action": "confirm_all",
            "expected_version": dossier.version,
            "session_number": 1,
        })
        assert resp_confirm.status_code in (200, 302)
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY

        # 2. Tamper PDF bytes on disk -> GET detects tamper -> redirects to wait without mutating DB
        with open(job.pdf.path, "wb") as f:
            f.write(b"%PDF-1.4 tampered bytes")

        resp_tampered = client.get(interp_url)
        assert resp_tampered.status_code == 302
        assert resp_tampered.headers["Location"] == reverse("tutor-import-wait", args=[job.pk])
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        raw = job.interpretation_dossier
        assert raw.get("status") == "active"

        # 3. Action reextract with fresh valid PDF -> saves READY
        with open(job.pdf.path, "wb") as f:
            f.write(C01_PATH.read_bytes())

        fresh_dossier = job.get_interpretation_dossier()
        resp_reextract = client.post(interp_url, {
            "action": "reextract",
            "expected_version": fresh_dossier.version,
            "session_number": 1,
        })
        assert resp_reextract.status_code in (200, 302)
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.has_valid_ready_dossier() is True

    def test_b3b_real_path_cancellation_lifecycle(self):
        """B3b-2: Cancellation keeps ORGANIZING during request and transitions to FAILED upon finish."""
        from curriculum.views import _finish_cancelled_import_stage
        import uuid

        client, user = _tutor_client_and_user("t2-b3b-cancel-teacher")
        owner_token = uuid.uuid4()
        now = timezone.now()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            interpretation_claim_token=owner_token,
            interpretation_claimed_at=now,
            progress_stage="reading_pdf",
        )

        cancel_url = reverse("tutor-import-cancel", args=[job.pk])
        resp = client.post(cancel_url)
        assert resp.status_code in (302, 303)

        job.refresh_from_db()
        # During cancel_requested, interpretation_state remains ORGANIZING
        assert job.cancel_requested is True
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING

        # Finishing the cancelled stage concretizes FAILED
        _finish_cancelled_import_stage(job)
        job.refresh_from_db()
        assert job.cancelled_at is not None
        assert job.progress_stage == ""
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert job.interpretation_claim_token is None

    def test_b3b_legacy_topics_proposed_with_valid_dossier_precedence(self):
        """B3b-3: Job with legacy topics_proposed + topics + finished_at AND valid dossier offers review."""
        client, user = _tutor_client_and_user("t2-b3b-precedence-teacher")
        now = timezone.now()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_TOPICS_PROPOSED,
            topics=[{"id": 1, "title": "Tema A", "description": "Desc"}],
            progress_stage="",
            progress_finished_at=now,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_dossier=_valid_c01_dossier_dict(),
        )

        # GET wait must render review option, NOT redirect to detail
        wait_url = reverse("tutor-import-wait", args=[job.pk])
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        assert resp_wait.context["ready_for_review"] is True
        content = resp_wait.content.decode("utf-8")
        assert "Estamos organizando tu planeación" in content
        assert "Planeación organizada/lista para revisar" in content
        assert "Revisar planeación" in content
        interp_url = reverse("tutor-import-interpretation", args=[job.pk])
        assert interp_url in content

        # GET status must report finished with interpretation redirect_url, NOT detail
        status_url = reverse("tutor-import-status", args=[job.pk])
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "finished"
        assert data["interpretation_state"] == "ready"
        assert data["redirect_url"] == interp_url
        assert not data["redirect_url"].endswith(f"/tutor/imports/{job.pk}/")

    def test_b3b_missing_keys_fail_closed(self):
        """B3b-4: Raw payload missing version or status fails closed, never treated as ready."""
        client, user = _tutor_client_and_user("t2-b3b-missing-keys-teacher")
        valid_sha = hashlib.sha256(C01_PATH.read_bytes()).hexdigest()

        # Incomplete payload without version or status
        incomplete_dossier = {
            "source_sha256": valid_sha,
            "source_name": "incomplete.pdf",
            "page_count": 5,
        }

        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,  # Even if DB says ready
            interpretation_dossier=incomplete_dossier,
        )

        # has_valid_ready_dossier must be False
        assert job.has_valid_ready_dossier() is False

        # Inconsistent state must derive error, never finished
        wait_url = reverse("tutor-import-wait", args=[job.pk])
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        assert resp_wait.context["ready_for_review"] is False
        content = resp_wait.content.decode("utf-8")
        assert "Revisar planeación" not in content

        # GET status must report state error and redirect to wait
        status_url = reverse("tutor-import-status", args=[job.pk])
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "error"
        assert data["redirect_url"] == reverse("tutor-import-wait", args=[job.pk])


class TestTask2B3cLifecyclePolicy:
    """Non-tautological real-path tests verifying the unified lifecycle mutation policy (CORRECCIÓN T2-B3c)."""

    def test_upload_outer_race_does_not_overwrite_foreign_ready(self, monkeypatch):
        """B3c-1: If a concurrent worker sets READY, upload outer except does not clobber it to FAILED."""
        from curriculum import views

        client, user = _tutor_client_and_user("t2-b3c-upload-race-ready-teacher")
        upload_url = reverse("tutor-import-upload")

        def _race_trigger(job):
            # Concurrent worker finishes interpretation before local trigger returns
            valid_dossier = _valid_c01_dossier_dict()
            CurriculumImportJob.objects.filter(pk=job.pk).update(
                interpretation_dossier=valid_dossier,
                interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
                interpretation_claim_token=None,
                error_message="",
            )
            # Local trigger crashes
            raise RuntimeError("Concurrent worker finished first; local trigger crashed")

        monkeypatch.setattr(views, "trigger_job_interpretation", _race_trigger)

        resp = client.post(upload_url, {"pdf": _c01_upload()})
        assert resp.status_code in (302, 303)

        job = CurriculumImportJob.objects.filter(created_by=user).latest("id")
        # Must preserve foreign READY and not be overwritten with FAILED
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.interpretation_dossier == _valid_c01_dossier_dict()
        assert job.error_message == ""

    def test_upload_outer_race_does_not_overwrite_foreign_organizing(self, monkeypatch):
        """B3c-1: If a concurrent worker claimed ORGANIZING, upload outer except does not clobber it to FAILED."""
        import uuid
        from curriculum import views

        client, user = _tutor_client_and_user("t2-b3c-upload-race-org-teacher")
        upload_url = reverse("tutor-import-upload")
        foreign_token = uuid.uuid4()

        def _race_trigger(job):
            # Concurrent worker claims job
            CurriculumImportJob.objects.filter(pk=job.pk).update(
                interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
                interpretation_claim_token=foreign_token,
                interpretation_claimed_at=timezone.now(),
            )
            # Local trigger crashes
            raise RuntimeError("Foreign worker claimed job; local trigger crashed")

        monkeypatch.setattr(views, "trigger_job_interpretation", _race_trigger)

        resp = client.post(upload_url, {"pdf": _c01_upload()})
        assert resp.status_code in (302, 303)

        job = CurriculumImportJob.objects.filter(created_by=user).latest("id")
        # Must preserve foreign ORGANIZING and keep foreign claim token
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        assert job.interpretation_claim_token == foreign_token
        assert job.error_message == ""

    def test_old_cancel_owner_cannot_wipe_new_claim_token(self):
        """B3c-2: Stale worker attempting cancellation cannot clear new claim token or state."""
        import uuid
        from curriculum.views import _finish_cancelled_import_stage

        _, user = _tutor_client_and_user("t2-b3c-stale-cancel-teacher")
        token_1 = uuid.uuid4()
        token_2 = uuid.uuid4()
        now = timezone.now()

        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            interpretation_claim_token=token_1,
            interpretation_claimed_at=now,
            cancel_requested=True,
        )

        # New worker takes over the claim
        job.interpretation_claim_token = token_2
        job.save(update_fields=["interpretation_claim_token"])

        # Stale worker 1 finishes cancellation expecting token_1
        _finish_cancelled_import_stage(job, expected_claim_token=token_1)

        job.refresh_from_db()
        # token_2 must be completely untouched and state remains ORGANIZING
        assert job.interpretation_claim_token == token_2
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        assert job.cancelled_at is None

    def test_save_interpretation_dossier_cannot_manufacture_ready(self):
        """B3c-3: save_interpretation_dossier rejects explicit_state='ready' if physical verification fails."""
        _, user = _tutor_client_and_user("t2-b3c-expl-ready-teacher")
        raw_missing_pdf = {
            "version": 1,
            "status": "active",
            "source_sha256": "0" * 64,
            "source_name": "nonexistent.pdf",
            "page_count": 1,
        }
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=None,  # No physical file
            status=CurriculumImportJob.STATUS_UPLOADED,
        )

        final_state = job.save_interpretation_dossier(raw_missing_pdf, explicit_state="ready")
        job.refresh_from_db()

        # Must fail closed to not_started, never ready
        assert final_state != CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
        assert job.has_valid_ready_dossier() is False

    def test_legacy_extract_preserves_ready_interpretation_dossier_and_state(self):
        """B3c-2: Legacy extract starting does NOT wipe interpretation_dossier or interpretation_state."""
        from curriculum.views import _start_import_stage
        from django.test import RequestFactory

        _, user = _tutor_client_and_user("t2-b3c-legacy-preserve-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_dossier=_valid_c01_dossier_dict(),
        )
        assert job.has_valid_ready_dossier() is True

        rf = RequestFactory()
        req = rf.post(f"/tutor/imports/{job.pk}/", {"action": "extract"})
        req.user = user

        # Start import stage
        _start_import_stage(req, job, "extract")

        job.refresh_from_db()
        # Legacy stage is set
        assert job.progress_stage == "extract"
        # BUT interpretation_state and interpretation_dossier are completely preserved!
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.interpretation_dossier == _valid_c01_dossier_dict()
        assert job.has_valid_ready_dossier() is True

    def test_reextract_failure_sets_failed_and_wait_status_reports_error_then_success_recovers(self, monkeypatch):
        """B3c-4: Failed reextract persists FAILED so GET status reports error/no review, then success restores READY."""
        client, user = _tutor_client_and_user("t2-b3c-reextract-failure-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_dossier=_valid_c01_dossier_dict(),
        )

        interp_url = reverse("tutor-import-interpretation", args=[job.pk])
        wait_url = reverse("tutor-import-wait", args=[job.pk])
        status_url = reverse("tutor-import-status", args=[job.pk])

        # 1. Simulate reextract failure by making prepare throw
        from curriculum.source_interpreter import CurriculumSourceInterpreter, SourcePdfReadError

        def _failing_prepare(*args, **kwargs):
            raise SourcePdfReadError("Stream corrupto durante reextracción simulada")

        monkeypatch.setattr(CurriculumSourceInterpreter, "prepare", _failing_prepare)

        resp_fail = client.post(interp_url, {
            "action": "reextract",
            "expected_version": 1,
            "session_number": 1,
        })
        assert resp_fail.status_code == 422

        job.refresh_from_db()
        # DB state MUST be failed with error message
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert "Stream corrupto" in (job.interpretation_error_message or job.error_message)

        # GET wait must NOT offer review button
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        assert resp_wait.context["ready_for_review"] is False
        assert "Revisar planeación" not in resp_wait.content.decode("utf-8")

        # GET status must report error, NOT finished
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "error"
        assert data["interpretation_state"] == "failed"
        assert data["error"] == "No pudimos leer el archivo PDF de la planeación. Puedes volver a intentarlo."
        assert "Stream corrupto" not in data["error"]
        assert "simulada" not in data["error"]
        assert data["redirect_url"] != interp_url

        # 2. Now perform a successful reextract (un-monkeypatch)
        monkeypatch.undo()
        resp_success = client.post(interp_url, {
            "action": "reextract",
            "expected_version": 1,
            "session_number": 1,
        })
        assert resp_success.status_code in (200, 302)

        job.refresh_from_db()
        # DB state MUST be restored to READY
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.has_valid_ready_dossier() is True
        assert job.error_message == ""

        # GET status reports finished with redirect to interpretation
        resp_status_ok = client.get(status_url)
        data_ok = resp_status_ok.json()
        assert data_ok["state"] == "finished"
        assert data_ok["interpretation_state"] == "ready"
        assert data_ok["redirect_url"] == interp_url

    def test_migration_0037_claim_precedence_over_valid_dossier(self):
        """B3c-5: Migration 0037 prioritizes active claim over ready dossier (organizing > ready)."""
        import uuid
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        # Migrate backward to 0036
        migrate_back = [("curriculum", "0036_curriculumimportjob_interpretation_claim_token_and_more")]
        executor.migrate(migrate_back)
        old_apps = executor.loader.project_state(migrate_back).apps
        OldJob = old_apps.get_model("curriculum", "CurriculumImportJob")

        # Create physical test file in storage
        content = b"%PDF-1.4 test valid content for migration probe"
        file_sha = hashlib.sha256(content).hexdigest()
        file_path = default_storage.save("test_migration_c01.pdf", ContentFile(content))

        valid_dossier = {
            "version": 1,
            "status": "active",
            "source_sha256": file_sha,
            "source_name": "test_migration_c01.pdf",
            "page_count": 1,
        }

        # Case 1: Active claim + valid dossier -> MUST become organizing!
        j1 = OldJob.objects.create(
            pdf=file_path,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_dossier=valid_dossier,
        )
        # Case 2: No claim + valid dossier -> MUST become ready
        j2 = OldJob.objects.create(
            pdf=file_path,
            interpretation_dossier=valid_dossier,
        )
        # Case 3: No claim + legacy error -> MUST become not_started
        j3 = OldJob.objects.create(
            pdf=file_path,
            error_message="Legacy extraction error",
        )

        try:
            # Migrate forward to 0037
            migrate_to = [("curriculum", "0037_curriculumimportjob_interpretation_state_and_more")]
            executor.loader.build_graph()
            executor.migrate(migrate_to)
            new_apps = executor.loader.project_state(migrate_to).apps
            NewJob = new_apps.get_model("curriculum", "CurriculumImportJob")

            rec1 = NewJob.objects.get(pk=j1.pk)
            rec2 = NewJob.objects.get(pk=j2.pk)
            rec3 = NewJob.objects.get(pk=j3.pk)

            # Ordering verification: active claim wins over ready dossier!
            assert rec1.interpretation_state == "organizing"
            assert rec2.interpretation_state == "ready"
            assert rec3.interpretation_state == "not_started"

        finally:
            # Cleanup storage file
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
            # Ensure database is returned to latest leaf state
            executor.loader.build_graph()
            executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db
class TestTask2B3dSeamClosure:
    """Causal regressions for B3d seam closure:
    - finish_worker_success/failure reject None/empty owner token.
    - finish_cancelled_stage(expected_token=None) against active claim is a total NO-OP.
    - save_interpretation_dossier against active foreign claim raises conflict and leaves claim intact.
    - trigger fast reconciliation against foreign claim preserves claim token.
    - InterpretationCancelledError does not inherit from TimeoutError; reextract returns 409 not 504.
    - reextract during foreign claim returns 409 without mutation.
    - GET wait / status / detail leave dict(client.session) strictly identical.
    """

    def test_finish_worker_success_and_failure_reject_none_or_empty_token(self):
        """B3d-1: finish_worker_success/failure reject owner_token None/empty with ValueError."""
        from curriculum.interpretation_commands import (
            finish_worker_failure,
            finish_worker_success,
        )

        job = CurriculumImportJob.objects.create(
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
        )

        dossier_dict = _valid_c01_dossier_dict()

        for invalid_token in (None, ""):
            with pytest.raises(ValueError, match="owner_token must be a valid"):
                finish_worker_success(job, invalid_token, dossier_dict)

            with pytest.raises(ValueError, match="owner_token must be a valid"):
                finish_worker_failure(job, invalid_token, "some error")

        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
        assert job.interpretation_claim_token is None
        assert job.interpretation_dossier == {}

    def test_finish_cancelled_stage_none_token_against_active_claim_is_noop(self):
        """B3d-2: finish_cancelled_stage(expected_token=None) against active claim is a total NO-OP."""
        from curriculum.interpretation_commands import finish_cancelled_stage

        token_a = uuid.uuid4()
        now = timezone.now()
        job = CurriculumImportJob.objects.create(
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_claim_token=token_a,
            interpretation_claimed_at=now,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            progress_stage="interpreting",
            cancel_requested=True,
        )

        # Call cancel without expected token
        rows = finish_cancelled_stage(job, expected_claim_token=None)
        assert rows == 0

        # Total NO-OP verification: no fields changed
        job.refresh_from_db()
        assert job.interpretation_claim_token == token_a
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        assert job.progress_stage == "interpreting"
        assert job.cancelled_at is None
        assert job.error_message == ""

        # With exact token, CAS succeeds
        rows_cas = finish_cancelled_stage(job, expected_claim_token=token_a)
        assert rows_cas == 1
        job.refresh_from_db()
        assert job.interpretation_claim_token is None
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert job.progress_stage == ""
        assert job.cancelled_at is not None

    def test_save_interpretation_dossier_against_foreign_claim_raises_conflict_and_leaves_claim_intact(self):
        """B3d-3: save_interpretation_dossier against active foreign claim raises CurriculumInterpretationError."""
        from curriculum.source_interpreter import CurriculumInterpretationError

        foreign_token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_claim_token=foreign_token,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        )

        valid_dossier = _valid_c01_dossier_dict()

        # Without owner_token: must raise conflict and NOT modify DB
        with pytest.raises(CurriculumInterpretationError, match="Conflicto de concurrencia"):
            job.save_interpretation_dossier(valid_dossier)

        job.refresh_from_db()
        assert job.interpretation_claim_token == foreign_token
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        assert job.interpretation_dossier == {}

        # With matching owner_token: succeeds
        job.save_interpretation_dossier(valid_dossier, owner_token=foreign_token)
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.interpretation_claim_token is None
        assert job.interpretation_dossier == valid_dossier

    def test_trigger_fast_reconciliation_against_foreign_claim_does_not_clear_claim(self):
        """B3d-4: Fast reconciliation does not clobber an active foreign claim."""
        from curriculum.views import trigger_job_interpretation

        foreign_token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_dossier=_valid_c01_dossier_dict(),
            interpretation_claim_token=foreign_token,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        )

        # Trigger interpretation on job with valid dossier + active foreign claim
        dossier = trigger_job_interpretation(job)
        assert dossier is not None

        job.refresh_from_db()
        # Foreign claim token must NOT be cleared!
        assert job.interpretation_claim_token == foreign_token

    def test_interpretation_cancelled_error_does_not_inherit_timeout_and_caller_returns_409(self, monkeypatch):
        """B3d-5: InterpretationCancelledError does not inherit from TimeoutError, caller returns 409."""
        from curriculum.source_interpreter import (
            CurriculumInterpretationError,
            CurriculumSourceInterpreter,
            InterpretationCancelledError,
            InterpretationTimeoutError,
        )

        assert issubclass(InterpretationCancelledError, CurriculumInterpretationError)
        assert not issubclass(InterpretationCancelledError, TimeoutError)
        assert issubclass(InterpretationTimeoutError, TimeoutError)

        client, user = _tutor_client_and_user("t2-b3d-cancel-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_dossier=_valid_c01_dossier_dict(),
        )

        def _cancelled_prepare(*args, **kwargs):
            raise InterpretationCancelledError("Cancelación cooperativa probada")

        monkeypatch.setattr(CurriculumSourceInterpreter, "prepare", _cancelled_prepare)

        interp_url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.post(interp_url, {
            "action": "reextract",
            "expected_version": 1,
            "session_number": 1,
        })
        # Must return 409 (cancellation), NOT 504 (timeout)
        assert resp.status_code == 409
        assert "cancelada" in resp.content.decode("utf-8").lower()

    def test_reextract_during_foreign_claim_returns_409_without_mutation(self):
        """B3d-6: reextract during active foreign claim returns 409 Conflict without modifying persistence."""
        client, user = _tutor_client_and_user("t2-b3d-foreign-claim-teacher")
        foreign_token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            interpretation_claim_token=foreign_token,
            cancel_requested=True,
        )

        interp_url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.post(interp_url, {
            "action": "reextract",
            "expected_version": 1,
            "session_number": 1,
        })
        assert resp.status_code == 409
        assert "en progreso" in resp.content.decode("utf-8").lower()

        job.refresh_from_db()
        assert job.interpretation_claim_token == foreign_token
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        # cancel_requested was NOT cleared
        assert job.cancel_requested is True

    def test_get_wait_detail_status_pure_session_dict_unchanged_across_multiple_gets(self):
        """B3d-7: GET wait, detail, and status do not mutate request.session."""
        client, user = _tutor_client_and_user("t2-b3d-pure-session-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_dossier=_valid_c01_dossier_dict(),
        )

        # Populate session with markers
        s = client.session
        s["probe_marker"] = "alive"
        s[f"legacy_stage_{job.pk}"] = "extract"
        s.save()

        initial_session_items = dict(client.session)

        # GET wait
        resp_wait_1 = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert dict(client.session) == initial_session_items

        resp_wait_2 = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert dict(client.session) == initial_session_items

        # GET detail
        resp_detail = client.get(reverse("tutor-import-detail", args=[job.pk]))
        assert dict(client.session) == initial_session_items

        # GET status
        resp_status = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert dict(client.session) == initial_session_items


class TestTask2B3eSeamClosureAndErrorSeparation:
    """Causal regressions for B3e:
    1. claim_interpretation_worker rejects None, empty, whitespace, and non-UUID tokens before DB update (zero mutation).
    2. validate_claim_token matrix tests for valid UUID objects, string UUIDs, and rejects invalid inputs.
    3. Legacy error_message with interpretation_state=NOT_STARTED does not trigger error state or presentation.
    4. Legacy pipeline mutations to error_message do not alter interpretation_state or presentation.
    5. Worker failure and reextract failure write exclusively to interpretation_error_message, preserving error_message.
    6. Recovery to READY clears interpretation_error_message without wiping legacy error_message.
    7. Migration 0038 conservative data copy (failed copies error, other states do not) and clean reversibility.
    """

    def test_claim_interpretation_worker_rejects_none_empty_and_invalid_tokens_zero_mutation(self):
        """B3e-1: claim_interpretation_worker rejects invalid owner_token before any UPDATE."""
        from curriculum.interpretation_commands import claim_interpretation_worker

        job = CurriculumImportJob.objects.create(
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
        )

        invalid_tokens = (None, "", "   ", "not-a-uuid", 12345, [], {})
        for invalid_token in invalid_tokens:
            with pytest.raises(ValueError, match="owner_token must be a valid"):
                claim_interpretation_worker(job, owner_token=invalid_token)

            job.refresh_from_db()
            assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
            assert job.interpretation_claim_token is None
            assert job.interpretation_claimed_at is None

        # Valid UUID object works
        valid_uuid = uuid.uuid4()
        rows = claim_interpretation_worker(job, owner_token=valid_uuid)
        assert rows == 1
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        assert job.interpretation_claim_token == valid_uuid

    def test_validate_claim_token_direct_matrix(self):
        """B3e-2: validate_claim_token normalizes valid UUID / string UUID and raises ValueError on invalid."""
        from curriculum.interpretation_commands import validate_claim_token

        test_uuid = uuid.uuid4()
        assert validate_claim_token(test_uuid) == test_uuid
        assert validate_claim_token(str(test_uuid)) == test_uuid

        for bad in (None, "", "  ", "abc", 123, object()):
            with pytest.raises(ValueError, match="owner_token must be a valid"):
                validate_claim_token(bad)

    def test_legacy_error_message_with_not_started_does_not_derive_error_presentation(self):
        """B3e-3: Legacy error in error_message + NOT_STARTED reports waiting/normal, never error."""
        client, user = _tutor_client_and_user("t2-b3e-legacy-err-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
            error_message="Error fatal del pipeline legado de extracción.",
            interpretation_error_message="",
        )

        from curriculum.views import _get_derived_import_presentation

        pres = _get_derived_import_presentation(job)
        assert pres["state"] == "waiting"
        assert pres["error"] == ""
        assert pres["label"] == "Esperando al asistente"

        # GET status poll returns waiting and empty error
        resp_status = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "waiting"
        assert data["interpretation_state"] == "not_started"
        assert data["error"] == ""

    def test_legacy_pipeline_writes_to_error_message_do_not_alter_interpretation_lifecycle(self):
        """B3e-4: Legacy pipeline updates to error_message do not alter READY interpretation."""
        client, user = _tutor_client_and_user("t2-b3e-legacy-pipeline-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_dossier=_valid_c01_dossier_dict(),
            page_count=5,
        )

        # Legacy worker sets error_message
        job.error_message = "Legacy stage subtopics failed due to LLM timeout."
        job.save(update_fields=["error_message"])

        from curriculum.views import _get_derived_import_presentation

        pres = _get_derived_import_presentation(job)
        assert pres["state"] == "finished"
        assert pres["error"] == ""
        assert pres["label"] == "Planeación organizada/lista para revisar"

        resp_status = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "finished"
        assert data["interpretation_state"] == "ready"
        assert data["error"] == ""

    def test_interpretation_failure_and_reextract_failure_write_only_to_interpretation_error_message(self):
        """B3e-5: Interpretation failures write to interpretation_error_message and leave error_message intact."""
        from curriculum.interpretation_commands import (
            finish_worker_failure,
            record_reextract_failure,
        )

        token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_claim_token=token,
            interpretation_claimed_at=timezone.now(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            error_message="Preserved legacy error message",
        )

        rows = finish_worker_failure(job, owner_token=token, error_message="Fallo del modelo V0")
        assert rows == 1

        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert job.interpretation_error_message == "Fallo del modelo V0"
        assert job.error_message == "Preserved legacy error message"

        # Reextract failure also targets interpretation_error_message
        record_reextract_failure(job, error_message="Reextracción falló por PDF corrupto")
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert job.interpretation_error_message == "Reextracción falló por PDF corrupto"
        assert job.error_message == "Preserved legacy error message"

    def test_successful_recovery_clears_interpretation_error_and_preserves_legacy_error(self):
        """B3e-6: Recovery to READY clears interpretation_error_message but never wipes legacy error_message."""
        token = uuid.uuid4()
        job = CurriculumImportJob.objects.create(
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_claim_token=token,
            interpretation_claimed_at=timezone.now(),
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
            interpretation_error_message="Error previo de interpretación",
            error_message="Legacy warning message that must not be lost",
        )

        from curriculum.interpretation_commands import finish_worker_success

        rows = finish_worker_success(job, owner_token=token, dossier=_valid_c01_dossier_dict())
        assert rows == 1

        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.interpretation_error_message == ""
        assert job.error_message == "Legacy warning message that must not be lost"

    def test_migration_0038_conservative_copy_and_reversibility(self):
        """B3e-7: Migration 0038 copies error_message ONLY for failed jobs, and reverses cleanly."""
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        # Migrate backward to 0037
        migrate_back = [("curriculum", "0037_curriculumimportjob_interpretation_state_and_more")]
        executor.migrate(migrate_back)
        old_apps = executor.loader.project_state(migrate_back).apps
        OldJob = old_apps.get_model("curriculum", "CurriculumImportJob")

        j_failed = OldJob.objects.create(
            interpretation_state="failed",
            error_message="Error genuino de interpretación",
        )
        j_not_started = OldJob.objects.create(
            interpretation_state="not_started",
            error_message="Error legacy ajeno",
        )
        j_ready = OldJob.objects.create(
            interpretation_state="ready",
            error_message="Error residual previo",
        )
        j_organizing = OldJob.objects.create(
            interpretation_state="organizing",
            error_message="Error transitorio",
        )

        try:
            # Migrate forward to 0038
            migrate_to = [("curriculum", "0038_curriculumimportjob_interpretation_error_message_and_more")]
            executor.loader.build_graph()
            executor.migrate(migrate_to)
            new_apps = executor.loader.project_state(migrate_to).apps
            NewJob = new_apps.get_model("curriculum", "CurriculumImportJob")

            rf = NewJob.objects.get(pk=j_failed.pk)
            rn = NewJob.objects.get(pk=j_not_started.pk)
            rr = NewJob.objects.get(pk=j_ready.pk)
            ro = NewJob.objects.get(pk=j_organizing.pk)

            # ONLY failed copied the error_message!
            assert rf.interpretation_error_message == "Error genuino de interpretación"
            assert rn.interpretation_error_message == ""
            assert rr.interpretation_error_message == ""
            assert ro.interpretation_error_message == ""

            # Reverse back to 0037 succeeds cleanly
            executor.loader.build_graph()
            executor.migrate(migrate_back)

        finally:
            # Return to latest leaf nodes
            executor.loader.build_graph()
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_not_started_with_legacy_error_and_extract_stage_does_not_derive_error(self):
        """B3f-1: NOT_STARTED + legacy error_message + progress_stage='extract' does not derive error."""
        client, user = _tutor_client_and_user("t2-b3f-extract-legacy-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
            progress_stage="extract",
            error_message="Legacy extraction error",
            interpretation_error_message="",
        )

        from curriculum.views import _get_derived_import_presentation, _import_progress_state

        state = _import_progress_state(job)
        assert state != "error"

        pres = _get_derived_import_presentation(job)
        assert pres["state"] != "error"
        assert pres["error"] == ""
        assert "Legacy extraction error" not in pres["error"]

    def test_failed_and_cancelled_with_only_legacy_error_does_not_expose_it(self):
        """B3f-2: FAILED/cancelled without interpretation_error uses generic honest message, never legacy error."""
        from curriculum.views import _get_derived_import_presentation

        # Case A: FAILED with only legacy error
        job_failed = CurriculumImportJob.objects.create(
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
            error_message="Legacy subtopics error from old pipeline",
            interpretation_error_message="",
        )
        pres_failed = _get_derived_import_presentation(job_failed)
        assert pres_failed["state"] == "error"
        assert pres_failed["error"] == "La generación se interrumpió."
        assert "Legacy subtopics error" not in pres_failed["error"]

        # Case B: Cancelled with only legacy error
        now_dt = timezone.now()
        job_cancelled = CurriculumImportJob.objects.create(
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            cancel_requested=True,
            cancelled_at=now_dt,
            error_message="Legacy subtopics error from old pipeline",
            interpretation_error_message="",
        )
        pres_cancelled = _get_derived_import_presentation(job_cancelled)
        assert pres_cancelled["state"] == "error"
        assert pres_cancelled["error"] == "Interpretación cancelada a petición."
        assert "Legacy subtopics error" not in pres_cancelled["error"]

    def test_waiter_and_owner_lost_do_not_return_legacy_error(self):
        """B3f-3: Owner-lost and waiter paths do not raise or expose legacy error_message."""
        from curriculum.source_interpreter import CurriculumInterpretationError
        from curriculum.views import trigger_job_interpretation
        from unittest.mock import patch

        client, user = _tutor_client_and_user("t2-b3f-waiter-teacher")
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
            error_message="SENTINEL_LEGACY_ERROR",
            interpretation_error_message="",
        )

        # 1. Owner lost: prepare succeeds locally but rows_persisted is 0
        from curriculum.interpretation_commands import finish_worker_success
        with patch("curriculum.interpretation_commands.finish_worker_success", return_value=0):
            with pytest.raises(CurriculumInterpretationError) as exc_info:
                trigger_job_interpretation(job)
            assert "SENTINEL_LEGACY_ERROR" not in str(exc_info.value)
            assert "Se perdió el reclamo de interpretación" in str(exc_info.value)

        # 2. Waiter path: foreign claim active then released without dossier or interpretation error
        job2 = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            interpretation_claim_token=uuid.uuid4(),
            interpretation_claimed_at=timezone.now(),
            error_message="SENTINEL_LEGACY_ERROR",
            interpretation_error_message="",
        )

        # Simulate claim released while waiter is polling
        def simulate_claim_release(*args, **kwargs):
            CurriculumImportJob.objects.filter(pk=job2.pk).update(
                interpretation_claim_token=None,
                interpretation_claimed_at=None,
            )

        import threading
        timer = threading.Timer(0.05, simulate_claim_release)
        timer.start()
        try:
            with pytest.raises(CurriculumInterpretationError) as exc_info:
                trigger_job_interpretation(job2, wait_timeout=2.0, poll_interval=0.02)
            assert "SENTINEL_LEGACY_ERROR" not in str(exc_info.value)
            assert "finalizó sin generar dossier ni error" in str(exc_info.value)
        finally:
            timer.cancel()

    def test_reextract_success_after_cancellation_preserves_legacy_error_sentinel_and_clears_interpretation_error(self):
        """B3f-4: Reextract success after cancel clears interpretation_error_message, preserves legacy error_message."""
        client, user = _tutor_client_and_user("t2-b3f-reextract-sentinel-teacher")
        now_dt = timezone.now()
        job = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=_c01_upload(),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            interpretation_dossier=_valid_c01_dossier_dict(),
            cancel_requested=True,
            cancelled_at=now_dt,
            error_message="LEGACY_PRESERVED_SENTINEL_ERROR",
            interpretation_error_message="Interpretación cancelada a petición.",
        )

        resp = client.post(
            reverse("tutor-import-interpretation", args=[job.pk]),
            {"action": "reextract", "expected_version": "1", "session_number": 1},
        )
        assert resp.status_code in (200, 302)

        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.interpretation_error_message == ""
        assert job.error_message == "LEGACY_PRESERVED_SENTINEL_ERROR"
        assert job.cancel_requested is False
        assert job.cancelled_at == now_dt













