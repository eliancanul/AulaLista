"""PDA recovery enters only exact current, complete, source-rebuilt Mode A groups."""
import copy
from dataclasses import replace

import pytest

from scripts.session_declarations import extract_declarations, snapshot_hash
from scripts.anchor_scope_audit import ScopeAuditConfig, ScopeAuditError, route_record, validate_scope_recordings
from test_anchor_scope_audit import Stub

PAGES = ['Proyecto: Formas\n\nLenguajes\nAB1. Descripción de formas.\n'
         '-AB1 PDA1: Identifica las formas.\n-AB1 PDA2: Distingue los tamaños.\nRecursos:\n']


def extract(pages=PAGES, **kwargs):
    return extract_declarations(pages, source_doc_sha256=snapshot_hash(pages), **kwargs)


def test_complete_pda_recovery_to_source_replay_pipeline_is_review_only():
    baseline = extract(pda_context=True)
    provider = Stub()
    result = extract(pda_context=True, scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True, pda_context=True))
    assert {k: v for k, v in result.items() if k != 'scope_audit'} == baseline
    assert provider.last_request.pda_context is True
    assert len(baseline['pda_context']['recoveries']) == 2
    assert result['scope_audit']['status'] == 'candidates_for_review'
    assert len(result['scope_audit']['candidates']) == 2
    for proposal in result['scope_audit']['candidates']:
        assert proposal['state'] == 'needs_human_review'
        assert proposal['semantic_validation'] is False
        assert proposal['production_applied'] is False
        assert proposal['claim_emitted'] is False
    assert all(record['unit'] is None and record['claim'] is None for record in result['records'])


@pytest.mark.parametrize('mutation', ['cropped_value', 'wrong_reason', 'wrong_kind', 'false_claim', 'source_changed'])
def test_router_never_trusts_a_forged_recovery_record(mutation):
    record = copy.deepcopy(extract(pda_context=True)['records'][0])
    doc = {'id': 'SYNTHETIC', 'pages': list(PAGES)}
    assert route_record(doc, record, pda_context=True)['eligible'] is True
    if mutation == 'cropped_value':
        record['evidence'][1]['region']['end'] -= 1
        record['evidence'][1]['excerpt'] = record['evidence'][1]['excerpt'][:-1]
    elif mutation == 'wrong_reason':
        record['reason'] = 'label_mention'
    elif mutation == 'wrong_kind':
        record['kind'] = 'contenido'
    elif mutation == 'false_claim':
        record['claim'] = {'fake': True}
    else:
        doc['pages'][0] = PAGES[0].replace('formas.', 'figuras.')
    assert route_record(doc, record, pda_context=True)['eligible'] is False


@pytest.mark.parametrize('mutation', ['option_off', 'group_subset', 'source_changed', 'record_changed'])
def test_public_replay_reconstructs_current_pda_profile_and_full_group(mutation):
    provider = Stub()
    extract(pda_context=True, scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True, pda_context=True))
    request = provider.last_request
    if mutation == 'option_off':
        request = replace(request, pda_context=False)
    elif mutation == 'group_subset':
        groups = copy.deepcopy(request.groups)
        groups[1].pop()
        request = replace(request, groups=groups)
    elif mutation == 'source_changed':
        request = replace(request, pages=(PAGES[0] + ' ',))
    else:
        groups = copy.deepcopy(request.groups)
        groups[1][0]['immutable_value_span']['excerpt'] = 'Forged'
        request = replace(request, groups=groups)
    with pytest.raises(ScopeAuditError):
        validate_scope_recordings(request=request, recordings=provider.last_recordings)


def test_missing_record_in_prior_packet_cannot_be_recycled_as_current_group():
    provider = Stub(mutate_packet=lambda packet: packet['records'].pop())
    result = extract(pda_context=True, scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True, pda_context=True))
    assert result['scope_audit']['status'] == 'invalid'
    assert result['scope_audit']['candidates'] == []
    assert result['scope_audit']['errors'] == ['current_record_binding_mismatch']


@pytest.mark.parametrize('extract_flag,audit_flag', [(True, False), (False, True)])
def test_profile_mismatch_rejects_before_provider_invocation(extract_flag, audit_flag):
    provider = Stub()
    result = extract(pda_context=extract_flag,
                     scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True, pda_context=audit_flag))
    assert provider.calls == 0
    assert result['scope_audit']['errors'] == ['pda_context_config_mismatch']


