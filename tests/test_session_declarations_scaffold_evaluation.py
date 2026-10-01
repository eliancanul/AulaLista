"""Independent scaffold oracles and mutations; never import product parsers."""
from copy import deepcopy
import builtins
import hashlib
import json
from pathlib import Path

import pytest

from scripts import evaluate_session_declarations as evaluator

FIXTURES = Path(__file__).parent / 'fixtures/interpretation'
BASE = FIXTURES / 'session_declarations_scaffold_v1.json'
SUPPLEMENT = FIXTURES / 'session_declarations_scaffold_supplement_v1.json'
BASE_SHA = '3b83730070b9e04859a39af78065dbf70399bdfb3a6d5edbbc3a8941d71f3b09'
SUPPLEMENT_SHA = 'f5136feae92c5c186845f2b080113a3a36f1aa2d1e20a2c8ebfa6b3bdd6cbc0d'


def loaded():
    assert hashlib.sha256(BASE.read_bytes()).hexdigest() == BASE_SHA
    assert hashlib.sha256(SUPPLEMENT.read_bytes()).hexdigest() == SUPPLEMENT_SHA
    return json.loads(BASE.read_bytes()), json.loads(SUPPLEMENT.read_bytes())


def source(span, sha, role):
    return dict(document_sha256=sha, page_number=span['page'], role=role,
                region=dict(kind='text_offsets', start=span['start'], end=span['end']), excerpt=span['quote'])


def sync(record):
    record['claim']['evidence'] = deepcopy(record['evidence']) + [deepcopy(record['unit']['anchor'])]


def oracle(document, requirements=()):
    """Build exact predictions from the authored reference, not any parser."""
    requirements = {r['declaration_id']: r for r in requirements if r['document_id'] == document['id']}
    sha = evaluator.hash_canonical_pages(document['pages'])
    output = dict(version='session-declarations.v1', source_doc_sha256=sha, extraction_sha256=sha,
                  records=[], limits=['Independent synthetic test oracle'])
    units = {u['id']: u for u in document['units']}
    for d in document['declarations']:
        expected_unit = units.get(d['unit_id'])
        unit = dict(id=expected_unit['id'], kind=expected_unit['kind'],
                    anchor=source(expected_unit['anchor'], sha, 'unit_anchor')) if expected_unit else None
        evidence = [source(d[role], sha, role) for role in ('label', 'value')]
        requirement = requirements.get(d['id'])
        if requirement:
            evidence += [source(proof, sha, proof['role']) for proof in requirement['proofs']]
        record = dict(id=d['id'], kind=d['kind'], decision=d['expected_decision'], reason=d['reason'],
                      unit=unit, evidence=evidence, claim=None)
        if record['decision'] == 'candidate':
            record['claim'] = dict(claim_id=d['id'], claim_type='field', subject=unit['id'],
                                   predicate=evaluator.PREDICATES[d['kind']], object_value=d['value']['quote'],
                                   source_doc_sha256=sha, state='needs_human_review', confidence=None,
                                   metadata={'basis': 'explicit'})
            if requirement:
                record['claim']['metadata']['unit_scope_basis'] = requirement['unit_scope_basis']
            sync(record)
        output['records'].append(record)
    for challenge in document['challenges']:
        output['records'].append(dict(id=challenge['id'], kind=None, decision='abstained',
                                      reason=challenge['reason'], unit=None, claim=None,
                                      evidence=[source(challenge['anchor'], sha, 'label')]))
    return output


def selected(name):
    reference, supplement = loaded()
    doc = next(d for d in reference['documents'] if d['id'] == name)
    requirements = [r for r in supplement['candidate_scope_requirements'] if r['document_id'] == name]
    return doc, oracle(doc, requirements), {r['declaration_id']: r for r in requirements}


def assert_scope_only_failure(doc, output, requirements, lost=1):
    report = evaluator.score(doc, output, requirements)
    total, count = report['metrics'], len(doc['declarations'])
    assert total['literal_declarations']['correct'] == count
    assert total['unit_assignment']['correct'] == count - lost
    assert total['joint_detection_unit']['correct'] == count - lost
    assert total['strict_session_claims']['correct'] == count - lost
    assert total['session_candidates']['correct'] == count - lost
    assert total['output']['invalid_records'] == 0
    assert report['unit_errors']
    return report


