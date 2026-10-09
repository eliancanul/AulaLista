"""Frozen real synthetic output replay and declared offline policy doubles.

The frozen output is an observed model response to synthetic data, not a gold
reference or permission for another invocation. Corrected responses are doubles.
"""
import copy
import hashlib
import json
import uuid
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from curriculum.models import CurriculumImportJob, CurriculumTeacherReview
from curriculum.source_interpreter import (
    ImportDossier, InterpretedField, SessionPlan, REQUIRED_GENERAL_FIELDS,
    REQUIRED_SESSION_FIELDS, STATUS_MISSING, derive_operational_queue, resolve,
)
from curriculum.teacher_review import (
    _validate_output, advance_review, open_review, submit_answer, resume_changed_dossier,
)
from curriculum.teacher_review_context import canonical_context_bytes, restore_provider_context
from curriculum.teacher_review_provider import ReviewProviderError
from curriculum.teacher_review_questions import question_policy
from test_t15_curriculum_import import make_minimal_pdf
from test_teacher_review import ready_job, start, save, advance

pytestmark = pytest.mark.django_db
FIXTURE = Path(__file__).parent / 'fixtures/teacher_review/oversized_question_v1.json'


def recorded_case():
    frozen = json.loads(FIXTURE.read_text())
    context = restore_provider_context(frozen['context'])
    output = frozen['response']
    for name, value in [('context', context), ('response', output)]:
        assert hashlib.sha256(canonical_context_bytes(value)).hexdigest() == frozen['provenance'][name + '_canonical_sha256']
    return context, output


@pytest.fixture
def recorded_review():
    context, output = recorded_case()
    teacher = get_user_model().objects.create_user('synthetic-validation-teacher', is_staff=True)
    client = Client(); client.force_login(teacher)
    pdf = make_minimal_pdf([page['text'] for page in context['source_document']['pages']])
    assert hashlib.sha256(pdf).hexdigest() == context['source_document']['source_sha256']
    job = CurriculumImportJob.objects.create(created_by=teacher,
        pdf=SimpleUploadedFile('same-document-synthetic.pdf', pdf, content_type='application/pdf'))
    dossier = ImportDossier.from_dict(context['dossier'])
    assert job.save_interpretation_dossier(dossier) == 'ready'
    review = CurriculumTeacherReview.objects.create(job=job, dossier_version=dossier.version,
        source_sha256=dossier.source_sha256,
        state={'turns': copy.deepcopy(context['turns']), 'receipts': [],
               'status': 'pending', 'error': '', 'events': []})
    return client, teacher, job, review, context, output


def test_recorded_sixteen_target_question_is_rejected_without_losing_answer(recorded_review):
    _, teacher, job, review, context, output = recorded_review
    assert len(context['missing_fields']) == 21
    assert len(output['targets']) == 16
    assert len(output['answer_updates']) == 5
    assert len(output['question']) == 271  # Length alone would miss this defect.
    before = copy.deepcopy(job.interpretation_dossier)
    seen = []
    def replay(current):
        seen.append(current)
        return copy.deepcopy(output)
    review = advance(review, teacher, replay)
    assert review.state['error'] == 'question_too_many_targets'
    assert review.state['turns'] == context['turns']
    job.refresh_from_db()
    assert job.interpretation_dossier == before
    assert not review.generation_token and not job.is_approved
    assert len(seen[0]['question_policy']['candidate_target_ids']) == 5
    assert len(seen[0]['missing_fields']) == 21
    assert seen[0]['source_document'] == context['source_document']


def test_five_recorded_quotes_finish_without_sixteen_redundant_questions(recorded_review, monkeypatch):
    client, teacher, job, review, old_context, old_output = recorded_review
    response_double = {'question': None, 'targets': [],
                       'answer_updates': copy.deepcopy(old_output['answer_updates'])}
    observed = []
    def corrected_double(context):
        observed.append(context)
        assert len(context['question_policy']['candidate_target_ids']) == 5
        assert len(context['dossier']['sessions']) == 2
        assert context['source_document'] == old_context['source_document']
        return response_double
    review = advance(review, teacher, corrected_double)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    queue = derive_operational_queue(dossier)
    assert queue.requires_resolution_count == 0
    assert queue.pending_review_count == 7 and queue.not_specified_count == 9
    assert review.state['status'] == 'limited' and review.state['error'] == ''
    assert len(review.state['turns']) == 1
    assert review.state['turns'][0]['answer'] == old_context['turns'][0]['answer']
    assert len(review.state['turns'][0]['applied']) == 5
    assert all(not ref.confirmed_page for session in dossier.sessions for ref in session.annex_references)
    assert dossier.general_fields['grado'].value == ''
    assert 'Grado: 3ro' in observed[0]['source_document']['pages'][0]['text']
    for item in old_context['all_targets']:
        if item['priority_state'] in ('not_specified', 'pending_review'):
            assert item['target_id'] not in observed[0]['question_policy']['candidate_target_ids']
    def forbidden(*args, **kwargs):
        pytest.fail('No provider call after the necessary gaps are resolved')
    monkeypatch.setattr('curriculum.teacher_review.get_review_provider', forbidden)
    advance(review, teacher, forbidden)
    page = client.get(reverse('tutor-import-interpretation', args=[job.pk]))
    assert page.context['can_approve'] is True and page.context['pending_count'] == 7
    assert not job.is_approved and not job.approvals.exists()
    assert len(observed) == 1


