"""Four narrow settings-only availability regressions. Explicit provider doubles only."""
import uuid

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse

from curriculum.models import CurriculumTeacherReview
from test_teacher_review import ready_job, start, save, advance, ask_first, apply_and_next

pytestmark = pytest.mark.django_db


def _form(response):
    soup = BeautifulSoup(response.content, 'html.parser')
    form = soup.find('form', id='teacher-answer-form')
    assert form is not None
    data = {node['name']: node.get('value', '') for node in form.find_all('input')}
    return soup, form, data


def _no_runtime(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Availability display must not construct/call provider, preflight, or metadata')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider', forbidden)
    monkeypatch.setattr('curriculum.gemini_review_provider.GeminiHighAgyProvider.preflight', forbidden)
    monkeypatch.setattr('curriculum.gemini_review_provider._metadata', forbidden)


def _disabled(settings):
    settings.AULALISTA_TEACHER_REVIEW_PROVIDER = 'gemini'
    settings.AULALISTA_GEMINI_LIVE_ENABLED = False
    settings.AULALISTA_GEMINI_AGY_LAUNCHER = ''
    settings.AULALISTA_GEMINI_AGY_AGENT_FILE = ''


def test_fresh_availability_notice_reads_settings_only_and_never_claims_validation(ready_job, settings, monkeypatch):
    client, user, job = ready_job
    _no_runtime(monkeypatch)
    url = reverse('tutor-import-interpretation', args=[job.pk])
    cases = [
        ('', False, '', '', 'provider_not_configured'),
        ('gemini', False, '', '', 'gemini_live_not_enabled'),
        ('gemini', True, '', '', 'gemini_route_not_configured'),
        ('gemini', True, '/synthetic-not-executed/launcher', '/synthetic-not-executed/agent.md', 'provider_configured_unverified'),
    ]
    for provider, live, launcher, agent, code in cases:
        settings.AULALISTA_TEACHER_REVIEW_PROVIDER = provider
        settings.AULALISTA_GEMINI_LIVE_ENABLED = live
        settings.AULALISTA_GEMINI_AGY_LAUNCHER = launcher
        settings.AULALISTA_GEMINI_AGY_AGENT_FILE = agent
        response = client.get(url)
        assert response.status_code == 200
        notice = response.context['provider_notice']
        assert notice['code'] == code
        assert notice['message'].strip()
        visible = BeautifulSoup(response.content, 'html.parser').find(id='provider-configuration-status')
        assert visible is not None and visible.get_text(strip=True)
        assert visible.get('data-provider-status') == code
        if code == 'provider_configured_unverified':
            words = notice['message'].lower()
            assert ('sin' in words or 'no ' in words) and ('valid' in words or 'comproba' in words or 'comprueba' in words)
    review = CurriculumTeacherReview.objects.get(job=job)
    assert review.state['status'] == 'new' and review.state['turns'] == []
    assert review.generation_token is None
    assert not job.is_approved


def test_disabled_provider_keeps_pending_and_edit_drafts_in_usable_one_box(ready_job, settings, monkeypatch):
    client, user, job = ready_job
    review = advance(save(start(job, user, ask_first), user, 'Stored literal answer'), user, apply_and_next)
    first, pending = review.state['turns']
    _disabled(settings)
    _no_runtime(monkeypatch)
    url = reverse('tutor-import-interpretation', args=[job.pk])
    for suffix, text, turn_id in [('', 'Pending durable draft', pending['id']),
                                  (f'?edit={first["id"]}', 'Editable durable correction', first['id'])]:
        _, form, data = _form(client.get(url + suffix))
        assert client.post(url, {**data, 'action': 'save_draft', 'answer': text}).status_code == 200
        response = client.get(url + suffix)
        soup, form, data = _form(response)
        assert len(soup.find_all('textarea')) == 1
        assert form.find('textarea').text == text
        assert data['turn_id'] == turn_id
        assert not form.find('button', {'value': 'edit' if suffix else 'answer'}).has_attr('disabled')
        assert response.context['provider_notice']['code'] == 'gemini_live_not_enabled'
        assert soup.find(id='provider-configuration-status') is not None
    assert _form(client.get(url))[1].find('textarea').text == 'Pending durable draft'
    review.refresh_from_db()
    assert review.state['turns'][0]['answer'] == 'Stored literal answer'
    assert review.state['turns'][1]['answer'] is None
    assert review.generation_token is None


def test_disabled_continuation_still_saves_answers_and_corrections(ready_job, settings, monkeypatch, tmp_path):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    _disabled(settings)
    settings.AULALISTA_GEMINI_ATTEMPT_DIR = str(tmp_path / 'must-not-be-created')
    monkeypatch.setattr('curriculum.gemini_review_provider.GeminiHighAgyProvider.preflight',
                        lambda *a, **k: pytest.fail('Live-disabled provider must not run preflight'))
    url = reverse('tutor-import-interpretation', args=[job.pk])
    turn_id = review.state['turns'][0]['id']
    for action, suffix, text in [('answer', '', '  Saved literal answer.\n'),
                                 ('edit', f'?edit={turn_id}', '  Saved literal correction.\n')]:
        _, _, data = _form(client.get(url + suffix))
        response = client.post(url, {**data, 'action': action, 'answer': text})
        assert response.status_code == 302
        review.refresh_from_db()
        assert review.state['turns'][0]['answer'] == text
        assert review.state['error'] == 'gemini_live_not_enabled'
        assert review.generation_token is None
        page = client.get(url)
        assert page.context['provider_notice']['code'] == 'gemini_live_not_enabled'
        assert text.strip() in page.content.decode()
    assert len(review.state['turns'][0]['answer_history']) == 2
    assert not (tmp_path / 'must-not-be-created').exists()
    job.refresh_from_db()
    assert not job.is_approved


def test_unknown_result_notice_has_priority_and_remains_blocked(ready_job, settings, monkeypatch):
    client, user, job = ready_job
    review = save(start(job, user, ask_first), user, 'Retained answer before unknown result')
    settings.AULALISTA_TEACHER_REVIEW_PROVIDER = 'gemini'
    settings.AULALISTA_GEMINI_LIVE_ENABLED = True
    settings.AULALISTA_GEMINI_AGY_LAUNCHER = '/synthetic-not-executed/launcher'
    settings.AULALISTA_GEMINI_AGY_AGENT_FILE = '/synthetic-not-executed/agent.md'
    _no_runtime(monkeypatch)
    url = reverse('tutor-import-interpretation', args=[job.pk])
    for code in ('gemini_attempt_unknown', 'gemini_prior_attempt_unknown'):
        review.state.update(status='pending', error=code)
        review.save(update_fields=['state'])
        response = client.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        assert soup.find(id='provider-configuration-status') is None
        assert soup.find('button', {'value': 'continue'}) is None
        assert 'pendientes de conciliación' in soup.get_text()
        rejected = client.post(url, {'action': 'continue', 'expected_revision': review.revision,
                                     'expected_version': review.dossier_version})
        assert rejected.status_code == 409
        review.refresh_from_db()
        assert review.state['error'] == code
        assert review.state['turns'][0]['answer'] == 'Retained answer before unknown result'
        assert review.generation_token is None
