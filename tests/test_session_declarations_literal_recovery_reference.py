"""Independent source-only freeze checks; these are not matcher tests.

Only standard-library authored-data validation runs here. No matcher, scorer,
scanner, prediction, private input, Django setup or extraction grammar is used
to determine an expected answer.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'interpretation'
REFERENCE = FIXTURES / 'session_declarations_literal_recovery_v1.json'
REFERENCE_SHA256 = '1a8f35662fe3d097cd14ce874d3e37ca9a52ecbace93ec2a7a371bfaf9d96184'
PRIOR_HASHES = {
    'activity_annex_semantics_v1.json': '0a565876b3595209cf7969e0ee37437f7efaeafbea9f10cd82851e3424c812d9',
    'activity_annex_v1.json': 'c49e767843a695a3fa3e760f259ab17ffc2dc29ae01367dfa4e2dc3214bac48c',
    'activity_session_bullets_v1.json': '79eebb377323b3a060f5243cd9d80fa459e956a774781c1937d16b84d59399b6',
    'activity_session_v1.json': '9fb8fdc7595e24c065bfba0f8babd833d74f2eae208f2f228aaa4c8055a8b347',
    'project_anchor_structure_v1.json': '266bcf93012d61774489fe82884e1a5979c43a5a142b47988b4f6992541be21e',
    'session_declarations_labels_v1.json': 'a5674e0ef46a8b8e6f374df3e6198bdf917ff3b2ec04ec6c96b23e9b2105d9e9',
    'session_declarations_project_metadata_v1.json': '9323aaaba522c8397aeb675afcafbd745c01d71c99338dbcb5745eded9f97d13',
    'session_declarations_scaffold_supplement_v1.json': 'f5136feae92c5c186845f2b080113a3a36f1aa2d1e20a2c8ebfa6b3bdd6cbc0d',
    'session_declarations_scaffold_v1.json': '3b83730070b9e04859a39af78065dbf70399bdfb3a6d5edbbc3a8941d71f3b09',
    'session_declarations_v1.json': '3c7a9aedf5be30b8755d12e6567d154b5d54859d1ff0a868727b8576060201f5',
}
SCORER_HASHES = {
    'scripts/evaluate_session_declarations.py': '393285dc7a472febecb3056f162eeecb91510f8c927db5d4e516e2e7c053a8ca',
}
CONTEXT_PROOF_HASHES = {
    'scripts/anchor_scope_catalogue.py': '2f408dc2738927503630e1fe42081385a8b04deaee0fb076c049a2f43c3430af',
    'docs/development/project-anchor-structure-v1.md': '540e251ebaf68b4df3d712784d0666f8ea1ce457ef0fcaccd9aefbdd55e2201b',
}
DENOMINATORS = {
    'documents': 119,
    'literal_declarations': 37,
    'new_recovery_literals': 19,
    'dotted_descriptor_recoveries': 0,
    'dotted_descriptor_challenges': 48,
    'local_content_list_recoveries': 19,
    'baseline_preservation_literals': 18,
    'unit_assignment': 37,
    'known_session_units': 1,
    'known_project_units': 1,
    'unresolved_units': 35,
    'session_candidates': 1,
    'scope_abstentions': 36,
    'new_recovery_scope_abstentions': 19,
    'challenges': 109,
    'documents_without_declarations': 85,
    'clean_silence_documents': 2,
    'source_proven_context_reset_controls': 3,
    'source_proven_context_reset_recoveries': 1,
    'source_unsafe_context_reset_challenges': 2,
}
RECOVERY_COUNTS = {
    'local_singular_hyphen': 1, 'local_plural_bullet': 1,
    'local_incorporation_singular_star': 1, 'local_incorporation_plural': 1,
    'local_case_and_indentation': 1, 'local_crlf': 1,
    'local_nfd_header_and_value': 1, 'local_balanced_quotes': 1,
    'local_blank_lines_full_list': 1, 'local_explicit_activity_stop': 1,
    'local_heading_with_value': 1, 'local_two_labelled_fields_closure': 1,
    'local_same_page_session_unresolved': 1, 'local_same_page_project_unresolved': 1,
    'local_repeated_physical_labels': 2, 'local_previous_page_unit_not_inherited': 1,
    'local_complete_typed_adjacency': 1, 'local_safe_source_proven_book_context': 1,
}


class LiteralRecoveryReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
        cls.documents = cls.reference['documents']
        cls.by_id = {document['id']: document for document in cls.documents}
        cls.recoveries = cls.reference['scope']['new_recovery_opportunities']
        cls.baseline = cls.reference['scope']['baseline_preservation_opportunities']

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

    def test_frozen_fixture_all_prior_bytes_and_scorer(self):
        self.assertEqual(hashlib.sha256(REFERENCE.read_bytes()).hexdigest(), REFERENCE_SHA256)
        self.assertEqual(self.reference['scope']['preserved_reference_sha256'], PRIOR_HASHES)
        self.assertEqual(self.reference['scope']['preserved_scorer_sha256'], SCORER_HASHES)
        self.assertEqual(self.reference['scope']['preserved_context_proof_sha256'], CONTEXT_PROOF_HASHES)
        for name, expected in PRIOR_HASHES.items():
            with self.subTest(reference=name):
                self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), expected)
        for name, expected in (SCORER_HASHES | CONTEXT_PROOF_HASHES).items():
            with self.subTest(scorer=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)

    def test_existing_envelope_and_authored_source_shape(self):
        self.assertEqual(set(self.reference), {'version', 'reference_kind', 'scope', 'documents'})
        self.assertEqual(self.reference['version'], 'session-declarations-reference.v1')
        self.assertEqual(self.reference['reference_kind'], 'synthetic_prematcher_development')
        self.assertEqual(self.reference['scope']['base_commit'], '740b5ca6d9b852824ebb8abdfcb8aa226f5016bb')
        self.assertEqual(len(self.documents), len(self.by_id))
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

    def test_source_bindings_are_exact_page_snapshots_not_pdf_hashes(self):
        binding = self.reference['scope']['source_binding']
        self.assertEqual(binding['kind'], 'synthetic_exact_page_snapshot')
        self.assertEqual(binding['algorithm'], 'sha256')
        self.assertEqual(set(binding['page_snapshots_sha256']), set(self.by_id))
        for document in self.documents:
            encoded = json.dumps(document['pages'], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            self.assertEqual(binding['page_snapshots_sha256'][document['id']], hashlib.sha256(encoded).hexdigest())

    def test_full_original_spans_and_occurrence_identity(self):
        for document in self.documents:
            with self.subTest(document=document['id']):
                ids, positions = set(), set()
                for category in ('units', 'declarations', 'challenges'):
                    for item in document[category]:
                        self.assertNotIn(item['id'], ids)
                        ids.add(item['id'])
                        self.assertTrue(item['id'])
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

    def test_new_recovery_never_assigns_unit_or_claim(self):
        recovered = set()
        for locator in self.recoveries:
            self.assertEqual(set(locator), {'document_id', 'declaration_id', 'route'})
            self.assertEqual(locator['route'], 'local_content_list')
            pair = locator['document_id'], locator['declaration_id']
            self.assertNotIn(pair, recovered)
            recovered.add(pair)
            declaration = self.declaration(locator)
            self.assertEqual(declaration['kind'], 'contenido')
            self.assertIsNone(declaration['unit_id'])
            self.assertEqual((declaration['expected_decision'], declaration['reason']),
                             ('abstained', 'unresolved_scope'))
            self.assertEqual(set(declaration), {
                'id', 'kind', 'label', 'value', 'unit_id', 'expected_decision', 'reason',
            })
        baseline = {(item['document_id'], item['declaration_id']) for item in self.baseline}
        self.assertEqual(len(baseline), len(self.baseline))
        self.assertTrue(recovered.isdisjoint(baseline))
        all_literals = {(document['id'], item['id']) for document in self.documents for item in document['declarations']}
        self.assertEqual(recovered | baseline, all_literals)
        for locator in self.baseline:
            self.assertEqual(set(locator), {'document_id', 'declaration_id'})
            declaration = self.declaration(locator)
            self.assertIn(declaration['kind'], ('contenido', 'pda'))
            units = {unit['id']: unit for unit in self.by_id[locator['document_id']]['units']}
            unit = units.get(declaration['unit_id'])
            expected = ('abstained', 'unresolved_scope') if unit is None else (
                ('candidate', 'explicit_session') if unit['kind'] == 'session' else ('abstained', 'project_scope'))
            self.assertEqual((declaration['expected_decision'], declaration['reason']), expected)

    def test_fixed_separate_denominators(self):
        declarations = [item for document in self.documents for item in document['declarations']]
        reasons = Counter(item['reason'] for item in declarations)
        actual = {
            'documents': len(self.documents), 'literal_declarations': len(declarations),
            'new_recovery_literals': len(self.recoveries), 'dotted_descriptor_recoveries': 0,
            'dotted_descriptor_challenges': sum(len(document['challenges']) for document in self.documents
                if any(tag.startswith('dotted_descriptor_') for tag in document['design_tags'])),
            'local_content_list_recoveries': sum(item['route'] == 'local_content_list' for item in self.recoveries),
            'baseline_preservation_literals': len(self.baseline), 'unit_assignment': len(declarations),
            'known_session_units': reasons['explicit_session'], 'known_project_units': reasons['project_scope'],
            'unresolved_units': reasons['unresolved_scope'],
            'session_candidates': sum(item['expected_decision'] == 'candidate' for item in declarations),
            'scope_abstentions': sum(item['expected_decision'] == 'abstained' for item in declarations),
            'new_recovery_scope_abstentions': sum(self.declaration(item)['expected_decision'] == 'abstained' for item in self.recoveries),
            'challenges': sum(len(document['challenges']) for document in self.documents),
            'documents_without_declarations': sum(document['absence_expected'] for document in self.documents),
            'clean_silence_documents': sum(not document['declarations'] and not document['challenges'] for document in self.documents),
            'source_proven_context_reset_controls': len(self.reference['scope']['source_proven_context_reset_controls']),
            'source_proven_context_reset_recoveries': sum(item['expected_safe_existing_context_proof'] for item in self.reference['scope']['source_proven_context_reset_controls']),
            'source_unsafe_context_reset_challenges': sum(not item['expected_safe_existing_context_proof'] for item in self.reference['scope']['source_proven_context_reset_controls']),
        }
        self.assertEqual(actual, DENOMINATORS)
        self.assertEqual(self.reference['scope']['frozen_denominators'], DENOMINATORS)
        self.assertEqual(dict(Counter(item['document_id'] for item in self.recoveries)), RECOVERY_COUNTS)

    def test_full_list_and_full_compositional_header_are_unchanged(self):
        declaration = self.by_id['local_incorporation_singular_star']['declarations'][0]
        self.assertEqual(declaration['label']['quote'], 'Incorporación de Contenido local:')
        self.assertEqual(declaration['value']['quote'], '* Marcas de posición.\n* Símbolos de dirección.')
        self.assertEqual(len(self.by_id['local_blank_lines_full_list']['declarations']), 1)
        self.assertEqual(self.by_id['local_blank_lines_full_list']['declarations'][0]['value']['quote'],
                         '- Nombres de fichas.\n\n- Formas de marcas.')
        repeated = self.by_id['local_repeated_physical_labels']['declarations']
        self.assertEqual(repeated[0]['label']['quote'], repeated[1]['label']['quote'])
        self.assertEqual(repeated[0]['value']['quote'], repeated[1]['value']['quote'])
        self.assertNotEqual(repeated[0]['label']['start'], repeated[1]['label']['start'])
        self.assertNotEqual(repeated[0]['value']['start'], repeated[1]['value']['start'])

    def test_unicode_crlf_internal_whitespace_are_original_slices(self):
        nfd = self.by_id['local_nfd_header_and_value']['declarations'][0]
        self.assertEqual(nfd['label']['quote'], 'Incorporacio\u0301n de Contenidos locales:')
        for key in ('label', 'value'):
            self.assertNotEqual(nfd[key]['quote'], unicodedata.normalize('NFC', nfd[key]['quote']))
        crlf = self.by_id['local_crlf']['declarations'][0]
        self.assertEqual(crlf['value']['quote'], '- Nombres\u00a0de fichas.\r\n\t- Formas de marcas.')
        self.assertEqual(self.by_id['local_case_and_indentation']['declarations'][0]['label']['quote'], 'cOnTeNiDoS LoCaLeS:')
        self.assertEqual(self.by_id['local_balanced_quotes']['declarations'][0]['value']['quote'],
                         '- Compara «L1» y «L2».\n- Formas llamadas “círculos”.')

    def test_no_descriptor_boundary_or_terminal_list_admission(self):
        for document in self.documents:
            if any(tag.startswith('dotted_descriptor_') for tag in document['design_tags']):
                self.assertFalse(any(item['document_id'] == document['id'] for item in self.recoveries))
        for identity in ('local_terminal_complete_list', 'local_list_across_page', 'local_heading_across_page',
                         'dotted_narrative_no_repeated_prefix', 'dotted_narrative_repeated_prefix'):
            self.assertEqual(self.by_id[identity]['declarations'], [])
            self.assertTrue(self.by_id[identity]['challenges'])
        self.assertEqual(self.by_id['local_previous_page_unit_not_inherited']['units'][0]['anchor']['page'], 1)
        self.assertEqual(self.by_id['local_previous_page_unit_not_inherited']['declarations'][0]['label']['page'], 2)


    def test_independent_typed_adjacency_and_known_closure_controls(self):
        document = self.by_id['local_complete_typed_adjacency']
        baseline, recovery = document['declarations']
        self.assertEqual((baseline['label']['quote'], baseline['value']['quote']),
                         ('Contenido:', 'Marcas de orientación.'))
        self.assertEqual(baseline['value']['page'], recovery['label']['page'])
        gap = document['pages'][0][baseline['value']['end']:recovery['label']['start']]
        self.assertEqual(gap, '\n\n')
        self.assertFalse(gap.strip())
        self.assertIsNone(recovery['unit_id'])
        self.assertEqual(dict(Counter(self.declaration(item)['kind'] for item in self.baseline)),
                         {'pda': 17, 'contenido': 1})
        for identity in ('local_unknown_note_closure', 'local_unlabelled_continuation_context',
                         'local_unknown_note_context', 'local_uncertain_typed_adjacency',
                         'local_nonwhitespace_typed_gap', 'local_activity_typed_adjacency',
                         'local_example_typed_adjacency', 'local_nonadoption_typed_adjacency',
                         'local_quoted_typed_adjacency', 'local_example_previous_page_typed_adjacency'):
            self.assertEqual(self.by_id[identity]['declarations'], [])
            self.assertTrue(self.by_id[identity]['challenges'])
        for identity in ('local_singular_hyphen', 'local_heading_with_value',
                         'local_two_labelled_fields_closure', 'local_explicit_activity_stop',
                         'local_repeated_physical_labels'):
            self.assertTrue(self.by_id[identity]['declarations'])


    def test_existing_project_context_proof_source_prefix_controls(self):
        controls = self.reference['scope']['source_proven_context_reset_controls']
        self.assertEqual([item['document_id'] for item in controls], [
            'local_safe_source_proven_book_context', 'local_active_example_book_context',
            'local_inherited_quote_book_context',
        ])
        self.assertEqual([item['expected_safe_existing_context_proof'] for item in controls], [True, False, False])
        self.assertEqual([item['prefix_paragraph_closed'] for item in controls], [True, False, True])
        self.assertEqual([item['prefix_quote_open'] for item in controls], [False, False, True])
        profiles = []
        for control in controls:
            document = self.by_id[control['document_id']]
            self.assertEqual(document['units'], [])
            self.assertEqual(len(document['pages']), 2)
            self.assertSpan(document['pages'], control['proof_profile_span'])
            self.assertEqual(control['proof_profile_span']['page'], 2)
            self.assertEqual([item['role'] for item in control['witnesses']], [
                'planning_root', 'project_label', 'project_title', 'scenario',
                'purpose', 'product', 'project_association',
            ])
            for witness in control['witnesses']:
                self.assertSpan(document['pages'], witness['span'])
                self.assertEqual(witness['span']['page'], 2)
            profiles.append(control['proof_profile_span']['quote'])
            if control['expected_safe_existing_context_proof']:
                self.assertEqual(len(document['declarations']), 1)
                declaration = document['declarations'][0]
                self.assertIsNone(declaration['unit_id'])
                self.assertEqual((declaration['expected_decision'], declaration['reason']),
                                 ('abstained', 'unresolved_scope'))
            else:
                self.assertEqual(document['declarations'], [])
                self.assertEqual(len(document['challenges']), 1)
        self.assertEqual(profiles[0], profiles[1])
        self.assertEqual(profiles[0], profiles[2])
        self.assertEqual(self.by_id['local_safe_source_proven_book_context']['pages'][0],
                         'Ejemplo de una propuesta no adoptada.\n\n')
        self.assertEqual(self.by_id['local_active_example_book_context']['pages'][0],
                         'Ejemplo de una propuesta no adoptada.\n')
        self.assertEqual(self.by_id['local_inherited_quote_book_context']['pages'][0],
                         '“Ejemplo de una propuesta no adoptada.\n\n')

    def test_adversarial_coverage_is_explicit_and_separate(self):
        required = {
            'partial_code', 'partial_numbered_label', 'partial_local_label', 'missing_local_colon',
            'numbered_list', 'mixed_bullet_families', 'incomplete_prior_value', 'incomplete_descriptor',
            'wrapped_descriptor', 'wrapped_item', 'incomplete_item', 'typed_label_in_list', 'heading_in_list',
            'activity_in_list', 'code_row_in_list', 'unclosed_value_quote', 'mismatched_value_quote',
            'quoted_header', 'example_before_planning_root', 'nonadoption_before_planning_root',
            'open_source_quote', 'mismatched_source_quote', 'source_prefix_safety',
            'unsafe_context_inherited_across_pages', 'example_previous_page', 'nonadoption_previous_page',
            'open_quote_previous_page', 'mismatched_quote_previous_page', 'inline_label_mention',
            'inline_local_header', 'inline_next_label', 'no_cross_page_join', 'narrative_ambiguity',
            'repeated_prefix_narrative', 'descriptor_next_code_mismatch', 'canonical_equality_not_literal_equality',
            'activity_before_context', 'field_does_not_reset_activity', 'local_header_does_not_reset_activity',
            'unsupported_synonym', 'arbitrary_qualifier', 'unaccented_prefix', 'number_disagreement',
            'terminal_page_only', 'missing_explicit_closure', 'bulleted_heading_not_closure',
            'unknown_note_not_closure', 'unlabelled_continuation_not_context', 'unknown_note_not_context',
            'uncertain_typed_adjacency_not_context', 'nonwhitespace_gap_not_adjacency',
            'activity_vetoes_typed_adjacency', 'example_vetoes_typed_adjacency',
            'nonadoption_vetoes_typed_adjacency', 'quotation_vetoes_typed_adjacency',
            'active_prior_example_paragraph', 'context_proof_cannot_clear_active_example',
            'inherited_open_quote', 'context_proof_cannot_clear_open_quote',
        }
        challenges = [document for document in self.documents if document['challenges']]
        self.assertLessEqual(required, {tag for document in challenges for tag in document['design_tags']})
        for document in self.documents:
            for challenge in document['challenges']:
                self.assertEqual(set(challenge), {'id', 'anchor', 'reason'})
                self.assertIn(challenge['reason'], {'uncertain_boundary', 'quoted', 'nonaffirmative', 'label_mention'})


if __name__ == '__main__':
    unittest.main()
