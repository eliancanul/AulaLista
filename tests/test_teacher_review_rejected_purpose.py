"""Rejected-source proposal recovery: synthetic PDFs and declared doubles only."""
import copy

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse

from curriculum.models import CurriculumTeacherReview
from curriculum.pi_review_provider import PiReply
from curriculum.teacher_review import open_review
from test_teacher_review_learning_purpose import uploaded_case, purpose_editor

pytestmark = pytest.mark.django_db

RECEIPT = {'synthetic': True, 'attempt_id': 'known-fixture-attempt',
           'usage': {'input_tokens': 123, 'output_tokens': 17, 'total_tokens': 140}}


def rejected_case(monkeypatch, *, fault='quote', legacy=None, missing_closure=False):
    client, teacher, job, candidate = uploaded_case(missing_closure=missing_closure)
    if legacy:
        dossier = job.get_interpretation_dossier()
        if legacy == 'missing':
            dossier.general_fields.pop('proposito')
        elif legacy == 'null':
            dossier.general_fields['proposito'].value = None
        assert job.save_interpretation_dossier(dossier) == 'ready'
        assert job.has_valid_ready_dossier()
    if fault == 'quote':
        candidate['evidence'][0]['quote'] = 'Esta cita inventada no aparece en el PDF sintético.'
    elif fault == 'content':
        candidate['evidence'] = [item for item in candidate['evidence'] if item['role'] != 'content']
    elif fault == 'null':
        candidate = None
    calls = []
    def declared_double(context):
        calls.append(copy.deepcopy(context))
        return PiReply({'question': None, 'targets': [], 'answer_updates': [],
                        'purpose_proposal': candidate}, copy.deepcopy(RECEIPT))
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider', lambda: declared_double)
    review = open_review(job)
    url = reverse('tutor-import-interpretation', args=[job.pk])
    assert client.post(url, {'action': 'continue', 'expected_revision': review.revision,
                            'expected_version': review.dossier_version}).status_code == 302
    job.refresh_from_db(); review.refresh_from_db()
    return client, teacher, job, review, calls


@pytest.mark.parametrize('fault', ['quote', 'content'])
def test_rejected_proposal_is_active_recoverable_and_preserves_known_cost(monkeypatch, fault):
    client, _, job, review, calls = rejected_case(monkeypatch, fault=fault)
    assert review.state['status'] == 'needs_input'
    assert review.state['purpose_assessments'][-1]['decision'] == 'abstained'
    assert review.state['purpose_assessments'][-1]['issues']
    assert review.state['events'][-1]['provider_receipt'] == RECEIPT
    purpose = job.get_interpretation_dossier().general_fields['proposito']
    assert not purpose.value and not purpose.evidence and purpose.review == 'pending'
    assert review.state['turns'] == [] and not job.is_approved
    url = reverse('tutor-import-interpretation', args=[job.pk])
    original = copy.deepcopy(review.state)
    for _ in range(3):
        page = BeautifulSoup(client.get(url).content, 'html.parser')
        assert page.select_one('a[data-edit-purpose]') is not None
        assert page.select_one('[data-manual-recovery]') is not None
        assert page.select_one('button[value="continue"]') is None
    assert client.post(url, {'action': 'continue', 'expected_revision': review.revision,
                            'expected_version': review.dossier_version}).status_code == 302
    review.refresh_from_db()
    assert len(calls) == 1 and review.state == original


