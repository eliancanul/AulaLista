"""Same-turn source inference through public review forms, all transports OFF."""
import copy

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
import pytest

from curriculum.models import CurriculumImportJob, CurriculumTeacherReview
from curriculum.teacher_review import open_review
from helpers import tutor_client
from test_t15_curriculum_import import make_minimal_pdf
from test_learning_purpose import implicit_case
from test_teacher_review import ready_job

pytestmark = pytest.mark.django_db


def uploaded_case(*, explicit_purpose=None, missing_closure=False):
    client = tutor_client('learning-purpose-teacher')
    teacher = get_user_model().objects.get(pk=client.session['_auth_user_id'])
    candidate, document = implicit_case()
    pdf = make_minimal_pdf([document['pages'][0]['text'] + '\nCampos formativos: Lenguajes\n'
                           'Finalidad: Organizar una experiencia de observación.\n'
                           + (f'Propósito: {explicit_purpose}\n' if explicit_purpose else '')
                           + 'SESION 1: Observar\nInicio: Observar semillas.\n'
                           'Desarrollo: Comparar semillas.\n'
                           + ('' if missing_closure else 'Cierre: Compartir conclusiones.')])
    response = client.post(reverse('tutor-import-upload'), {
        'pdf': SimpleUploadedFile('purpose-synthetic.pdf', pdf, content_type='application/pdf')})
    assert response.status_code == 302
    job = CurriculumImportJob.objects.get(created_by=teacher)
    assert job.has_valid_ready_dossier()
    return client, teacher, job, candidate


def test_same_review_call_saves_inferred_purpose_without_question_or_approval(monkeypatch, settings):
    settings.AULALISTA_PI_LIVE_ENABLED = False
    settings.AULALISTA_LUNA_LIVE_ENABLED = False
    settings.AULALISTA_GEMINI_LIVE_ENABLED = False
    client, _, job, candidate = uploaded_case()
    original = copy.deepcopy(job.interpretation_dossier)
    assert not original['general_fields']['proposito']['value']
    seen = []
    def declared_double(context):
        seen.append(copy.deepcopy(context))
        return {'question': None, 'targets': [], 'answer_updates': [], 'purpose_proposal': candidate}
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider', lambda: declared_double)
    review = open_review(job)
    url = reverse('tutor-import-interpretation', args=[job.pk])
    response = client.post(url, {'action': 'continue', 'expected_revision': review.revision,
                                'expected_version': review.dossier_version})
    assert response.status_code == 302
    job.refresh_from_db(); review.refresh_from_db()
    purpose = job.get_interpretation_dossier().general_fields['proposito']
    assert purpose.value == 'Comparar tipos de semillas.'
    assert (purpose.origin, purpose.status, purpose.review) == ('proposed', 'ambiguous', 'pending')
    assert purpose.evidence and purpose.reason.startswith('Propuesta de aprendizaje:')
    assert review.state['turns'] == []
    assert review.state['error'] == ''
    assert review.state['purpose_assessments'][-1]['decision'] == 'proposed'
    assert not job.is_approved and not job.approvals.exists()
    assert seen[0]['purpose_policy']['eligible'] is True
    assert len(seen) == 1
    reopened = client.get(url)
    assert reopened.status_code == 200 and len(seen) == 1
    assert b'Propuesta de aprendizaje' in reopened.content
    assert b'requiere revisi' in reopened.content
    assert job.interpretation_dossier['source_sha256'] == original['source_sha256']
    assert job.interpretation_dossier['sessions'] == original['sessions']


def test_existing_explicit_purpose_does_not_need_inference_or_demonstration(monkeypatch):
    client, _, job, _ = uploaded_case(explicit_purpose='Identificar semillas del entorno.')
    original = job.get_interpretation_dossier().general_fields['proposito'].to_dict()
    assert original['origin'] == 'extracted'
    def forbidden():
        pytest.fail('No extra provider call when required data are already present')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider', forbidden)
    review = open_review(job)
    response = client.post(reverse('tutor-import-interpretation', args=[job.pk]), {
        'action': 'continue', 'expected_revision': review.revision, 'expected_version': review.dossier_version})
    assert response.status_code == 302
    job.refresh_from_db()
    assert job.get_interpretation_dossier().general_fields['proposito'].to_dict() == original