def test_frozen_oracle_separate_denominators_and_no_product_import(monkeypatch):
    reference, supplement = loaded()
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert not any(fragment in name for fragment in ('session_declarations', 'scanner', 'text_extraction'))
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    report = evaluator.evaluate(reference, lambda d: oracle(d, supplement['candidate_scope_requirements']),
                                scope_contract=supplement, reference_bytes=BASE.read_bytes())
    assert report['evaluator_version'] == 'session-declarations-evaluation.v1.3.3'
    total = report['total']
    for metric, count in [('literal_declarations', 28), ('session_candidates', 17),
                          ('strict_session_claims', 17), ('scope_abstentions', 11)]:
        assert total[metric]['expected'] == total[metric]['correct'] == count
    assert total['challenges']['expected'] == total['challenges']['explicit_abstentions'] == 12
    assert total['negative_documents']['expected'] == 8
    assert total['output']['documents'] == 25
    additional = report['additional_reference']['total']
    assert additional['output']['documents'] == 5
    assert additional['literal_declarations']['expected'] == additional['literal_declarations']['correct'] == 5
    assert additional['scope_abstentions']['expected'] == additional['scope_abstentions']['correct'] == 5
    assert additional['strict_session_claims']['expected'] == 0
    assert additional['strict_session_claims']['recall'] is None
    assert additional['challenges']['expected'] == additional['negative_documents']['expected'] == 0
    assert report['scope_contract']['basis_counts'] == dict(same_page_explicit=7,
                                                          structural_scaffold_proposal=8, explicit_continuation=2)


@pytest.mark.parametrize('name', ['marker_attached_pair', 'marker_spaced_crlf_repeated', 'scaffold_new_session',
                                  'scaffold_empty_tail', 'scaffold_complete_metadata', 'scaffold_bullet_metadata',
                                  'scaffold_crlf_metadata', 'explicit_continuation_after_developed'])
@pytest.mark.parametrize('mutation', ['missing', 'null', 'unknown', 'contradict', 'top_level_only'])
def test_every_fixed_candidate_requires_exact_claim_metadata_basis(name, mutation):
    doc, pristine, requirements = selected(name)
    for index in range(len(pristine['records'])):
        output = deepcopy(pristine)
        record = output['records'][index]
        original = record['claim']['metadata'].pop('unit_scope_basis')
        if mutation == 'null':
            record['claim']['metadata']['unit_scope_basis'] = None
        elif mutation == 'unknown':
            record['claim']['metadata']['unit_scope_basis'] = 'physical_proximity'
        elif mutation == 'contradict':
            record['claim']['metadata']['unit_scope_basis'] = next(b for b in evaluator.SCOPE_BASES if b != original)
        elif mutation == 'top_level_only':
            record['unit_scope_basis'] = original
        output['implementation_version'] = 'legacy-no-exemption'
        assert_scope_only_failure(doc, output, requirements)


@pytest.mark.parametrize('role', ['unit_scaffold_tail', 'unit_scaffold_prefix'])
@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'crop', 'alter', 'substitute', 'desync',
                                      'hash', 'coordinates', 'region_kind', 'claim_hash', 'claim_only'])
