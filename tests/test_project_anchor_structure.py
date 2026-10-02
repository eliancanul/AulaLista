"""Opt-in structural catalogue tests, original synthetic evidence only."""
import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.anchor_scope_audit import ScopeAuditConfig, ScopeAuditError, audit_scopes
from scripts.anchor_scope_catalogue import canonical, catalogue_from_sources, document_hash, sha
from scripts.replay_interpretation import replay_scope_audit
from scripts.session_declarations import extract_declarations
from test_anchor_scope_audit import Stub

FIXTURE = Path(__file__).parent / 'fixtures/interpretation/project_anchor_structure_v1.json'
DOCS = json.loads(FIXTURE.read_text())['documents']


def catalogue(doc, enabled=True):
    return catalogue_from_sources({'documents': [{'id': doc['id'], 'pages': doc['pages']}]},
                                  governing_projects=enabled)


def book_entries(result):
    return [e for e in result['entries'] if e['kind'] == 'project'
            and e['excerpt'].casefold().startswith('proyecto del libro')]


@pytest.mark.parametrize('doc', DOCS, ids=[d['id'] for d in DOCS])
def test_frozen_target_promotions_and_nonpromotions(doc):
    result = catalogue(doc)
    target = [e for e in book_entries(result) if e['eligibility'] == 'selectable']
    assert len(target) == (1 if doc['expected_selectable'] else 0)
    assert result['catalog_version'] == 'anchor-catalogue.v2'
    assert result['project_structure_version'] == 'project-anchor-structure.v1'
    assert not result['scope_semantics_approved']
    if target:
        entry = target[0]
        assert entry['text_role'] == 'governing_heading'
        assert entry['recognition_reason'] == 'structurally_governing_book_project'
        for key in ('page_number', 'start', 'end', 'excerpt', 'excerpt_sha256'):
            assert entry[key] == doc['anchor'][key]
        assert entry['document_sha256'] == doc['document_sha256']
        proof = entry['structural_evidence']
        assert len(proof) == len(doc['proof'])
        for actual, expected in zip(proof, doc['proof']):
            assert {k: actual[k] for k in expected} == expected
            assert actual['document_id'] == doc['id']
            assert actual['document_sha256'] == doc['document_sha256']
        assert {s['page_number'] for s in proof} == {entry['page_number']}
        binding = {k: entry[k] for k in ('document_id', 'document_sha256', 'page_number',
                   'start', 'end', 'kind', 'excerpt_sha256')}
        assert entry['anchor_id'] == 'anchor:' + sha(canonical(binding))
    if doc['id'] == 'reference-second-project':
        other = [e for e in result['entries'] if e['excerpt'] == 'Proyecto: Otro trabajo']
        assert len(other) == 1 and other[0]['eligibility'] == 'selectable'


def test_default_and_false_preserve_original_v1_bytes_for_all_synthetic_sources():
    # Frozen canonical v1 output hash over the unchanged 43 original synthetic
    # documents, generated with preserved baseline429397d, never the new grammar.
    # No Git history, private source, PDF or network is required by this test.
    expected = '0333b27d240794c10b6524c7267630abf5022eb9eac7e770627fcc865f7ee36c'
    sources = [{'documents': [{'id': d['id'], 'pages': d['pages']}]} for d in DOCS]
    assert sha(canonical([catalogue_from_sources(s) for s in sources])) == expected
    assert sha(canonical([catalogue_from_sources(s, governing_projects=False) for s in sources])) == expected


def test_physical_repetition_keeps_ids_and_review_veto():
    original = DOCS[0]
    doc = dict(id='REPEATED', pages=original['pages'] * 2)
    targets = [a for a in book_entries(catalogue(doc)) if a['eligibility'] == 'selectable']
    assert len(targets) == 2
    assert targets[0]['anchor_id'] != targets[1]['anchor_id']
    assert all(a['repeated_literal'] for a in targets)


@pytest.mark.parametrize('opt_in', [1, 0, None, 'true', {}, []])
def test_nonboolean_opt_in_is_rejected(opt_in):
    with pytest.raises(ValueError, match='invalid governing projects'):
        catalogue_from_sources({'documents': [{'id': 'S', 'pages': DOCS[0]['pages']}]},
                               governing_projects=opt_in)
    provider = Stub()
    result = audit_scopes(pages=DOCS[0]['pages'], declarations=extract_declarations(DOCS[0]['pages'], source_doc_sha256=document_hash(DOCS[0]['pages'])),
                         config=ScopeAuditConfig('S', provider, True, governing_projects=opt_in))
    assert result['errors'] == ['governing_projects_contract']
    assert provider.calls == 0


