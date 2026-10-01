"""Pre-matcher freeze checks, independent of product parsing and extraction."""
import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / 'fixtures/interpretation/session_declarations_v1.json'
SHA256 = '3c7a9aedf5be30b8755d12e6567d154b5d54859d1ff0a868727b8576060201f5'


def test_pre_matcher_reference_is_frozen_with_separate_denominators():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
    reference = json.loads(FIXTURE.read_bytes())
    assert reference['version'] == 'session-declarations-reference.v1'
    docs = reference['documents']
    assert len(docs) == 36
    declarations = [d for doc in docs for d in doc['declarations']]
    assert len(declarations) == 45
    assert sum(d['expected_decision'] == 'candidate' for d in declarations) == 36
    assert sum(d['expected_decision'] == 'abstained' for d in declarations) == 9
    assert sum(len(d['challenges']) for d in docs) == 22
    assert sum(d['absence_expected'] for d in docs) == 15


def test_authored_spans_are_literal_and_unit_links_are_consistent():
    docs = json.loads(FIXTURE.read_bytes())['documents']
    assert len({d['id'] for d in docs}) == len(docs)
    for document in docs:
        units = {u['id']: u for u in document['units']}
        spans = [u['anchor'] for u in units.values()]
        labels = set()
        for declaration in document['declarations']:
            spans.extend((declaration['label'], declaration['value']))
            assert declaration['label']['page'] == declaration['value']['page']
            assert declaration['label']['end'] <= declaration['value']['start']
            key = tuple(declaration['label'][k] for k in ('page', 'start', 'end'))
            assert key not in labels
            labels.add(key)
            uid = declaration['unit_id']
            assert uid is None or uid in units
            if declaration['expected_decision'] == 'candidate':
                assert uid is not None and units[uid]['kind'] == 'session'
        spans.extend(c['anchor'] for c in document['challenges'])
        for span in spans:
            assert type(span['page']) is int
            assert type(span['start']) is type(span['end']) is int
            page = document['pages'][span['page'] - 1]
            assert 0 <= span['start'] < span['end'] <= len(page)
            assert page[span['start']:span['end']] == span['quote']
        assert document['absence_expected'] == (not document['declarations'])
