"""Independent pre-implementation freeze checks for synthetic authored gold.

Only the JSON reference is read. These tests never import or run the matcher,
evaluator, product scanner, extraction, or saved prediction outputs. They can run
with the standard-library unittest runner without loading the Django test setup.
"""

import hashlib
import json
from pathlib import Path
import unittest


FIXTURE = (
    Path(__file__).parent
    / 'fixtures/interpretation/session_declarations_scaffold_v1.json'
)
SHA256 = '3b83730070b9e04859a39af78065dbf70399bdfb3a6d5edbbc3a8941d71f3b09'

MARKER_CANDIDATES = ('marker_attached_pair', 'marker_spaced_crlf_repeated')
MARKER_CHALLENGES = (
    'marker_prose_mention',
    'marker_quoted_example',
    'marker_unquoted_example',
    'marker_missing_colon',
    'marker_after_inicio',
    'marker_after_desarrollo',
    'marker_after_cierre',
)
SCAFFOLD_CANDIDATES = (
    'scaffold_empty_tail',
    'scaffold_complete_metadata',
    'scaffold_bullet_metadata',
    'scaffold_crlf_metadata',
)
UNRESOLVED_SCOPE = (
    'scaffold_developed_session',
    'scaffold_prior_activity_without_moment',
    'scaffold_truncated_value',
    'scaffold_reset',
    'scaffold_two_prior_headers',
    'scaffold_loose_prefix',
    'scaffold_intermediate_page',
    'scaffold_current_activity_prefix',
)
IDENTITY_CONTROLS = (
    'scaffold_new_session',
    'scaffold_new_project',
    'explicit_continuation_after_developed',
)


class SessionDeclarationsScaffoldReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = FIXTURE.read_bytes()
        cls.reference = json.loads(cls.raw)
        cls.documents = cls.reference['documents']
        cls.by_id = {doc['id']: doc for doc in cls.documents}

    def test_frozen_bytes_metadata_and_separate_denominators(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), SHA256)
        self.assertEqual(
            self.reference['version'], 'session-declarations-reference.v1'
        )
        self.assertIn('not held-out or teacher gold', self.reference['reference_kind'])
        scope = self.reference['scope']
        self.assertIsInstance(scope, dict)
        self.assertEqual(scope['development_base'], '420334b')
        self.assertIn('Entirely synthetic', scope['input'])
        self.assertEqual(
            scope['metadata_fields'],
            ['Fecha', 'Tiempo', 'Duración', 'Tema de la sesión', 'Organización',
             'Campo', 'Campos'],
        )
        self.assertIn('Final reserve or holdout material', scope['exclusions'])
        self.assertIn('Cross-page value reconstruction', scope['exclusions'])
        expected_ids = set(
            MARKER_CANDIDATES + MARKER_CHALLENGES + SCAFFOLD_CANDIDATES
            + UNRESOLVED_SCOPE + IDENTITY_CONTROLS + ('scaffold_open_quote',)
        )
        self.assertEqual(set(self.by_id), expected_ids)
        self.assertEqual(len(self.documents), 25)
        declarations = [d for doc in self.documents for d in doc['declarations']]
        self.assertEqual(len(declarations), 28)
        self.assertEqual(
            sum(d['expected_decision'] == 'candidate' for d in declarations), 17
        )
        self.assertEqual(
            sum(d['expected_decision'] == 'abstained' for d in declarations), 11
        )
        self.assertEqual(sum(d['reason'] == 'unresolved_scope' for d in declarations), 9)
        self.assertEqual(sum(d['reason'] == 'project_scope' for d in declarations), 2)
        self.assertEqual(sum(len(doc['challenges']) for doc in self.documents), 12)
        self.assertEqual(sum(doc['absence_expected'] for doc in self.documents), 8)

    def test_literal_unicode_spans_required_shape_and_local_unit_links(self):
        self.assertEqual(len(self.by_id), len(self.documents))
        global_opportunity_ids = set()
        for doc in self.documents:
            with self.subTest(document=doc['id']):
                self.assertEqual(
                    set(doc), {'id', 'pages', 'units', 'declarations',
                               'challenges', 'absence_expected'}
                )
                self.assertTrue(doc['pages'])
                self.assertTrue(all(isinstance(page, str) for page in doc['pages']))
                units = {unit['id']: unit for unit in doc['units']}
                self.assertEqual(len(units), len(doc['units']))
                spans = []
                for unit in doc['units']:
                    self.assertEqual(set(unit), {'id', 'kind', 'anchor'})
                    self.assertIn(unit['kind'], {'session', 'project'})
                    spans.append(unit['anchor'])
                label_locations = set()
                for declaration in doc['declarations']:
                    self.assertEqual(
                        set(declaration), {'id', 'kind', 'label', 'value',
                                           'unit_id', 'expected_decision', 'reason'}
                    )
                    self.assertIn(declaration['kind'], {'contenido', 'pda'})
                    self.assertIn(declaration['expected_decision'], {'candidate', 'abstained'})
                    label, value = declaration['label'], declaration['value']
                    spans.extend((label, value))
                    self.assertEqual(label['page'], value['page'])
                    self.assertLessEqual(label['end'], value['start'])
                    self.assertEqual(label['quote'], label['quote'].strip())
                    self.assertEqual(value['quote'], value['quote'].strip())
                    location = tuple(label[key] for key in ('page', 'start', 'end'))
                    self.assertNotIn(location, label_locations)
                    label_locations.add(location)
                    uid = declaration['unit_id']
                    self.assertTrue(uid is None or uid in units)
                    if declaration['expected_decision'] == 'candidate':
                        self.assertIsNotNone(uid)
                        self.assertEqual(units[uid]['kind'], 'session')
                        self.assertEqual(declaration['reason'], 'explicit_session')
                    elif declaration['reason'] == 'unresolved_scope':
                        self.assertIsNone(uid)
                    elif declaration['reason'] == 'project_scope':
                        self.assertEqual(units[uid]['kind'], 'project')
                    else:
                        self.fail('Unexpected declaration adjudication')
                for challenge in doc['challenges']:
                    self.assertEqual(set(challenge), {'id', 'anchor', 'reason'})
                    spans.append(challenge['anchor'])
                for opportunity in doc['declarations'] + doc['challenges']:
                    self.assertNotIn(opportunity['id'], global_opportunity_ids)
                    global_opportunity_ids.add(opportunity['id'])
                for span in spans:
                    self.assertEqual(set(span), {'page', 'start', 'end', 'quote'})
                    self.assertIs(type(span['page']), int)
                    self.assertIs(type(span['start']), int)
                    self.assertIs(type(span['end']), int)
                    self.assertGreaterEqual(span['page'], 1)
                    self.assertLessEqual(span['page'], len(doc['pages']))
                    page = doc['pages'][span['page'] - 1]
                    self.assertGreaterEqual(span['start'], 0)
                    self.assertLess(span['start'], span['end'])
                    self.assertLessEqual(span['end'], len(page))
                    self.assertEqual(page[span['start']:span['end']], span['quote'])
                self.assertIs(type(doc['absence_expected']), bool)
                self.assertEqual(doc['absence_expected'], not doc['declarations'])

    def test_markers_preserve_full_typed_labels_and_distinct_repeated_blocks(self):
        expected_labels = {
            'marker_attached_pair': ['Contenido:', 'X7 PDA2:'],
            'marker_spaced_crlf_repeated': [
                'Contenidos curriculares:', 'X7\tPDA2:', 'X7\tPDA2:'
            ],
        }
        for doc_id in MARKER_CANDIDATES:
            doc = self.by_id[doc_id]
            self.assertEqual(
                [d['label']['quote'] for d in doc['declarations']],
                expected_labels[doc_id],
            )
            for declaration in doc['declarations']:
                label = declaration['label']
                page = doc['pages'][label['page'] - 1]
                line_start = page.rfind('\n', 0, label['start']) + 1
                self.assertIn(page[line_start:label['start']], {'-', '  - ', '\t- '})
                self.assertTrue(label['quote'].endswith(':'))
                self.assertLess(declaration['value']['end'], page.index('Inicio:'))
                self.assertEqual(declaration['expected_decision'], 'candidate')
        repeated = self.by_id['marker_spaced_crlf_repeated']['declarations'][1:]
        self.assertEqual(repeated[0]['value']['quote'], repeated[1]['value']['quote'])
        self.assertIn('\r\n', repeated[0]['value']['quote'])
        self.assertNotEqual(repeated[0]['label']['start'], repeated[1]['label']['start'])
        self.assertNotEqual(repeated[0]['id'], repeated[1]['id'])

    def test_marker_prose_examples_missing_colon_and_moments_are_challenges(self):
        for doc_id in MARKER_CHALLENGES:
            doc = self.by_id[doc_id]
            self.assertEqual(doc['declarations'], [])
            self.assertTrue(doc['challenges'])
            self.assertTrue(doc['absence_expected'])
        self.assertIn('-Leer X7 PDA2:', self.by_id['marker_prose_mention']['pages'][0])
        self.assertIn('Ejemplo:\n-X7 PDA2:', self.by_id['marker_unquoted_example']['pages'][0])
        self.assertEqual(
            self.by_id['marker_missing_colon']['challenges'][0]['anchor']['quote'],
            'X7 PDA2',
        )
        for doc_id, first_moment in (
            ('marker_after_inicio', 'Inicio:'),
            ('marker_after_desarrollo', 'Desarrollo:'),
            ('marker_after_cierre', 'Cierre:'),
        ):
            doc = self.by_id[doc_id]
            for challenge in doc['challenges']:
                self.assertGreater(challenge['anchor']['start'], doc['pages'][0].index(first_moment))

    def test_bounded_scaffold_positives_have_previous_anchor_and_page_local_values(self):
        for doc_id in SCAFFOLD_CANDIDATES:
            doc = self.by_id[doc_id]
            self.assertEqual(len(doc['pages']), 2)
            self.assertEqual(len(doc['units']), 1)
            anchor = doc['units'][0]['anchor']
            self.assertEqual(anchor['page'], 1)
            self.assertEqual(anchor['quote'], 'SESIÓN 1: Explorar formas')
            for moment in ('Inicio:', 'Desarrollo:', 'Cierre:'):
                self.assertNotIn(moment, doc['pages'][0])
            for declaration in doc['declarations']:
                self.assertEqual(declaration['unit_id'], 's1')
                self.assertEqual(declaration['expected_decision'], 'candidate')
                self.assertEqual(declaration['label']['page'], 2)
                self.assertEqual(declaration['value']['page'], 2)
                self.assertLess(declaration['value']['end'], doc['pages'][1].index('Inicio:'))
        empty_tail = self.by_id['scaffold_empty_tail']
        anchor = empty_tail['units'][0]['anchor']
        self.assertEqual(empty_tail['pages'][0][anchor['end']:].strip(), '')
        complete_tail = self.by_id['scaffold_complete_metadata']['pages'][0]
        for line in (
            'Fecha: 2026-01-12', 'Tiempo: 40 minutos',
            'Tema de la sesión: Formas de tarjetas', 'Organización: Equipos',
            'Campo: Saberes y pensamiento científico',
        ):
            self.assertIn('\n' + line + '\n', complete_tail)
        bullet_doc = self.by_id['scaffold_bullet_metadata']
        self.assertIn('- Duración: 45 minutos', bullet_doc['pages'][0])
        self.assertIn('- Campos: Lenguajes', bullet_doc['pages'][0])
        self.assertTrue(bullet_doc['pages'][1].startswith('- Tiempo: 45 minutos\n- Campo:'))
        crlf_doc = self.by_id['scaffold_crlf_metadata']
        self.assertTrue(all('\r\n' in page for page in crlf_doc['pages']))
        self.assertEqual(
            crlf_doc['declarations'][1]['value']['quote'],
            'Describe tarjetas\r\ny compara sus tamaños.',
        )

    def test_doubtful_continuation_is_explicit_unresolved_scope_not_silence(self):
        for doc_id in UNRESOLVED_SCOPE:
            doc = self.by_id[doc_id]
            self.assertTrue(doc['declarations'])
            self.assertFalse(doc['absence_expected'])
            for declaration in doc['declarations']:
                self.assertIsNone(declaration['unit_id'])
                self.assertEqual(declaration['expected_decision'], 'abstained')
                self.assertEqual(declaration['reason'], 'unresolved_scope')
        self.assertEqual(len(self.by_id['scaffold_two_prior_headers']['units']), 2)
        intermediate = self.by_id['scaffold_intermediate_page']
        self.assertEqual(len(intermediate['pages']), 3)
        self.assertEqual(intermediate['declarations'][0]['label']['page'], 3)
        self.assertEqual(intermediate['units'][0]['anchor']['page'], 1)
        truncated = self.by_id['scaffold_truncated_value']
        self.assertEqual(len(truncated['declarations']), 1)
        self.assertEqual(truncated['declarations'][0]['kind'], 'pda')
        self.assertEqual(truncated['challenges'][0]['reason'], 'uncertain_boundary')
        self.assertTrue(truncated['pages'][0].endswith('Contenido: Formas y\n'))
        self.assertTrue(truncated['pages'][1].startswith('colores.\n'))

    def test_new_units_do_not_inherit_prior_session_and_explicit_continuation_survives(self):
        new_session = self.by_id['scaffold_new_session']
        for declaration in new_session['declarations']:
            self.assertEqual(declaration['unit_id'], 's2')
            self.assertEqual(declaration['expected_decision'], 'candidate')
        self.assertEqual(new_session['units'][1]['anchor']['page'], 2)
        new_project = self.by_id['scaffold_new_project']
        self.assertEqual(new_project['units'][1]['kind'], 'project')
        self.assertEqual(new_project['units'][1]['anchor']['page'], 2)
        for declaration in new_project['declarations']:
            self.assertEqual(declaration['unit_id'], 'p1')
            self.assertEqual(declaration['expected_decision'], 'abstained')
            self.assertEqual(declaration['reason'], 'project_scope')
        continuation = self.by_id['explicit_continuation_after_developed']
        self.assertIn('Desarrollo:\n-Comparar tarjetas.', continuation['pages'][0])
        self.assertTrue(continuation['pages'][1].startswith('Continuación de la sesión 1\n'))
        for declaration in continuation['declarations']:
            self.assertEqual(declaration['unit_id'], 's1')
            self.assertEqual(declaration['expected_decision'], 'candidate')
        self.assertEqual(continuation['units'][0]['anchor']['page'], 1)

    def test_open_cross_page_quote_remains_challenge_without_declaration(self):
        quoted = self.by_id['scaffold_open_quote']
        self.assertTrue(quoted['pages'][0].endswith('«\n'))
        self.assertIn('\n»\nInicio:', quoted['pages'][1])
        self.assertEqual(quoted['declarations'], [])
        self.assertTrue(quoted['absence_expected'])
        self.assertEqual(len(quoted['challenges']), 2)
        for challenge in quoted['challenges']:
            self.assertEqual(challenge['anchor']['page'], 2)
            self.assertEqual(challenge['reason'], 'quoted')


if __name__ == '__main__':
    unittest.main()