def test_human_answer_outranks_model_proposal_in_the_same_turn(ready_job):
    from test_teacher_review import start, save, advance, ask_first
    _, user, job = ready_job
    candidate, _ = implicit_case()
    review = start(job, user, ask_first)
    answer = 'Reconocer plantas del entorno.'
    review = save(review, user, answer)
    def double(context):
        turn = context['turns'][0]
        return {'question': None, 'targets': [], 'answer_updates': [{
            'turn_id': turn['id'], 'target_id': turn['targets'][0], 'quote': answer}],
            'purpose_proposal': candidate}
    review = advance(review, user, double)
    job.refresh_from_db()
    field = job.get_interpretation_dossier().general_fields['proposito']
    assert field.value == answer and field.origin == 'teacher_entered'
    assert review.state['turns'][0]['answer'] == answer
    assert review.state['purpose_assessments'][-1]['issues'] == ['current_purpose_retained']
    assert not job.is_approved


def test_inferred_purpose_requires_explicit_human_review_before_approval(monkeypatch):
    from curriculum.models import PublishedPackageSnapshot, ClassroomSession
    client, _, job, candidate = uploaded_case()
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider', lambda: lambda context: {
        'question': None, 'targets': [], 'answer_updates': [], 'purpose_proposal': candidate})
    review = open_review(job)
    url = reverse('tutor-import-interpretation', args=[job.pk])
    client.post(url, {'action': 'continue', 'expected_revision': review.revision,
                     'expected_version': review.dossier_version})
    job.refresh_from_db()
    page = client.get(url)
    assert page.context['can_approve'] is True
    approval_url = reverse('tutor-import-approve', args=[job.pk])
    data = {'expected_version': job.get_interpretation_dossier().version, 'confirm_approval': '1'}
    assert client.post(approval_url, data).status_code == 400
    assert not job.approvals.exists()
    assert client.post(approval_url, {**data, 'confirm_pending_items': '1'}).status_code == 302
    job.refresh_from_db()
    assert job.is_approved and job.approvals.count() == 1
    assert PublishedPackageSnapshot.objects.count() == ClassroomSession.objects.count() == 0


def proposed_case(monkeypatch, *, missing_closure=False):
    client, teacher, job, candidate = uploaded_case(missing_closure=missing_closure)
    calls = []
    def declared_double(context):
        calls.append(copy.deepcopy(context))
        target = next((item['target_id'] for item in context['all_targets']
                       if missing_closure and item['field_name'] == 'cierre'), None)
        return {'question': '¿Cómo cerrarán la actividad?' if target else None,
                'targets': [target] if target else [], 'answer_updates': [], 'purpose_proposal': candidate}
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider', lambda: declared_double)
    review = open_review(job)
    url = reverse('tutor-import-interpretation', args=[job.pk])
    assert client.post(url, {'action': 'continue', 'expected_revision': review.revision,
                            'expected_version': review.dossier_version}).status_code == 302
    job.refresh_from_db()
    return client, teacher, job, calls


def purpose_editor(client, job):
    from bs4 import BeautifulSoup
    url = reverse('tutor-import-interpretation', args=[job.pk])
    page = BeautifulSoup(client.get(url).content, 'html.parser')
    link = page.select_one('a[data-edit-purpose]')
    assert link is not None, 'The inferred purpose must have a visible review/correction route'
    response = client.get(url + link['href'])
    editor = BeautifulSoup(response.content, 'html.parser')
    assert len(editor.find_all('textarea')) == 1, 'Keep the single-box contract'
    form = editor.select_one('form[data-purpose-review]')
    assert form is not None
    data = {field['name']: field.get('value', '') for field in form.find_all('input')
            if field.get('type') != 'checkbox'}
    data['action'] = 'review_purpose'
    return url, editor, data


