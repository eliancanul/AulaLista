"""Synthetic source + declared LLM proposals, not a model quality evaluation."""
import copy

import pytest

from curriculum.learning_purpose import assess_learning_purpose


def source(pages):
    return {'source_sha256': 'a' * 64, 'page_count': len(pages),
            'pages': [{'page_number': n, 'text': text, 'status': 'text'}
                      for n, text in enumerate(pages, 1)]}


def implicit_case():
    first = 'El alumnado elaborará un catálogo para comparar tipos de semillas.'
    second = 'Las alumnas comparan tipos de semillas y explican sus diferencias.'
    document = source(['Proyecto: "Semillas del patio"\n' + first + '\n' + second])
    candidate = {'action': 'comparar', 'content': 'tipos de semillas', 'scope_id': 'project-1',
                 'evidence': [
                     {'role': 'action', 'page': 1, 'quote': first},
                     {'role': 'content', 'page': 1, 'quote': first},
                     {'role': 'product', 'page': 1, 'quote': first},
                     {'role': 'action', 'page': 1, 'quote': second}], 'counterevidence': []}
    return candidate, document


def test_implicit_learning_purpose_has_real_evidence_and_explained_pending_proposal():
    candidate, document = implicit_case()
    original = copy.deepcopy((candidate, document))
    result = assess_learning_purpose(candidate, document)
    assert result['decision'] == 'proposed'
    assert result['value'] == 'Comparar tipos de semillas.'
    assert result['origin'] == 'proposed'
    assert result['review'] == 'pending'
    assert result['status'] == 'ambiguous'
    assert result['rule'] == 'A & C & (P | E) & I & S & !X'
    assert result['reason'].startswith('Propuesta de aprendizaje:')
    assert result['evidence'][0]['excerpt'] == candidate['evidence'][0]['quote']
    assert 'probability' not in result and 'confidence' not in result
    assert (candidate, document) == original


@pytest.mark.parametrize('change', ['invented_quote', 'wrong_page', 'bool_page', 'unknown_role', 'extra_authority', 'missing_evidence', 'malformed'])
def test_unverified_or_malformed_candidate_abstains_without_creating_evidence(change):
    candidate, document = implicit_case()
    if change == 'invented_quote': candidate['evidence'][0]['quote'] = 'Texto inventado.'
    if change == 'wrong_page': candidate['evidence'][0]['page'] = 2
    if change == 'bool_page': candidate['evidence'][0]['page'] = True
    if change == 'unknown_role': candidate['evidence'][0]['role'] = 'approved'
    if change == 'extra_authority': candidate['review'] = 'confirmed'
    if change == 'missing_evidence': candidate['evidence'] = []
    if change == 'malformed': candidate = {'action': None}
    result = assess_learning_purpose(candidate, document)
    assert result['decision'] == 'abstained'
    assert result['value'] is None
    assert result['review'] == 'pending'
    assert result['issues']


@pytest.mark.parametrize('case', ['product_only', 'teacher_only', 'missing_content', 'missing_demonstration', 'one_assertion', 'repeated_assertion', 'counterevidence', 'hidden_negation', 'decorative_title'])
def test_insufficient_or_contradictory_support_abstains(case):
    candidate, document = implicit_case()
    if case == 'product_only': candidate['action'] = 'elaborar'
    elif case == 'teacher_only':
        document['pages'][0]['text'] = document['pages'][0]['text'].replace('El alumnado', 'La docente').replace('Las alumnas', 'Las docentes')
        for item in candidate['evidence']:
            item['quote'] = item['quote'].replace('El alumnado', 'La docente').replace('Las alumnas', 'Las docentes')
    elif case == 'missing_content': candidate['content'] = 'fracciones impropias'
    elif case == 'missing_demonstration': candidate['evidence'] = [e for e in candidate['evidence'] if e['role'] != 'product']
    elif case == 'one_assertion': candidate['evidence'] = candidate['evidence'][:3]
    elif case == 'repeated_assertion':
        repeated = candidate['evidence'][0]['quote']
        document['pages'][0]['text'] = 'Proyecto: "Semillas del patio"\n' + repeated + '\n' + repeated
        candidate['evidence'][-1]['quote'] = repeated
    elif case == 'counterevidence': candidate['counterevidence'] = [candidate['evidence'][0]]
    elif case == 'hidden_negation':
        document['pages'][0]['text'] = document['pages'][0]['text'].replace('El alumnado elaborará', 'No se pretende que El alumnado elaborará')
    elif case == 'decorative_title':
        document['pages'][0]['text'] = 'Proyecto: Comparar tipos de semillas\nProducto: Un catálogo vistoso.'
        candidate['evidence'] = [
            {'role': 'action', 'page': 1, 'quote': 'Comparar tipos de semillas'},
            {'role': 'content', 'page': 1, 'quote': 'Comparar tipos de semillas'},
            {'role': 'product', 'page': 1, 'quote': 'Producto: Un catálogo vistoso.'}]
    result = assess_learning_purpose(candidate, document)
    assert result['decision'] == 'abstained', (case, result)
    assert result['value'] is None
    assert result['issues']


