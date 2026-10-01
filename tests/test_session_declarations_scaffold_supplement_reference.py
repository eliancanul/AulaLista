"""Independent pre-output checks of authored scaffold supplemental data.

Only frozen fixtures and the archived reference-test bytes are read. No product
module, matcher, scorer, scanner, extraction, or prediction output is imported or
executed. Run with standard-library unittest discovery, without Django or pytest.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest


TESTS = Path(__file__).parent
BASE_PATH = 'tests/fixtures/interpretation/session_declarations_scaffold_v1.json'
BASE = TESTS / 'fixtures/interpretation/session_declarations_scaffold_v1.json'
SUPPLEMENT = (
    TESTS / 'fixtures/interpretation/session_declarations_scaffold_supplement_v1.json'
)
BASE_TEST = TESTS / 'test_session_declarations_scaffold_reference.py'
BASE_SHA256 = '3b83730070b9e04859a39af78065dbf70399bdfb3a6d5edbbc3a8941d71f3b09'
BASE_TEST_SHA256 = 'bfcc78bb40edf5437656b7eb466542ed749a356e67124a1e59034d75cc9aaa60'
SUPPLEMENT_SHA256 = 'f5136feae92c5c186845f2b080113a3a36f1aa2d1e20a2c8ebfa6b3bdd6cbc0d'

SAME_PAGE = (
    ('marker_attached_pair', 'marker_attached_pair-d1'),
    ('marker_attached_pair', 'marker_attached_pair-d2'),
    ('marker_spaced_crlf_repeated', 'marker_spaced_crlf_repeated-d1'),
    ('marker_spaced_crlf_repeated', 'marker_spaced_crlf_repeated-d2'),
    ('marker_spaced_crlf_repeated', 'marker_spaced_crlf_repeated-d3'),
    ('scaffold_new_session', 'scaffold_new_session-d1'),
    ('scaffold_new_session', 'scaffold_new_session-d2'),
)
SCAFFOLD = (
    ('scaffold_empty_tail', 'scaffold_empty_tail-d1'),
    ('scaffold_empty_tail', 'scaffold_empty_tail-d2'),
    ('scaffold_complete_metadata', 'scaffold_complete_metadata-d1'),
    ('scaffold_complete_metadata', 'scaffold_complete_metadata-d2'),
    ('scaffold_bullet_metadata', 'scaffold_bullet_metadata-d1'),
    ('scaffold_bullet_metadata', 'scaffold_bullet_metadata-d2'),
    ('scaffold_crlf_metadata', 'scaffold_crlf_metadata-d1'),
    ('scaffold_crlf_metadata', 'scaffold_crlf_metadata-d2'),
)
CONTINUATION = (
    ('explicit_continuation_after_developed',
     'explicit_continuation_after_developed-d1'),
    ('explicit_continuation_after_developed',
     'explicit_continuation_after_developed-d2'),
)

# Both coordinates and quotes are authored constants, not generated boundaries.
# CRLF, indentation, tabs and terminal newlines are physical evidence.
SCAFFOLD_PROOFS = {
    'scaffold_empty_tail': (
        ('unit_scaffold_tail', 1, 0, 27,
         'SESIÓN 1: Explorar formas\n\n'),
        ('unit_scaffold_prefix', 2, 0, 69,
         'Contenido: Formas de las tarjetas.\nPDA: Describe formas de tarjetas.\n'),
    ),
    'scaffold_complete_metadata': (
        ('unit_scaffold_tail', 1, 0, 163,
         'SESIÓN 1: Explorar formas\nFecha: 2026-01-12\nTiempo: 40 minutos\n'
         'Tema de la sesión: Formas de tarjetas\nOrganización: Equipos\n'
         'Campo: Saberes y pensamiento científico\n'),
        ('unit_scaffold_prefix', 2, 0, 63,
         'Contenido: Formas y tamaños.\nPDA: Compara tamaños de tarjetas.\n'),
    ),
    'scaffold_bullet_metadata': (
        ('unit_scaffold_tail', 1, 0, 154,
         'SESIÓN 1: Explorar formas\n-Fecha: 2026-01-13\n- Duración: 45 minutos\n'
         '  - Tema de la sesión: Tarjetas de colores\n-Organización: Parejas\n'
         '- Campos: Lenguajes\n'),
        ('unit_scaffold_prefix', 2, 0, 110,
         '- Tiempo: 45 minutos\n- Campo: Lenguajes\n'
         'Contenido: Descripción de colores.\nPDA: Describe colores de tarjetas.\n'),
    ),
    'scaffold_crlf_metadata': (
        ('unit_scaffold_tail', 1, 0, 68,
         'SESIÓN 1: Explorar formas\r\nDuración: 35 minutos\r\nCampos: Lenguajes\r\n'),
        ('unit_scaffold_prefix', 2, 0, 159,
         'Fecha: 2026-01-14\r\nTema de la sesión: Tarjetas pequeñas\r\n'
         '- Contenidos:\tDescripción de tarjetas pequeñas.\r\n'
         '-X7 PDA2:\tDescribe tarjetas\r\ny compara sus tamaños.\r\n'),
    ),
}
CONTINUATION_PROOF = (
    'unit_continuation', 2, 0, 27, 'Continuación de la sesión 1'
)
NEGATIVE_SPANS = {
    'scaffold_empty_date_tail': ((2, 0, 4), (2, 5, 33)),
    'scaffold_truncated_topic_prefix': ((2, 31, 35), (2, 36, 64)),
    'scaffold_free_prose_after_pda': ((2, 0, 4), (2, 5, 33)),
    'scaffold_general_data_reset_tail': ((2, 0, 4), (2, 5, 33)),
    'scaffold_desarrollo_before_pda': ((2, 12, 16), (2, 17, 45)),
}


class SessionDeclarationsScaffoldSupplementReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_raw = BASE.read_bytes()
        cls.raw = SUPPLEMENT.read_bytes()
        cls.base = json.loads(cls.base_raw)
        cls.reference = json.loads(cls.raw)
        cls.base_by_id = {doc['id']: doc for doc in cls.base['documents']}
        cls.requirements = cls.reference['candidate_scope_requirements']
        cls.by_requirement = {
            (item['document_id'], item['declaration_id']): item
            for item in cls.requirements
        }
        cls.additional = cls.reference['additional_reference']
        cls.documents = cls.additional['documents']
        cls.by_id = {doc['id']: doc for doc in cls.documents}

    def assert_literal_span(self, pages, span, *, proof=False):
        keys = {'page', 'start', 'end', 'quote'}
        if proof:
            keys.add('role')
        self.assertEqual(set(span), keys)
        for key in ('page', 'start', 'end'):
            self.assertIs(type(span[key]), int)
        self.assertGreaterEqual(span['page'], 1)
        self.assertLessEqual(span['page'], len(pages))
        page = pages[span['page'] - 1]
        self.assertGreaterEqual(span['start'], 0)
        self.assertLess(span['start'], span['end'])
        self.assertLessEqual(span['end'], len(page))
        self.assertIsInstance(span['quote'], str)
        self.assertEqual(page[span['start']:span['end']], span['quote'])

    def test_frozen_hashes_and_base_reference_are_exact(self):
        self.assertEqual(hashlib.sha256(self.base_raw).hexdigest(), BASE_SHA256)
        self.assertEqual(hashlib.sha256(BASE_TEST.read_bytes()).hexdigest(), BASE_TEST_SHA256)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), SUPPLEMENT_SHA256)
        self.assertEqual(
            self.reference['base_reference'],
            {'path': BASE_PATH, 'sha256': BASE_SHA256},
        )

    def test_supplement_schema_provenance_and_separate_denominators(self):
        self.assertEqual(
            set(self.reference),
            {'version', 'reference_kind', 'scope', 'base_reference',
             'candidate_scope_requirements', 'additional_reference'},
        )
        self.assertEqual(
            self.reference['version'], 'session-declarations-scaffold-supplement.v1'
        )
        self.assertIn('not held-out or teacher gold', self.reference['reference_kind'])
        self.assertEqual(self.reference['scope']['development_base'], '8093752')
        self.assertIn('separate denominator', self.reference['scope']['denominator_policy'])
        self.assertIn('Before product outputs', self.reference['scope']['freeze_stage'])
        self.assertIn('Cross-page value reconstruction', self.reference['scope']['exclusions'])
        self.assertEqual(set(self.additional), {'version', 'reference_kind', 'scope', 'documents'})
        self.assertEqual(self.additional['version'], 'session-declarations-reference.v1')
        self.assertEqual(self.additional['scope']['development_base'], '8093752')
        self.assertIn('not held-out or teacher gold', self.additional['reference_kind'])
        self.assertEqual(self.base['scope']['development_base'], '420334b')
        historical = [item for doc in self.base['documents'] for item in doc['declarations']]
        self.assertEqual(len(self.base['documents']), 25)
        self.assertEqual(len(historical), 28)
        self.assertEqual(Counter(item['expected_decision'] for item in historical),
                         {'candidate': 17, 'abstained': 11})
        self.assertEqual(sum(len(doc['challenges']) for doc in self.base['documents']), 12)
        self.assertEqual(len(self.documents), 5)
        self.assertTrue(set(self.by_id).isdisjoint(self.base_by_id))

    def test_exact_seventeen_candidate_ids_and_seven_eight_two_bases(self):
        expected = {
            **{key: 'same_page_explicit' for key in SAME_PAGE},
            **{key: 'structural_scaffold_proposal' for key in SCAFFOLD},
            **{key: 'explicit_continuation' for key in CONTINUATION},
        }
        self.assertEqual(len(self.requirements), 17)
        self.assertEqual(len(self.by_requirement), 17)
        self.assertEqual(set(self.by_requirement), set(expected))
        historical_candidates = {
            (doc['id'], declaration['id'])
            for doc in self.base['documents']
            for declaration in doc['declarations']
            if declaration['expected_decision'] == 'candidate'
        }
        self.assertEqual(set(self.by_requirement), historical_candidates)
        for key, item in self.by_requirement.items():
            with self.subTest(candidate=key):
                self.assertEqual(set(item), {'document_id', 'declaration_id',
                                             'unit_scope_basis', 'proofs'})
                self.assertEqual(item['unit_scope_basis'], expected[key])
                self.assertIsInstance(item['proofs'], list)
        self.assertEqual(Counter(item['unit_scope_basis'] for item in self.requirements),
                         {'same_page_explicit': 7, 'structural_scaffold_proposal': 8,
                          'explicit_continuation': 2})

    def test_same_page_candidates_have_no_extra_proof(self):
        for key in SAME_PAGE:
            with self.subTest(candidate=key):
                requirement = self.by_requirement[key]
                self.assertEqual(requirement['proofs'], [])
                doc = self.base_by_id[key[0]]
                declaration = next(item for item in doc['declarations'] if item['id'] == key[1])
                unit = next(item for item in doc['units'] if item['id'] == declaration['unit_id'])
                self.assertEqual(unit['anchor']['page'], declaration['label']['page'])
                self.assertEqual(unit['anchor']['page'], declaration['value']['page'])

    def test_scaffold_proofs_have_exact_roles_coordinates_and_literal_quotes(self):
        fields = ('role', 'page', 'start', 'end', 'quote')
        for key in SCAFFOLD:
            with self.subTest(candidate=key):
                proofs = self.by_requirement[key]['proofs']
                self.assertEqual(len(proofs), 2)
                self.assertEqual(tuple(tuple(item[name] for name in fields) for item in proofs),
                                 SCAFFOLD_PROOFS[key[0]])
                pages = self.base_by_id[key[0]]['pages']
                for item in proofs:
                    self.assert_literal_span(pages, item, proof=True)
                tail, prefix = proofs
                self.assertEqual(tail['end'], len(pages[0]))
                self.assertEqual(prefix['end'], pages[1].index('Inicio:'))
                self.assertEqual(tail['quote'], pages[0])
                for moment in ('Inicio:', 'Desarrollo:', 'Cierre:'):
                    self.assertNotIn(moment, tail['quote'])
                    self.assertNotIn(moment, prefix['quote'])
        for doc_id in SCAFFOLD_PROOFS:
            self.assertEqual(self.by_requirement[(doc_id, doc_id + '-d1')]['proofs'],
                             self.by_requirement[(doc_id, doc_id + '-d2')]['proofs'])
        crlf = self.by_requirement[('scaffold_crlf_metadata', 'scaffold_crlf_metadata-d2')]
        self.assertTrue(all('\r\n' in proof['quote'] for proof in crlf['proofs']))
        self.assertIn('\tDescribe tarjetas\r\ny compara sus tamaños.', crlf['proofs'][1]['quote'])

    def test_explicit_continuation_has_one_exact_phrase_proof(self):
        fields = ('role', 'page', 'start', 'end', 'quote')
        for key in CONTINUATION:
            with self.subTest(candidate=key):
                proofs = self.by_requirement[key]['proofs']
                self.assertEqual(len(proofs), 1)
                self.assertEqual(tuple(proofs[0][name] for name in fields), CONTINUATION_PROOF)
                doc = self.base_by_id[key[0]]
                self.assert_literal_span(doc['pages'], proofs[0], proof=True)
                self.assertIn('Desarrollo:', doc['pages'][0])
                self.assertEqual(proofs[0]['page'], doc['units'][0]['anchor']['page'] + 1)
                self.assertNotIn('\n', proofs[0]['quote'])

    def test_five_additional_documents_keep_detection_and_abstain_without_scope(self):
        self.assertEqual(set(self.by_id), set(NEGATIVE_SPANS))
        self.assertEqual(len(self.by_id), len(self.documents))
        declarations = [item for doc in self.documents for item in doc['declarations']]
        self.assertEqual(len(declarations), 5)
        self.assertEqual(Counter(item['expected_decision'] for item in declarations), {'abstained': 5})
        self.assertEqual(Counter(item['reason'] for item in declarations), {'unresolved_scope': 5})
        self.assertEqual(sum(len(doc['challenges']) for doc in self.documents), 0)
        self.assertEqual(sum(doc['absence_expected'] for doc in self.documents), 0)
        for doc in self.documents:
            with self.subTest(document=doc['id']):
                self.assertEqual(set(doc), {'id', 'pages', 'units', 'declarations',
                                            'challenges', 'absence_expected'})
                self.assertEqual(len(doc['pages']), 2)
                self.assertTrue(all(isinstance(page, str) for page in doc['pages']))
                self.assertEqual(len(doc['units']), 1)
                unit = doc['units'][0]
                self.assertEqual(set(unit), {'id', 'kind', 'anchor'})
                self.assertEqual((unit['id'], unit['kind']), ('s1', 'session'))
                self.assertEqual(unit['anchor'], {'page': 1, 'start': 0, 'end': 25,
                                                   'quote': 'SESIÓN 1: Explorar formas'})
                self.assert_literal_span(doc['pages'], unit['anchor'])
                self.assertEqual(len(doc['declarations']), 1)
                declaration = doc['declarations'][0]
                self.assertEqual(set(declaration), {'id', 'kind', 'label', 'value',
                                                    'unit_id', 'expected_decision', 'reason'})
                self.assertEqual(declaration['id'], doc['id'] + '-d1')
                self.assertEqual(declaration['kind'], 'pda')
                self.assertIsNone(declaration['unit_id'])
                self.assertEqual(declaration['expected_decision'], 'abstained')
                self.assertEqual(declaration['reason'], 'unresolved_scope')
                for field, expected, quote in zip(
                    ('label', 'value'), NEGATIVE_SPANS[doc['id']],
                    ('PDA:', 'Describe formas de tarjetas.'),
                ):
                    span = declaration[field]
                    self.assert_literal_span(doc['pages'], span)
                    self.assertEqual(tuple(span[name] for name in ('page', 'start', 'end')), expected)
                    self.assertEqual(span['quote'], quote)
                self.assertEqual(declaration['label']['page'], declaration['value']['page'])
                self.assertLessEqual(declaration['label']['end'], declaration['value']['start'])
                self.assertEqual(doc['challenges'], [])
                self.assertIs(doc['absence_expected'], False)

    def test_five_negative_vetoes_are_physical_and_do_not_erase_complete_pda(self):
        empty_date = self.by_id['scaffold_empty_date_tail']
        self.assertEqual(empty_date['pages'][0], 'SESIÓN 1: Explorar formas\nFecha:\n')
        truncated = self.by_id['scaffold_truncated_topic_prefix']
        self.assertTrue(truncated['pages'][1].startswith('Tema de la sesión: Tarjetas de\nPDA:'))
        free_prose = self.by_id['scaffold_free_prose_after_pda']
        self.assertEqual(free_prose['pages'][1],
                         'PDA: Describe formas de tarjetas.\n'
                         'Las tarjetas permanecen sobre la mesa.\nInicio:\n-Observar tarjetas.\n')
        self.assertNotIn('Las tarjetas', free_prose['declarations'][0]['value']['quote'])
        reset = self.by_id['scaffold_general_data_reset_tail']
        self.assertEqual(reset['pages'][0],
                         'SESIÓN 1: Explorar formas\nDATOS GENERALES\nFecha: 2026-01-20\n')
        self.assertGreater(reset['pages'][0].index('DATOS GENERALES'), reset['units'][0]['anchor']['end'])
        desarrollo = self.by_id['scaffold_desarrollo_before_pda']
        self.assertTrue(desarrollo['pages'][1].startswith('Desarrollo:\nPDA:'))
        self.assertTrue(all('Inicio:' not in page for page in desarrollo['pages']))
        for doc in self.documents:
            self.assertIn('PDA: Describe formas de tarjetas.\n', doc['pages'][1])
            for moment in ('Inicio:', 'Desarrollo:', 'Cierre:'):
                self.assertNotIn(moment, doc['pages'][0])


if __name__ == '__main__':
    unittest.main()
