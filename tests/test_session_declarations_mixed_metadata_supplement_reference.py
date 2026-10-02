"""Source-only integrity checks; never import extraction or product code."""
import hashlib
import json
from pathlib import Path
import unicodedata
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/interpretation/session_declarations_mixed_metadata_supplement_v1.json'
BASE_FIXTURE = ROOT / 'tests/fixtures/interpretation/session_declarations_mixed_fields_v1.json'
CONTRACT = ROOT / 'docs/development/session-declarations-mixed-metadata-supplement-v1.md'
SOURCE_SHA = '8fbe9730c40cf4a5896fb3062f0ccf6526272b4458ab0c95625b6b3740da843b'
SOURCE_STAGE_SHA = '1532d4a098934b3db425f5861b819cca8c21fdbb44ed4010e97db5a19f28f84e'
FIXTURE_SHA = 'ff93882fc51e2fc1e7e30be1aa693ec7bf069ccae013713159cf0b0b1b9b5083'
BASE_SHA = 'cffc43ca220904ebf38e50b9be8e83a919f1beaeae01cbea07c124508256dc8b'
POSITIVE_IDS = {
    'dated_suffix_lf', 'dated_suffix_crlf_spaces',
    'initial_fecha_wrapped_inline_tiempo', 'session_fecha_wrapped_inline_tiempo',
    'dated_suffix_inline_tiempo', 'activity_then_dated_reset',
    'example_then_dated_reset', 'closed_quote_then_dated_reset',
}
NEGATIVE_IDS = {
    'false_suffix_longer_phrase', 'title_suffix_not_metadata',
    'unknown_split_label', 'tab_inside_split_label', 'c0_inside_split_label',
    'format_control_theme_value', 'bare_cr_label_boundary',
    'non_ascii_space_suffix', 'example_metadata_cannot_reset',
    'open_quote_dated_not_reset', 'after_activity_metadata_cannot_reset',
    'missing_colon_split_label', 'unknown_colon_in_continuation',
    'arbitrary_fake_session', 'numbered_sesion_not_continuation',
    'metadata_valid_mixed_unclosed',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def physical_line(source, start):
    left = source.rfind('\n', 0, start) + 1
    right = source.find('\n', start)
    if right < 0:
        right = len(source)
    return source[left:right].removesuffix('\r')


def unsafe_character(text):
    """Reference safety assertion, not a metadata recognizer."""
    without_paired_crlf = text.replace('\r\n', '\n')
    return any(
        (unicodedata.category(c) in {'Cc', 'Cf'} and c != '\n')
        or (c.isspace() and c not in {' ', '\n'})
        for c in without_paired_crlf
    )


class MixedMetadataSupplementReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = FIXTURE.read_bytes()
        cls.fixture = json.loads(cls.raw)
        cls.documents = cls.fixture['documents']
        cls.by_id = {d['id']: d for d in cls.documents}

    def test_frozen_artifact_and_unchanged_base(self):
        self.assertEqual(sha(self.raw), FIXTURE_SHA)
        self.assertEqual(sha(BASE_FIXTURE.read_bytes()), BASE_SHA)
        contract = CONTRACT.read_text(encoding='utf-8')
        for digest in (SOURCE_SHA, SOURCE_STAGE_SHA, FIXTURE_SHA):
            self.assertIn(digest, contract)

    def test_frozen_sources_and_saved_preannotation_stage(self):
        sources = [{'id': d['id'], 'pages': d['pages']} for d in self.documents]
        compact = json.dumps(sources, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.assertEqual(sha(compact), SOURCE_SHA)
        self.assertEqual(self.fixture['source_first_sha256'], SOURCE_SHA)
        self.assertEqual(self.fixture['source_unannotated_fixture_sha256'], SOURCE_STAGE_SHA)
        stage = {
            'version': 1,
            'reference_kind': 'source_only_mixed_metadata_supplement',
            'source_first_sha256': SOURCE_SHA,
            'source_freeze_stage': 'sources_saved_before_annotations',
            'documents': sources,
        }
        encoded_stage = (json.dumps(stage, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        self.assertEqual(sha(encoded_stage), SOURCE_STAGE_SHA)

    def test_schema_and_fixed_denominators(self):
        self.assertEqual(set(self.fixture), {
            'version', 'reference_kind', 'source_first_sha256',
            'source_freeze_stage', 'documents', 'default_mixed_fields',
            'enabled_patch_contract', 'counts', 'source_unannotated_fixture_sha256',
        })
        self.assertEqual(self.fixture['version'], 1)
        self.assertEqual(self.fixture['reference_kind'], 'source_only_mixed_metadata_supplement')
        self.assertEqual(self.fixture['source_freeze_stage'], 'sources_saved_before_annotations')
        self.assertEqual(set(self.by_id), POSITIVE_IDS | NEGATIVE_IDS)
        self.assertEqual(len(self.by_id), len(self.documents))
        actual = {'documents': len(self.documents)}
        for output, key in [('recoveries', 'expected_recoveries'),
                            ('rejections', 'expected_rejections'),
                            ('typed_controls', 'typed_controls')]:
            actual[output] = sum(len(d[key]) for d in self.documents)
        self.assertEqual(actual, {'documents': 24, 'recoveries': 8, 'rejections': 16, 'typed_controls': 0})
        self.assertEqual(actual, self.fixture['counts'])
        for doc in self.documents:
            with self.subTest(doc=doc['id']):
                self.assertEqual(set(doc), {'id', 'pages', 'tags', 'expected_recoveries', 'expected_rejections', 'typed_controls'})
                self.assertEqual(len(doc['pages']), 1)
                self.assertTrue(all(isinstance(p, str) for p in doc['pages']))
                self.assertEqual(doc['typed_controls'], [])
                self.assertEqual(len(doc['expected_recoveries']) + len(doc['expected_rejections']), 1)
                if doc['id'] in POSITIVE_IDS:
                    self.assertEqual(len(doc['expected_recoveries']), 1)
                    self.assertIn('positive', doc['tags'])
                    self.assertNotIn('negative', doc['tags'])
                else:
                    self.assertEqual(len(doc['expected_rejections']), 1)
                    self.assertIn('negative', doc['tags'])
                    self.assertNotIn('positive', doc['tags'])

    def test_same_evidence_only_compatibility_contract(self):
        base = json.loads(BASE_FIXTURE.read_bytes())
        self.assertIs(self.fixture['default_mixed_fields'], False)
        patch = self.fixture['enabled_patch_contract']
        self.assertEqual(patch, base['enabled_patch_contract'])
        self.assertEqual(patch['requires_existing_record'], {
            'kind': None, 'decision': 'abstained', 'reason': 'combined_label', 'claim': None,
        })
        self.assertEqual(patch['only_added_evidence_role'], 'value')
        self.assertEqual(patch['unit_effect'], 'preserve_existing')
        self.assertEqual(patch['new_units'], 0)
        self.assertEqual(patch['new_claims'], 0)
        self.assertIs(patch['typed_detection_credit'], False)

    def check_span(self, doc, span):
        self.assertEqual(set(span), {'page', 'start', 'end', 'quote'})
        self.assertIs(type(span['page']), int)
        self.assertIs(type(span['start']), int)
        self.assertIs(type(span['end']), int)
        self.assertGreaterEqual(span['page'], 1)
        self.assertLessEqual(span['page'], len(doc['pages']))
        source = doc['pages'][span['page'] - 1]
        self.assertGreaterEqual(span['start'], 0)
        self.assertGreater(span['end'], span['start'])
        self.assertLessEqual(span['end'], len(source))
        self.assertEqual(source[span['start']:span['end']], span['quote'])
        self.assertEqual(source[span['start']:span['end']].encode('utf-8'), span['quote'].encode('utf-8'))

    def test_all_exact_spans_and_annotation_schema(self):
        ids = set()
        for doc in self.documents:
            for recovery in doc['expected_recoveries']:
                with self.subTest(doc=doc['id']):
                    self.assertEqual(set(recovery), {'id', 'label', 'value', 'closing_heading', 'context', 'context_reset'})
                    self.assertNotIn(recovery['id'], ids)
                    ids.add(recovery['id'])
                    self.assertEqual(recovery['id'], doc['id'] + ':recover:1')
                    for key in ('label', 'value', 'closing_heading'):
                        self.check_span(doc, recovery[key])
                    reset = recovery['context_reset']
                    if reset is not None:
                        self.check_span(doc, reset)
                        self.assertEqual(recovery['context'], 'session_metadata')
                    else:
                        self.assertEqual(recovery['context'], 'initial_metadata')
            for rejection in doc['expected_rejections']:
                with self.subTest(doc=doc['id']):
                    self.assertEqual(set(rejection), {'id', 'anchor', 'category', 'expected_effect'})
                    self.assertNotIn(rejection['id'], ids)
                    ids.add(rejection['id'])
                    self.assertEqual(rejection['id'], doc['id'] + ':reject:1')
                    self.check_span(doc, rejection['anchor'])
                    self.assertEqual(rejection['anchor']['quote'], 'Contenidos/PDA:')
                    self.assertEqual(rejection['expected_effect'], 'no_value_added')
                    self.assertIsInstance(rejection['category'], str)
                    self.assertTrue(rejection['category'])

    def test_complete_values_and_unchanged_base_bounds(self):
        allowed_closers = {'Inicio:', 'Recursos:', 'Materiales:',
                           'Descripción de actividades:', 'Cierre:',
                           'Evaluación:', 'Observaciones:'}
        for doc_id in POSITIVE_IDS:
            doc = self.by_id[doc_id]
            recovery = doc['expected_recoveries'][0]
            label, value, closer = (recovery[k] for k in ('label', 'value', 'closing_heading'))
            source = doc['pages'][0]
            with self.subTest(doc=doc_id):
                self.assertEqual({label['page'], value['page'], closer['page']}, {1})
                self.assertLessEqual(label['end'], value['start'])
                self.assertLess(value['end'], closer['start'])
                self.assertRegex(label['quote'], r'^Contenidos? *(?:/|y) *PDAs? *:$')
                self.assertEqual(physical_line(source, label['start']).strip(' '), label['quote'])
                self.assertIn(closer['quote'], allowed_closers)
                self.assertEqual(physical_line(source, closer['start']).strip(' '), closer['quote'])
                self.assertEqual(source[label['end']:closer['start']].strip(' \r\n'), value['quote'])
                self.assertLessEqual(len(value['quote']), 2048)
                self.assertLessEqual(sum(bool(line.strip(' ')) for line in value['quote'].replace('\r\n', '\n').split('\n')), 32)
                self.assertFalse(unsafe_character(source))

    def test_full_dated_reset_never_truncated_at_metadata_boundary(self):
        dated_ids = {
            'dated_suffix_lf', 'dated_suffix_crlf_spaces', 'dated_suffix_inline_tiempo',
            'activity_then_dated_reset', 'example_then_dated_reset',
            'closed_quote_then_dated_reset',
        }
        for doc_id in dated_ids:
            doc = self.by_id[doc_id]
            recovery = doc['expected_recoveries'][0]
            source = doc['pages'][0]
            reset = recovery['context_reset']
            with self.subTest(doc=doc_id):
                self.assertEqual(physical_line(source, reset['start']).strip(' '), reset['quote'])
                self.assertRegex(reset['quote'], r'^Sesión [0-9]+ Fecha: [A-Za-záéíóú]+ [0-9]+ +Tema de la$')
                self.assertTrue(reset['quote'].endswith('Tema de la'))
                suffix_start = reset['end'] - len('Tema de la')
                self.assertEqual(source[suffix_start:reset['end']], 'Tema de la')
                self.assertLess(reset['end'], recovery['label']['start'])
                following = source[reset['end']:].replace('\r\n', '\n').split('\n')
                self.assertEqual(following[0].strip(' '), '')
                self.assertEqual(following[1].strip(' '), 'sesión:')
                self.assertNotEqual(reset['quote'], 'sesión:')
        initial = self.by_id['initial_fecha_wrapped_inline_tiempo']['expected_recoveries'][0]
        self.assertIsNone(initial['context_reset'])
        ordinary = self.by_id['session_fecha_wrapped_inline_tiempo']['expected_recoveries'][0]
        self.assertEqual(ordinary['context_reset']['quote'], 'Sesión 4')

    def test_explicit_metadata_continuation_witnesses(self):
        expected = {
            'initial_fecha_wrapped_inline_tiempo': 'Tema largo\ncon continuación. Tiempo: 35 minutos',
            'session_fecha_wrapped_inline_tiempo': 'Observamos hojas\ny sus cambios. Tiempo: 35 minutos',
            'dated_suffix_inline_tiempo': 'Exploración del entorno\ncon registros compartidos. Tiempo: 35 minutos',
        }
        for doc_id, quote in expected.items():
            doc = self.by_id[doc_id]
            source = doc['pages'][0]
            recovery = doc['expected_recoveries'][0]
            with self.subTest(doc=doc_id):
                self.assertIn(quote, source)
                self.assertLess(source.index(quote) + len(quote), recovery['label']['start'])
                self.assertNotIn('Tiempo:', recovery['value']['quote'])
                self.assertNotIn('sesión:', recovery['value']['quote'])
        crlf = self.by_id['dated_suffix_crlf_spaces']
        self.assertIn('\r\n', crlf['expected_recoveries'][0]['value']['quote'])
        self.assertNotIn('\n', crlf['pages'][0].replace('\r\n', ''))
        unicode_value = self.by_id['dated_suffix_inline_tiempo']['expected_recoveries'][0]['value']['quote']
        self.assertIn('🌳', unicode_value)
        self.assertIn('can\u0303as', unicode_value)

    def test_negative_challenges_are_literal_and_never_sanitized(self):
        witnesses = {
            'false_suffix_longer_phrase': 'Tema de la vida\nsesión:',
            'title_suffix_not_metadata': 'Título: Tema de la\nsesión:',
            'unknown_split_label': 'Asunto de la\nsesión:',
            'tab_inside_split_label': 'Tema\tde la',
            'c0_inside_split_label': 'Tema de\x00 la',
            'format_control_theme_value': 'continua\u200bción. Tiempo:',
            'bare_cr_label_boundary': 'Tema de la\rsesión:',
            'non_ascii_space_suffix': '\u00a0Tema de la',
            'example_metadata_cannot_reset': 'Ejemplo no adoptado:\nFecha:',
            'open_quote_dated_not_reset': '“Ejemplo ajeno:\nSesión',
            'after_activity_metadata_cannot_reset': 'Inicio:\nEscuchar una historia.\nFecha:',
            'missing_colon_split_label': 'Tema de la\nsesión\n',
            'unknown_colon_in_continuation': 'con continuación. Duración: 35 minutos',
            'arbitrary_fake_session': 'Proyecto de sesión 23 Fecha:',
            'numbered_sesion_not_continuation': 'Tema de la\nsesión 24:',
            'metadata_valid_mixed_unclosed': 'Contenidos/PDA:\nRelata una historia.\n',
        }
        self.assertEqual(set(witnesses), NEGATIVE_IDS)
        for doc_id, quote in witnesses.items():
            doc = self.by_id[doc_id]
            with self.subTest(doc=doc_id):
                self.assertIn(quote, doc['pages'][0])
                self.assertEqual(doc['expected_recoveries'], [])
                self.assertEqual(doc['expected_rejections'][0]['expected_effect'], 'no_value_added')
        unsafe_ids = {'tab_inside_split_label', 'c0_inside_split_label',
                      'format_control_theme_value', 'bare_cr_label_boundary',
                      'non_ascii_space_suffix'}
        for doc_id in unsafe_ids:
            self.assertTrue(unsafe_character(self.by_id[doc_id]['pages'][0]))
        self.assertNotIn('”', self.by_id['open_quote_dated_not_reset']['pages'][0])
        self.assertIn('”\nSesión', self.by_id['closed_quote_then_dated_reset']['pages'][0])
        unclosed = self.by_id['metadata_valid_mixed_unclosed']['pages'][0]
        self.assertTrue(unclosed.endswith('Relata una historia.\n'))


if __name__ == '__main__':
    unittest.main()