@pytest.mark.parametrize('flag', [None, 0, 1, 'true', {}, []])
def test_pda_route_and_config_require_a_literal_boolean(flag):
    record = extract(pda_context=True)['records'][0]
    with pytest.raises(ValueError):
        route_record({'id': 'SYNTHETIC', 'pages': PAGES}, record, pda_context=flag)
    provider = Stub()
    result = extract(pda_context=True, scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True, pda_context=flag))
    assert provider.calls == 0
    assert result['scope_audit']['errors'] == ['pda_context_contract']


@pytest.mark.parametrize('local,pda', [(False, False), (False, True), (True, False), (True, True)])
def test_profile_pairs_and_mixed_evidence_preserve_each_scope_group(local, pda):
    pages = ['Proyecto: Formas\n\nContenido local:\n- Nombres de figuras.\nRecursos:\n',
             'Lenguajes\nAB1. Descripción de figuras.\n-AB1 PDA1: Identifica formas.\nRecursos:\n',
             'Sesión 2\nContenidos/PDA: Describe formas.\nInicio:\nLeer.']
    provider = Stub()
    options = dict(literal_recovery=local, pda_context=pda)
    config = ScopeAuditConfig('SYNTHETIC', provider, True, **options)
    before = extract(pages, **options, scope_audit=config)
    before_request = copy.deepcopy(getattr(provider, 'last_request', None))
    mixed = extract(pages, **options, mixed_fields=True, scope_audit=config)
    assert before['scope_audit'] == mixed['scope_audit']
    if before_request:
        assert before_request == provider.last_request
    assert all(r['kind'] is not None for group in (before_request.groups.values() if before_request else []) for r in group)


@pytest.mark.parametrize('mutation', ['missing', 'reordered', 'empty', 'tampered'])
def test_input_group_forgery_fails_before_any_provider_call(mutation):
    from scripts.anchor_scope_audit import audit_scopes
    base = extract(pda_context=True)
    if mutation == 'missing':
        base['records'].pop()
    elif mutation == 'reordered':
        base['records'].reverse()
    elif mutation == 'empty':
        base['records'].clear()
    else:
        base['records'][0]['claim'] = {'fake': True}
    provider = Stub()
    result = audit_scopes(pages=PAGES, declarations=base,
                          config=ScopeAuditConfig('SYNTHETIC', provider, True, pda_context=True))
    assert result['status'] == 'invalid'
    assert result['errors'] == ['current_route_reconstruction_mismatch']
    assert provider.calls == result['provider_attempts'] == 0


@pytest.mark.parametrize('old_flags,new_flags', [
    ((False, False), (False, True)), ((False, True), (False, False)),
    ((True, True), (False, True)), ((False, True), (True, True)),
    ((False, False), (True, True)), ((True, True), (False, False)),
])
def test_profile_changes_reject_old_recording_even_when_groups_are_identical(old_flags, new_flags):
    from test_anchor_scope_audit import PAGES as LEGACY
    provider = Stub()
    local, pda = old_flags
    extract(LEGACY, literal_recovery=local, pda_context=pda,
            scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True, literal_recovery=local, pda_context=pda))
    request = replace(provider.last_request, literal_recovery=new_flags[0], pda_context=new_flags[1])
    with pytest.raises(ScopeAuditError, match='profile_group'):
        validate_scope_recordings(request=request, recordings=provider.last_recordings)


def test_code_fingerprint_changes_invalidate_identical_current_groups(monkeypatch):
    from pathlib import Path
    from test_anchor_scope_audit import PAGES as LEGACY
    provider = Stub()
    extract(LEGACY, pda_context=True,
            scope_audit=ScopeAuditConfig('SYNTHETIC', provider, True, pda_context=True))
    original = Path.read_bytes
    def changed(path):
        raw = original(path)
        return raw + b'\n# changed code' if path.name == 'pda_context_recovery.py' else raw
    monkeypatch.setattr(Path, 'read_bytes', changed)
    with pytest.raises(ScopeAuditError, match='current_profile_group_binding'):
        validate_scope_recordings(request=provider.last_request, recordings=provider.last_recordings)


def test_provider_kind_property_error_is_sanitized_before_invocation():
    class Broken:
        @property
        def kind(self):
            raise RuntimeError('private provider details must not escape')
        def propose(self, request):
            raise AssertionError('must not be invoked')
    result = extract(pda_context=True, scope_audit=ScopeAuditConfig('SYNTHETIC', Broken(), True, pda_context=True))
    assert result['scope_audit']['errors'] == ['provider_failure']
    assert result['scope_audit']['provider_attempts'] == 0