def test_scaffold_proof_mutations_preserve_exact_literal_credit(role, mutation):
    doc, output, requirements = selected('scaffold_empty_tail')
    record = output['records'][0]
    proof = next(r for r in record['evidence'] if r['role'] == role)
    if mutation == 'missing':
        record['evidence'].remove(proof)
    elif mutation == 'duplicate':
        record['evidence'].append(deepcopy(proof))
    elif mutation == 'crop':
        proof['region']['end'] -= 1
        proof['excerpt'] = proof['excerpt'][:-1]
    elif mutation == 'alter':
        proof['excerpt'] += ' altered'
    elif mutation == 'substitute':
        proof['role'] = 'unit_continuation'
    elif mutation == 'hash':
        proof['document_sha256'] = '0' * 64
    elif mutation == 'coordinates':
        proof['page_number'] = 99
    elif mutation == 'region_kind':
        proof['region']['kind'] = 'rectangle'
    elif mutation == 'claim_only':
        record['evidence'].remove(proof)
    if mutation not in ('desync', 'claim_hash', 'claim_only'):
        sync(record)
    elif mutation == 'desync':
        proof['region']['end'] -= 1
        proof['excerpt'] = proof['excerpt'][:-1]
    elif mutation == 'claim_hash':
        next(r for r in record['claim']['evidence'] if r['role'] == role)['document_sha256'] = '0' * 64
    report = assert_scope_only_failure(doc, output, requirements)
    if mutation in ('alter', 'hash', 'coordinates', 'region_kind', 'claim_hash'):
        assert report['metrics']['output']['invalid_provenance_records'] == 1


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'crop', 'alter', 'substitute', 'desync', 'hash'])
def test_named_continuation_proofs_are_checked_independently(mutation):
    doc, output, requirements = selected('explicit_continuation_after_developed')
    record = output['records'][0]
    proof = next(r for r in record['evidence'] if r['role'] == 'unit_continuation')
    if mutation == 'missing':
        record['evidence'].remove(proof)
    elif mutation == 'duplicate':
        record['evidence'].append(deepcopy(proof))
    elif mutation == 'crop':
        proof['region']['end'] -= 1
        proof['excerpt'] = proof['excerpt'][:-1]
    elif mutation == 'alter':
        proof['excerpt'] += ' altered'
    elif mutation == 'substitute':
        proof['role'] = 'unit_scaffold_tail'
    elif mutation == 'hash':
        proof['document_sha256'] = '0' * 64
    elif mutation == 'desync':
        record['claim']['evidence'] = [r for r in record['claim']['evidence'] if r['role'] != 'unit_continuation']
    if mutation != 'desync':
        sync(record)
    assert_scope_only_failure(doc, output, requirements)


def test_evidence_order_does_not_change_scope_credit():
    doc, output, requirements = selected('scaffold_empty_tail')
    for record in output['records']:
        record['evidence'].reverse()
        record['claim']['evidence'].reverse()
    assert evaluator.score(doc, output, requirements)['metrics']['strict_session_claims']['correct'] == 2


def test_legacy_without_basis_cannot_opt_into_scaffold_using_proof_roles():
    doc, output, _ = selected('scaffold_empty_tail')
    for record in output['records']:
        del record['claim']['metadata']['unit_scope_basis']
    assert_scope_only_failure(doc, output, None, lost=2)


def test_label_and_value_provenance_errors_still_erase_literal_credit():
    doc, pristine, requirements = selected('scaffold_empty_tail')
    for role in ('label', 'value'):
        output = deepcopy(pristine)
        record = output['records'][0]
        next(r for r in record['evidence'] if r['role'] == role)['document_sha256'] = '0' * 64
        sync(record)
        total = evaluator.score(doc, output, requirements)['metrics']
        assert total['literal_declarations']['correct'] == 1
        assert total['output']['invalid_records'] == 1


def custom_scaffold(prior, current, *, anchor_page=1):
    """Coordinates below are authored for simple strings, outside the scorer."""
    header, label, value = 'SESIÓN 1: Formas', 'PDA:', 'Describe formas.'
    pages = [prior, current] if anchor_page == 1 else [prior, '\n', current]
    page = len(pages)
    def span(text, quote, page):
        start = text.index(quote)
        return dict(page=page, start=start, end=start + len(quote), quote=quote)
    unit = dict(id='s1', kind='session', anchor=span(prior, header, 1))
    doc = dict(id='independent-source-grammar', pages=pages, units=[unit], challenges=[], absence_expected=False,
               declarations=[dict(id='d1', kind='pda', label=span(current, label, page), value=span(current, value, page),
                                  unit_id='s1', expected_decision='candidate', reason='explicit_session')])
    end = current.index('Inicio:') if 'Inicio:' in current else len(current)
    proofs = [dict(role='unit_scaffold_tail', page=1, start=unit['anchor']['start'], end=len(prior),
                   quote=prior[unit['anchor']['start']:]),
              dict(role='unit_scaffold_prefix', page=page, start=0, end=end, quote=current[:end])]
    req = dict(document_id=doc['id'], declaration_id='d1', unit_scope_basis='structural_scaffold_proposal', proofs=proofs)
    return doc, oracle(doc, [req])