def test_server_rechecks_question_scope_after_applying_valid_human_quotes(recorded_review):
    _, teacher, job, review, _, old_output = recorded_review
    bad = {'question': '¿Cuál es el propósito?',
           'targets': [old_output['answer_updates'][1]['target_id']],
           'answer_updates': copy.deepcopy(old_output['answer_updates'])}
    review = advance(review, teacher, lambda _: bad)
    assert review.state['error'] == 'question_has_no_required_gap'
    assert review.state['turns'][0]['answer']
    job.refresh_from_db()
    assert derive_operational_queue(job.get_interpretation_dossier()).requires_resolution_count == 5


def test_legacy_optional_question_and_answer_remain_editable(ready_job):
    _, teacher, job = ready_job
    review = open_review(job)
    # A pre-policy persisted question is historical data, not a new generation.
    from curriculum.teacher_review import targets
    target = next(item for item in targets(job.get_interpretation_dossier()).values()
                  if item.field_name == 'grado')
    turn = {'id': str(uuid.uuid4()), 'question': '¿Para qué grado es la actividad?',
            'targets': [target.target_id], 'answer': None, 'skipped': False,
            'answer_history': [], 'applied': [], 'question_source_sha256': review.source_sha256}
    review.state.update(status='asking', turns=[turn])
    review.save(update_fields=['state'])
    review = save(review, teacher, 'Quinto grado')
    def apply_legacy(context):
        assert target.target_id not in context['question_policy']['candidate_target_ids']
        return {'question': None, 'targets': [], 'answer_updates': [
            {'turn_id': turn['id'], 'target_id': target.target_id, 'quote': 'Quinto grado'}]}
    review = advance(review, teacher, apply_legacy)
    job.refresh_from_db()
    assert job.get_interpretation_dossier().general_fields['grado'].value == 'Quinto grado'
    review, _ = submit_answer(job_id=job.pk, user=teacher, expected_revision=review.revision,
        expected_version=review.dossier_version, expected_draft_epoch=review.draft_epoch,
        receipt=str(uuid.uuid4()), turn_id=turn['id'], answer='Sexto grado', edit=True)
    assert [entry['answer'] for entry in review.state['turns'][0]['answer_history']] == ['Quinto grado', 'Sexto grado']


def test_resume_changed_dossier_keeps_unanswered_legacy_question_visible_without_provider(recorded_review):
    client, teacher, job, review, _, old_output = recorded_review
    review = advance(review, teacher, lambda _: {'question': None, 'targets': [],
        'answer_updates': copy.deepcopy(old_output['answer_updates'])})
    legacy = {'id': str(uuid.uuid4()), 'question': old_output['question'],
              'targets': old_output['targets'], 'answer': None, 'skipped': False,
              'answer_history': [], 'applied': [], 'question_source_sha256': review.source_sha256}
    review.state['turns'].append(legacy)
    review.state['status'] = 'asking'
    review.save(update_fields=['state'])
    job.refresh_from_db()
    dossier = resolve(job.get_interpretation_dossier(),
        {'general_fields': {'metodologia': 'Lectura compartida'}},
        actor=teacher.username, pdf_source=job.pdf)
    assert job.save_interpretation_dossier(dossier) == 'ready'
    review = resume_changed_dossier(job_id=job.pk, user=teacher,
        expected_revision=review.revision, expected_version=dossier.version)
    assert review.state['status'] == 'pending'
    def forbidden(*args, **kwargs):
        pytest.fail('Resuming the saved question must not dispatch a model request')
    review = advance(review, teacher, forbidden)
    assert review.state['status'] == 'asking'
    page = client.get(reverse('tutor-import-interpretation', args=[job.pk]))
    assert page.context['form_turn']['id'] == legacy['id']
    assert page.content.count(b'<textarea') == 1
    assert not review.draft_state  # The question remains accessible without a draft.
    review = advance(save(review, teacher, '', skip=True), teacher, forbidden)
    assert review.state['status'] == 'limited'
    assert len(review.state['turns']) == 2 and review.state['turns'][1]['skipped'] is True


