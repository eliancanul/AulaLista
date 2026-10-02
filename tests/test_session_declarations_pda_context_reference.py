"""Source-only checks for the independently authored local-PDA reference.

No matcher, scanner, scorer, product grammar, private source, prediction, Django
setup, or network lookup determines these answers. Exact slices validate the
coordinates of literals authored before product output was observed.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest
import unicodedata


FIXTURES = Path(__file__).parent / 'fixtures' / 'interpretation'
REFERENCE = FIXTURES / 'session_declarations_pda_context_v1.json'
REFERENCE_SHA256 = 'b3c87fe0af0d7bdc1cfb556e802dee22177b3625a7986c9b31eaf0a483f96cf1'
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
}
PRIOR_HASHES = {
    'activity_annex_semantics_v1.json': '0a565876b3595209cf7969e0ee37437f7efaeafbea9f10cd82851e3424c812d9',
    'activity_annex_v1.json': 'c49e767843a695a3fa3e760f259ab17ffc2dc29ae01367dfa4e2dc3214bac48c',
    'activity_session_bullets_v1.json': '79eebb377323b3a060f5243cd9d80fa459e956a774781c1937d16b84d59399b6',
    'activity_session_v1.json': '9fb8fdc7595e24c065bfba0f8babd833d74f2eae208f2f228aaa4c8055a8b347',
    'project_anchor_structure_v1.json': '266bcf93012d61774489fe82884e1a5979c43a5a142b47988b4f6992541be21e',
    'session_declarations_labels_v1.json': 'a5674e0ef46a8b8e6f374df3e6198bdf917ff3b2ec04ec6c96b23e9b2105d9e9',
    'session_declarations_literal_recovery_v1.json': '1a8f35662fe3d097cd14ce874d3e37ca9a52ecbace93ec2a7a371bfaf9d96184',
    'session_declarations_project_metadata_v1.json': '9323aaaba522c8397aeb675afcafbd745c01d71c99338dbcb5745eded9f97d13',
    'session_declarations_scaffold_supplement_v1.json': 'f5136feae92c5c186845f2b080113a3a36f1aa2d1e20a2c8ebfa6b3bdd6cbc0d',
    'session_declarations_scaffold_v1.json': '3b83730070b9e04859a39af78065dbf70399bdfb3a6d5edbbc3a8941d71f3b09',
    'session_declarations_v1.json': '3c7a9aedf5be30b8755d12e6567d154b5d54859d1ff0a868727b8576060201f5',
}


class PdaContextReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
        cls.documents = cls.reference['documents']
        cls.by_id = {document['id']: document for document in cls.documents}
        cls.scope = cls.reference['scope']
        cls.recoveries = cls.scope['new_recovery_opportunities']
        cls.baseline = cls.scope['baseline_preservation_opportunities']

    def assertSpan(self, pages, span):
        self.assertEqual(set(span), {'page', 'start', 'end', 'quote'})
        for key in ('page', 'start', 'end'):
            self.assertIs(type(span[key]), int)
        self.assertGreaterEqual(span['page'], 1)
        self.assertLessEqual(span['page'], len(pages))
        page = pages[span['page'] - 1]
        self.assertGreaterEqual(span['start'], 0)
        self.assertGreater(span['end'], span['start'])
        self.assertLessEqual(span['end'], len(page))
        self.assertEqual(page[span['start']:span['end']], span['quote'])

    def declaration(self, locator):
        return next(item for item in self.by_id[locator['document_id']]['declarations']
                    if item['id'] == locator['declaration_id'])

    def test_fixture_and_historical_references_are_frozen(self):
        self.assertEqual(hashlib.sha256(REFERENCE.read_bytes()).hexdigest(), REFERENCE_SHA256)
        self.assertEqual(self.scope['preserved_reference_sha256'], PRIOR_HASHES)
        for name, expected in PRIOR_HASHES.items():
            with self.subTest(reference=name):
                self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), expected)

    def test_existing_envelope_and_authored_document_shape(self):
        self.assertEqual(set(self.reference), {'version', 'reference_kind', 'scope', 'documents'})
        self.assertEqual(self.reference['version'], 'session-declarations-reference.v1')
        self.assertEqual(self.reference['reference_kind'], 'synthetic_prematcher_development')
        self.assertEqual(self.scope['base_commit'], '27b2b5850908ba3c088458f5d866077de58b20cf')
        self.assertEqual(self.scope['status'], 'independent_source_first_reference')
        self.assertEqual(len(self.documents), len(self.by_id))
        self.assertEqual(set(self.scope['source_adjudications']), set(self.by_id))
        for document in self.documents:
            with self.subTest(document=document['id']):
                self.assertEqual(set(document), {
                    'id', 'pages', 'units', 'declarations', 'challenges', 'absence_expected', 'design_tags',
                })
                self.assertTrue(document['id'])
                self.assertTrue(document['pages'])
                self.assertTrue(all(isinstance(page, str) for page in document['pages']))
                self.assertTrue(document['design_tags'])
                self.assertEqual(len(document['design_tags']), len(set(document['design_tags'])))
                self.assertIs(type(document['absence_expected']), bool)
                self.assertEqual(document['absence_expected'], not document['declarations'])
                self.assertTrue(self.scope['source_adjudications'][document['id']])

    def test_each_exact_page_snapshot_has_an_independent_binding(self):
        binding = self.scope['source_binding']
        self.assertEqual(binding['kind'], 'synthetic_exact_page_snapshot')
        self.assertEqual(binding['algorithm'], 'sha256')
        self.assertEqual(set(binding['page_snapshots_sha256']), set(self.by_id))
        for document in self.documents:
            source = json.dumps(document['pages'], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            self.assertEqual(binding['page_snapshots_sha256'][document['id']], hashlib.sha256(source).hexdigest())

    def test_exact_full_literal_spans_and_physical_occurrences(self):
        for document in self.documents:
            with self.subTest(document=document['id']):
                ids, positions = set(), set()
                for category in ('units', 'declarations', 'challenges'):
                    for item in document[category]:
                        self.assertNotIn(item['id'], ids)
                        ids.add(item['id'])
                        keys = ('label', 'value') if category == 'declarations' else ('anchor',)
                        for key in keys:
                            self.assertSpan(document['pages'], item[key])
                        anchor = item['label'] if category == 'declarations' else item['anchor']
                        position = tuple(anchor[key] for key in ('page', 'start', 'end'))
                        self.assertNotIn(position, positions)
                        positions.add(position)
                        if category == 'declarations':
                            self.assertEqual(item['label']['page'], item['value']['page'])
                            self.assertLessEqual(item['label']['end'], item['value']['start'])
                            self.assertTrue(item['label']['quote'].endswith(':'))
                            for key in ('label', 'value'):
                                self.assertEqual(item[key]['quote'], item[key]['quote'].strip())
                            gap = document['pages'][item['label']['page'] - 1][item['label']['end']:item['value']['start']]
                            self.assertFalse(gap.strip())

    def test_new_recoveries_never_create_content_unit_or_candidate(self):
        recovered = set()
        for locator in self.recoveries:
            self.assertEqual(set(locator), {'document_id', 'declaration_id', 'route'})
            self.assertEqual(locator['route'], 'local_dotted_pda_context')
            pair = locator['document_id'], locator['declaration_id']
            self.assertNotIn(pair, recovered)
            recovered.add(pair)
        baseline = {(item['document_id'], item['declaration_id']) for item in self.baseline}
        self.assertEqual(len(baseline), len(self.baseline))
        self.assertTrue(recovered.isdisjoint(baseline))
        all_literals = {(document['id'], item['id']) for document in self.documents for item in document['declarations']}
        self.assertEqual(recovered | baseline, all_literals)
        for document in self.documents:
            for declaration in document['declarations']:
                self.assertEqual(set(declaration), {
                    'id', 'kind', 'label', 'value', 'unit_id', 'expected_decision', 'reason',
                })
                self.assertEqual(declaration['kind'], 'pda')
                self.assertIsNone(declaration['unit_id'])
                self.assertEqual((declaration['expected_decision'], declaration['reason']),
                                 ('abstained', 'unresolved_scope'))

    def test_source_context_witnesses_are_page_local_and_not_declarations(self):
        witnessed = Counter()
        for context in self.scope['source_context_witnesses']:
            self.assertEqual(set(context), {'document_id', 'field', 'descriptor', 'declaration_ids'})
            document = self.by_id[context['document_id']]
            for role in ('field', 'descriptor'):
                self.assertSpan(document['pages'], context[role])
            self.assertEqual(context['field']['page'], context['descriptor']['page'])
            self.assertLessEqual(context['field']['end'], context['descriptor']['start'])
            self.assertTrue(context['declaration_ids'])
            for declaration_id in context['declaration_ids']:
                declaration = self.declaration({'document_id':document['id'], 'declaration_id':declaration_id})
                self.assertEqual(context['descriptor']['page'], declaration['label']['page'])
                self.assertLessEqual(context['descriptor']['end'], declaration['label']['start'])
                witnessed[document['id'], declaration_id] += 1
        self.assertEqual(witnessed, Counter((item['document_id'], item['declaration_id']) for item in self.recoveries))
        for identity in ('silence_field_only', 'silence_descriptor_only', 'silence_descriptor_colon'):
            self.assertEqual(self.by_id[identity]['declarations'], [])
            self.assertEqual(self.by_id[identity]['challenges'], [])
            self.assertEqual(self.by_id[identity]['units'], [])

    def test_fixed_separate_denominators(self):
        declarations = [item for document in self.documents for item in document['declarations']]
        actual = {
            'documents': len(self.documents),
            'literal_declarations': len(declarations),
            'new_recovery_literals': len(self.recoveries),
            'baseline_preservation_literals': len(self.baseline),
            'pda_literals': sum(item['kind'] == 'pda' for item in declarations),
            'contenido_literals': sum(item['kind'] == 'contenido' for item in declarations),
            'scope_abstentions': sum(item['expected_decision'] == 'abstained' for item in declarations),
            'unresolved_units': sum(item['unit_id'] is None for item in declarations),
            'session_candidates': sum(item['expected_decision'] == 'candidate' for item in declarations),
            'new_context_blocks': len(self.scope['source_context_witnesses']),
            'challenges': sum(len(document['challenges']) for document in self.documents),
            'documents_without_declarations': sum(document['absence_expected'] for document in self.documents),
            'clean_silence_documents': sum(not document['declarations'] and not document['challenges'] for document in self.documents),
            'historical_preservation_documents': len(self.scope['historical_preservation_documents']),
            'positive_documents': sum('positive' in document['design_tags'] for document in self.documents),
            'negative_documents': sum('negative' in document['design_tags'] for document in self.documents),
        }
        self.assertEqual(actual, DENOMINATORS)
        self.assertEqual(self.scope['frozen_denominators'], DENOMINATORS)

    def test_historical_source_and_ambiguity_are_preserved_without_repair(self):
        for locator in self.scope['historical_preservation_documents']:
            historical = json.loads((FIXTURES / locator['reference']).read_text(encoding='utf-8'))
            source = next(item for item in historical['documents'] if item['id'] == locator['source_document_id'])
            preserved = self.by_id[locator['document_id']]
            for key in ('pages', 'units', 'declarations', 'challenges', 'absence_expected'):
                self.assertEqual(preserved[key], source[key])
            self.assertEqual(preserved['design_tags'][:-1], source['design_tags'])
        for identity in ('preserved_dotted_incomplete_prior_value', 'preserved_dotted_narrative_no_repeated_prefix',
                         'preserved_dotted_narrative_repeated_prefix', 'preserved_dotted_next_label_inline',
                         'preserved_dotted_terminal_without_corroboration'):
            self.assertEqual(self.by_id[identity]['declarations'], [])
            self.assertTrue(self.by_id[identity]['challenges'])

    def test_exact_unicode_whitespace_and_full_multiline_values(self):
        crlf = self.by_id['context_crlf_horizontal']['declarations'][0]
        self.assertEqual(crlf['label']['quote'], 'AB7\tPDA 002:')
        self.assertEqual(crlf['value']['quote'], 'Compara\u00a0señales\r\ny describe sus formas.')
        nfd = self.by_id['context_nfd']['declarations'][0]
        for role in ('label', 'value'):
            self.assertNotEqual(nfd[role]['quote'], unicodedata.normalize('NFC', nfd[role]['quote']))
        self.assertEqual(self.by_id['context_multiline_full_value']['declarations'][0]['value']['quote'],
                         'Describe señales\ny compara las formas.\nExplica sus diferencias.')
        repeated = self.by_id['context_repeated_occurrences']['declarations']
        for role in ('label', 'value'):
            self.assertEqual(repeated[0][role]['quote'], repeated[1][role]['quote'])
            self.assertNotEqual(repeated[0][role]['start'], repeated[1][role]['start'])
        max_lines = next(item for item in self.scope['source_context_witnesses']
                         if item['document_id'] == 'context_eight_line_descriptor')
        self.assertEqual(len(max_lines['descriptor']['quote'].splitlines()), 8)

    def test_transition_punctuation_wrap_and_code_nonidentity_are_authored(self):
        expected_fields = {
            'context_transition_abbrev_science': 'Saberes y P. Científico',
            'context_transition_abbrev_ethics': 'Ética, N. y Sociedades',
            'context_transition_abbrev_community': 'De lo H. y lo Comunitario',
            'context_transition_abbrev_wrapped_two': 'Saberes y P.\nCientífico',
            'context_transition_abbrev_wrapped_three': 'Ética,\nN. y\nSociedades',
            'context_transition_wrapped_three': 'De lo Humano\ny lo\nComunitario',
        }
        for identity, field in expected_fields.items():
            contexts = [item for item in self.scope['source_context_witnesses'] if item['document_id'] == identity]
            self.assertEqual(contexts[1]['field']['quote'], field)
            self.assertEqual(len(self.by_id[identity]['declarations']), 2)
        mismatch = self.by_id['context_mismatched_codes']
        self.assertIn('Ñ7. Reconocimiento de marcas.', mismatch['pages'][0])
        self.assertEqual(mismatch['declarations'][0]['label']['quote'], 'AB9999 PDA 002:')
        self.assertEqual(self.by_id['context_ordinary_colon_descriptor']['declarations'][0]['value']['quote'],
                         'Describe una señal.')

    def test_incomplete_values_and_uncorroborated_transitions_never_crop(self):
        for document in self.documents:
            if any(tag in document['design_tags'] for tag in (
                    'incomplete_blocks_rest', 'uncorroborated_closure', 'invalid_field_transition')):
                with self.subTest(document=document['id']):
                    self.assertEqual(document['declarations'], [])
                    self.assertTrue(document['challenges'])
                    self.assertTrue(document['absence_expected'])
        self.assertEqual(len(self.by_id['negative_incomplete_before_next_label']['challenges']), 2)
        self.assertEqual(len(self.by_id['negative_incomplete_before_descriptor']['challenges']), 2)
        self.assertEqual(len(self.by_id['negative_incomplete_before_field']['challenges']), 2)
        self.assertEqual(self.by_id['negative_descriptor_loose_prose']['declarations'], [])
        self.assertEqual(len(self.by_id['context_blank_before_pda']['declarations']), 1)

    def test_context_safety_remains_sticky_and_units_are_never_inherited(self):
        for document in self.documents:
            if 'sticky_blocker' in document['design_tags'] or 'prior_page_safety' in document['design_tags']:
                with self.subTest(document=document['id']):
                    self.assertEqual(document['declarations'], [])
                    self.assertTrue(document['challenges'])
            if 'real_unit_reset' in document['design_tags']:
                self.assertEqual(len(document['declarations']), 1)
                unit = document['units'][0]
                declaration = document['declarations'][0]
                self.assertLess(unit['anchor']['end'], declaration['label']['start'])
                self.assertIsNone(declaration['unit_id'])
        previous = self.by_id['context_previous_page_unit']
        self.assertEqual(previous['units'][0]['anchor']['page'], 1)
        self.assertEqual(previous['declarations'][0]['label']['page'], 2)
        self.assertIsNone(previous['declarations'][0]['unit_id'])
        for identity in ('negative_field_cross_page', 'negative_descriptor_cross_page',
                         'negative_value_cross_page', 'negative_unit_cross_page'):
            self.assertEqual(len(self.by_id[identity]['pages']), 2)
            self.assertEqual(self.by_id[identity]['declarations'], [])


if __name__ == '__main__':
    unittest.main()
