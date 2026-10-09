"""Synthetic necessity checks; neither teacher gold nor curricular validation."""
import hashlib
import json
from pathlib import Path

import pytest

from curriculum.annex_mentions import annex_requirement, iter_annex_mentions
from curriculum.claims import PREDICATE_REQUIERE_ANEXO, compile_dossier_to_atomic_claims
from curriculum.source_interpreter import (
    CurriculumSourceInterpreter, ImportDossier, PRIORITY_PENDING_REVIEW, PRIORITY_REQUIRES_RESOLUTION,
    derive_operational_queue,
)
from test_project_session_context import dossier_for

FIXTURE = Path(__file__).parent / 'fixtures/interpretation/activity_annex_semantics_v1.json'
CASES = json.loads(FIXTURE.read_text())['cases']


def _dossier(text):
    return dossier_for(['SESIÓN 1: Explorar\nInicio:\nActividad 1: ' + text + '\n'])


def _requires(dossier):
    return [c for c in compile_dossier_to_atomic_claims(dossier)
            if c.predicate == PREDICATE_REQUIERE_ANEXO]


def test_semantic_challenge_reference_stays_frozen():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == '0a565876b3595209cf7969e0ee37437f7efaeafbea9f10cd82851e3424c812d9'


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_mentions_survive_without_fabricating_an_unconditional_requirement(case):
    dossier = _dossier(case['text'])
    session, = dossier.sessions
    activity, = session.activities
    refs = {ref.annex_number: ref for ref in session.annex_references}
    claims = {c.object_value: c for c in _requires(dossier)}
    items = {item.annex_number: item for item in derive_operational_queue(dossier).items
             if item.scope == 'annex'}
    assert {n for m in iter_annex_mentions(case['text']) for n in m.numbers} == set(refs)
    for expected in case['expected']:
        number = str(expected['annex_number'])
        ref = refs[number]
        assert annex_requirement(case['text'], number) is expected['required']
        assert ref.reference_id in activity.annex_ids
        assert case['text'] in activity.annex_evidence[ref.reference_id][0].excerpt
        assert (ref.reference_id in claims) is (expected['required'] is True)
        assert ref.confirmed_page is None and not ref.candidate_pages
        item = items[number]
        if expected['required'] is True:
            assert claims[ref.reference_id].state == 'candidate'
            assert item.is_required and 'BLOCKS_CONVERSION' in item.blocking_codes
            assert item.priority_state == PRIORITY_REQUIRES_RESOLUTION
        else:
            assert not item.is_required and item.required_for == []
            assert item.blocking_codes == []
            assert item.priority_state == PRIORITY_PENDING_REVIEW
            # Physical availability and the teacher's decision are untouched.
            assert item.operational_state == 'requires_resolution'

    restored = ImportDossier.from_dict(dossier.to_dict())
    assert [c.to_dict() for c in _requires(restored)] == [c.to_dict() for c in _requires(dossier)]
    assert [(i.annex_number, i.is_required) for i in derive_operational_queue(restored).items if i.scope == 'annex'] == [
        (i.annex_number, i.is_required) for i in items.values()]


@pytest.mark.parametrize(('text', 'outcomes'), [
    ('No usar el anexo 1 y consultar el anexo 2.', {'1': False, '2': True}),
    ('Consultar el anexo 1 sin usar el anexo 2.', {'1': True, '2': False}),
    ('No olvidar consultar los anexos 01 y 02.', {'1': True, '2': True}),
    ('Consultar el anexo 1; no consultarlo.', {'1': False}),
    ('Recordar el anexo 1; volver a usarlo.', {'1': True}),
    ('Comparar el anexo 1 con el anexo 2 y corregirlo.', {'1': None, '2': None}),
    ('Consultar el anexo 1; no usar el anexo 1.', {'1': None}),
    ('Anexo 1 mencionado en la introducción.', {'1': None}),
    ('Consultar el anexo 1 si hay tiempo.', {'1': None}),
    ('Consultar el anexo 1 para decidir si hay tiempo.', {'1': None}),
])
def test_local_polarity_and_bounded_anaphora(text, outcomes):
    for number, expected in outcomes.items():
        assert annex_requirement(text, number) is expected


