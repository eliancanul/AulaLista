import hashlib
import pytest
from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from curriculum.models import CurriculumImportJob
from curriculum.teacher_review import advance_review,open_review,unresolved
from onebox_ci_fixture import configure,generated_pdf,complete_job,USERNAME,PASSWORD,FIRST_ANSWER,EDITED_ANSWER,PENDING_ANSWER

@pytest.mark.django_db
def test_generated_fixture_actual_upload_and_adaptive_provider(settings,monkeypatch):
    teacher,provider=configure(settings,monkeypatch)
    pdf=generated_pdf()
    c=Client(enforce_csrf_checks=True)
    assert c.login(username=USERNAME,password=PASSWORD)
    upload=reverse('tutor-import-upload')
    c.get(upload)
    assert c.post(upload,{'pdf':SimpleUploadedFile('synthetic-ci.pdf',pdf)}).status_code==403
    response=c.post(upload,{'csrfmiddlewaretoken':c.cookies['csrftoken'].value,'pdf':SimpleUploadedFile('synthetic-ci.pdf',pdf)})
    assert response.status_code==302
    job=CurriculumImportJob.objects.get()
    assert job.has_valid_ready_dossier(),(job.interpretation_state,job.interpretation_error_message)
    assert len(job.get_interpretation_dossier().sessions)==2
    view=c.get(reverse('tutor-import-interpretation',args=[job.pk])).content.decode()
    assert all(text in view for text in ['Primera lectura','Segunda lectura','Anexo'])
    url=reverse('tutor-import-interpretation',args=[job.pk])
    def post_form(action,answer=None,suffix=""):
        html=BeautifulSoup(c.get(url+suffix).content,'html.parser')
        button=html.find('button',attrs={'value':action})
        form=button.find_parent('form')
        data={i['name']:i.get('value','') for i in form.find_all('input')}
        data['action']=action
        if answer is not None:data['answer']=answer
        return c.post(url+suffix,data)
    assert post_form('continue').status_code==302
    assert len(provider.contexts)==1
    job.refresh_from_db(); assert job.teacher_review.state['status']=='asking', (job.teacher_review.state,provider.contexts[0]['missing_fields'])
    ctx=provider.contexts[0]
    assert ctx['source_document']['source_sha256']==hashlib.sha256(pdf).hexdigest()
    assert len(ctx['source_document']['pages'])==2
    assert 'LAMINA SINTETICA UNICA CI' in ctx['source_document']['pages'][1]['text']
    assert post_form('answer',FIRST_ANSWER).status_code==302
    job.refresh_from_db()
    assert len(job.teacher_review.state['turns'])==2
    assert FIRST_ANSWER.strip() in job.teacher_review.state['turns'][1]['question']
    first_turn,second_turn=job.teacher_review.state['turns']
    q2page=BeautifulSoup(c.get(url).content,'html.parser')
    draft={i['name']:i.get('value','') for i in q2page.find('form',id='teacher-answer-form').find_all('input')}
    assert c.post(url,{**draft,'action':'save_draft','answer':PENDING_ANSWER}).status_code==200
    assert post_form('edit',EDITED_ANSWER,'?edit='+first_turn['id']).status_code==302
    job.refresh_from_db();review=job.teacher_review
    assert review.state['status']=='asking' and not review.state['error'],review.state
    assert len(review.state['turns'])==2
    assert review.state['turns'][1]['id']==second_turn['id'] and review.state['turns'][1]['answer'] is None
    current=BeautifulSoup(c.get(url).content,'html.parser')
    assert current.textarea.get_text()==PENDING_ANSWER
    assert current.find('input',attrs={'name':'turn_id'})['value']==second_turn['id']
    assert [h['answer'] for h in review.state['turns'][0]['answer_history']]==[FIRST_ANSWER,EDITED_ANSWER]
    for _ in range(5):
        assert post_form('skip','').status_code==302
    job.refresh_from_db()
    assert len(job.teacher_review.state['turns'])==6
    assert job.teacher_review.state['status']=='needs_input',job.teacher_review.state
    blocked=c.post(reverse('tutor-import-approve',args=[job.pk]),{'csrfmiddlewaretoken':c.cookies['csrftoken'].value,'expected_version':job.get_interpretation_dossier().version,'confirm_approval':'1','confirm_pending_items':'1'})
    assert blocked.status_code in (400,409)
    resolved=complete_job(teacher,pdf)
    assert not unresolved(resolved.get_interpretation_dossier()), [(i['scope'],i['field_name'],i['operational_state']) for i in unresolved(resolved.get_interpretation_dossier())]
    r=open_review(resolved)
    r=advance_review(job_id=resolved.pk,user=teacher,expected_revision=r.revision,expected_version=r.dossier_version)
    assert r.state['status']=='complete'
    assert len(provider.contexts)==8
    approval_url=reverse('tutor-import-approve',args=[resolved.pk])
    fields={'csrfmiddlewaretoken':c.cookies['csrftoken'].value,'expected_version':resolved.get_interpretation_dossier().version}
    assert c.post(approval_url,fields).status_code in (400,409)
    approval=c.post(approval_url,{**fields,'confirm_approval':'1'})
    assert approval.status_code==302,approval.content
    resolved.refresh_from_db();assert resolved.is_approved
