"""Mac browser acceptance of one uploaded PDF, with an explicit Pi call double."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from curriculum.models import CurriculumImportJob, CurriculumTeacherReview, CurriculumPackage, PublishedPackageSnapshot, ClassroomSession
from curriculum.pi_review_provider import PiReply
from curriculum.source_interpreter import ImportDossier, derive_operational_queue
from curriculum.teacher_review import open_review, save_local_draft
from curriculum.teacher_review_context import restore_provider_context
from test_t15_curriculum_import import make_minimal_pdf


@pytest.mark.browser
@pytest.mark.django_db(transaction=True)
def test_browser_same_uploaded_document_reopens_and_approves(settings, monkeypatch, tmp_path, request):
    chrome=os.environ.get('TEACHER_REVIEW_CHROME') or shutil.which('google-chrome')
    assert chrome and Path(chrome).is_file(), 'Installed Chrome required for this acceptance'
    for name in ('AULALISTA_PI_LIVE_ENABLED','AULALISTA_LUNA_LIVE_ENABLED','AULALISTA_GEMINI_LIVE_ENABLED'):
        setattr(settings,name,False)
    settings.AULALISTA_IMPORT_ASYNC=False
    settings.AULALISTA_TEACHER_REVIEW_PROVIDER='pi_luna'
    settings.AULALISTA_PI_ATTEMPT_DIR=str(tmp_path/'no-real-attempts')
    teacher=get_user_model().objects.create_user(username='same-document-browser-teacher',password='invented-browser-fixture-only',is_staff=True)
    teacher.user_permissions.add(Permission.objects.get(codename='access_admin'))
    pdf=make_minimal_pdf([
        'Proyecto: Lectura sintetica\nGrado: 3ro\nSESION 1: Primera lectura\nInicio: Observar el texto.\nCierre: Compartir una idea.\nUsar Anexo 1.',
        'SESION 2: Segunda lectura\nInicio: Recuperar ideas.\nDesarrollo: Comparar dos frases.\nANEXO 1\nLAMINA SINTETICA DE ACEPTACION',
    ])
    pdf_path=tmp_path/'same-document-generated.pdf';pdf_path.write_bytes(pdf)
    values={'campos_formativos':'Lenguajes','proposito':'Comparar relatos de la comunidad.','finalidad':'Compartir una lectura con el grupo.','desarrollo':'Leer dos relatos y comparar sus personajes.','cierre':'Escribir una conclusion y compartirla.'}
    answers=['  Lenguajes\n','  Comparar relatos de la comunidad.\nCompartir una lectura con el grupo.\n','  Leer dos relatos y comparar sus personajes.\n','  Escribir una conclusion y compartirla.\n']
    # Historical broad questions remain accessible; they are not new output.
    frozen=json.loads((Path(__file__).parent/'fixtures/teacher_review/oversized_question_v1.json').read_text())
    legacy_context=restore_provider_context(frozen['context'])
    assert hashlib.sha256(pdf).hexdigest()==legacy_context['source_document']['source_sha256']
    legacy_job=CurriculumImportJob.objects.create(created_by=teacher,pdf=SimpleUploadedFile('legacy-synthetic.pdf',pdf,content_type='application/pdf'))
    assert legacy_job.save_interpretation_dossier(ImportDossier.from_dict(legacy_context['dossier']))=='ready'
    legacy_review=open_review(legacy_job)
    legacy_turn={'id':str(uuid.uuid4()),'question':frozen['response']['question'],'targets':frozen['response']['targets'],
        'answer':None,'skipped':False,'answer_history':[],'applied':[],
        'question_source_sha256':legacy_review.source_sha256}
    assert len(legacy_turn['targets'])==16
    legacy_review.state.update(status='asking',turns=[legacy_turn]);legacy_review.save(update_fields=['state'])
    legacy_draft='  Borrador histórico conservado\nSin respuesta enviada.\n'
    save_local_draft(job_id=legacy_job.pk,user=teacher,expected_revision=legacy_review.revision,
        expected_epoch=legacy_review.draft_epoch,turn_id=legacy_turn['id'],text=legacy_draft,mode='answer')
    contexts=[]
    def forbidden(*a,**k): raise AssertionError('OFF browser acceptance must not use real runtime or inference')
    def declared_pi_double(provider,context):
        assert not provider.live_enabled
        contexts.append(copy.deepcopy(context))
        job=CurriculumImportJob.objects.exclude(pk=legacy_job.pk).get(created_by=teacher)
        saved=CurriculumTeacherReview.objects.get(job=job)
        for turn in context['turns']:
            stored=next(t for t in saved.state['turns'] if t['id']==turn['id'])
            assert stored['answer']==turn['answer']
            assert stored['answer_history']==turn['answer_history']
        by_id={t['target_id']:t for t in context['all_targets']}
        updates=[]
        for turn in context['turns']:
            if turn['answer'] is None or turn['skipped']:continue
            for target in turn['eligible_targets']:
                quote=values[by_id[target]['field_name']]
                assert quote in turn['answer']
                updates.append({'turn_id':turn['id'],'target_id':target,'quote':quote})
        applied={u['target_id'] for u in updates}
        missing=[t for t in context['missing_fields'] if t['priority_state']=='requires_resolution' and t['target_id'] not in applied]
        group=[]
        if missing:
            remaining={t['target_id'] for t in missing}
            policy_group=next(g for g in context['question_policy']['groups'] if remaining.intersection(g['target_ids']))
            group=[by_id[t] for t in policy_group['target_ids'] if t in remaining][:3]
        return PiReply({'question':'Pregunta sintética: '+', '.join(t['human_label'] for t in group) if group else None,'targets':[t['target_id'] for t in group],'answer_updates':updates},{'test_double':True,'live_inference':False,'call':len(contexts)})
    monkeypatch.setattr('curriculum.pi_review_provider.PiLunaProvider.__call__',declared_pi_double)
    monkeypatch.setattr('curriculum.pi_review_provider.PiLunaProvider._identity',forbidden)
    monkeypatch.setattr('curriculum.luna_review_provider.LunaCodexCliProvider.__call__',forbidden)
    monkeypatch.setattr('curriculum.gemini_review_provider.GeminiHighAgyProvider.__call__',forbidden)
    monkeypatch.setattr('curriculum.curriculum_import.chat_json',forbidden)
    live_server=request.getfixturevalue('live_server')
    evidence=Path(os.environ['TEACHER_REVIEW_EVIDENCE_DIR'])/'same-document';evidence.mkdir(parents=True,exist_ok=True)
    config={'baseUrl':live_server.url,'chrome':chrome,'profile':str(tmp_path/'fresh-chrome-profile'),'pdf':str(pdf_path),'evidenceDir':str(evidence),'username':teacher.username,'password':'invented-browser-fixture-only','answers':answers,
        'legacyReviewPath':reverse('tutor-import-interpretation',args=[legacy_job.pk]),'legacyQuestion':legacy_turn['question'],'legacyDraft':legacy_draft}
    node=shutil.which('node')
    assert node, 'Installed Node required for CDP acceptance'
    result=subprocess.run([node,str(Path(__file__).with_name('teacher_review_same_document_browser.mjs'))],input=json.dumps(config),text=True,capture_output=True,timeout=150)
    print(result.stdout)
    assert result.returncode==0,result.stdout+result.stderr
    job=CurriculumImportJob.objects.exclude(pk=legacy_job.pk).get(created_by=teacher);job.refresh_from_db()
    review=job.teacher_review;dossier=job.get_interpretation_dossier()
    assert job.is_approved and job.approvals.count()==1
    assert len(review.state['turns'])==4<=6
    assert derive_operational_queue(dossier).requires_resolution_count==0
    assert dossier.source_sha256==hashlib.sha256(pdf).hexdigest()
    for actual,expected in zip(review.state['turns'],answers):
        assert actual['answer']==expected.replace('\n','\r\n')
        assert actual['answer_history'][-1]['answer']==actual['answer']
    assert not review.draft_state
    assert CurriculumImportJob.objects.count()==2
    assert CurriculumPackage.objects.count()==1
    assert PublishedPackageSnapshot.objects.count()==ClassroomSession.objects.count()==0
    assert len(contexts)==5
    legacy_review.refresh_from_db()
    assert legacy_review.state['turns']==[legacy_turn]
    assert legacy_review.draft_state['drafts'][legacy_turn['id']]['text']==legacy_draft
    assert not legacy_job.approvals.exists()
    for context in contexts:
        assert len(context['dossier']['sessions'])==2
        assert context['source_document']['page_count']==2
        assert 'LAMINA SINTETICA DE ACEPTACION' in context['source_document']['pages'][1]['text']
    assert not (tmp_path/'no-real-attempts').exists()
    evidence.joinpath('same-document-server-checks.json').write_text(json.dumps({'live_inference':False,'provider':'production pi_luna selector with declared Pi call double','same_uploaded_job':True,'pdf_sha256':hashlib.sha256(pdf).hexdigest(),'questions':4,'new_authenticated_session_reopen':True,'literal_answers_saved':True,'human_role_confirmation':True,'approvals':1,'legacy_sixteen_target_question_and_saved_draft_preserved':True,'legacy_GET_provider_calls':0,'published_snapshots':0,'classroom_sessions':0},indent=2))