@pytest.mark.parametrize('kind', ['optional', 'confirmation', 'cross_session', 'cross_general_topic', 'too_long'])
def test_bounded_question_scope_is_enforced_even_with_few_targets(kind):
    context, output = recorded_case()
    context['question_policy'] = question_policy(context['all_targets'])
    targets = context['all_targets']
    required = [t for t in targets if t['priority_state'] == 'requires_resolution']
    question = '¿Puedes aclarar este dato?'
    if kind in ('optional', 'confirmation'):
        priority = 'not_specified' if kind == 'optional' else 'pending_review'
        asked = [next(t['target_id'] for t in targets if t['priority_state'] == priority)]
        error = 'question_has_no_required_gap'
    elif kind == 'cross_session':
        asked = [t['target_id'] for t in required if t['scope'] == 'session']
        error = 'question_incoherent_group'
    elif kind == 'cross_general_topic':
        asked = [t['target_id'] for t in required if t['scope'] == 'general']
        error = 'question_incoherent_group'
    else:
        asked = [required[0]['target_id']]; question = 'x' * 501
        error = 'question_too_long'
    with pytest.raises(ReviewProviderError, match='^' + error + '$'):
        _validate_output({'question': question, 'targets': asked, 'answer_updates': []}, context)


@pytest.mark.parametrize('session_count,expected_remaining', [(2, 0), (4, 0), (5, 3)])
def test_grouping_covers_more_than_six_gaps_without_hiding_a_long_question(ready_job, session_count, expected_remaining):
    _, teacher, job = ready_job
    prior = job.get_interpretation_dossier()
    dossier = ImportDossier(source_sha256=prior.source_sha256, source_name=prior.source_name, page_count=1,
        general_fields={name: InterpretedField(name, '', status=STATUS_MISSING) for name in REQUIRED_GENERAL_FIELDS},
        sessions=[SessionPlan(f'session-{n}', n, f'Sesión sintética {n}', pages=[1],
            fields={name: InterpretedField(name, '', status=STATUS_MISSING) for name in REQUIRED_SESSION_FIELDS})
            for n in range(1, session_count + 1)])
    assert job.save_interpretation_dossier(dossier) == 'ready'
    initial_gaps = derive_operational_queue(dossier).requires_resolution_count
    assert initial_gaps == 4 + session_count * 3 > 6
    contexts = []
    def value(item):
        return 'Lenguajes' if item['field_name'] == 'campos_formativos' else 'Dato docente ' + item['target_id']
    def grouped_double(context):
        contexts.append(context)
        by_id = {t['target_id']: t for t in context['all_targets']}
        updates = [{'turn_id': turn['id'], 'target_id': target, 'quote': value(by_id[target])}
                   for turn in context['turns'] if turn['answer'] is not None
                   for target in turn['eligible_targets']]
        applied = {u['target_id'] for u in updates}
        groups = [[t for t in group['target_ids'] if t not in applied]
                  for group in context['question_policy']['groups']]
        group = next((ids for ids in groups if ids), []) if context['questions_remaining'] else []
        return {'question': '¿Cómo planteas ' + ', '.join(by_id[t]['human_label'] for t in group) + '?' if group else None,
                'targets': group, 'answer_updates': updates}
    review = start(job, teacher, grouped_double)
    while review.state['status'] == 'asking':
        turn = review.state['turns'][-1]
        by_id = {t['target_id']: t for t in contexts[-1]['all_targets']}
        assert len(turn['targets']) <= 3
        answer = '\n'.join(value(by_id[t]) for t in turn['targets'])
        review = advance(save(review, teacher, answer), teacher, grouped_double)
    job.refresh_from_db()
    assert derive_operational_queue(job.get_interpretation_dossier()).requires_resolution_count == expected_remaining
    assert len(review.state['turns']) == min(2 + session_count, 6)
    assert len(contexts) == len(review.state['turns']) + 1
    assert not job.is_approved
    if expected_remaining:
        assert review.state['status'] == 'needs_input'
