"""Test-only generated data/provider. Never configure this in application settings."""
import copy
import hashlib
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from curriculum.models import CurriculumImportJob
from curriculum.source_interpreter import ImportDossier, InterpretedField, SessionPlan, REQUIRED_GENERAL_FIELDS, REQUIRED_SESSION_FIELDS, STATUS_MISSING, resolve
from test_t15_curriculum_import import make_minimal_pdf

USERNAME='onebox-ci-teacher'
PASSWORD='onebox-ci-test-only'
FIRST_ANSWER='  Acuerdo docente literal\nSegunda línea.\n'
EDITED_ANSWER='  Acuerdo docente corregido\nSin perder saltos.\n'
PENDING_ANSWER='Borrador pendiente de la segunda pregunta'

def generated_pdf():
    return make_minimal_pdf([
        'Proyecto: Lectura sintetica\nGrado: 3ro\nSESION 1: Primera lectura\nInicio: Observar el texto.\nDesarrollo: Leer y comentar.\nCierre: Compartir una idea.\nUsar Anexo 1.',
        'SESION 2: Segunda lectura\nInicio: Recuperar ideas.\nDesarrollo: Comparar dos frases.\nCierre: Escribir una conclusion.\nANEXO 1\nLAMINA SINTETICA UNICA CI',
    ])

class SyntheticAdaptiveProvider:
    """Pure deterministic test double; records every complete source context."""
    def __init__(self): self.contexts=[]
    def __call__(self,context):
        self.contexts.append(copy.deepcopy(context))
        answered=[t for t in context['turns'] if t['answer'] is not None and not t['skipped']]
        updates=[{'turn_id':t['id'],'target_id':target,'quote':t['answer']}
                 for t in answered for target in t['eligible_targets']]
        asked={target for t in context['turns'] for target in t['targets']}
        candidates=[t for t in context['missing_fields'] if t['target_id'] not in asked and t.get('field_name') and t['scope']!='annex']
        if not context['turns']:
            candidates.sort(key=lambda t:t['field_name']!='proposito')
        if any(t['answer'] is None for t in context['turns']) or context['questions_remaining']==0 or not candidates:
            return {'question':None,'targets':[],'answer_updates':updates}
        target=candidates[0]
        prefix=('A partir de '+answered[-1]['answer'].strip()+', ') if answered else ''
        return {'question':f"{prefix}pregunta sintética {len(context['turns'])+1}: {target['human_label']}",
                'targets':[target['target_id']],'answer_updates':updates}

def configure(settings,monkeypatch):
    settings.AULALISTA_IMPORT_ASYNC=False
    settings.AULALISTA_GEMINI_LIVE_ENABLED=False
    # Both provider selection and transport boundaries are fail-closed locally.
    settings.AULALISTA_TEACHER_REVIEW_PROVIDER='test-only-not-registered'
    provider=SyntheticAdaptiveProvider()
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',lambda:provider)
    def live_forbidden(*args,**kwargs):
        raise AssertionError('This CI suite must not call any live inference transport')
    monkeypatch.setattr('curriculum.gemini_review_provider.GeminiHighAgyProvider.__call__',live_forbidden)
    monkeypatch.setattr('curriculum.curriculum_import.chat_json',live_forbidden)
    teacher=get_user_model().objects.create_user(username=USERNAME,password=PASSWORD,is_staff=True)
    teacher.user_permissions.add(Permission.objects.get(codename='access_admin'))
    return teacher,provider

def complete_job(teacher,pdf):
    job=CurriculumImportJob.objects.create(created_by=teacher,pdf=SimpleUploadedFile('complete-synthetic.pdf',pdf,content_type='application/pdf'))
    fields={name:InterpretedField(name,'',status=STATUS_MISSING) for name in REQUIRED_GENERAL_FIELDS | {'metodologia','escenario_proyecto','grado','duracion_proyecto'}}
    sessions=[SessionPlan(f'complete-{n}',n,f'Sesión de aprobación {n}',pages=[n],fields={name:InterpretedField(name,'',status=STATUS_MISSING) for name in REQUIRED_SESSION_FIELDS | {'materiales','evaluacion','contexto_ejecucion'}}) for n in (1,2)]
    dossier=ImportDossier(source_sha256=hashlib.sha256(pdf).hexdigest(),source_name='complete-synthetic.pdf',page_count=2,general_fields=fields,sessions=sessions)
    dossier=resolve(dossier,{'general_fields':{name:['Lenguajes'] if name=='campos_formativos' else 'Confirmado por docente' for name in fields}},actor=teacher.username,pdf_source=job.pdf)
    for session in sessions:
        dossier=resolve(dossier,{'session_id':session.session_id,'session_fields':{name:'Confirmado por docente' for name in session.fields}},actor=teacher.username,pdf_source=job.pdf)
    assert job.save_interpretation_dossier(dossier)=='ready'
    return job