def test_teacher_can_visibly_correct_inferred_purpose_without_a_model_call(monkeypatch):
    from django.test import Client
    client, teacher, job, calls = proposed_case(monkeypatch)
    before = job.get_interpretation_dossier().general_fields['proposito'].to_dict()
    url, editor, data = purpose_editor(client, job)
    assert editor.textarea.get_text() == before['value']
    answer = '  Identificar diferencias entre semillas del entorno.\n'
    response = client.post(url, {**data, 'answer': answer, 'confirm_purpose_review': '1'})
    assert response.status_code == 302
    fresh = Client(); fresh.force_login(teacher)
    page = fresh.get(url)
    job.refresh_from_db()
    field = job.get_interpretation_dossier().general_fields['proposito']
    review = CurriculumTeacherReview.objects.get(job=job)
    assert field.value == answer.strip()
    assert (field.origin, field.review) == ('teacher_entered', 'corrected')
    assert field.original_value == before['value']
    assert [item.to_dict() for item in field.evidence] == before['evidence']
    assert review.state['purpose_reviews'][-1]['answer'] == answer
    assert review.state['turns'] == [] and len(calls) == 1
    assert answer.strip().encode() in page.content
    assert not job.is_approved and not job.approvals.exists()


def test_purpose_draft_survives_reopen_and_cancel_keeps_the_proposal(monkeypatch):
    from django.test import Client
    from bs4 import BeautifulSoup
    client, teacher, job, calls = proposed_case(monkeypatch)
    original = job.get_interpretation_dossier().general_fields['proposito'].to_dict()
    url, _, data = purpose_editor(client, job)
    draft = '  Borrador docente todavía sin confirmar.\n'
    saved = client.post(url + '?edit_purpose=1', {**data, 'action': 'save_draft', 'answer': draft})
    assert saved.status_code == 200 and saved.json()['saved'] is True
    fresh = Client(); fresh.force_login(teacher)
    reopened = BeautifulSoup(fresh.get(url + '?edit_purpose=1').content, 'html.parser')
    assert reopened.textarea.get_text() == draft
    form = reopened.select_one('form[data-purpose-review]')
    post = {field['name']: field.get('value', '') for field in form.find_all('input')
            if field.get('type') != 'checkbox'}
    assert fresh.post(url, {**post, 'action': 'discard_draft'}).status_code == 302
    job.refresh_from_db()
    assert job.get_interpretation_dossier().general_fields['proposito'].to_dict() == original
    _, editor, _ = purpose_editor(fresh, job)
    assert editor.textarea.get_text() == original['value']
    assert len(calls) == 1


@pytest.mark.parametrize('fault,expected', [('confirmation', 400), ('empty', 400), ('receipt', 400),
                                           ('version', 409), ('revision', 409), ('draft_epoch', 409)])
def test_purpose_review_rejects_unconfirmed_or_stale_submissions(monkeypatch, fault, expected):
    from bs4 import BeautifulSoup
    client, _, job, calls = proposed_case(monkeypatch)
    before = copy.deepcopy(job.interpretation_dossier)
    url, _, data = purpose_editor(client, job)
    data.update(answer='Comparar semillas mediante dibujos.', confirm_purpose_review='1')
    if fault == 'confirmation': data.pop('confirm_purpose_review')
    elif fault == 'empty': data['answer'] = '  '
    elif fault == 'receipt': data['receipt'] = 'invalid'
    elif fault == 'version': data['expected_version'] = int(data['expected_version']) - 1
    elif fault == 'revision': data['expected_revision'] = int(data['expected_revision']) + 1
    elif fault == 'draft_epoch': data['draft_epoch'] = int(data['draft_epoch']) + 1
    response = client.post(url, data)
    assert response.status_code == expected
    job.refresh_from_db()
    assert job.interpretation_dossier == before and not job.approvals.exists()
    assert len(calls) == 1
    page = BeautifulSoup(response.content, 'html.parser')
    assert page.textarea.get_text() == data['answer']