@pytest.mark.parametrize('boundary', ['Fase', 'Sesión', 'Momento'])
def test_different_source_units_cannot_be_merged_into_one_purpose(boundary):
    candidate, document = implicit_case()
    first, second = candidate['evidence'][0]['quote'], candidate['evidence'][-1]['quote']
    document['pages'][0]['text'] = ('Proyecto: "Semillas del patio"\n' + boundary + ' 1: Primer trabajo\n'
                                   + first + '\n' + boundary + ' 2: Segundo trabajo\n' + second)
    result = assess_learning_purpose(candidate, document)
    assert result['decision'] == 'abstained'
    assert 'scope_mismatch' in result['issues']


def test_a_second_project_cannot_supply_support_to_the_first():
    candidate, document = implicit_case()
    document['pages'][0]['text'] = document['pages'][0]['text'].replace(candidate['evidence'][-1]['quote'],
        'Proyecto: "Otra planeación"\n' + candidate['evidence'][-1]['quote'])
    result = assess_learning_purpose(candidate, document)
    assert result['decision'] == 'abstained'
    assert 'scope_mismatch' in result['issues']


def test_model_cannot_invent_a_scope_or_infer_without_a_project_anchor():
    candidate, document = implicit_case()
    candidate['scope_id'] = 'project-99'
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'
    candidate['scope_id'] = 'project-1'
    document['pages'][0]['text'] = document['pages'][0]['text'].split('\n', 1)[1]
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_project_intention_may_be_corroborated_by_one_explicit_source_unit():
    candidate, document = implicit_case()
    document['pages'][0]['text'] = document['pages'][0]['text'].replace(candidate['evidence'][-1]['quote'],
        'Fase 1: Comparación\n' + candidate['evidence'][-1]['quote'])
    assert assess_learning_purpose(candidate, document)['decision'] == 'proposed'


def test_review_schema_and_runtime_shape_admit_only_bounded_proposals():
    from curriculum.teacher_review_provider import RESPONSE_SCHEMA, review_response_has_valid_shape
    candidate, _ = implicit_case()
    reply = {'question': None, 'targets': [], 'answer_updates': [], 'purpose_proposal': candidate}
    assert "purpose_proposal" in RESPONSE_SCHEMA["properties"]
    assert "purpose_proposal" in RESPONSE_SCHEMA["required"]
    assert review_response_has_valid_shape(reply)
    assert review_response_has_valid_shape({'question': None, 'targets': [], 'answer_updates': []})
    reply['purpose_proposal']['approved'] = True
    assert not review_response_has_valid_shape(reply)


@pytest.mark.parametrize('mode', ['complete', 'semantic-v1', 'semantic-v2', 'semantic-v2-values'])
def test_inference_policy_and_authority_survive_every_context_mode(settings, mode):
    from curriculum.teacher_review_task_context import provider_task_payload, build_task_context
    from curriculum.teacher_review_table_context import restore_table_context
    from curriculum.teacher_review_context import restore_provider_context
    from test_teacher_review_task_context import task_fixture
    context = task_fixture()
    context['purpose_policy'] = {'eligible': True, 'target_id': 'purpose-test',
                                 'source_scope': {'scope_id': 'project-1'}, 'review_required': True}
    settings.AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = mode
    system, payload = provider_task_payload(context)
    if mode == 'complete': restored = restore_provider_context(payload)
    elif mode == 'semantic-v1': restored = payload
    else: restored = restore_table_context(payload)
    assert restored['purpose_policy'] == context['purpose_policy']
    assert 'purpose_proposal' in system
    assert 'A & C & (P | E) & I & S & !X' in system


