"""Validate independently authored synthetic source spans, never matcher output."""
import hashlib
import json
from pathlib import Path

PATH = Path(__file__).parent / 'fixtures/interpretation/project_anchor_structure_v1.json'
EXPECTED_SHA256 = '266bcf93012d61774489fe82884e1a5979c43a5a142b47988b4f6992541be21e'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def test_original_synthetic_reference_is_hash_bound_and_separate():
    assert digest(PATH.read_bytes()) == EXPECTED_SHA256
    ref = json.loads(PATH.read_text())
    assert ref['version'] == 'project-anchor-structure-reference.v1'
    assert ref['reference_kind'] == 'original_synthetic_pre_matcher'
    assert ref['scope'] == 'development_only_no_private_sources'
    assert ref['denominators'] == dict(documents=43, governing=6, reference_only=26, ambiguous=9, narrative=2)
    docs = ref['documents']
    assert len({d['id'] for d in docs}) == len(docs) == 43
    roles = ['governing', 'reference_only', 'ambiguous', 'narrative']
    for role in roles:
        assert sum(d['expected_role'] == role for d in docs) == ref['denominators'][role]
    for doc in docs:
        raw = json.dumps(doc['pages'], ensure_ascii=False, separators=(',', ':')).encode()
        assert digest(raw) == doc['document_sha256']
        assert doc['expected_selectable'] is (doc['expected_role'] == 'governing')
        proof = doc['proof']
        if doc['expected_selectable']:
            assert doc['anchor'] is not None
            required = ['planning_root', 'project_label', 'project_title', 'scenario', 'purpose', 'product', 'project_association']
            assert [p['role'] for p in proof[:7]] == required
            assert all(proof[i]['end'] <= proof[i+1]['start'] for i in range(6))
            assert doc['anchor']['start'] == proof[1]['start']
            assert doc['anchor']['end'] == proof[2]['end']
        else:
            assert doc['anchor'] is None and proof == []
        for span in ([doc['anchor']] if doc['anchor'] else []) + proof:
            assert type(span['page_number']) is int and 1 <= span['page_number'] <= len(doc['pages'])
            text = doc['pages'][span['page_number'] - 1]
            assert type(span['start']) is int and type(span['end']) is int
            assert 0 <= span['start'] < span['end'] <= len(text)
            assert text[span['start']:span['end']] == span['excerpt']
            assert digest(span['excerpt'].encode()) == span['excerpt_sha256']
    assert '\r\n' in next(d['pages'][0] for d in docs if d['id'] == 'positive-crlf')