def test_explicit_purpose_confirmation_retains_inferred_origin_without_approving(monkeypatch):
    client, _, job, calls = proposed_case(monkeypatch)
    original = job.get_interpretation_dossier().general_fields['proposito'].to_dict()
    url, _, data = purpose_editor(client, job)
    data.update(answer=original['value'], confirm_purpose_review='1')
    assert client.post(url, data).status_code == 302
    job.refresh_from_db()
    purpose = job.get_interpretation_dossier().general_fields['proposito']
    assert purpose.value == original['value'] and purpose.origin == 'proposed'
    assert purpose.review == 'confirmed'
    assert not job.is_approved and not job.approvals.exists()
    assert len(calls) == 1


def test_replaying_a_purpose_review_does_not_duplicate_or_overwrite_it(monkeypatch):
    client, _, job, calls = proposed_case(monkeypatch)
    url, _, data = purpose_editor(client, job)
    data.update(answer='Distinguir rasgos de las semillas.', confirm_purpose_review='1')
    assert client.post(url, data).status_code == 302
    job.refresh_from_db()
    after = copy.deepcopy(job.interpretation_dossier)
    assert client.post(url, data).status_code == 302
    assert client.post(url, {**data, 'answer': 'Otro texto.'}).status_code == 409
    job.refresh_from_db()
    review = CurriculumTeacherReview.objects.get(job=job)
    assert job.interpretation_dossier == after
    assert len(review.state['purpose_reviews']) == 1
    assert not review.state['turns'] and len(calls) == 1


def test_purpose_review_preserves_pending_question_and_its_separate_draft(monkeypatch):
    from bs4 import BeautifulSoup
    client, _, job, calls = proposed_case(monkeypatch, missing_closure=True)
    url = reverse('tutor-import-interpretation', args=[job.pk])
    initial = BeautifulSoup(client.get(url).content, 'html.parser')
    form = initial.select_one('#teacher-answer-form')
    data = {field['name']: field.get('value', '') for field in form.find_all('input')}
    pending_text = '  Una respuesta de cierre todavía sin enviar.\n'
    assert client.post(url, {**data, 'action': 'save_draft', 'answer': pending_text}).status_code == 200
    before_turns = copy.deepcopy(CurriculumTeacherReview.objects.get(job=job).state['turns'])
    assert len(before_turns) == 1 and before_turns[0]['answer'] is None
    _, editor, correction = purpose_editor(client, job)
    assert editor.select_one('#teacher-answer-form').has_attr('data-purpose-review')
    assert not editor.select_one('form.review-approval')
    assert client.post(url, {**correction, 'answer': 'Describir diferencias entre las semillas.',
                            'confirm_purpose_review': '1'}).status_code == 302
    reopened = BeautifulSoup(client.get(url).content, 'html.parser')
    assert len(reopened.find_all('textarea')) == 1
    assert reopened.textarea.get_text() == pending_text
    assert CurriculumTeacherReview.objects.get(job=job).state['turns'] == before_turns
    assert len(calls) == 1


def test_rejected_purpose_text_survives_reload_after_another_tab_saves(monkeypatch):
    from django.test import Client
    from bs4 import BeautifulSoup
    client, teacher, job, calls = proposed_case(monkeypatch)
    url, _, data = purpose_editor(client, job)
    other = Client(); other.force_login(teacher)
    assert other.post(url, {**data, 'action': 'save_draft', 'answer': 'Borrador en otra pestaña.'}).status_code == 200
    rejected = '  Mi corrección que no debe perderse tras el conflicto.\n'
    response = client.post(url, {**data, 'answer': rejected, 'confirm_purpose_review': '1'})
    assert response.status_code == 409
    assert BeautifulSoup(response.content, 'html.parser').textarea.get_text() == rejected
    reopened = BeautifulSoup(client.get(url + '?edit_purpose=1').content, 'html.parser')
    assert reopened.textarea.get_text() == rejected
    assert len(calls) == 1


