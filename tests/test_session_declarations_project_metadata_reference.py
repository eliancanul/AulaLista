"""Pre-matcher checks on authored synthetic data, not extraction behavior.

Only standard-library data checks run here. No matcher, scorer, scanner, Django
setup, private input, prediction or grammar is used to determine expectations.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'interpretation'
REFERENCE = FIXTURES / 'session_declarations_project_metadata_v1.json'
REFERENCE_SHA256 = '9323aaaba522c8397aeb675afcafbd745c01d71c99338dbcb5745eded9f97d13'
PRIOR_HASHES = {
    'session_declarations_v1.json': '3c7a9aedf5be30b8755d12e6567d154b5d54859d1ff0a868727b8576060201f5',
    'session_declarations_labels_v1.json': 'a5674e0ef46a8b8e6f374df3e6198bdf917ff3b2ec04ec6c96b23e9b2105d9e9',
    'session_declarations_scaffold_v1.json': '3b83730070b9e04859a39af78065dbf70399bdfb3a6d5edbbc3a8941d71f3b09',
    'session_declarations_scaffold_supplement_v1.json': 'f5136feae92c5c186845f2b080113a3a36f1aa2d1e20a2c8ebfa6b3bdd6cbc0d',
}
DENOMINATORS = {
    'documents': 46,
    'literal_declarations': 28,
    'unit_assignment': 28,
    'known_project_units': 10,
    'known_session_units': 2,
    'unresolved_units': 16,
    'session_candidates': 2,
    'scope_abstentions': 26,
    'challenges': 40,
    'documents_without_declarations': 27,
    'clean_silence_documents': 2,
}
DECLARATION_COUNTS = {
    'general_named_multiple': 2,
    'project_repeated_occurrences': 2,
    'project_labelled_field_content': 2,
    'general_spanish_codes_nfc': 2,
    'general_spanish_codes_nfd': 1,
    'general_crlf_horizontal': 1,
    'project_field_and_code_switches': 4,
    'general_multiline_value': 2,
    'inline_context_mentions_in_value': 1,
    'balanced_quotes_inside_value': 1,
    'project_not_inherited_by_session': 1,
    'previous_page_project_not_inherited': 1,
    'previous_page_session_not_inherited': 1,
    'same_page_session_controls': 2,
    'empty_project_is_unresolved': 1,
    'local_codes_need_not_match': 1,
    'new_explicit_project_after_activity': 1,
    'complete_value_then_activity_stop': 1,
    'context_switch_into_explicit_example': 1,
}


class ProjectMetadataReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
        cls.documents = cls.reference['documents']
        cls.by_id = {document['id']: document for document in cls.documents}

    def assertSpan(self, pages, span):
        self.assertEqual(set(span), {'page', 'start', 'end', 'quote'})
        self.assertIs(type(span['page']), int)
        self.assertIs(type(span['start']), int)
        self.assertIs(type(span['end']), int)
        self.assertGreaterEqual(span['page'], 1)
        self.assertLessEqual(span['page'], len(pages))
        self.assertGreaterEqual(span['start'], 0)
        self.assertGreater(span['end'], span['start'])
        self.assertLessEqual(span['end'], len(pages[span['page'] - 1]))
        self.assertEqual(pages[span['page'] - 1][span['start']:span['end']], span['quote'])

    def test_frozen_reference_and_prior_bytes(self):
        self.assertEqual(hashlib.sha256(REFERENCE.read_bytes()).hexdigest(), REFERENCE_SHA256)
        self.assertEqual(self.reference['scope']['preserved_reference_sha256'], PRIOR_HASHES)
        for name, expected in PRIOR_HASHES.items():
            with self.subTest(reference=name):
                self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), expected)

    def test_existing_reference_envelope_without_semantic_additions(self):
        self.assertEqual(set(self.reference), {'version', 'reference_kind', 'scope', 'documents'})
        self.assertEqual(self.reference['version'], 'session-declarations-reference.v1')
        self.assertEqual(self.reference['reference_kind'], 'synthetic_prematcher_development')
        self.assertEqual(self.reference['scope']['base_commit'], 'ad1616a1d8b958bbcc7652c814369ca8b1474416')
        self.assertEqual(len(self.documents), len(self.by_id))
        for document in self.documents:
            with self.subTest(document=document['id']):
                self.assertEqual(set(document), {
                    'id', 'pages', 'units', 'declarations', 'challenges', 'absence_expected', 'design_tags',
                })
                self.assertTrue(document['id'])
                self.assertTrue(document['pages'])
                self.assertTrue(all(isinstance(page, str) for page in document['pages']))
                self.assertEqual(len(document['design_tags']), len(set(document['design_tags'])))
                self.assertTrue(document['design_tags'])

    def test_exact_spans_ids_and_physical_occurrences(self):
        for document in self.documents:
            with self.subTest(document=document['id']):
                ids, anchors = set(), set()
                for category in ('units', 'declarations', 'challenges'):
                    for item in document[category]:
                        self.assertNotIn(item['id'], ids)
                        ids.add(item['id'])
                        self.assertTrue(item['id'])
                        keys = ('label', 'value') if category == 'declarations' else ('anchor',)
                        for key in keys:
                            self.assertSpan(document['pages'], item[key])
                        anchor = item['label'] if category == 'declarations' else item['anchor']
                        physical = (anchor['page'], anchor['start'], anchor['end'])
                        self.assertNotIn(physical, anchors)
                        anchors.add(physical)
                        if category == 'declarations':
                            self.assertEqual(item['label']['page'], item['value']['page'])
                            self.assertLessEqual(item['label']['end'], item['value']['start'])
                            for key in ('label', 'value'):
                                self.assertEqual(item[key]['quote'], item[key]['quote'].strip())
                            self.assertTrue(item['label']['quote'].endswith(':'))
                            self.assertFalse(item['label']['quote'].startswith('-'))

    def test_decisions_and_unit_assignment_are_authored_separately(self):
        for document in self.documents:
            units = {unit['id']: unit for unit in document['units']}
            for unit in units.values():
                self.assertEqual(set(unit), {'id', 'kind', 'anchor'})
                self.assertIn(unit['kind'], ('project', 'session'))
            for declaration in document['declarations']:
                with self.subTest(document=document['id'], declaration=declaration['id']):
                    self.assertEqual(set(declaration), {
                        'id', 'kind', 'label', 'value', 'unit_id', 'expected_decision', 'reason',
                    })
                    self.assertIn(declaration['kind'], ('contenido', 'pda'))
                    unit = units.get(declaration['unit_id'])
                    if declaration['unit_id'] is None:
                        self.assertEqual((declaration['expected_decision'], declaration['reason']),
                                         ('abstained', 'unresolved_scope'))
                    else:
                        self.assertIsNotNone(unit)
                        self.assertEqual(unit['anchor']['page'], declaration['label']['page'])
                        self.assertLess(unit['anchor']['start'], declaration['label']['start'])
                        expected = ('candidate', 'explicit_session') if unit['kind'] == 'session' else ('abstained', 'project_scope')
                        self.assertEqual((declaration['expected_decision'], declaration['reason']), expected)
            for challenge in document['challenges']:
                self.assertEqual(set(challenge), {'id', 'anchor', 'reason'})
                self.assertIn(challenge['reason'], {
                    'label_mention', 'nonaffirmative', 'quoted', 'table_ambiguous',
                    'negated', 'conditional', 'uncertain_boundary',
                })
            self.assertIs(type(document['absence_expected']), bool)
            self.assertEqual(document['absence_expected'], not document['declarations'])

    def test_fixed_separate_denominators(self):
        declarations = [item for document in self.documents for item in document['declarations']]
        reasons = Counter(item['reason'] for item in declarations)
        actual = {
            'documents': len(self.documents), 'literal_declarations': len(declarations),
            'unit_assignment': len(declarations), 'known_project_units': reasons['project_scope'],
            'known_session_units': reasons['explicit_session'], 'unresolved_units': reasons['unresolved_scope'],
            'session_candidates': sum(item['expected_decision'] == 'candidate' for item in declarations),
            'scope_abstentions': sum(item['expected_decision'] == 'abstained' for item in declarations),
            'challenges': sum(len(document['challenges']) for document in self.documents),
            'documents_without_declarations': sum(document['absence_expected'] for document in self.documents),
            'clean_silence_documents': sum(not document['declarations'] and not document['challenges'] for document in self.documents),
        }
        self.assertEqual(actual, DENOMINATORS)
        self.assertEqual(self.reference['scope']['frozen_denominators'], DENOMINATORS)
        self.assertEqual({document['id']: len(document['declarations']) for document in self.documents
                          if document['declarations']}, DECLARATION_COUNTS)

    def test_repetition_and_context_switches_preserve_values(self):
        repeated = self.by_id['project_repeated_occurrences']['declarations']
        self.assertEqual(repeated[0]['label']['quote'], repeated[1]['label']['quote'])
        self.assertEqual(repeated[0]['value']['quote'], repeated[1]['value']['quote'])
        self.assertNotEqual(repeated[0]['label']['start'], repeated[1]['label']['start'])
        self.assertNotEqual(repeated[0]['value']['start'], repeated[1]['value']['start'])
        switched = self.by_id['project_field_and_code_switches']['declarations']
        self.assertEqual([item['value']['quote'] for item in switched], [
            'Describe dos marcas.', 'Explica un mensaje.', 'Compara dos figuras.', 'Figuras y posiciones.',
        ])
        self.assertTrue(all(item['unit_id'] == 'p1' for item in switched))
        self.assertEqual(self.by_id['context_rows_are_not_declarations']['declarations'], [])
        self.assertEqual(self.by_id['context_rows_are_not_declarations']['challenges'], [])

    def test_unicode_crlf_and_multiline_are_original_slices(self):
        nfd = self.by_id['general_spanish_codes_nfd']['declarations'][0]
        self.assertEqual(nfd['label']['quote'], 'U\u03082 PDA1:')
        self.assertEqual(nfd['value']['quote'], 'Describe una sen\u0303al de acuerdo.')
        self.assertNotEqual(nfd['label']['quote'], unicodedata.normalize('NFC', nfd['label']['quote']))
        self.assertNotEqual(nfd['value']['quote'], unicodedata.normalize('NFC', nfd['value']['quote']))
        nfc = self.by_id['general_spanish_codes_nfc']['declarations']
        self.assertEqual([item['label']['quote'] for item in nfc], ['Ñ2 PDA1:', 'ÁB3 PDA 02:'])
        crlf = self.by_id['general_crlf_horizontal']
        self.assertIn('\r\n', crlf['pages'][0])
        self.assertIn('\u00a0', crlf['pages'][0])
        self.assertEqual(crlf['declarations'][0]['label']['quote'], 'L1\tPDA 0002:')
        self.assertEqual(self.by_id['general_multiline_value']['declarations'][0]['value']['quote'],
                         'Compara palabras mediante\nla observación de sus letras.')

    def test_codes_and_fields_inside_values_are_not_context_boundaries(self):
        value = self.by_id['inline_context_mentions_in_value']['declarations'][0]['value']['quote']
        self.assertEqual(value, 'Explica la referencia X7 mediante\nun ejemplo de Lenguajes escrito en una tarjeta.')
        self.assertEqual(self.by_id['balanced_quotes_inside_value']['declarations'][0]['value']['quote'],
                         'Compara «X7» con la palabra «Lenguajes».')
        mismatch = self.by_id['local_codes_need_not_match']
        self.assertIn('L1 Representaciones escritas.', mismatch['pages'][0])
        self.assertEqual(mismatch['declarations'][0]['label']['quote'], 'Ñ7 PDA1:')
        for identity in ('canonical_heading_inside_open_value', 'code_row_inside_value_example'):
            self.assertEqual(self.by_id[identity]['declarations'], [])
            self.assertEqual(self.by_id[identity]['challenges'][0]['reason'], 'uncertain_boundary')

    def test_no_inherited_project_or_previous_page_session(self):
        document = self.by_id['project_not_inherited_by_session']
        self.assertEqual({unit['kind'] for unit in document['units']}, {'project', 'session'})
        self.assertEqual([item['unit_id'] for item in document['declarations']], ['p1'])
        for identity in ('previous_page_project_not_inherited', 'previous_page_session_not_inherited'):
            document = self.by_id[identity]
            self.assertEqual(document['units'][0]['anchor']['page'], 1)
            self.assertEqual(document['declarations'][0]['label']['page'], 2)
            self.assertIsNone(document['declarations'][0]['unit_id'])
            self.assertEqual(document['declarations'][0]['reason'], 'unresolved_scope')
        empty = self.by_id['empty_project_is_unresolved']
        self.assertEqual(empty['units'], [])
        self.assertIsNone(empty['declarations'][0]['unit_id'])
        self.assertEqual(self.by_id['new_explicit_project_after_activity']['declarations'][0]['unit_id'], 'p1')

    def test_concrete_negative_coverage_and_no_claim_denominator(self):
        required_tags = {
            'activity_before_block', 'activity_inside_block', 'explicit_example', 'explicit_nonadoption',
            'field_mention_in_prose', 'longer_field_title', 'quoted_field_heading', 'unrecognized_block',
            'code_without_field', 'unknown_heading_stops_block', 'quoted_block', 'quote_across_page',
            'pipe_table', 'mixed_typed_row', 'incomplete_code', 'foreign_script_code', 'oversize_code',
            'unsupported_combining_mark', 'unicode_casefold_lookalikes', 'double_hyphen', 'other_bullet', 'missing_colon', 'negated',
            'conditional', 'suggested_not_adopted', 'after_inicio', 'after_desarrollo', 'after_cierre',
            'ambiguous_context_boundary', 'code_in_value_example', 'unclosed_value_quote',
            'truncated_value', 'example_stops_switch', 'vertical_inside_code',
        }
        challenges = [document for document in self.documents if document['challenges']]
        self.assertLessEqual(required_tags, {tag for document in challenges for tag in document['design_tags']})
        for moment in ('inicio', 'desarrollo', 'cierre'):
            self.assertEqual(self.by_id['after_' + moment]['declarations'], [])
        self.assertEqual(len(self.by_id['malformed_local_codes']['challenges']), 8)
        self.assertEqual(len(self.by_id['mixed_typed_row']['challenges']), 2)
        self.assertEqual(len(self.by_id['pipe_table_row']['challenges']), 2)
        candidates = [(document['id'], item['id']) for document in self.documents
                      for item in document['declarations'] if item['expected_decision'] == 'candidate']
        self.assertEqual(candidates, [('same_page_session_controls', 'd1'), ('same_page_session_controls', 'd2')])


if __name__ == '__main__':
    unittest.main()
