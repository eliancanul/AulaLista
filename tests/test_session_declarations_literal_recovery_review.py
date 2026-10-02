"""Independent fail-closed regressions for the opt-in source grammar."""
import copy
from dataclasses import replace

import pytest

from scripts.session_declarations import extract_declarations, snapshot_hash
from scripts.anchor_scope_audit import (
    ScopeAuditConfig, ScopeAuditError, audit_scopes, route_record, validate_scope_recordings,
)


BASE_PAGE = (
    'DATOS GENERALES\nContenido local:\n'
    '- Nombres de fichas.\n- Formas de marcas.\nRecursos:\n'
)
NONPHYSICAL_VERTICALS = ('\v', '\f', '\x1c', '\x1d', '\x1e', '\x1f', '\x85', '\u2028', '\u2029')


def recover(page):
    return extract_declarations([page], source_doc_sha256=snapshot_hash([page]),
                                literal_recovery=True)


@pytest.mark.parametrize('separator', NONPHYSICAL_VERTICALS, ids=lambda s: f'U+{ord(s):04X}')
@pytest.mark.parametrize('position', [
    'before_closure', 'before_item', 'after_item', 'before_root', 'after_root',
])
def test_nonphysical_vertical_rows_never_become_closed_list_or_context(separator, position):
    if position == 'before_closure':
        page = BASE_PAGE.replace('Recursos:', separator + 'Recursos:')
    elif position == 'before_item':
        page = BASE_PAGE.replace('- Nombres', separator + '- Nombres')
    elif position == 'after_item':
        page = BASE_PAGE.replace('fichas.\n', 'fichas.' + separator + '\n')
    elif position == 'before_root':
        page = BASE_PAGE.replace('DATOS GENERALES', separator + 'DATOS GENERALES')
    else:
        page = BASE_PAGE.replace('DATOS GENERALES', 'DATOS GENERALES' + separator)
    output = recover(page)
    assert output['literal_recovery']['recoveries'] == []
    assert all(record['claim'] is None for record in output['records'])


@pytest.mark.parametrize('indentation', [' ', '\t', '\u00a0', '\u2003'])
def test_supported_horizontal_indentation_still_preserves_the_full_list(indentation):
    page = BASE_PAGE.replace('- Nombres', indentation + '- Nombres').replace(
        'Recursos:', indentation + 'Recursos:')
    output = recover(page)
    proof, = output['literal_recovery']['recoveries']
    record, = [r for r in output['records'] if r['id'] == proof['record_id']]
    value, = [e for e in record['evidence'] if e['role'] == 'value']
    assert value['excerpt'] == '- Nombres de fichas.\n- Formas de marcas.'
    assert page[value['region']['start']:value['region']['end']] == value['excerpt']


def test_opt_in_control_guard_never_changes_legacy_metadata_corroboration():
    # Preserve the pre-implementation default, including its existing limits.
    # Recovery-specific hardening must not tighten this older shared helper.
    page = ('DATOS GENERALES\nCampo formativo: Lenguajes\n'
            'Contenido: Nombres de fichas.\nL1 Identificación de fichas.\n'
            'PDA1: Describe una \x00ficha.\n')
    default = extract_declarations([page], source_doc_sha256=snapshot_hash([page]))
    explicit_false = extract_declarations([page], source_doc_sha256=snapshot_hash([page]),
                                          literal_recovery=False)
    assert default == explicit_false
    contenido, = [r for r in default['records'] if r['evidence'][0]['excerpt'] == 'Contenido:']
    assert contenido['reason'] == 'unresolved_scope'
    value, = [e for e in contenido['evidence'] if e['role'] == 'value']
    assert value['excerpt'] == 'Nombres de fichas.'


SCOPE_PAGE = ('Proyecto: Fichas\n\nContenido local:\n- Nombres de marcas.\n'
              '- Formas de señales.\nRecursos:\n')


@pytest.mark.parametrize('mutation', ['cropped_value', 'source_hash', 'reason', 'decision', 'stale_source'])
def test_current_source_route_never_trusts_forged_or_stale_local_records(mutation):
    output = recover(SCOPE_PAGE)
    record, = copy.deepcopy(output['records'])
    doc = {'id': 'SYNTHETIC_REVIEW', 'pages': [SCOPE_PAGE]}
    assert route_record(doc, record, literal_recovery=True)['eligible'] is True
    if mutation == 'cropped_value':
        value, = [e for e in record['evidence'] if e['role'] == 'value']
        value['excerpt'] = value['excerpt'].split('\n')[0]
        value['region']['end'] = value['region']['start'] + len(value['excerpt'])
    elif mutation == 'source_hash':
        record['evidence'][1]['document_sha256'] = 'a' * 64
    elif mutation == 'reason':
        record['reason'] = 'explicit_session'
    elif mutation == 'decision':
        record['decision'] = 'candidate'
    else:
        doc['pages'] = [SCOPE_PAGE.replace('Formas', 'Colores')]
    assert route_record(doc, record, literal_recovery=True)['eligible'] is False


class CaptureOnlyProvider:
    kind = 'synthetic_test'

    def __init__(self):
        self.calls = 0
        self.request = None

    def propose(self, request):
        self.calls += 1
        self.request = request
        return []


@pytest.mark.parametrize('mutation', ['cropped_value', 'changed_reason', 'flag_off', 'source_changed'])
def test_replay_reconstructs_current_groups_before_accepting_any_recording(mutation):
    provider = CaptureOnlyProvider()
    output = recover(SCOPE_PAGE)
    audit_scopes(pages=[SCOPE_PAGE], declarations=output,
                 config=ScopeAuditConfig('SYNTHETIC_REVIEW', provider, True, literal_recovery=True))
    assert provider.calls == 1
    request = provider.request
    groups = copy.deepcopy(request.groups)
    if mutation == 'cropped_value':
        value = groups[1][0]['immutable_value_span']
        value['excerpt'] = value['excerpt'].split('\n')[0]
        value['end'] = value['start'] + len(value['excerpt'])
        request = replace(request, groups=groups)
    elif mutation == 'changed_reason':
        groups[1][0]['prior_reason'] = 'explicit_session'
        request = replace(request, groups=groups)
    elif mutation == 'flag_off':
        request = replace(request, literal_recovery=False)
    else:
        request = replace(request, pages=(SCOPE_PAGE.replace('Formas', 'Colores'),))
    with pytest.raises(ScopeAuditError, match='current_route_reconstruction_mismatch|current_source_binding'):
        validate_scope_recordings(request=request, recordings=[])
