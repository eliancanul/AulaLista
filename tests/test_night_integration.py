"""Authenticated synthetic integration of the versioned editor and review history."""
import sqlite3
import pytest
from test_sprint_S07_integration import service
from test_t15_curriculum_import import make_minimal_pdf

pytestmark = pytest.mark.django_db(transaction=True)


def upload(client):
    content = make_minimal_pdf(['Proyecto: La lectura\nPropósito: Leer el texto.\nMateriales: Papel'])
    response = client.post('/api/v1/interpretations', files={'file': ('synthetic.pdf', content, 'application/pdf')})
    assert response.status_code == 201, response.text
    return response.json()


def test_empty_fields_and_line_endings_roundtrip_with_history_and_source(service):
    _, store, users, clients = service
    client, other = clients
    result = upload(client)
    identifier = result['document_id']
    before = result['draft']
    exact = {'title': '  Edición docente\n', 'objective': 'Leer la fuente conservada',
             'materials': [''], 'steps': ['Leer', ''], 'assessment': ''}
    response = client.patch(f'/api/v1/drafts/{identifier}', json={'expected_revision': 1, 'changes': exact})
    assert response.status_code == 200
    assert all(response.json()[k] == v for k, v in exact.items())
    assert response.json()['approval_status'] == 'pending'
    assert response.json()['source_ids'] == before['source_ids']
    assert client.get('/api/v1/interpretations').json()[0]['document_id'] == identifier
    assert other.get('/api/v1/interpretations').json() == []
    for path in [f'/api/v1/drafts/{identifier}/history', f'/api/v1/interpretations/{identifier}/source']:
        assert other.get(path).status_code == 404
    source = client.get(f'/api/v1/interpretations/{identifier}/source')
    assert source.status_code == 200
    assert source.content == store.get_source(users[0].pk, identifier)['content']
    assert source.headers['x-source-sha256'] == store.get_source(users[0].pk, identifier)['sha256']
    assert client.post(f'/api/v1/drafts/{identifier}/approve', json={'expected_revision': 2, 'confirm': True}).status_code == 200
    approved = client.get(f'/api/v1/drafts/{identifier}/history').json()
    assert [r['action'] for r in approved] == ['created', 'edited', 'approved']
    assert client.patch(f'/api/v1/drafts/{identifier}', json={'expected_revision': 3, 'changes': {'title': 'Otro título'}}).status_code == 200
    history = client.get(f'/api/v1/drafts/{identifier}/history').json()
    assert history[:3] == approved
    assert history[-1]['draft']['approval_status'] == 'pending'
    assert history[-2]['draft']['title'] == exact['title']


def test_blank_lines_never_make_insufficient_draft_approvable(service):
    _, _, _, clients = service
    client = clients[0]
    identifier = upload(client)['document_id']
    assert client.patch(f'/api/v1/drafts/{identifier}', json={'expected_revision': 1, 'changes': {'steps': ['', '  ', '\n']}}).status_code == 200
    assert client.post(f'/api/v1/drafts/{identifier}/approve', json={'expected_revision': 2, 'confirm': True}).status_code == 422


@pytest.mark.parametrize('approve', [False, True])
def test_list_refuses_corrupt_source_without_exposing_approval_or_affecting_other_owner(service, approve):
    _, store, _, clients = service
    client, other = clients
    identifier = upload(client)['document_id']
    assert client.patch(f'/api/v1/drafts/{identifier}', json={'expected_revision': 1, 'changes': {'steps': ['Revisar fuente']}}).status_code == 200
    if approve:
        assert client.post(f'/api/v1/drafts/{identifier}/approve', json={'expected_revision': 2, 'confirm': True}).status_code == 200
    assert client.get('/api/v1/interpretations').status_code == 200
    with sqlite3.connect(store.path) as db:
        db.execute('UPDATE documents SET source=? WHERE id=?', (b'corrupted synthetic source', identifier))
    for route in ['/api/v1/interpretations', f'/api/v1/interpretations/{identifier}',
                  f'/api/v1/interpretations/{identifier}/source', f'/api/v1/drafts/{identifier}/history']:
        response = client.get(route)
        assert response.status_code == 409
        assert 'source_changed' in response.text
        assert 'approved' not in response.text
    assert other.get('/api/v1/interpretations').json() == []