@pytest.mark.parametrize('tail', ['Inicio:\n', 'Desarrollo:\n', 'Cierre:\n', '-Observar tarjetas.\n',
                                  'Prosa libre.\n', 'Fecha:\n', 'Fecha: 20 de\n', 'Tiempo: 40,\n',
                                  'Tema de la sesión: Formas y\n', 'Organización: Pares;\n',
                                  'Campos: Lenguajes:\n', 'Fecha: 20-\n', 'Campos: «Lenguajes\n',
                                  'DATOS GENERALES\n', 'Proyecto: Otro\n', 'SESIÓN 2: Otra\n',
                                  'Contenido: Formas y\n'])
def test_prior_tail_source_blockers_even_with_exact_full_proofs(tail):
    doc, output = custom_scaffold('SESIÓN 1: Formas\n' + tail, 'PDA: Describe formas.\nInicio:\n-Observar.\n')
    assert_scope_only_failure(doc, output, None)


@pytest.mark.parametrize('current', [
    'PDA: Describe formas.\n',
    'Desarrollo:\nPDA: Describe formas.\nInicio:\n',
    'Cierre:\nPDA: Describe formas.\nInicio:\n',
    'Desarrollo:\nPDA: Describe formas.\nCierre:\n',
    'Prosa inicial.\nPDA: Describe formas.\nInicio:\n',
    'TÍTULO DE PRESENTACIÓN\nPDA: Describe formas.\nInicio:\n',
    'PDA: Describe formas.\nUna frase libre.\nInicio:\n',
    'PDA: Describe formas.\n-Observar.\nInicio:\n',
    'Tema de la sesión: Tarjetas de\nPDA: Describe formas.\nInicio:\n',
    'Fecha:\nPDA: Describe formas.\nInicio:\n',
    'Proyecto: Otro\nPDA: Describe formas.\nInicio:\n',
    'DATOS GENERALES\nPDA: Describe formas.\nInicio:\n',
    'SESIÓN 2: Otra\nPDA: Describe formas.\nInicio:\n',
    '«\nPDA: Describe formas.\nInicio:\n',
    'PDA: Describe formas.\nCampos: “Lenguajes\nInicio:\n',
])
def test_prefix_source_blockers_even_with_exact_full_proofs(current):
    doc, output = custom_scaffold('SESIÓN 1: Formas\nFecha: 2026-01-20\n', current)
    assert_scope_only_failure(doc, output, None)


def test_source_parent_ambiguity_quote_entry_and_nonadjacent_page():
    for prior in ['SESIÓN 2: Otra\nSESIÓN 1: Formas\n', '«\nSESIÓN 1: Formas\n']:
        doc, output = custom_scaffold(prior, 'PDA: Describe formas.\nInicio:\n')
        assert_scope_only_failure(doc, output, None)
    doc, output = custom_scaffold('SESIÓN 1: Formas\n', 'PDA: Describe formas.\nInicio:\n', anchor_page=2)
    assert_scope_only_failure(doc, output, None)


def test_earlier_project_context_and_balanced_quotes_are_allowed():
    doc, output = custom_scaffold('Proyecto: Tarjetas\nSESIÓN 1: Formas\nTema de la sesión: «Tarjetas»\n',
                                  'Campo: “Lenguajes”\nPDA: Describe formas.\nInicio:\n')
    assert evaluator.score(doc, output)['metrics']['strict_session_claims']['correct'] == 1


@pytest.mark.parametrize('mutation', ['missing_bytes', 'wrong_bytes', 'changed_reference', 'binding_hash',
                                      'missing_requirement', 'duplicate_requirement', 'wrong_id', 'proof_crop',
                                      'proof_quote', 'missing_additional', 'additional_candidate'])