@pytest.mark.parametrize('fault', ['quote', 'content', 'null'])
def test_manual_completion_recovers_without_a_call_or_accepting_rejected_evidence(monkeypatch, fault):
    client, _, job, review, calls = rejected_case(monkeypatch, fault=fault)
    before = copy.deepcopy(review.state.get('purpose_assessments', []))
    url, page, data = purpose_editor(client, job)
    assert page.textarea.get_text() == ''
    assert len(page.find_all('textarea')) == 1
    answer = '  Distinguir formas y tamaños de semillas.\n'
    assert client.post(url, {**data, 'answer': answer, 'confirm_purpose_review': '1'}).status_code == 302
    job.refresh_from_db(); review.refresh_from_db()
    purpose = job.get_interpretation_dossier().general_fields['proposito']
    assert (purpose.value, purpose.origin, purpose.review) == (answer.strip(), 'teacher_entered', 'corrected')
    assert purpose.evidence == []
    assert review.state['status'] == 'limited'
    assert review.state.get('purpose_assessments', []) == before
    assert review.state['purpose_reviews'][-1]['answer'] == answer
    receipts = [event['provider_receipt'] for event in review.state['events'] if 'provider_receipt' in event]
    assert receipts == [RECEIPT]
    assert review.state['turns'] == [] and len(calls) == 1 and not job.is_approved
    reopened = client.get(url)
    assert reopened.context['can_approve'] is True
    assert BeautifulSoup(reopened.content, 'html.parser').select_one('a[data-edit-purpose]') is not None


def test_legacy_closed_rejection_reopens_manually_without_mutating_on_get(monkeypatch):
    client, _, job, review, calls = rejected_case(monkeypatch)
    state = copy.deepcopy(review.state)
    state['status'] = 'limited'  # exact legacy persistence shape, synthetic content only
    review.state = state; review.save(update_fields=['state'])
    old_revision = review.revision
    url = reverse('tutor-import-interpretation', args=[job.pk])
    page = client.get(url)
    assert BeautifulSoup(page.content, 'html.parser').select_one('[data-manual-recovery]')
    _, editor, data = purpose_editor(client, job)
    assert editor.textarea.get_text() == ''
    review.refresh_from_db()
    assert review.state == state and review.revision == old_revision and len(calls) == 1
    assert client.post(url, {**data, 'answer': 'Comparar semillas del patio.',
                            'confirm_purpose_review': '1'}).status_code == 302
    job.refresh_from_db(); review.refresh_from_db()
    assert job.get_interpretation_dossier().general_fields['proposito'].origin == 'teacher_entered'
    assert review.state['events'][0]['provider_receipt'] == RECEIPT
    assert len(calls) == 1


def test_manual_recovery_after_six_questions_does_not_add_a_seventh_or_call(monkeypatch):
    from curriculum.teacher_review import targets
    client, _, job, review, calls = rejected_case(monkeypatch)
    purpose_id = next(key for key, item in targets(job.get_interpretation_dossier()).items()
                      if item.scope == 'general' and item.field_name == 'proposito')
    state = copy.deepcopy(review.state)
    state['turns'] = [{'id': f'synthetic-past-{n}', 'question': f'Pregunta sintética {n}',
        'targets': [purpose_id], 'answer': 'No sé', 'skipped': True, 'applied': [],
        'answer_history': [], 'question_source_sha256': review.source_sha256} for n in range(6)]
    review.state = state; review.save(update_fields=['state'])
    url, editor, data = purpose_editor(client, job)
    assert '6 de 6' in editor.get_text()
    assert client.post(url, {**data, 'answer': 'Reconocer rasgos de semillas.',
                            'confirm_purpose_review': '1'}).status_code == 302
    review.refresh_from_db()
    assert review.state['turns'] == state['turns'] and len(calls) == 1
    assert review.state['status'] == 'limited'
    assert not job.is_approved


def test_recovery_draft_and_rejected_submission_remain_available(monkeypatch):
    from django.test import Client
    client, teacher, job, review, calls = rejected_case(monkeypatch, fault='null')
    url, _, data = purpose_editor(client, job)
    other = Client(); other.force_login(teacher)
    assert other.post(url, {**data, 'action': 'save_draft', 'answer': 'Borrador de otra pestaña.'}).status_code == 200
    literal = '  Mi propósito manual pendiente tras conflicto.\n'
    assert client.post(url, {**data, 'answer': literal, 'confirm_purpose_review': '1'}).status_code == 409
    reopened = BeautifulSoup(client.get(url + '?edit_purpose=1').content, 'html.parser')
    assert reopened.textarea.get_text() == literal
    assert len(calls) == 1


