"""Value-label separation using invented data and frozen synthetic failures."""
import copy
import json
from pathlib import Path

import pytest
from curriculum.teacher_review_quote_values import (
    labelled_value_spans, quote_matches_labelled_value, VALUE_QUOTE_INSTRUCTIONS, AmbiguousLabelledAnswer,
)
from curriculum.teacher_review import _validate_output
from curriculum.teacher_review_context import canonical_context_bytes as canon
from curriculum.teacher_review_task_context import provider_task_payload, build_task_context
from curriculum.teacher_review_table_context import restore_table_context, TABLE_SYSTEM
from curriculum.teacher_review_provider import ReviewProviderError
from curriculum.pi_review_provider import PiReply
from test_teacher_review_task_context import task_fixture
from test_teacher_review import ready_job, start, save, advance

FROZEN = json.loads((Path(__file__).parent / 'fixtures/teacher_review/labeled_value_quote_failure_v1.json').read_text())


def context_for_case(case):
    context = task_fixture()
    target = next(item for item in context['all_targets'] if item['scope'] == case['scope']
                  and item['field_name'] == case['field_name']
                  and (case['session_number'] is None or item['session_number'] == case['session_number']))
    # Include every asked label represented in this frozen multi-field answer;
    # the production question had both purpose/finality as one coherent group.
    asked = [target]
    if case['field_name'] in ('proposito', 'finalidad'):
        asked = [item for item in context['all_targets'] if item['scope'] == 'general'
                 and item['field_name'] in ('proposito', 'finalidad')]
    turn = {'id': 'synthetic-label-turn', 'question': 'Aclaración sintética',
            'targets': [item['target_id'] for item in asked], 'answer': case['answer'],
            'eligible_targets': [item['target_id'] for item in asked], 'skipped': False,
            'answer_source_sha256': context['dossier']['source_sha256'], 'answer_dossier_version': 1,
            'answer_history': [{'answer': case['answer'], 'at': '2026-01-01T00:00:00Z'}], 'applied': []}
    context['turns'] = [turn]
    return context, turn, target


@pytest.mark.parametrize('case', FROZEN['cases'], ids=lambda row: row['field_name'])
def test_all_five_observed_labelled_quotes_are_rejected_without_rewriting(case):
    context, turn, target = context_for_case(case)
    before = canon(context)
    update = {'turn_id': turn['id'], 'target_id': target['target_id'], 'quote': case['bad_quote']}
    output = {'question': None, 'targets': [], 'answer_updates': [update]}
    bad_before = copy.deepcopy(output)
    with pytest.raises(ReviewProviderError, match='human_quote_includes_metadata_or_wrong_field'):
        _validate_output(output, context)
    assert output == bad_before
    assert canon(context) == before
    good = {**output, 'answer_updates': [{**update, 'quote': case['expected_value']}]}
    assert _validate_output(good, context) == good
    assert good['answer_updates'][0]['quote'] in turn['answer']
    assert canon(context) == before


def simple(label, answer):
    records = [{'target_id': 'target-a', 'human_label': label}]
    turn = {'targets': ['target-a'], 'answer': answer}
    return turn, records


@pytest.mark.parametrize('label', ['Materiales (opcionales)', 'Objetivo: tramo A', 'Texto [base]',
                                  'Énfasis / versión 2', 'Grupo A+B', 'Pregunta ¿por qué?'])
@pytest.mark.parametrize('value', ['Usar tarjetas 2:1.', 'Analizar «Inicio: una historia».',
                                  'Cierre: este prefijo pertenece al contenido.', 'Explorar una relación causa: efecto.'])
def test_generic_labels_and_varied_values_do_not_use_fixture_vocabulary(label, value):
    answer = ' \t' + label + ':  ' + value + '\r\n'
    turn, records = simple(label, answer)
    before = copy.deepcopy(turn)
    assert not quote_matches_labelled_value(label + ':  ' + value, 'target-a', turn, records)
    assert quote_matches_labelled_value(value, 'target-a', turn, records)
    assert turn == before