def test_contract_validation_precedes_any_predictor(mutation):
    reference, contract = loaded()
    raw = BASE.read_bytes()
    if mutation == 'missing_bytes':
        raw = None
    elif mutation == 'wrong_bytes':
        raw += b'\n'
    elif mutation == 'changed_reference':
        reference['scope']['development_base'] = 'changed'
    elif mutation == 'binding_hash':
        contract['base_reference']['sha256'] = '0' * 64
    elif mutation == 'missing_requirement':
        contract['candidate_scope_requirements'].pop()
    elif mutation == 'duplicate_requirement':
        contract['candidate_scope_requirements'].append(deepcopy(contract['candidate_scope_requirements'][0]))
    elif mutation == 'wrong_id':
        contract['candidate_scope_requirements'][0]['declaration_id'] = 'missing'
    elif mutation in ('proof_crop', 'proof_quote'):
        proof = next(r for r in contract['candidate_scope_requirements'] if r['unit_scope_basis'] == 'structural_scaffold_proposal')['proofs'][0]
        if mutation == 'proof_crop':
            proof['end'] -= 1
            proof['quote'] = proof['quote'][:-1]
        else:
            proof['quote'] += 'altered'
    elif mutation == 'missing_additional':
        contract['additional_reference']['documents'].pop()
    elif mutation == 'additional_candidate':
        contract['additional_reference']['documents'][0]['declarations'][0].update(unit_id='s1', expected_decision='candidate', reason='explicit_session')
    def forbidden(_):
        pytest.fail('Predictor ran before scope contract was validated')
    with pytest.raises(ValueError):
        evaluator.evaluate(reference, forbidden, scope_contract=contract, reference_bytes=raw)


def test_unknown_display_heading_cannot_be_absorbed_as_wrapped_value():
    doc, output = custom_scaffold('SESIÓN 1: Formas\n',
                                  'Contenido: Formas\nMATERIALES\nPDA: Describe formas.\nInicio:\n')
    assert_scope_only_failure(doc, output, None)


def test_source_discovery_is_not_repaired_by_cropped_gold_value():
    # The source contains a complete first sentence followed by an unlabelled
    # sentence. Even an authored value covering only the first sentence cannot
    # make the surrounding source a valid scaffold prefix.
    doc, output = custom_scaffold('SESIÓN 1: Formas\n',
                                  'PDA: Describe formas.\nProsa sin etiqueta.\nInicio:\n')
    assert_scope_only_failure(doc, output, None)


def test_same_page_basis_forbids_extra_scope_proofs():
    doc, output, requirements = selected('marker_attached_pair')
    record = output['records'][0]
    record['evidence'].append({**deepcopy(record['evidence'][0]), 'role': 'unit_continuation'})
    sync(record)
    assert_scope_only_failure(doc, output, requirements)


def test_claim_review_and_confidence_constraints_remain_enforced():
    doc, pristine, requirements = selected('scaffold_empty_tail')
    for change in ({'state': 'approved'}, {'confidence': 1.0}):
        output = deepcopy(pristine)
        output['records'][0]['claim'].update(change)
        result = evaluator.score(doc, output, requirements)
        assert result['metrics']['strict_session_claims']['correct'] == 1
        assert result['metrics']['output']['invalid_records'] == 1


def test_scope_contract_cli_reports_supplement_hash_and_separate_reference(monkeypatch, tmp_path, capsys):
    _, supplement = loaded()
    actual_evaluate = evaluator.evaluate
    def independent(reference, predictor=None, **kwargs):
        return actual_evaluate(reference, lambda d: oracle(d, supplement['candidate_scope_requirements']), **kwargs)
    monkeypatch.setattr(evaluator, 'evaluate', independent)
    destination = tmp_path / 'scope_report.json'
    assert evaluator.main(['--reference', str(BASE), '--scope-contract', str(SUPPLEMENT),
                           '--output', str(destination)]) == 0
    report = json.loads(destination.read_bytes())
    assert json.loads(capsys.readouterr().out) == report
    assert report['reference_sha256'] == BASE_SHA
    assert report['scope_contract_sha256'] == SUPPLEMENT_SHA
    assert report['scope_contract']['candidate_requirements'] == 17
    assert report['total']['strict_session_claims']['expected'] == 17
    assert report['additional_reference']['total']['literal_declarations']['expected'] == 5


