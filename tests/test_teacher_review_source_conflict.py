"""New synthetic HTTP boundary probe; no provider or private source input."""
import copy
import uuid
import pytest
from bs4 import BeautifulSoup
from django.urls import reverse
from test_teacher_review import ready_job, start, save, ask_first

pytestmark = pytest.mark.django_db

@pytest.mark.parametrize('action', ['answer', 'skip', 'edit'])
def test_source_conflict_keeps_submitted_answer(ready_job, monkeypatch, action):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    if action == 'edit':
        review = save(review, user, 'Original saved answer')
    turn = review.state['turns'][0]
    before = copy.deepcopy(review.state)
    literal = '  Texto docente pendiente: <script>nunca_ejecutar()</script>\n'
    with job.pdf.open('ab') as stream:
        stream.write(b'\n% synthetic source changed after opening the form')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',
                        lambda: pytest.fail('No provider may be constructed'))
    url = reverse('tutor-import-interpretation', args=[job.pk])
    response = client.post(url, {'action': action, 'expected_version': review.dossier_version,
        'expected_revision': review.revision, 'draft_epoch': review.draft_epoch,
        'receipt': str(uuid.uuid4()), 'turn_id': turn['id'], 'answer': literal})
    assert response.status_code == 409
    review.refresh_from_db()
    assert review.state == before
    assert not job.is_approved
    backup = client.session.get(f'teacher-review-draft-{job.pk}')
    assert backup and backup['drafts'][turn['id']]['text'] == literal
    area = BeautifulSoup(response.content, 'html.parser').find('textarea')
    assert area and area.get_text() == literal and area.has_attr('readonly')
    assert b'<script>nunca_ejecutar()</script>' not in response.content
    reopened = client.get(url)
    assert reopened.status_code == 409
    assert BeautifulSoup(reopened.content, 'html.parser').find('textarea').get_text() == literal


def test_preserved_answer_is_visible_after_source_restored_without_applying_it(ready_job, monkeypatch):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    turn = review.state['turns'][0]
    before = copy.deepcopy(review.state)
    with job.pdf.open('rb') as stream:
        original_source = stream.read()
    with job.pdf.open('ab') as stream:
        stream.write(b'\n% synthetic source changed')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',
                        lambda: pytest.fail('Recovery views must not construct a provider'))
    url = reverse('tutor-import-interpretation', args=[job.pk])
    literal = '  Respuesta que requiere un nuevo envío explícito.\n'
    response = client.post(url, {'action': 'answer', 'expected_version': review.dossier_version,
        'expected_revision': review.revision, 'draft_epoch': review.draft_epoch,
        'receipt': str(uuid.uuid4()), 'turn_id': turn['id'], 'answer': literal})
    assert response.status_code == 409
    with job.pdf.open('wb') as stream:
        stream.write(original_source)
    response = client.get(url + f'?edit={turn["id"]}')
    assert response.status_code == 200
    page = BeautifulSoup(response.content, 'html.parser')
    form = page.find('form', id='teacher-answer-form')
    assert form.find('textarea').get_text() == literal
    assert form.find('input', attrs={'name': 'turn_id'})['value'] == turn['id']
    review.refresh_from_db()
    assert review.state == before
    assert review.generation_token is None


def test_answer_conflict_does_not_hide_or_replace_separate_purpose_backup(ready_job, monkeypatch):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    turn = review.state['turns'][0]
    purpose = {'turn_id': 'purpose-review', 'text': 'Propósito anterior conservado.', 'mode': 'purpose'}
    session = client.session
    session[f'teacher-review-purpose-draft-{job.pk}'] = purpose
    session.save()
    with job.pdf.open('ab') as stream:
        stream.write(b'\n% synthetic source changed')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',
                        lambda: pytest.fail('Conflict views must not construct a provider'))
    url = reverse('tutor-import-interpretation', args=[job.pk])
    literal = 'Respuesta actual conservada.'
    response = client.post(url, {'action': 'answer', 'expected_version': review.dossier_version,
        'expected_revision': review.revision, 'draft_epoch': review.draft_epoch,
        'receipt': str(uuid.uuid4()), 'turn_id': turn['id'], 'answer': literal})
    page = BeautifulSoup(response.content, 'html.parser')
    assert page.find('textarea', id='preserved-answer').get_text() == literal
    assert page.find('textarea', id='preserved-purpose') is None
    assert client.session[f'teacher-review-purpose-draft-{job.pk}'] == purpose
    response = client.get(url + '?edit_purpose=1')
    page = BeautifulSoup(response.content, 'html.parser')
    assert page.find('textarea', id='preserved-purpose').get_text() == purpose['text']
    assert client.session[f'teacher-review-draft-{job.pk}']['drafts'][turn['id']]['text'] == literal


@pytest.mark.parametrize('invalid', ['turn', 'oversize', 'duplicate', 'extra_field'])
def test_source_conflict_does_not_backup_invalid_submissions(ready_job, monkeypatch, invalid):
    from curriculum.teacher_review import MAX_ANSWER
    client, user, job = ready_job
    review = start(job, user, ask_first)
    before = copy.deepcopy(review.state)
    with job.pdf.open('ab') as stream:
        stream.write(b'\n% synthetic source changed')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',
                        lambda: pytest.fail('Invalid input must not construct a provider'))
    data = {'action': 'answer', 'expected_version': review.dossier_version,
        'expected_revision': review.revision, 'draft_epoch': review.draft_epoch,
        'receipt': str(uuid.uuid4()), 'turn_id': review.state['turns'][0]['id'], 'answer': 'Untrusted input'}
    if invalid == 'turn':
        data['turn_id'] = 'not-a-persisted-turn'
    elif invalid == 'oversize':
        data['answer'] = 'x' * (MAX_ANSWER + 1)
    elif invalid == 'duplicate':
        data['answer'] = ['First text', 'Second text']
    else:
        data['unapproved_field'] = 'unexpected'
    response = client.post(reverse('tutor-import-interpretation', args=[job.pk]), data)
    assert response.status_code == (400 if invalid in ('duplicate', 'extra_field') else 409)
    assert not client.session.get(f'teacher-review-draft-{job.pk}')
    assert BeautifulSoup(response.content, 'html.parser').find('textarea') is None
    review.refresh_from_db()
    assert review.state == before


def test_source_conflict_backup_still_requires_owner_and_csrf(ready_job, monkeypatch):
    from django.test import Client
    from helpers import tutor_client
    client, user, job = ready_job
    review = start(job, user, ask_first)
    with job.pdf.open('ab') as stream:
        stream.write(b'\n% synthetic source changed')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',
                        lambda: pytest.fail('Rejected auth must not construct a provider'))
    url = reverse('tutor-import-interpretation', args=[job.pk])
    data = {'action': 'answer', 'expected_version': review.dossier_version,
        'expected_revision': review.revision, 'draft_epoch': review.draft_epoch,
        'receipt': str(uuid.uuid4()), 'turn_id': review.state['turns'][0]['id'], 'answer': 'Private synthetic text'}
    other = tutor_client()
    assert other.post(url, data).status_code == 404
    assert other.get(url).status_code == 404
    assert not other.session.get(f'teacher-review-draft-{job.pk}')
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    assert strict.post(url, data).status_code == 403
    assert not strict.session.get(f'teacher-review-draft-{job.pk}')
