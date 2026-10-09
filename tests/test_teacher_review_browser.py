"""Current Django one-box CI browser gate; generated data and explicit fake provider."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from django.urls import reverse
from curriculum.models import CurriculumImportJob,PublishedPackageSnapshot,ClassroomSession
from onebox_ci_fixture import configure,generated_pdf,complete_job,USERNAME,PASSWORD,FIRST_ANSWER,EDITED_ANSWER,PENDING_ANSWER

@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_current_onebox_browser_journey(tmp_path,settings,monkeypatch,request):
    chrome=os.environ.get('TEACHER_REVIEW_CHROME') or shutil.which('google-chrome') or shutil.which('chromium')
    required=os.environ.get('TEACHER_REVIEW_BROWSER_REQUIRED')=='1' or bool(os.environ.get('CI'))
    if not chrome or not Path(chrome).is_file() or not shutil.which('node'):
        if required: pytest.fail('Required current one-box browser acceptance needs installed Chrome and Node')
        pytest.skip('Current one-box browser acceptance requires installed Chrome and Node')
    teacher,provider=configure(settings,monkeypatch)
    pdf_bytes=generated_pdf();pdf=tmp_path/'generated-onebox.pdf';pdf.write_bytes(pdf_bytes)
    resolved=complete_job(teacher,pdf_bytes)
    # Requested only after the capability check; no server/browser starts on skip.
    live_server=request.getfixturevalue('live_server')
    evidence=Path(os.environ.get('TEACHER_REVIEW_EVIDENCE_DIR',str(tmp_path/'evidence')))
    evidence.mkdir(parents=True,exist_ok=True)
    config={'baseUrl':live_server.url,'chrome':chrome,'profile':str(tmp_path/'profile'),'pdf':str(pdf),
        'pdfSha':hashlib.sha256(pdf_bytes).hexdigest(),'evidenceDir':str(evidence.resolve()),
        'username':USERNAME,'password':PASSWORD,'firstAnswer':FIRST_ANSWER,'editedAnswer':EDITED_ANSWER,
        'pendingAnswer':PENDING_ANSWER,'completeReviewPath':reverse('tutor-import-interpretation',args=[resolved.pk])}
    result=subprocess.run(['node',str(Path(__file__).with_name('teacher_review_browser.mjs'))],input=json.dumps(config),text=True,capture_output=True,timeout=180)
    print(result.stdout)
    # Synthetic fixture metadata only, never PDF text, answers, credentials or tokens.
    from curriculum.models import CurriculumTeacherReview
    print(json.dumps({'onebox_server_transition':{
        'provider_calls':len(provider.contexts),
        'reviews':[{'job_id':r.job_id,'revision':r.revision,'draft_epoch':r.draft_epoch,
            'status':r.state.get('status'),'error':r.state.get('error'),
            'question_count':len(r.state.get('turns',[])),
            'answered':[t.get('answer') is not None for t in r.state.get('turns',[])],
            'generation_claimed':bool(r.generation_token)}
            for r in CurriculumTeacherReview.objects.order_by('job_id')]}},sort_keys=True))
    assert result.returncode==0,result.stdout+result.stderr
    uploaded=CurriculumImportJob.objects.exclude(pk=resolved.pk).get()
    assert uploaded.created_by==teacher
    assert uploaded.get_interpretation_dossier().source_sha256==config['pdfSha']
    review=uploaded.teacher_review
    assert len(review.state['turns'])==6
    assert review.state['status']=='needs_input'
    # Native HTML form submission canonicalizes textarea line breaks to CRLF.
    # Assert the exact transport text, including spaces and final line breaks.
    transport_first=FIRST_ANSWER.replace('\n','\r\n')
    transport_edited=EDITED_ANSWER.replace('\n','\r\n')
    assert review.state['turns'][0]['answer']==transport_edited
    assert [h['answer'] for h in review.state['turns'][0]['answer_history']]==[transport_first,transport_edited]
    assert uploaded.approvals.count()==0 and not uploaded.is_approved
    resolved.refresh_from_db()
    assert resolved.approvals.count()==1 and resolved.is_approved
    assert resolved.teacher_review.state['turns']==[]
    assert PublishedPackageSnapshot.objects.count()==0
    assert ClassroomSession.objects.count()==0
    assert provider.contexts,'The required browser journey did not exercise its provider double'
    for context in provider.contexts:
        assert len(context['dossier']['sessions'])==2
        assert context['source_document']['source_sha256']==config['pdfSha']
        assert context['source_document']['page_count']==2
        assert 'LAMINA SINTETICA UNICA CI' in context['source_document']['pages'][1]['text']
        assert context['source_document']['ocr_performed'] is False
    evidence.joinpath('teacher-review-server-checks.json').write_text(json.dumps({'provider':'explicit deterministic test double','live_inference':False,'question_count':6,'literal_history':True,'source_sha_verified':True,'all_pages_and_sessions_in_context':True,'approved_complete_fixture':True,'unresolved_fixture_approved':False,'published_snapshots':0,'classroom_sessions':0},indent=2))