@pytest.mark.parametrize('separator', ['\v', '\f', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029'])
def test_vertical_separators_cannot_create_source_structure(separator):
    doc, output = custom_scaffold('SESIÓN 1: Formas\n',
                                  f'Campo: Lenguajes{separator}PDA: Describe formas.\nInicio:\n')
    assert_scope_only_failure(doc, output, None)
    doc, output = custom_scaffold(f'SESIÓN 1: Formas\nFecha: 20{separator}enero\n',
                                  'PDA: Describe formas.\nInicio:\n')
    assert_scope_only_failure(doc, output, None)


@pytest.mark.parametrize('code', ['ABCDE1', 'AB12345'])
def test_scope_parser_does_not_expand_local_code_grammar(code):
    doc, output = custom_scaffold('SESIÓN 1: Formas\n',
                                  f'{code} PDA2: Compara tamaños.\nPDA: Describe formas.\nInicio:\n')
    assert_scope_only_failure(doc, output, None)


@pytest.mark.parametrize('role', ['unit_scaffold_tail', 'unit_scaffold_prefix', 'unit_continuation'])
@pytest.mark.parametrize('mutation', ['unknown_role', 'missing_role', 'nondict', 'nonstring_role'])
def test_corrupted_auxiliary_proof_roles_remain_scope_errors(role, mutation):
    name = 'explicit_continuation_after_developed' if role == 'unit_continuation' else 'scaffold_empty_tail'
    doc, output, requirements = selected(name)
    record = output['records'][0]
    index = next(i for i, r in enumerate(record['evidence']) if r['role'] == role)
    if mutation == 'unknown_role':
        record['evidence'][index]['role'] = 'misspelled_proof'
    elif mutation == 'missing_role':
        del record['evidence'][index]['role']
    elif mutation == 'nonstring_role':
        record['evidence'][index]['role'] = ['wrong']
    else:
        record['evidence'][index] = None
    sync(record)
    assert_scope_only_failure(doc, output, requirements)


def test_contract_rejects_cropped_named_continuation_before_predicting():
    reference, supplement = loaded()
    requirement = next(r for r in supplement['candidate_scope_requirements'] if r['unit_scope_basis'] == 'explicit_continuation')
    proof = requirement['proofs'][0]
    proof['end'] -= 1
    proof['quote'] = proof['quote'][:-1]
    def forbidden(_):
        pytest.fail('Predictor called for an invalid named-continuation contract')
    with pytest.raises(ValueError, match='complete literal continuation'):
        evaluator.evaluate(reference, forbidden, scope_contract=supplement, reference_bytes=BASE.read_bytes())


@pytest.mark.parametrize('with_requirements', [False, True])
@pytest.mark.parametrize('mutation', ['hash', 'role', 'coordinates', 'region_kind', 'nondict'])
def test_abstained_auxiliaries_retain_ordinary_record_validation(with_requirements, mutation):
    reference, _ = loaded()
    doc = next(d for d in reference['documents'] if d['id'] == 'marker_after_inicio')
    output = oracle(doc)
    record = output['records'][0]
    proof = {**deepcopy(record['evidence'][0]), 'role': 'unit_scaffold_tail'}
    record['evidence'].append(proof)
    if mutation == 'hash':
        proof['document_sha256'] = '0' * 64
    elif mutation == 'role':
        # Keep a scaffold role to reproduce the former contract-mode trigger.
        record['evidence'].append({**deepcopy(proof), 'role': 'UNKNOWN'})
    elif mutation == 'coordinates':
        proof['region']['end'] += 1
    elif mutation == 'region_kind':
        proof['region']['kind'] = 'rectangle'
    else:
        record['evidence'].append(None)
    requirements = {'unused-positive': {'unit_scope_basis': 'same_page_explicit', 'proofs': []}} if with_requirements else None
    report = evaluator.score(doc, output, requirements)
    first = report['challenge_diagnostics_v1_2'][0]
    assert first['safety'] == 'no_claim_unknown'
    assert first['malformed_record'] is True
    assert first['explicit_abstention'] is False
    assert report['record_errors']
    assert report['metrics']['output']['invalid_records'] == 1
    assert report['metrics']['challenges']['invalid_records'] == 1
    assert report['metrics']['challenges']['explicit_abstentions'] == 1


@pytest.mark.parametrize('location', ['header', 'tail_metadata', 'prefix_metadata'])
@pytest.mark.parametrize('marker', ['Inicio: Observar tarjetas.', 'Desarrollo: Observar tarjetas.',
                                    'Cierre: Compartir tarjetas.', 'Proyecto: Otro',
                                    'SESIÓN 2: Otra', 'DATOS GENERALES',
                                    'Inicio\u00a0: Observar.', 'SESIÓN2: Otra', 'DATOS\u00a0GENERALES'])
@pytest.mark.parametrize('separator', ['\t', ' '])
def test_embedded_structure_is_not_metadata_or_an_empty_scaffold_header(location, marker, separator):
    prior, current = 'SESIÓN 1: Formas\n', 'PDA: Describe formas.\nInicio:\n'
    if location == 'header':
        prior = 'SESIÓN 1: Formas' + separator + marker + '\n'
    elif location == 'tail_metadata':
        prior += 'Fecha: 2026-01-20' + separator + marker + '\n'
    else:
        current = 'Fecha: 2026-01-20' + separator + marker + '\n' + current
    doc, output = custom_scaffold(prior, current)
    assert_scope_only_failure(doc, output, None)


@pytest.mark.parametrize('bullet', ['*', '+', '◦', '1.', '1)', '12.', '12)', '-', '•'])
@pytest.mark.parametrize('gap', ['', ' '])
def test_distinct_activity_bullets_cannot_be_absorbed_into_curricular_wrapping(bullet, gap):
    doc, output = custom_scaffold('SESIÓN 1: Formas\n',
                                  'Contenido: Formas\n' + bullet + gap + 'Observar tarjetas.\n'
                                  'PDA: Describe formas.\nInicio:\n')
    assert_scope_only_failure(doc, output, None)


def test_ordinary_metadata_and_nonlabelled_moment_words_remain_admissible():
    doc, output = custom_scaffold('SESIÓN 1: Formas\nTema de la sesión: El inicio del juego\n',
                                  'Organización: Equipos para el cierre del juego\n'
                                  'PDA: Describe formas.\nInicio:\n')
    assert evaluator.score(doc, output)['metrics']['strict_session_claims']['correct'] == 1


@pytest.mark.parametrize('location', ['header', 'tail_metadata', 'prefix_activity'])
def test_unit_separator_control_cannot_bypass_structural_proof_guards(location):
    prior, current = 'SESIÓN 1: Formas\n', 'PDA: Describe formas.\nInicio:\n'
    if location == 'header':
        prior = 'SESIÓN 1: Formas\x1f\n'
    elif location == 'tail_metadata':
        prior += 'Organización: Parejas\x1f\n'
    else:
        current = 'Contenido: Formas\n\x1f-Observar tarjetas.\n' + current
    doc, output = custom_scaffold(prior, current)
    assert_scope_only_failure(doc, output, None)


def scaffold_after_document_prefix(prefix_pages, before_header=''):
    doc, original = custom_scaffold(before_header + 'SESIÓN 1: Formas\n', 'PDA: Describe formas.\nInicio:\n')
    shift = len(prefix_pages)
    doc['pages'] = list(prefix_pages) + doc['pages']
    for unit in doc['units']:
        unit['anchor']['page'] += shift
    for declaration in doc['declarations']:
        for field in ('label', 'value'):
            declaration[field]['page'] += shift
    proofs = [dict(role=ref['role'], page=ref['page_number'] + shift,
                   start=ref['region']['start'], end=ref['region']['end'], quote=ref['excerpt'])
              for ref in original['records'][0]['evidence'] if ref['role'].startswith('unit_scaffold_')]
    requirement = dict(document_id=doc['id'], declaration_id='d1',
                       unit_scope_basis='structural_scaffold_proposal', proofs=proofs)
    return doc, oracle(doc, [requirement])


@pytest.mark.parametrize('opening,closing', [('«', '»'), ('“', '”'), ('"', '"')])
def test_quote_entering_scaffold_from_earlier_document_page_blocks_scope(opening, closing):
    doc, output = scaffold_after_document_prefix(['Ejemplo citado:\n' + opening + '\n'])
    assert_scope_only_failure(doc, output, None)
    # Reading all prior pages also permits a quote that closes before the unit,
    # even when its opening and closing delimiters are on different pages.
    doc, output = scaffold_after_document_prefix(['Ejemplo citado:\n' + opening + '\n'], closing + '\n')
    assert evaluator.score(doc, output)['metrics']['strict_session_claims']['correct'] == 1
    doc, output = scaffold_after_document_prefix(['Ejemplo citado:\n' + opening + 'Texto citado.' + closing + '\n'])
    assert evaluator.score(doc, output)['metrics']['strict_session_claims']['correct'] == 1


@pytest.mark.parametrize('indent', ['\u00a0', '\u1680', '\u2000', '\u2001', '\u2002', '\u2003',
                                   '\u2004', '\u2005', '\u2006', '\u2007', '\u2008', '\u2009',
                                   '\u200a', '\u202f', '\u205f', '\u3000'])
@pytest.mark.parametrize('bullet', ['-Observar tarjetas.', '• Observar tarjetas.', '* Observar tarjetas.',
                                   '+ Observar tarjetas.', '◦ Observar tarjetas.', '1.Observar tarjetas.', '1)Observar tarjetas.'])
def test_unicode_horizontal_indentation_does_not_hide_activity_lines(indent, bullet):
    doc, output = custom_scaffold('SESIÓN 1: Formas\n',
                                  'Contenido: Formas\n' + indent + bullet + '\n'
                                  'PDA: Describe formas.\nInicio:\n')
    assert_scope_only_failure(doc, output, None)


@pytest.mark.parametrize('separator', ['\v', '\f', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029'])
def test_activity_horizontal_class_never_consumes_vertical_separators(separator):
    assert evaluator._SCOPE_ACTIVITY.match(separator + '-Observar tarjetas.') is None
    doc, output = custom_scaffold('SESIÓN 1: Formas\n',
                                  'Contenido: Formas' + separator + '-Observar tarjetas.\n'
                                  'PDA: Describe formas.\nInicio:\n')
    assert_scope_only_failure(doc, output, None)


@pytest.mark.parametrize('marker', ['Inicio: -Observar tarjetas.', 'Desarrollo: -Observar tarjetas.',
                                    'Cierre: -Compartir tarjetas.', 'Proyecto: Otro', 'SESIÓN2: Otra',
                                    'SESIÓN 2: Otra', 'DATOS GENERALES', 'Inicio\u00a0: -Observar tarjetas.'])
def test_embedded_structural_cut_inside_complete_typed_value_loses_scope_only(marker):
    entire_value = 'Describe formas. ' + marker
    current = 'PDA: ' + entire_value + '\nInicio:\n-Compartir.\n'
    doc, output = custom_scaffold('SESIÓN 1: Formas\n', current)
    # Pin the entire source value, so a partial-value mismatch cannot be the
    # reason the independent structural guard rejects the proposed scope.
    authored_value = doc['declarations'][0]['value']
    authored_value.update(end=authored_value['start'] + len(entire_value), quote=entire_value)
    record = output['records'][0]
    value_ref = next(ref for ref in record['evidence'] if ref['role'] == 'value')
    value_ref.update(excerpt=entire_value)
    value_ref['region']['end'] = authored_value['end']
    record['claim']['object_value'] = entire_value
    sync(record)
    report = assert_scope_only_failure(doc, output, None)
    assert any('curricular block contains an embedded' in error
               for detail in report['unit_errors'] for error in detail['errors'])
