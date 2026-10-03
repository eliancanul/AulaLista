"""Technical evaluator tests. Constructed outputs are not model or teacher results."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.sprint_eval.corpus import DEFAULT_CORPUS, get_case, load_corpus
from scripts.sprint_eval.rubric import evaluate, score_review


def technical_output(case):
    return {
        'document_id': case['document_id'],
        'source_segments': copy.deepcopy(case['source_segments']),
        'fields': copy.deepcopy(case['expected_fields']),
        'missing_questions': list(case['review_questions']),
        'draft': {'title': '', 'objective': '', 'materials': [], 'steps': [],
                  'assessment': '', 'source_ids': [], 'revision': 1, 'approval_status': 'pending'},
    }


class CorpusContractTests(unittest.TestCase):
    def test_nine_frozen_inputs_have_verifiable_repository_provenance(self):
        corpus = load_corpus()
        self.assertEqual(len(corpus['cases']), 9)
        self.assertEqual(corpus['classification'], 'synthetic_development_only')
        self.assertTrue(all(c['teacher_validated'] is False for c in corpus['cases']))

    def test_distribution_does_not_include_private_inventory_or_historical_reports(self):
        lock = json.loads((DEFAULT_CORPUS / 'freeze.v1.json').read_text())
        self.assertEqual(set(lock['files']), {'cases.v1.json', 'rubric.v1.json'})
        for name in ('inventory.v1.json', 'verification.v1.json', 'compatibility.v1.json'):
            self.assertFalse((DEFAULT_CORPUS / name).exists())

    def test_changed_input_is_rejected_before_evaluation(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('AULALISTA_SCRATCH_DIR')) as tmp:
            dest = Path(tmp) / 'corpus'
            shutil.copytree(DEFAULT_CORPUS, dest)
            with (dest / 'cases.v1.json').open('a') as stream:
                stream.write(' ')
            with self.assertRaisesRegex(ValueError, 'Frozen artifact mismatch'):
                load_corpus(dest)

    def test_unknown_case_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown case'):
            get_case('SC99')

    def test_all_constructed_controls_pass_only_technical_checks(self):
        for case in load_corpus()['cases']:
            with self.subTest(case=case['id']):
                result = evaluate(case, technical_output(case))
                self.assertEqual(result['status'], 'PASS')
                self.assertEqual(result['counts']['field_match'], [len(case['expected_fields'])] * 2)
                self.assertEqual(result['semantic_status'], 'NOT_EVALUATED')
                self.assertFalse(result['teacher_validated'])

    def test_empty_output_cannot_pass(self):
        result = evaluate(get_case('SC01'), {})
        self.assertEqual(result['status'], 'ISSUES')
        self.assertEqual(result['counts']['field_match'], [0, 4])

    def test_non_object_output_cannot_pass(self):
        self.assertEqual(evaluate(get_case('SC01'), [])['status'], 'ISSUES')

    def test_wrong_objective_with_real_citation_fails_field_comparison(self):
        case = get_case('SC01'); output = technical_output(case)
        output['fields'][1]['value'] = 'Memorizar una respuesta inventada.'
        result = evaluate(case, output)
        self.assertIn('field_mismatch:proposito', result['issues'])
        self.assertEqual(result['counts']['reference_integrity'], [2, 2])

    def test_dangling_reference_fails(self):
        case = get_case('SC01'); output = technical_output(case)
        output['fields'][0]['evidence_ids'] = ['nonexistent']
        self.assertIn('missing_or_dangling_evidence:proyecto', evaluate(case, output)['issues'])

    def test_source_spoofing_fails(self):
        case = get_case('SC01'); output = technical_output(case)
        output['source_segments'][0]['text'] = 'Nivel: primaria'
        self.assertIn('source_segments_changed_or_missing', evaluate(case, output)['issues'])

    def test_grade_never_implies_school_level(self):
        for id in ('SC08', 'SC09'):
            case = get_case(id); output = technical_output(case)
            level = next(f for f in output['fields'] if f['key'] == 'nivel_educativo')
            self.assertEqual(level['value'], None)
            level.update(value='primaria', status='extracted', evidence_ids=[id + '-s1'])
            self.assertIn('field_mismatch:nivel_educativo', evaluate(case, output)['issues'])

    def test_unknown_cannot_smuggle_a_value(self):
        case = get_case('SC05'); output = technical_output(case)
        output['fields'][0]['value'] = 'Crear un herbario.'
        self.assertIn('unknown_asserts_value_or_evidence:proposito', evaluate(case, output)['issues'])

    def test_duplicate_fields_fail(self):
        case = get_case('SC01'); output = technical_output(case)
        output['fields'].append(copy.deepcopy(output['fields'][0]))
        self.assertIn('duplicate_field:proyecto', evaluate(case, output)['issues'])

    def test_automatic_approval_fails(self):
        case = get_case('SC01'); output = technical_output(case)
        output['draft']['approval_status'] = 'approved'
        self.assertIn('human_approval_gate', evaluate(case, output)['issues'])

    def test_missing_questions_fail(self):
        case = get_case('SC01'); output = technical_output(case)
        output['missing_questions'] = []
        self.assertIn('missing_questions_required', evaluate(case, output)['issues'])

    def test_extra_claim_is_exposed_for_review_never_scored_as_entailed(self):
        case = get_case('SC01'); output = technical_output(case)
        output['fields'].append(dict(key='new_claim', value='invented', status='extracted', evidence_ids=['SC01-s1']))
        result = evaluate(case, output)
        self.assertEqual(result['unscored_fields'], ['new_claim'])
        self.assertEqual(result['semantic_status'], 'NOT_EVALUATED')

    def test_malformed_fields_report_issues(self):
        case = get_case('SC01'); output = technical_output(case)
        output['fields'] = [None, {'key': 'title', 'status': [], 'evidence_ids': [{}]}]
        self.assertEqual(evaluate(case, output)['status'], 'ISSUES')

    def review(self):
        case = get_case('SC01')
        dimensions = json.loads((DEFAULT_CORPUS / 'rubric.v1.json').read_text())['dimensions']
        return dict(reviewer='synthetic test evaluator', reviewer_kind='agent', case_id='SC01',
                    input_sha256=case['input_sha256'], output_sha256=hashlib.sha256(b'test output').hexdigest(),
                    scores={k: {'score': 2, 'evidence': 'Constructed control only, SC01-s1.'} for k in dimensions})

    def test_recorded_review_weighting_does_not_claim_teacher_validation(self):
        result = score_review(self.review())
        self.assertEqual(result['review_score'], 100)
        self.assertTrue(result['eligible'])
        self.assertFalse(result['teacher_validated'])
        self.assertEqual(result['reviewer_kind'], 'agent')

    def test_hard_gate_cannot_be_offset_by_other_dimensions(self):
        review = self.review(); review['scores']['human_authority']['score'] = 1
        result = score_review(review)
        self.assertEqual(result['review_score'], 95)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['failed_gates'], ['human_authority'])

    def test_incomplete_review_cannot_receive_a_score(self):
        review = self.review(); del review['scores']['coverage']
        with self.assertRaisesRegex(ValueError, 'All rubric dimensions required'):
            score_review(review)

    def test_review_requires_output_identity_and_evidence(self):
        review = self.review(); review['output_sha256'] = ''
        with self.assertRaisesRegex(ValueError, 'output SHA-256'):
            score_review(review)
        review = self.review(); review['scores']['coverage']['evidence'] = ''
        with self.assertRaisesRegex(ValueError, 'Review evidence required'):
            score_review(review)


if __name__ == '__main__':
    unittest.main()
