"""Contract integration against published S02/S06 modules; no model calls."""
import copy
import unittest

from check_compatibility import ROOT, check_case, dependencies
from scripts.sprint_eval.corpus import get_case, load_corpus, prepare_segment_bridge


class SegmentBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor, cls.schema = dependencies(ROOT, ROOT)

    def setUp(self):
        self.case = get_case('SC08')
        self.lines = self.extractor.extracted_page_segments(
            self.case['source_segments'][0]['text'], self.case['document_id'], 1)

    def test_all_nine_keep_frozen_inputs_and_pass_canonical_schema_and_rubric(self):
        for case in load_corpus()['cases']:
            with self.subTest(case=case['id']):
                row = check_case(case, self.extractor, self.schema)
                self.assertEqual(row['bridge']['model_input']['source_segments'], case['source_segments'])
                self.assertEqual(row['frozen_page_schema']['status'], 'PASS')
                self.assertEqual(row['frozen_rubric']['status'], 'PASS')
                self.assertFalse(row['frozen_rubric']['teacher_validated'])
                self.assertEqual(row['raw_s02_schema']['status'], 'ISSUES')

    def test_line_only_projection_exposes_two_multiline_failures(self):
        failures = {}
        for case in load_corpus()['cases']:
            row = check_case(case, self.extractor, self.schema)
            if row['projected_s02_schema']['status'] != 'PASS':
                failures[case['id']] = row['unsupported_split_fields']
        self.assertEqual(failures, {'SC04': ['proyecto'], 'SC07': ['proposito']})

    def test_does_not_mutate_or_alias_inputs(self):
        before = copy.deepcopy((self.case, self.lines))
        result = prepare_segment_bridge(self.case, self.lines)
        result['model_input']['source_segments'][0]['text'] = 'changed'
        result['provenance']['s02_source_segments'].clear()
        self.assertEqual((self.case, self.lines), before)

    def test_rejects_source_identity_and_position_corruption(self):
        mutations = [('id', 'other-document'), ('page', 2), ('text', 'Nivel: primaria'),
                     ('text_start', -1), ('text_end', 9999), ('text_start', True),
                     ('kind', 'approved_curriculum')]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(self.lines)
                changed[0][key] = value
                with self.assertRaises(ValueError):
                    prepare_segment_bridge(self.case, changed)

    def test_rejects_missing_duplicate_and_reordered_lines(self):
        for changed in (self.lines[1:], self.lines[:-1], self.lines + self.lines[:1],
                        list(reversed(self.lines)), []):
            with self.subTest(ids=[s['id'] for s in changed]):
                with self.assertRaises(ValueError):
                    prepare_segment_bridge(self.case, changed)

    def test_rejects_changed_frozen_text(self):
        self.case['source_segments'][0]['text'] += '\nNivel: primaria'
        with self.assertRaisesRegex(ValueError, 'digest'):
            prepare_segment_bridge(self.case, self.lines)

    def test_rejects_two_frozen_segments_on_one_page(self):
        self.case['source_segments'].append(copy.deepcopy(self.case['source_segments'][0]))
        from scripts.sprint_eval.corpus import sha256
        self.case['input_sha256'] = sha256('\n'.join(s['text'] for s in self.case['source_segments']).encode())
        with self.assertRaisesRegex(ValueError, 'one frozen segment'):
            prepare_segment_bridge(self.case, self.lines)


if __name__ == '__main__':
    unittest.main()