@pytest.mark.parametrize('legacy', ['missing', 'null'])
def test_missing_or_null_legacy_purpose_can_be_completed_without_placeholder_text(monkeypatch, legacy):
    client, _, job, review, calls = rejected_case(monkeypatch, legacy=legacy)
    url, editor, data = purpose_editor(client, job)
    assert editor.textarea.get_text() == ''
    assert client.post(url, {**data, 'answer': 'Reconocer semillas del entorno.',
                            'confirm_purpose_review': '1'}).status_code == 302
    job.refresh_from_db()
    field = job.get_interpretation_dossier().general_fields['proposito']
    assert field.value == 'Reconocer semillas del entorno.'
    assert field.origin == 'teacher_entered' and not field.evidence
    assert len(calls) == 1 and not job.is_approved


def request_form(client, url):
    page = BeautifulSoup(client.get(url).content, 'html.parser')
    button = page.select_one('button[value="request_question"]')
    assert button is not None
    form = button.find_parent('form')
    return {**{item['name']: item.get('value', '') for item in form.find_all('input')},
            'action': 'request_question'}


def test_other_required_gap_can_request_a_question_only_by_explicit_action(monkeypatch):
    client, _, job, review, calls = rejected_case(monkeypatch, missing_closure=True)
    url, _, data = purpose_editor(client, job)
    assert client.post(url, {**data, 'answer': 'Reconocer rasgos de semillas.',
                            'confirm_purpose_review': '1'}).status_code == 302
    review.refresh_from_db()
    assert review.state['status'] == 'needs_input' and len(calls) == 1
    request_data = request_form(client, url)
    def next_double(context):
        calls.append(context)
        target = next(item['target_id'] for item in context['all_targets']
                      if item['field_name'] == 'cierre' and item['priority_state'] == 'requires_resolution')
        return PiReply({'question': '¿Cómo cerrarán la actividad?', 'targets': [target],
                        'answer_updates': [], 'purpose_proposal': None}, {'synthetic': True, 'attempt_id': 'second'})
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider', lambda: next_double)
    assert client.post(url, request_data).status_code == 302
    review.refresh_from_db()
    assert len(calls) == 2 and review.state['status'] == 'asking'
    assert len(review.state['turns']) == 1
    assert review.state['events'][0]['provider_receipt'] == RECEIPT
    assert client.post(url, request_data).status_code == 409
    assert len(calls) == 2


@pytest.mark.parametrize('stop', ['pi_attempt_unknown', 'luna_attempt_unknown', 'pi_prior_attempt_blocked', 'gemini_prior_attempt_unknown'])
def test_explicit_request_cannot_bypass_unreconciled_transport_stops(monkeypatch, stop):
    client, _, job, review, calls = rejected_case(monkeypatch)
    state = copy.deepcopy(review.state); state['error'] = stop
    review.state = state; review.save(update_fields=['state'])
    url = reverse('tutor-import-interpretation', args=[job.pk])
    page = BeautifulSoup(client.get(url).content, 'html.parser')
    assert page.select_one('button[value="request_question"]') is None
    assert client.post(url, {'action': 'request_question', 'expected_revision': review.revision,
                            'expected_version': review.dossier_version}).status_code == 409
    review.refresh_from_db()
    assert review.state == state and len(calls) == 1


def test_request_question_cannot_exceed_the_six_question_budget(monkeypatch):
    client, _, job, review, calls = rejected_case(monkeypatch)
    state = copy.deepcopy(review.state)
    state['turns'] = [{'id': str(i), 'answer': 'No sé', 'question': 'Pregunta sintética',
                      'skipped': True, 'targets': [], 'answer_history': [], 'applied': []} for i in range(6)]
    review.state = state; review.save(update_fields=['state'])
    url = reverse('tutor-import-interpretation', args=[job.pk])
    page = BeautifulSoup(client.get(url).content, 'html.parser')
    assert page.select_one('button[value="request_question"]') is None
    assert page.select_one('a[data-edit-purpose]') is not None
    assert client.post(url, {'action': 'request_question', 'expected_revision': review.revision,
                            'expected_version': review.dossier_version}).status_code == 409
    review.refresh_from_db()
    assert review.state == state and len(calls) == 1
