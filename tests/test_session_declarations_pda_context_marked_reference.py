"""Independent typography/reference checks; no product extraction is imported.

The frozen parent supplies source and expected semantic decisions. This suite
checks a mechanical, reversible hyphen transformation, exact spans, and unchanged
answers. It does not require that any source opportunity be a baseline delta.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unittest
import unicodedata


FIXTURES = Path(__file__).parent / 'fixtures' / 'interpretation'
PARENT = FIXTURES / 'session_declarations_pda_context_v1.json'
REFERENCE = FIXTURES / 'session_declarations_pda_context_marked_v1.json'
PARENT_SHA256 = 'b3c87fe0af0d7bdc1cfb556e802dee22177b3625a7986c9b31eaf0a483f96cf1'
REFERENCE_SHA256 = '7ffc16f2e399f47a5b9bccf801a6fe6f63a5c7b44dce0ae8535ff404106ef26b'
DENOMINATORS = {
    'documents': 132,
    'literal_declarations': 64,
    'new_recovery_literals': 62,
    'baseline_preservation_literals': 2,
    'pda_literals': 64,
    'contenido_literals': 0,
    'scope_abstentions': 64,
    'unresolved_units': 64,
    'session_candidates': 0,
    'new_context_blocks': 59,
    'challenges': 104,
    'documents_without_declarations': 86,
    'clean_silence_documents': 4,
    'historical_preservation_documents': 8,
    'positive_documents': 44,
    'negative_documents': 77,
    'inserted_hyphens': 151,
    'typographically_modified_documents': 113,
    'typographically_unmodified_documents': 19,
    'typographically_modified_pages': 113,
}


def authored_typography_positions(page):
    """Independent source-only recognition of the specified mechanical edit."""
    positions = []
    cursor = 0
    for line in page.split('\n'):
        match = re.match(
            r'(?P<indent>[ \t\u00a0]*)(?P<code>[^\s]+)[ \t\u00a0]+'
            r'[Pp][Dd][Aa][ \t\u00a0]*[0-9]+:', line)
        if match:
            code = unicodedata.normalize('NFC', match['code'])
            if re.fullmatch(r'[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{1,4}[0-9]{1,4}', code):
                positions.append(cursor + len(match['indent']))
        cursor += len(line) + 1
    return positions


def spans(value):
    if isinstance(value, list):
        for item in value:
            yield from spans(item)
    elif isinstance(value, dict):
        if set(value) == {'page', 'start', 'end', 'quote'}:
            yield value
        else:
            for item in value.values():
                yield from spans(item)


def semantic_shape(value):
    """Ignore only numerical offsets, retaining every authored expected field."""
    if isinstance(value, list):
        return [semantic_shape(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {'page', 'start', 'end', 'quote'}:
            return {'page': value['page'], 'quote': value['quote']}
        return {key: semantic_shape(item) for key, item in value.items()}
    return value


class PdaContextMarkedReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = json.loads(PARENT.read_text(encoding='utf-8'))
        cls.reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
        cls.scope = cls.reference['scope']
        cls.documents = cls.reference['documents']
        cls.by_id = {item['id']: item for item in cls.documents}
        cls.parent_by_id = {item['id']: item for item in cls.parent['documents']}
        cls.insertions = cls.scope['transformation']['insertions']

    def test_frozen_parent_supplement_and_all_prior_references(self):
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest(), PARENT_SHA256)
        self.assertEqual(hashlib.sha256(REFERENCE.read_bytes()).hexdigest(), REFERENCE_SHA256)
        self.assertEqual(self.scope['parent_reference'], {
            'path': 'tests/fixtures/interpretation/session_declarations_pda_context_v1.json',
            'sha256': PARENT_SHA256,
        })
        expected = dict(self.parent['scope']['preserved_reference_sha256'])
        expected[PARENT.name] = PARENT_SHA256
        self.assertEqual(self.scope['preserved_reference_sha256'], expected)
        for name, digest in expected.items():
            with self.subTest(reference=name):
                self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), digest)

    def test_one_marked_variant_of_every_parent_document_and_same_schema(self):
        self.assertEqual(set(self.reference), {'version', 'reference_kind', 'scope', 'documents'})
        self.assertEqual(self.reference['version'], 'session-declarations-reference.v1')
        self.assertEqual(self.reference['reference_kind'], self.parent['reference_kind'])
        self.assertEqual(len(self.documents), len(self.by_id))
        self.assertEqual([item['id'] for item in self.documents],
                         ['marked_' + item['id'] for item in self.parent['documents']])
        self.assertEqual(self.scope['transformation']['algorithm'],
                         'source-line-coded-numbered-pda-single-hyphen.v1')
        for document in self.documents:
            self.assertEqual(set(document), {
                'id', 'pages', 'units', 'declarations', 'challenges', 'absence_expected', 'design_tags',
            })

    def test_typography_is_exactly_the_declared_source_only_transformation(self):
        actual_ledger = []
        for source in self.parent['documents']:
            target = self.by_id['marked_' + source['id']]
            self.assertEqual(len(source['pages']), len(target['pages']))
            for page_number, (original, marked) in enumerate(zip(source['pages'], target['pages']), 1):
                positions = authored_typography_positions(original)
                expected = original
                for position in reversed(positions):
                    expected = expected[:position] + '-' + expected[position:]
                self.assertEqual(marked, expected)
                for ordinal, position in enumerate(positions):
                    actual_ledger.append({
                        'document_id': target['id'], 'source_document_id': source['id'],
                        'page': page_number, 'source_offset': position, 'target_offset': position + ordinal,
                    })
        self.assertEqual(self.insertions, actual_ledger)

    def test_removing_only_recorded_hyphens_reconstructs_parent_exactly(self):
        grouped = {}
        for insertion in self.insertions:
            self.assertEqual(set(insertion), {
                'document_id', 'source_document_id', 'page', 'source_offset', 'target_offset',
            })
            self.assertEqual(insertion['document_id'], 'marked_' + insertion['source_document_id'])
            grouped.setdefault((insertion['document_id'], insertion['page']), []).append(insertion['target_offset'])
        for document in self.documents:
            source = self.parent_by_id[document['id'].removeprefix('marked_')]
            for number, page in enumerate(document['pages'], 1):
                positions = grouped.get((document['id'], number), [])
                self.assertEqual(len(positions), len(set(positions)))
                original = page
                for position in sorted(positions, reverse=True):
                    self.assertEqual(original[position], '-')
                    original = original[:position] + original[position + 1:]
                self.assertEqual(original, source['pages'][number - 1])

    def test_all_expected_semantics_and_quotes_are_unchanged(self):
        for source in self.parent['documents']:
            target = self.by_id['marked_' + source['id']]
            with self.subTest(document=target['id']):
                for key in ('units', 'declarations', 'challenges', 'absence_expected', 'design_tags'):
                    self.assertEqual(semantic_shape(target[key]), semantic_shape(source[key]))
                for declaration in target['declarations']:
                    self.assertEqual(declaration['kind'], 'pda')
                    self.assertIsNone(declaration['unit_id'])
                    self.assertEqual((declaration['expected_decision'], declaration['reason']),
                                     ('abstained', 'unresolved_scope'))
        for key in ('new_recovery_opportunities', 'baseline_preservation_opportunities',
                    'historical_preservation_documents'):
            expected = [dict(item, document_id='marked_' + item['document_id'])
                        for item in self.parent['scope'][key]]
            self.assertEqual(self.scope[key], expected)
        self.assertEqual(self.scope['source_adjudications'],
                         {'marked_' + key: value for key, value in self.parent['scope']['source_adjudications'].items()})

    def test_every_span_is_remapped_to_an_exact_unchanged_literal(self):
        for source in self.parent['documents']:
            target = self.by_id['marked_' + source['id']]
            source_spans = list(spans(source))
            target_spans = list(spans(target))
            self.assertEqual(len(source_spans), len(target_spans))
            for before, after in zip(source_spans, target_spans):
                self.assert_remapped_span(source, target, before, after)
        expected_contexts = self.parent['scope']['source_context_witnesses']
        actual_contexts = self.scope['source_context_witnesses']
        self.assertEqual(len(expected_contexts), len(actual_contexts))
        for before, after in zip(expected_contexts, actual_contexts):
            self.assertEqual(after['document_id'], 'marked_' + before['document_id'])
            self.assertEqual(after['declaration_ids'], before['declaration_ids'])
            source = self.parent_by_id[before['document_id']]
            target = self.by_id[after['document_id']]
            for original_span, marked_span in zip(spans(before), spans(after)):
                self.assert_remapped_span(source, target, original_span, marked_span)

    def assert_remapped_span(self, source, target, before, after):
        self.assertEqual(set(after), {'page', 'start', 'end', 'quote'})
        for key in ('page', 'start', 'end'):
            self.assertIs(type(after[key]), int)
        self.assertEqual(after['page'], before['page'])
        self.assertEqual(after['quote'], before['quote'])
        self.assertGreaterEqual(after['page'], 1)
        self.assertLessEqual(after['page'], len(target['pages']))
        page = target['pages'][after['page'] - 1]
        self.assertGreaterEqual(after['start'], 0)
        self.assertLess(after['start'], after['end'])
        self.assertLessEqual(after['end'], len(page))
        self.assertEqual(page[after['start']:after['end']], after['quote'])
        positions = authored_typography_positions(source['pages'][before['page'] - 1])
        self.assertEqual(after['start'], before['start'] + sum(position <= before['start'] for position in positions))
        self.assertEqual(after['end'], before['end'] + sum(position < before['end'] for position in positions))

    def test_page_snapshot_hashes_bind_changed_original_strings(self):
        binding = self.scope['source_binding']
        self.assertEqual(binding['kind'], 'synthetic_exact_page_snapshot')
        self.assertEqual(binding['algorithm'], 'sha256')
        self.assertEqual(set(binding['page_snapshots_sha256']), set(self.by_id))
        for document in self.documents:
            encoded = json.dumps(document['pages'], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            self.assertEqual(binding['page_snapshots_sha256'][document['id']], hashlib.sha256(encoded).hexdigest())

    def test_fixed_semantic_and_typographic_denominators_are_separate(self):
        actual = dict(self.parent['scope']['frozen_denominators'])
        modified = {item['document_id'] for item in self.insertions}
        actual.update({
            'inserted_hyphens': len(self.insertions),
            'typographically_modified_documents': len(modified),
            'typographically_unmodified_documents': len(self.documents) - len(modified),
            'typographically_modified_pages': len({(item['document_id'], item['page']) for item in self.insertions}),
        })
        self.assertEqual(self.scope['frozen_denominators'], DENOMINATORS)
        self.assertEqual(actual, DENOMINATORS)
        declarations = [item for document in self.documents for item in document['declarations']]
        self.assertEqual(len(declarations), 64)
        self.assertEqual(len(self.scope['new_recovery_opportunities']), 62)
        self.assertEqual(len(self.scope['baseline_preservation_opportunities']), 2)
        self.assertEqual(sum(len(document['challenges']) for document in self.documents), 104)
        self.assertEqual(sum(document['absence_expected'] for document in self.documents), 86)
        self.assertEqual(Counter(item['reason'] for item in declarations), {'unresolved_scope': 64})

    def test_existing_markers_and_malformed_inline_adversaries_are_not_repaired(self):
        unchanged = (
            'context_hyphen_attached', 'context_hyphen_spaced', 'context_crlf_horizontal',
            'negative_pda_missing_code', 'negative_pda_missing_number', 'negative_pda_missing_colon',
            'negative_pda_double_hyphen', 'negative_pda_star_marker', 'negative_pda_bullet_marker',
            'negative_pda_foreign_code', 'negative_pda_long_letters', 'negative_pda_long_digits',
            'negative_descriptor_pda_inline',
        )
        for identity in unchanged:
            self.assertEqual(self.by_id['marked_' + identity]['pages'], self.parent_by_id[identity]['pages'])
        for identity in ('negative_example_prefix', 'negative_unknown_prefix', 'negative_quote_prefix',
                         'negative_incomplete_before_descriptor', 'negative_previous_page_example'):
            target = self.by_id['marked_' + identity]
            self.assertNotEqual(target['pages'], self.parent_by_id[identity]['pages'])
            self.assertEqual(target['declarations'], [])
            self.assertTrue(target['challenges'])
        nfd = self.by_id['marked_context_nfd']
        self.assertIn('-U\u03082 PDA1:', nfd['pages'][0])
        self.assertEqual(nfd['declarations'][0]['label']['quote'], 'U\u03082 PDA1:')
        repeated = self.by_id['marked_context_repeated_occurrences']['declarations']
        self.assertEqual(repeated[0]['label']['quote'], repeated[1]['label']['quote'])
        self.assertNotEqual(repeated[0]['label']['start'], repeated[1]['label']['start'])


if __name__ == '__main__':
    unittest.main()