def run_structural(pages, enabled=True, provider=None):
    provider = provider or Stub()
    result = extract_declarations(pages, source_doc_sha256=document_hash(pages),
                                  scope_audit=ScopeAuditConfig('S', provider, True, governing_projects=enabled))
    return result, provider


def test_opt_in_adds_only_detached_candidates_and_preserves_literal_baseline():
    pages = copy.deepcopy(DOCS[0]['pages'])
    baseline = extract_declarations(pages, source_doc_sha256=document_hash(pages))
    enabled, provider = run_structural(pages)
    routed = [r for r in baseline['records'] if r['reason'] == 'unresolved_scope']
    assert len(routed) == 1
    assert {k: v for k, v in enabled.items() if k != 'scope_audit'} == baseline
    assert enabled['scope_audit']['status'] == 'candidates_for_review'
    assert len(enabled['scope_audit']['candidates']) == 1
    candidate = enabled['scope_audit']['candidates'][0]
    assert candidate['anchor_kind'] == 'project'
    assert candidate['state'] == 'needs_human_review'
    assert not candidate['semantic_validation'] and not candidate['production_applied'] and not candidate['claim_emitted']
    assert all(r['unit'] is None and r['claim'] is None for r in enabled['records'])
    assert pages == DOCS[0]['pages']
    assert provider.calls == 1 and enabled['scope_audit']['external_calls'] == 0
    default, _ = run_structural(pages, False)
    assert default['scope_audit']['status'] == 'invalid'
    assert default['scope_audit']['errors'] == ['anchor_not_selectable']


def test_opt_in_is_not_enabled_by_disabled_scope_config():
    pages = DOCS[0]['pages']
    provider = Stub(fail=True)
    baseline = extract_declarations(pages, source_doc_sha256=document_hash(pages))
    outcome = extract_declarations(pages, source_doc_sha256=document_hash(pages),
                                  scope_audit=ScopeAuditConfig('S', provider, False, governing_projects=True))
    assert outcome == baseline and provider.calls == 0


def test_replay_reconstructs_mode_and_source_proof_and_refuses_rehashed_mutations():
    _, provider = run_structural(DOCS[0]['pages'])
    request, recordings = provider.last_request, provider.last_recordings
    assert replay_scope_audit(request=request, recordings=recordings)['status'] == 'candidates_for_review'
    for broken in [replace(request, governing_projects=False), replace(request, governing_projects=1)]:
        with pytest.raises(ScopeAuditError):
            replay_scope_audit(request=broken, recordings=recordings)
    changed = copy.deepcopy(request.catalogue)
    changed['entries'][0]['structural_evidence'][0]['excerpt'] = 'fabricated'
    with pytest.raises(ScopeAuditError, match='catalogue_source_reconstruction_mismatch'):
        replay_scope_audit(request=replace(request, catalogue=changed), recordings=recordings)
    changed = copy.deepcopy(request.catalogue)
    changed['entries'][0]['document_sha256'] = '0' * 64
    with pytest.raises(ScopeAuditError, match='catalogue_source_reconstruction_mismatch'):
        replay_scope_audit(request=replace(request, catalogue=changed), recordings=recordings)


def test_old_v1_recordings_cannot_be_reused_against_opt_in_catalogue():
    _, provider = run_structural(DOCS[0]['pages'], False)
    request = provider.last_request
    upgraded = catalogue_from_sources({'documents': [{'id': request.document_id, 'pages': list(request.pages)}]},
                                       governing_projects=True)
    with pytest.raises(ScopeAuditError, match='catalog_hash_mismatch'):
        replay_scope_audit(request=replace(request, catalogue=upgraded, governing_projects=True),
                           recordings=provider.last_recordings)


@pytest.mark.parametrize('barrier', ['proyecto:\n', 'Resumen asociado al\nproyecto:\n', 'SESIÓN S/N\n', 'DATOS GENERALES\n'])
def test_opt_in_does_not_relax_unwitnessed_later_barriers(barrier):
    page = DOCS[0]['pages'][0]
    page = page.replace('PDA:', barrier + 'PDA:')
    result, _ = run_structural([page])
    assert result['scope_audit']['status'] == 'invalid'
    assert result['scope_audit']['candidates'] == []