@pytest.mark.parametrize('answer,quote', [
    ('"Desarrollo: es parte del título"', 'Desarrollo: es parte del título'),
    ('Analizar la frase «Desarrollo: el viaje comienza».', 'Desarrollo: el viaje comienza'),
    ('Desarrollo: "Desarrollo: el viaje comienza"', 'Desarrollo: el viaje comienza'),
    ('Desarrollo: Leer 2:1 y discutir «Desarrollo: el viaje».', 'Leer 2:1 y discutir «Desarrollo: el viaje».'),
    ('Desarrollo: \'Desarrollo: una cita\'.', 'Desarrollo: una cita'),
])
def test_labels_inside_quoted_or_literal_content_are_preserved(answer, quote):
    turn, records = simple('Desarrollo', answer)
    assert quote_matches_labelled_value(quote, 'target-a', turn, records)
    assert turn['answer'] == answer


@pytest.mark.parametrize('answer', [
    'El desarrollo: explicar una experiencia.',
    '«Desarrollo: texto\nDesarrollo: todavía dentro de la cita»',
    'Otra etiqueta: Desarrollo: conserva el contenido.',
    '```\nDesarrollo: código literal\n```',
])
def test_ambiguous_or_free_prose_is_not_split_or_trimmed(answer):
    turn, records = simple('Desarrollo', answer)
    assert labelled_value_spans(answer, turn, records) is None
    assert quote_matches_labelled_value(answer, 'target-a', turn, records)
    assert turn['answer'] == answer


def test_ambiguous_same_labels_across_sessions_do_not_assign_values():
    records = [{'target_id': 'session1', 'human_label': 'Cierre'},
               {'target_id': 'session2', 'human_label': 'Cierre'}]
    turn = {'targets': ['session1', 'session2'], 'answer': 'Cierre: Compartir una idea.'}
    with pytest.raises(AmbiguousLabelledAnswer):
        labelled_value_spans(turn['answer'], turn, records)
    assert not quote_matches_labelled_value('Compartir una idea.', 'session1', turn, records)


def test_multi_field_block_rejects_cross_field_quote_and_label_only():
    records = [{'target_id': 'a', 'human_label': 'Propósito'}, {'target_id': 'b', 'human_label': 'Finalidad'}]
    turn = {'targets': ['a', 'b'], 'answer': 'Propósito: Comparar imágenes.\nFinalidad: Colaborar en equipo.'}
    assert not quote_matches_labelled_value('Colaborar en equipo.', 'a', turn, records)
    assert not quote_matches_labelled_value('Propósito', 'a', turn, records)
    assert quote_matches_labelled_value('Comparar imágenes.', 'a', turn, records)


def test_new_mode_changes_only_system_not_source_payload_or_codec(settings):
    context = task_fixture()
    settings.AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = 'semantic-v2'
    old_system, old_payload = provider_task_payload(context)
    settings.AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = 'semantic-v2-values'
    new_system, new_payload = provider_task_payload(context)
    assert old_system == TABLE_SYSTEM
    assert new_system == TABLE_SYSTEM + VALUE_QUOTE_INSTRUCTIONS
    assert canon(new_payload) == canon(old_payload)
    assert restore_table_context(new_payload) == build_task_context(context)


