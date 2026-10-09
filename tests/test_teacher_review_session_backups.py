"""New cross-tab HTTP counterexample using one authenticated browser session."""
import copy
import uuid
import pytest
from bs4 import BeautifulSoup
from django.test import Client
from django.urls import reverse
from test_teacher_review import ready_job, start, save, advance, ask_first, apply_and_next

pytestmark = pytest.mark.django_db


def test_source_conflicts_for_distinct_turns_keep_both_literal_backups(ready_job, monkeypatch):
    first_tab, user, job = ready_job
    review = advance(save(start(job, user, ask_first), user, 'Original saved value'), user, apply_and_next)
    edited, pending = review.state['turns']
    before = copy.deepcopy(review.state)
    second_tab = Client()
    second_tab.cookies = first_tab.cookies.copy()  # Same browser session, unlike separate force_login calls.
    assert second_tab.session.session_key == first_tab.session.session_key
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',
                        lambda: pytest.fail('Source conflict must not construct a provider'))
    with job.pdf.open('ab') as stream:
        stream.write(b'\n% synthetic source changed after opening both forms')
    url = reverse('tutor-import-interpretation', args=[job.pk])
    common = {'expected_version':review.dossier_version,'expected_revision':review.revision,
              'draft_epoch':review.draft_epoch}
    first_text = '  Respuesta pendiente de la segunda pregunta.\n'
    second_text = '  Corrección pendiente de la primera pregunta.\n'
    one = first_tab.post(url,{**common,'action':'answer','turn_id':pending['id'],
                            'receipt':str(uuid.uuid4()),'answer':first_text})
    assert one.status_code == 409
    assert BeautifulSoup(one.content,'html.parser').find('textarea').get_text() == first_text
    two = second_tab.post(url,{**common,'action':'edit','turn_id':edited['id'],
                             'receipt':str(uuid.uuid4()),'answer':second_text})
    assert two.status_code == 409
    assert BeautifulSoup(two.content,'html.parser').find('textarea').get_text() == second_text
    review.refresh_from_db()
    assert review.state == before
    one_again = first_tab.get(url + f'?edit={pending["id"]}')
    assert one_again.status_code == 409
    assert BeautifulSoup(one_again.content,'html.parser').find('textarea').get_text() == first_text


def _two_turn_conflicts(ready_job, monkeypatch, *, legacy=False):
    client, user, job = ready_job
    review = advance(save(start(job, user, ask_first), user, 'Original saved value'), user, apply_and_next)
    edited, pending = review.state['turns']
    with job.pdf.open('rb') as stream:
        source = stream.read()
    with job.pdf.open('ab') as stream:
        stream.write(b'\n% synthetic source conflict')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',
                        lambda: pytest.fail('Source conflict must not construct a provider'))
    url = reverse('tutor-import-interpretation', args=[job.pk])
    texts = {edited['id']: '  Corrección sin guardar.\n', pending['id']: '  Respuesta sin guardar.\n'}
    common = {'expected_version':review.dossier_version,'expected_revision':review.revision,
              'draft_epoch':review.draft_epoch}
    if legacy:
        session = client.session
        session[f'teacher-review-draft-{job.pk}'] = {'turn_id':edited['id'],
            'text':texts[edited['id']],'mode':'edit'}
        session.save()
    else:
        assert client.post(url, {**common,'action':'edit','turn_id':edited['id'],
            'receipt':str(uuid.uuid4()),'answer':texts[edited['id']]}).status_code == 409
    assert client.post(url, {**common,'action':'answer','turn_id':pending['id'],
        'receipt':str(uuid.uuid4()),'answer':texts[pending['id']]}).status_code == 409
    return client, user, job, review, url, source, texts


@pytest.mark.parametrize('legacy', [False, True])
def test_backups_reopen_for_each_original_turn_without_applying(ready_job, monkeypatch, legacy):
    client, _, job, review, url, source, texts = _two_turn_conflicts(ready_job, monkeypatch, legacy=legacy)
    before = copy.deepcopy(review.state)
    backups = client.session[f'teacher-review-draft-{job.pk}']['drafts']
    assert {key:row['text'] for key,row in backups.items()} == texts
    for turn_id, text in texts.items():
        response = client.get(url + f'?edit={turn_id}')
        assert response.status_code == 409
        page = BeautifulSoup(response.content,'html.parser')
        assert page.find('textarea').get_text() == text
        assert page.find('textarea').has_attr('readonly')
        assert any(link.get('href') == url + f'?edit={turn_id}' for link in page.find_all('a'))
    with job.pdf.open('wb') as stream:
        stream.write(source)
    for turn_id, text in texts.items():
        response = client.get(url + f'?edit={turn_id}')
        assert response.status_code == 200
        form = BeautifulSoup(response.content,'html.parser').find('form',id='teacher-answer-form')
        assert form.find('textarea').get_text() == text
        assert form.find('input',attrs={'name':'turn_id'})['value'] == turn_id
    review.refresh_from_db()
    assert review.state == before
    assert review.generation_token is None
    assert not job.is_approved