@pytest.mark.parametrize('transform', [
    lambda s: s.replace('Proyecto del Libro\nde Texto:', 'Proyecto del Libro:'),
    lambda s: s.replace('Temas asociados al\nproyecto:\n✓ Formas de papel.\n', ''),
    lambda s: s.replace('Construir un objeto de papel.', 'Construir un objeto de papel\npara una muestra.'),
    lambda s: s.replace('Contenidos/PDA asociados al proyecto:', 'Contenidos/PDA asociados al proyecto: Vinculación con otro campo:'),
    lambda s: s.replace('Planeación didáctica', '  PLANEACIÓN DIDÁCTICA  ').replace('Escenario:', 'ESCENARIO:'),
])
def test_supported_narrow_positive_variants_without_expanding_frozen_denominators(transform):
    page = transform(DOCS[0]['pages'][0])
    result = catalogue(dict(id='VARIANT', pages=[page]))
    assert len([e for e in book_entries(result) if e['eligibility'] == 'selectable']) == 1


@pytest.mark.parametrize('transform', [
    lambda s: s.replace('Escenario: -Taller.', 'Escenario: Si es posible en el taller.'),
    lambda s: s.replace('Propósito: Construir un objeto de papel.', 'Propósito: Se propone construir un objeto de papel.'),
    lambda s: s.replace('Producto: Una brújula de cartón.', 'Producto: Pendiente.'),
    lambda s: s.replace('Producto: Una brújula de cartón.', 'Producto: Una brújula de cartón.\nProducto:'),
    lambda s: s.replace('Contenidos/PDA asociados al proyecto:', 'Contenidos/PDA asociados al proyecto:\nContenidos/PDA asociados al proyecto: Título distinto:'),
    lambda s: s.replace('Planeación didáctica', '\u2028Planeación didáctica'),
    lambda s: s.replace('Proyecto del Libro', '\x0bProyecto del Libro'),
    lambda s: s.replace('La brújula de cartón', '(30-34)'),
])
def test_unsupported_empty_nonadopted_duplicate_and_separator_witnesses_stay_references(transform):
    page = transform(DOCS[0]['pages'][0])
    result = catalogue(dict(id='UNSUPPORTED', pages=[page]))
    assert not [e for e in book_entries(result) if e['eligibility'] == 'selectable']


def test_prior_page_example_context_survives_virtual_boundary_at_root():
    pages = ['Ejemplo: Fuente sin salto final', DOCS[0]['pages'][0]]
    assert not [e for e in book_entries(catalogue(dict(id='EXAMPLE', pages=pages))) if e['eligibility'] == 'selectable']


def test_source_change_changes_physical_id_without_normalizing_title_or_evidence():
    doc = dict(id='SOURCE', pages=DOCS[0]['pages'])
    before = book_entries(catalogue(doc))[0]
    changed = dict(id='SOURCE', pages=[doc['pages'][0] + '\nNota adicional.'])
    after = book_entries(catalogue(changed))[0]
    assert before['excerpt'] == after['excerpt']
    assert before['document_sha256'] != after['document_sha256']
    assert before['anchor_id'] != after['anchor_id']


def test_same_proof_cannot_select_other_document_anchor():
    first = dict(id='S', pages=DOCS[0]['pages'])
    second = dict(id='OTHER', pages=DOCS[0]['pages'])
    source = {'documents': [first, second]}
    text = json.dumps(source, ensure_ascii=False)
    provider = Stub(mutate=lambda response, request: [d.update(anchor_id=next(a['anchor_id'] for a in request.catalogue['entries'] if a['document_id']=='OTHER')) for d in response['record_decisions']])
    output = extract_declarations(first['pages'], source_doc_sha256=document_hash(first['pages']),
                                  scope_audit=ScopeAuditConfig('S', provider, True, source_windows_text=text,
                                                              source_windows_sha256=sha(text.encode()), governing_projects=True))
    assert output['scope_audit']['status'] == 'invalid'
    assert output['scope_audit']['errors'] == ['foreign_anchor_document']
    assert output['scope_audit']['candidates'] == []