@pytest.mark.django_db
def test_bad_labelled_batch_is_rejected_atomically_with_answer_and_receipt_preserved(ready_job):
    _, teacher, job = ready_job
    def ask(context):
        group = [item for item in context['all_targets'] if item['scope'] == 'general'
                 and item['field_name'] in ('proposito', 'finalidad')]
        return {'question': '¿Qué propósito y finalidad tendrá?', 'targets': [item['target_id'] for item in group], 'answer_updates': []}
    review = start(job, teacher, ask)
    answer = 'Propósito para el Alumno: Comparar imágenes.\nFinalidad e Intención Docente: Colaborar en equipo.'
    review = save(review, teacher, answer)
    job.refresh_from_db(); before = canon(job.interpretation_dossier)
    receipt = {'test_double': True, 'reported_usage': {'totalTokens': 123}, 'usage_complete': True}
    def bad(context):
        turn = context['turns'][0]
        ids = {item['field_name']: item['target_id'] for item in context['all_targets'] if item['scope'] == 'general'}
        return PiReply({'question': None, 'targets': [], 'answer_updates': [
            {'turn_id': turn['id'], 'target_id': ids['proposito'], 'quote': 'Comparar imágenes.'},
            {'turn_id': turn['id'], 'target_id': ids['finalidad'], 'quote': 'Finalidad e Intención Docente: Colaborar en equipo.'}]}, receipt)
    review = advance(review, teacher, bad)
    job.refresh_from_db()
    assert canon(job.interpretation_dossier) == before
    assert review.state['error'] == 'human_quote_includes_metadata_or_wrong_field'
    assert review.state['turns'][0]['answer'] == answer
    assert review.state['turns'][0]['answer_history'][-1]['answer'] == answer
    assert review.state['events'][-1]['provider_receipt'] == receipt
    assert not job.is_approved
    from curriculum.teacher_review import ReviewError
    with pytest.raises(ReviewError, match='autorización nueva'):
        advance(review, teacher, lambda _: pytest.fail('Rejected value must block another dispatch'))


def test_duplicate_known_label_blocks_update_instead_of_falling_back_to_prose():
    answer = 'Desarrollo: primera idea\nDesarrollo: otra idea.'
    turn, records = simple('Desarrollo', answer)
    with pytest.raises(AmbiguousLabelledAnswer): labelled_value_spans(answer, turn, records)
    assert not quote_matches_labelled_value(answer, 'target-a', turn, records)
    assert not quote_matches_labelled_value('otra idea.', 'target-a', turn, records)


def test_continuations_and_courtesy_do_not_erase_field_boundaries():
    records = [{'target_id': 'a', 'human_label': 'Propósito'}, {'target_id': 'b', 'human_label': 'Finalidad'}]
    answer = 'Propósito: Comparar imágenes.\nConservar sus detalles.\nFinalidad: Colaborar.\nGracias.'
    turn = {'targets': ['a', 'b'], 'answer': answer}
    assert quote_matches_labelled_value('Comparar imágenes.\nConservar sus detalles.', 'a', turn, records)
    assert not quote_matches_labelled_value('Colaborar.', 'a', turn, records)
    assert not quote_matches_labelled_value('Propósito: Comparar imágenes.', 'a', turn, records)
    assert quote_matches_labelled_value('Colaborar.', 'b', turn, records)


@pytest.mark.parametrize('opening,closing', [("'", "'"), ('"', '"'), ('«', '»'), ('“', '”'), ('```', '```')])
def test_multiline_quotation_label_is_content_of_original_field(opening, closing):
    records = [{'target_id': 'a', 'human_label': 'Propósito'}, {'target_id': 'b', 'human_label': 'Finalidad'}]
    answer = f'Propósito: Leer {opening}cuento\nFinalidad: personaje{closing}.'
    turn = {'targets': ['a', 'b'], 'answer': answer}
    assert quote_matches_labelled_value(f'Leer {opening}cuento\nFinalidad: personaje{closing}.', 'a', turn, records)
    assert not quote_matches_labelled_value('personaje', 'b', turn, records)
    assert turn['answer'] == answer


def test_apostrophes_inside_words_are_not_open_quotations():
    answer = "Desarrollo: Leer l'élève y don't; revisar l’élève."
    turn, records = simple('Desarrollo', answer)
    assert quote_matches_labelled_value("Leer l'élève y don't; revisar l’élève.", 'target-a', turn, records)
    assert not quote_matches_labelled_value(answer, 'target-a', turn, records)