def test_no_anaphoric_link_is_invented_across_activities():
    dossier = dossier_for(['SESIÓN 1: Explorar\nInicio:\n'
                           'Actividad 1: Consultar el anexo 1.\n'
                           'Actividad 2: Revisarlo de nuevo.\n'])
    first, second = dossier.sessions[0].activities
    assert first.annex_ids and not second.annex_ids
    assert all(c.subject == f'activity:{first.activity_id}' for c in _requires(dossier))


def test_foreign_context_cannot_remove_a_resource_blocker():
    dossier = _dossier('No usar el anexo 1.')
    ref, = dossier.sessions[0].annex_references
    for evidence in ref.evidence:
        if evidence.role == 'annex_mention_context':
            evidence.document_sha256 = 'foreign-source'
    item, = [i for i in derive_operational_queue(dossier).items if i.scope == 'annex']
    assert item.is_required and 'BLOCKS_CONVERSION' in item.blocking_codes


def test_late_condition_updates_relation_evidence_on_all_admitted_pages():
    dossier = dossier_for(['SESIÓN 1: Explorar\nDesarrollo:\n-Consultar el anexo 1 sólo si\n',
                           'la docente lo autoriza.\nCierre: Compartir.\n'])
    activity, = dossier.sessions[0].activities
    assert len(activity.annex_evidence[activity.annex_ids[0]]) == 2
    assert not _requires(dossier)


@pytest.mark.parametrize('labels', [('Actividad 1: ', 'Actividad 2: '), ('-', '-')])
def test_positive_use_in_one_activity_keeps_the_session_resource_required(labels):
    dossier = dossier_for(['SESIÓN 1: Explorar\nInicio:\n'
                           + labels[0] + 'Consultar el anexo 1.\n'
                           + labels[1] + 'No usar el anexo 1.\n'])
    first, second = dossier.sessions[0].activities
    claim, = _requires(dossier)
    assert claim.subject == f'activity:{first.activity_id}'
    assert second.annex_ids == first.annex_ids
    item, = [i for i in derive_operational_queue(dossier).items if i.scope == 'annex']
    assert item.is_required and 'BLOCKS_CONVERSION' in item.blocking_codes


def test_conflicting_anaphoric_instruction_withholds_need():
    assert annex_requirement('No usar el anexo 1 y corregirlo.', '1') is None


def test_an_unrecognized_past_mention_does_not_prove_negative_need():
    assert annex_requirement('El anexo 1 trabajado ayer.', '1') is None


@pytest.mark.parametrize('text', [
    'Resolver sin prisa el anexo 1.',
    'Resolver sin ayuda de otras personas el anexo 1.',
    'Evitar errores al consultar el anexo 1.',
    'Sustituir los colores del anexo 1.',
])
def test_incidental_negative_or_substitution_does_not_assert_nonuse(text):
    assert annex_requirement(text, '1') is None


def test_another_object_of_negation_does_not_negate_the_annex():
    assert annex_requirement('No usar una regla para consultar el anexo 1.', '1') is None


def test_alternative_resources_do_not_become_joint_requirements():
    text = 'Consultar el anexo 1 o el anexo 2.'
    assert annex_requirement(text, '1') is None
    assert annex_requirement(text, '2') is None


@pytest.mark.parametrize(('text', 'expected'), [
    ('Consultar el anexo 1 no es necesario.', False),
    ('El anexo 1 es obligatorio para la actividad.', True),
    ('El anexo 1 no es obligatorio para la actividad.', False),
    ('Revisar el anexo 1; sin prisa volver a usarlo.', None),
])
def test_explicit_predicate_and_anaphoric_negative_scope(text, expected):
    assert annex_requirement(text, '1') is expected


def test_legacy_multipage_fallback_does_not_invent_single_page_context():
    pages = ['Consultar el anexo 1.', 'No usar el anexo 2.']
    refs = CurriculumSourceInterpreter._detect_annex_references_in_session(
        session_text='\n'.join(pages), session_pages=[1, 2], sha256='synthetic',
        annex_candidates=[], pages_text=pages,
    )
    assert [(ref.annex_number, ref.source_pages) for ref in refs] == [('1', [1]), ('2', [2])]
    for ref in refs:
        assert not any(ev.role == 'annex_mention_context' for ev in ref.evidence)
        assert all(ev.excerpt in pages[ev.page_number - 1] for ev in ref.evidence)