@pytest.mark.parametrize('middle', [
    '«\nPropósito: Ordenar las hojas\nProducto: Un reloj\n»',
    'Propósito: Inicio: ordenar las hojas\nProducto: Un reloj',
    'Propósito: Ordenar las hojas\nLunes SESIÓN S/N\nProducto: Un reloj',
    'Propósito: Ordenar las hojas\nEjemplo:\nProducto: Un reloj',
])
def test_independent_review_quoted_inline_activity_and_unknown_session_repros(middle):
    page = ('Planeación didáctica\nProyecto del Libro de Texto: El reloj de hojas\n'
            'Escenario: Aula\n' + middle + '\nContenidos/PDA asociados al proyecto:\n'
            'PDA: Ordena las hojas por tamaño.\n')
    result = catalogue(dict(id='REVIEW', pages=[page]))
    assert not [e for e in book_entries(result) if e['eligibility'] == 'selectable']
    output, _ = run_structural([page])
    assert output['scope_audit']['candidates'] == []


def test_independent_review_mixed_metadata_witness_repro():
    page = ('Planeación didáctica\nProyecto del Libro de Texto: El reloj de hojas\n'
            'Escenario: Aula Producto: Otro\nPropósito: Ordenar las hojas\nProducto: Un reloj\n'
            'Contenidos/PDA asociados al proyecto:\nPDA: Ordena las hojas por tamaño.\n')
    assert not [e for e in book_entries(catalogue(dict(id='MIXED', pages=[page]))) if e['eligibility'] == 'selectable']
    output, _ = run_structural([page])
    assert output['scope_audit']['candidates'] == []


@pytest.mark.parametrize('transform', [
    lambda s: s.replace('Construir un objeto de papel.', 'Construir un objeto de papel\npara un trabajo Inicio: recortar.'),
    lambda s: s.replace('Metodología: Trabajo por proyectos.', 'Metodología: Inicio: recortar.'),
    lambda s: s.replace('Campo formativo: Lenguajes', 'Tiempo: Inicio: recortar.'),
    lambda s: s.replace('Construir un objeto de papel.', 'Construir un objeto de papel\nTaller Producto: Otro.'),
    lambda s: s.replace('Campo formativo: Lenguajes', 'Campo formativo: Lenguajes PDA: Otro.'),
    lambda s: s.replace('La brújula de cartón', 'Planeación didáctica'),
    lambda s: s.replace('La brújula de cartón', 'Lunes SESIÓN S/N'),
    lambda s: s.replace('La brújula de cartón', 'Proyecto del Libro'),
    lambda s: s.replace('La brújula de cartón', 'SESIÓN 1'),
])
def test_review_inline_activity_mixed_continuation_and_heading_as_title_repros(transform):
    page = transform(DOCS[0]['pages'][0])
    assert not [e for e in book_entries(catalogue(dict(id='REVIEW2', pages=[page]))) if e['eligibility'] == 'selectable']
    output, _ = run_structural([page])
    assert output['scope_audit']['candidates'] == []


@pytest.mark.parametrize('title', ['Proyecto del bosque', 'Planeación didáctica', 'Lunes SESIÓN S/N'])
def test_explicit_inline_title_is_not_a_new_physical_unit_line(title):
    page = DOCS[0]['pages'][0].replace('Proyecto del Libro\nde Texto:\nLa brújula de cartón',
                                     'Proyecto del Libro de Texto: ' + title)
    targets = [e for e in book_entries(catalogue(dict(id='INLINE', pages=[page]))) if e['eligibility']=='selectable']
    assert len(targets) == 1
    assert next(p['excerpt'] for p in targets[0]['structural_evidence'] if p['role']=='project_title') == title


@pytest.mark.parametrize('value', ['«Ordenar las hojas»', '“Ordenar las hojas”', '"Ordenar las hojas"'])
def test_quoted_support_value_stays_outside_bounded_unquoted_metadata_proof(value):
    page = DOCS[0]['pages'][0].replace('Construir un objeto de papel.', value)
    assert not [e for e in book_entries(catalogue(dict(id='QUOTED_SUPPORT', pages=[page]))) if e['eligibility']=='selectable']


def test_long_original_synthetic_metadata_does_not_change_witnesses():
    page = DOCS[0]['pages'][0].replace('Campo formativo: Lenguajes',
                                     'Campo formativo: Lenguajes\n' + 'Una descripción complementaria.\n' * 1000)
    targets = [e for e in book_entries(catalogue(dict(id='LONG', pages=[page]))) if e['eligibility']=='selectable']
    assert len(targets) == 1
    assert targets[0]['excerpt'] == DOCS[0]['anchor']['excerpt']