@pytest.mark.parametrize('action', ['save_draft', 'discard_draft', 'edit'])
def test_successful_action_clears_only_its_own_backup(ready_job, monkeypatch, action):
    client, _, job, review, url, source, texts = _two_turn_conflicts(ready_job, monkeypatch)
    edited, pending = review.state['turns']
    with job.pdf.open('wb') as stream:
        stream.write(source)
    # The explicit answer edit may request one declared no-op double; no real provider.
    calls=[]
    def provider(context):
        calls.append(context)
        return {'question':None,'targets':[],'answer_updates':[]}
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',lambda:provider)
    data = {'expected_version':review.dossier_version,'expected_revision':review.revision,
        'draft_epoch':review.draft_epoch,'action':action,'turn_id':edited['id'],
        'receipt':str(uuid.uuid4()),'answer':texts[edited['id']],'draft_mode':'edit'}
    response=client.post(url,data)
    assert response.status_code == (200 if action == 'save_draft' else 302)
    backups=client.session[f'teacher-review-draft-{job.pk}']['drafts']
    assert set(backups)=={pending['id']}
    assert backups[pending['id']]['text']==texts[pending['id']]
    assert len(calls)==(1 if action=='edit' else 0)
    response=client.get(url)
    assert BeautifulSoup(response.content,'html.parser').find('textarea').get_text()==texts[pending['id']]


@pytest.mark.parametrize('explicit', ['unknown', 'known_without_backup'])
def test_explicit_turn_without_backup_never_shows_another_turn_text(ready_job, monkeypatch, explicit):
    client, _, job, review, url, _, texts=_two_turn_conflicts(ready_job,monkeypatch)
    edited,pending=review.state['turns']
    session=client.session
    backups=session[f'teacher-review-draft-{job.pk}']['drafts']
    backups.pop(edited['id'])
    session[f'teacher-review-draft-{job.pk}']={'drafts':backups}
    session.save()
    turn_id='nonexistent-turn' if explicit=='unknown' else edited['id']
    response=client.get(url + f'?edit={turn_id}')
    # Preserve the existing no-backup GET route to source recovery.
    assert response.status_code==302
    assert response.url==reverse('tutor-import-wait',args=[job.pk])
    assert BeautifulSoup(response.content,'html.parser').find('textarea') is None
    assert texts[pending['id']].encode() not in response.content
    assert client.session[f'teacher-review-draft-{job.pk}']['drafts']==backups


def test_legacy_backup_is_read_without_rewriting_session_on_get(ready_job,monkeypatch):
    client,user,job=ready_job
    review=start(job,user,ask_first)
    turn=review.state['turns'][0]
    original={'turn_id':turn['id'],'text':'  Respaldo plano previo.\n','mode':'answer'}
    session=client.session; session[f'teacher-review-draft-{job.pk}']=original; session.save()
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',lambda:pytest.fail('GET provider'))
    response=client.get(reverse('tutor-import-interpretation',args=[job.pk]))
    assert BeautifulSoup(response.content,'html.parser').find('textarea').get_text()==original['text']
    assert client.session[f'teacher-review-draft-{job.pk}']==original


def test_session_backups_are_bounded_to_persisted_turns_and_answer_size(ready_job,monkeypatch):
    from curriculum.teacher_review import MAX_ANSWER,MAX_QUESTIONS
    client,user,job=ready_job
    review=start(job,user,ask_first)
    prototype=review.state['turns'][0]
    # Six declared persisted synthetic questions, not six provider executions.
    review.state['turns']=[{**copy.deepcopy(prototype),'id':str(uuid.uuid4()),
        'answer':'Prior answer' if index<MAX_QUESTIONS-1 else None}
        for index in range(MAX_QUESTIONS)]
    review.save(update_fields=['state'])
    with job.pdf.open('ab') as stream:stream.write(b'\n% source conflict')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider',lambda:pytest.fail('Provider forbidden'))
    url=reverse('tutor-import-interpretation',args=[job.pk])
    data={'action':'edit','expected_version':review.dossier_version,'expected_revision':review.revision,
          'draft_epoch':review.draft_epoch,'receipt':str(uuid.uuid4())}
    for index,turn in enumerate(review.state['turns']):
        text=str(index)+'x'*(MAX_ANSWER-1)
        assert client.post(url,{**data,'turn_id':turn['id'],'answer':text}).status_code==409
    backups=client.session[f'teacher-review-draft-{job.pk}']['drafts']
    assert len(backups)==MAX_QUESTIONS
    assert sum(len(row['text']) for row in backups.values())==MAX_QUESTIONS*MAX_ANSWER
    for change in ({'turn_id':'foreign-turn','answer':'No backup'},
                   {'turn_id':review.state['turns'][0]['id'],'answer':'x'*(MAX_ANSWER+1)}):
        assert client.post(url,{**data,**change}).status_code==409
        assert client.session[f'teacher-review-draft-{job.pk}']['drafts']==backups