def test_purpose_autosave_does_not_erase_a_question_conflict_backup(monkeypatch):
    from django.test import Client
    from bs4 import BeautifulSoup
    client, teacher, job, calls = proposed_case(monkeypatch, missing_closure=True)
    url = reverse('tutor-import-interpretation', args=[job.pk])
    form = BeautifulSoup(client.get(url).content, 'html.parser').select_one('#teacher-answer-form')
    data = {field['name']: field.get('value', '') for field in form.find_all('input')}
    other = Client(); other.force_login(teacher)
    assert other.post(url, {**data, 'action': 'save_draft', 'answer': 'Borrador remoto de cierre.'}).status_code == 200
    rejected = '  Mi respuesta de cierre después del conflicto.\n'
    assert client.post(url, {**data, 'action': 'answer', 'answer': rejected}).status_code == 409
    _, _, purpose_data = purpose_editor(client, job)
    assert client.post(url, {**purpose_data, 'action': 'save_draft', 'answer': 'Borrador de propósito.'}).status_code == 200
    reopened = BeautifulSoup(client.get(url).content, 'html.parser')
    assert reopened.textarea.get_text() == rejected
    assert len(calls) == 1


def test_changed_physical_source_blocks_edit_but_retains_submitted_text(monkeypatch):
    from bs4 import BeautifulSoup
    client, _, job, calls = proposed_case(monkeypatch)
    url, _, data = purpose_editor(client, job)
    before = copy.deepcopy(job.interpretation_dossier)
    # A different immutable input must not receive a correction authorized for
    # the prior one. This is synthetic; no user PDF is read or replaced.
    job.pdf.save('changed-synthetic-source.pdf', SimpleUploadedFile('changed.pdf',
        make_minimal_pdf(['Proyecto: Otra fuente\nTexto diferente.'])), save=True)
    rejected = '  Conservar esta revisión aunque cambie la fuente.\n'
    response = client.post(url, {**data, 'answer': rejected, 'confirm_purpose_review': '1'})
    assert response.status_code == 409
    assert BeautifulSoup(response.content, 'html.parser').textarea.get_text() == rejected
    reopened = client.get(url + '?edit_purpose=1')
    assert reopened.status_code == 409
    assert BeautifulSoup(reopened.content, 'html.parser').textarea.get_text() == rejected
    job.refresh_from_db()
    assert job.interpretation_dossier == before and not job.approvals.exists()
    assert len(calls) == 1


def test_old_source_backup_remains_recoverable_after_valid_reextraction(monkeypatch):
    from bs4 import BeautifulSoup
    from curriculum.source_interpreter import CurriculumSourceInterpreter
    client, _, job, calls = proposed_case(monkeypatch)
    url, _, data = purpose_editor(client, job)
    new_pdf = make_minimal_pdf(['Proyecto: Nueva fuente\nPropósito: Leer relatos.\n'
        'Finalidad: Compartir lecturas.\nCampos formativos: Lenguajes\n'
        'SESION 1: Lectura\nInicio: Escuchar.\nDesarrollo: Leer.\nCierre: Comentar.'])
    job.pdf.save('new-source.pdf', SimpleUploadedFile('new-source.pdf', new_pdf), save=True)
    rejected = 'Texto conservado que pertenece a la fuente anterior.'
    assert client.post(url, {**data, 'answer': rejected, 'confirm_purpose_review': '1'}).status_code == 409
    assert job.save_interpretation_dossier(CurriculumSourceInterpreter.prepare(new_pdf)) == 'ready'
    current = copy.deepcopy(job.interpretation_dossier)
    recovery = client.get(url + '?edit_purpose=1')
    assert recovery.status_code == 409
    page = BeautifulSoup(recovery.content, 'html.parser')
    assert page.textarea.get_text() == rejected and page.textarea.has_attr('readonly')
    assert not page.find('form')
    current_page = BeautifulSoup(client.get(url).content, 'html.parser')
    assert current_page.select_one('a[data-recover-purpose]') is not None
    job.refresh_from_db()
    assert job.interpretation_dossier == current and len(calls) == 1