def test_uncited_source_contradiction_cannot_be_hidden_by_model():
    candidate, document = implicit_case()
    document['pages'][0]['text'] += '\nEl alumnado no debe comparar tipos de semillas en este proyecto.'
    result = assess_learning_purpose(candidate, document)
    assert result['decision'] == 'abstained'
    assert result['checks']['X'] is True


def test_action_and_content_from_unrelated_assertions_do_not_make_a_purpose():
    candidate, document = implicit_case()
    for index in (0, 2, 3):
        candidate['evidence'][index]['quote'] = candidate['evidence'][index]['quote'].replace('tipos de semillas', 'colores de flores')
    content_statement = 'Contenido: tipos de semillas.'
    candidate['evidence'][1]['quote'] = content_statement
    document['pages'][0]['text'] = ('Proyecto: Jardín escolar\n' + candidate['evidence'][0]['quote']
                                  + '\n' + candidate['evidence'][-1]['quote'] + '\n' + content_statement)
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_standalone_numbered_headings_also_cut_source_units():
    candidate, document = implicit_case()
    document['pages'][0]['text'] = ('Proyecto: Semillas\nSESION 1\n' + candidate['evidence'][0]['quote']
                                  + '\nSESION 2\n' + candidate['evidence'][-1]['quote'])
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_producing_an_argument_can_be_learning_when_assessed_as_a_skill():
    first = 'El alumnado elaborará una argumentación sobre el consumo de agua.'
    second = 'Criterio: el alumnado elabora una argumentación con razones y ejemplos.'
    candidate = {'action': 'elaborar', 'content': 'una argumentación', 'scope_id': 'project-1',
        'evidence': [{'role': role, 'page': 1, 'quote': first} for role in ('action', 'content')]
                    + [{'role': 'assessment', 'page': 1, 'quote': second}], 'counterevidence': []}
    document = source(['Proyecto: Debate del agua\n' + first + '\n' + second])
    assert assess_learning_purpose(candidate, document)['value'] == 'Elaborar una argumentación.'


def test_unpunctuated_project_scenario_row_is_a_supported_scope_anchor():
    candidate, document = implicit_case()
    document['pages'][0]['text'] = document['pages'][0]['text'].replace(
        'Proyecto: "Semillas del patio"', 'Proyecto Semillas del patio Escenario Escolar')
    assert assess_learning_purpose(candidate, document)['decision'] == 'proposed'


def test_wrapped_parts_of_one_assertion_are_not_independent_support():
    first = 'El alumnado elaborará un catálogo para comparar tipos de semillas'
    second = 'y comparar tipos de semillas según su tamaño.'
    candidate, document = implicit_case()
    document['pages'][0]['text'] = 'Proyecto: Semillas\n' + first + '\n' + second
    for item in candidate['evidence'][:3]: item['quote'] = first
    candidate['evidence'][-1]['quote'] = second
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_teacher_artifact_is_not_a_demonstration_of_the_learners_skill():
    candidate, document = implicit_case()
    first = 'El alumnado compara tipos de semillas.'
    teacher_product = 'La docente elaborará un catálogo para comparar tipos de semillas.'
    for item in candidate['evidence'][:2]: item['quote'] = first
    candidate['evidence'][2]['quote'] = teacher_product
    document['pages'][0]['text'] = ('Proyecto: Semillas\n' + first + '\n'
        + candidate['evidence'][-1]['quote'] + '\n' + teacher_product)
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_same_source_quote_is_not_repeated_for_multiple_support_roles():
    candidate, document = implicit_case()
    result = assess_learning_purpose(candidate, document)
    assert len(result['evidence']) == 2
    assert 'Acción del alumnado' in result['evidence'][0]['role']
    assert 'Contenido' in result['evidence'][0]['role']
    assert 'Producto' in result['evidence'][0]['role']
    assert 'comparar' in result['reason'] and 'tipos de semillas' in result['reason']


def test_malformed_role_is_a_controlled_abstention():
    candidate, document = implicit_case()
    candidate['evidence'][0]['role'] = []
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_punctuation_crops_of_one_assertion_do_not_add_independence():
    candidate, document = implicit_case()
    document['pages'][0]['text'] = 'Proyecto: Semillas\n' + candidate['evidence'][0]['quote']
    candidate['evidence'] = candidate['evidence'][:3]
    candidate['evidence'][1]['quote'] = candidate['evidence'][1]['quote'].rstrip('.')
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_subject_after_the_purpose_clause_can_still_be_teacher_only():
    first = 'Para comparar tipos de semillas, la docente elaborará un catálogo.'
    second = 'La docente compara tipos de semillas para preparar su clase.'
    candidate, document = implicit_case()
    for item in candidate['evidence'][:3]: item['quote'] = first
    candidate['evidence'][-1]['quote'] = second
    document['pages'][0]['text'] = 'Proyecto: Semillas\n' + first + '\n' + second
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_hyphenated_session_labels_cannot_hide_scope_boundaries():
    candidate, document = implicit_case()
    document['pages'][0]['text'] = ('Proyecto: Semillas\nSesión 1 - Exploración\n'
        + candidate['evidence'][0]['quote'] + '\nSesión 2 - Observación\n' + candidate['evidence'][-1]['quote'])
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_a_decorative_unrelated_product_does_not_demonstrate_the_action():
    candidate, document = implicit_case()
    first, second, third = ('El alumnado compara tipos de semillas.',
        'Contenido: tipos de semillas.', 'Producto: portada decorativa del cuaderno.')
    candidate['evidence'] = [{'role': role, 'page': 1, 'quote': text} for role, text in
                             [('action', first), ('content', second), ('product', third)]]
    document['pages'][0]['text'] = 'Proyecto: Semillas\n' + '\n'.join([first, second, third])
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


@pytest.mark.parametrize('uncertainty', ['Probablemente', 'Tal vez', 'Posiblemente'])
def test_uncertain_source_assertions_do_not_support_a_proposal(uncertainty):
    candidate, document = implicit_case()
    for item in candidate['evidence']:
        item['quote'] = uncertainty + ' ' + item['quote']
    document['pages'][0]['text'] = ('Proyecto: Semillas\n' + candidate['evidence'][0]['quote']
                                  + '\n' + candidate['evidence'][-1]['quote'])
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


def test_nominal_contradiction_is_not_ignored_for_lack_of_a_verb_inflection():
    candidate, document = implicit_case()
    document['pages'][0]['text'] += '\nLa comparación de tipos de semillas queda excluida del proyecto.'
    result = assess_learning_purpose(candidate, document)
    assert result['decision'] == 'abstained' and result['checks']['X'] is True


@pytest.mark.parametrize('whitespace', ['\n', '\n\n', ' '])
def test_trailing_whitespace_cannot_expand_a_support_into_an_unrelated_assertion(whitespace):
    candidate, document = implicit_case()
    sentence = candidate['evidence'][0]['quote']
    document['pages'][0]['text'] = 'Proyecto: Semillas\n' + sentence + whitespace + 'Una nota de formato.'
    candidate['evidence'] = candidate['evidence'][:3]
    candidate['evidence'][1]['quote'] = sentence + whitespace
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'


@pytest.mark.parametrize('label', ['Fase #1', 'Fase # 1', 'Fase#1', 'Sesión #1', 'Momento # 1'])
def test_number_marker_does_not_hide_distinct_source_units(label):
    candidate, document = implicit_case()
    first = candidate['evidence'][0]['quote']
    second = candidate['evidence'][-1]['quote']
    document['pages'][0]['text'] = ('Proyecto: Semillas\n' + label + ': Exploración\n'
        + first + '\n' + label.replace('1', '2') + ': Observación\n' + second)
    result = assess_learning_purpose(candidate, document)
    assert result['decision'] == 'abstained'
    assert 'scope_mismatch' in result['issues']


@pytest.mark.parametrize('label', ['Fase #1', 'Fase # 1', 'Fase#1', 'Sesión #1', 'Momento # 1'])
def test_number_marker_still_allows_one_unit_corroborating_project_intention(label):
    candidate, document = implicit_case()
    second = candidate['evidence'][-1]['quote']
    document['pages'][0]['text'] = document['pages'][0]['text'].replace(second, label + ': Comparación\n' + second)
    assert assess_learning_purpose(candidate, document)['decision'] == 'proposed'


def test_project_intention_does_not_justify_combining_two_hash_numbered_phases():
    candidate, document = implicit_case()
    second = candidate['evidence'][-1]['quote']
    third = 'Los estudiantes comparan tipos de semillas con su equipo.'
    document['pages'][0]['text'] = document['pages'][0]['text'].replace(second, 'Fase #1: Inicio\n' + second)
    document['pages'][0]['text'] += '\nFase #2: Continuación\n' + third
    candidate['evidence'].append({'role': 'action', 'page': 1, 'quote': third})
    assert assess_learning_purpose(candidate, document)['decision'] == 'abstained'
