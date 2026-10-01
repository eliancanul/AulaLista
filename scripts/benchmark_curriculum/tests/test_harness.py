import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from scripts.benchmark_curriculum.common import ROOT, PYTHON, Runtime, canonical_output, canonical_bytes, sha_bytes, read_json, write_json
from scripts.benchmark_curriculum.metrics import rate, validate_citation, validate_anchor, score, read_source
from scripts.benchmark_curriculum.adapter import adapt
from scripts.benchmark_curriculum.fixtures import pdf_bytes
from scripts.benchmark_curriculum.runner import aggregate, load_freeze, validate_rows, bounded, make_order

SHA='a'*64
SOURCE={'document_sha256':SHA,'page_count':2,'pages':[{'text':'Proyecto: Uno\nSESIÓN 1: Uno\nPropósito: leer.','read_error':None},
    {'text':'Proyecto: Dos\nSESIÓN 1: Dos\nFinalidad: mirar.','read_error':None}], 'read_errors':[]}
EV={'document_sha256':SHA,'page_number':1,'excerpt':'Uno'}
ANCHOR={'schema_version':1,'kind':'session','document_sha256':SHA,'page_number':1,'occurrence':1,'text_start':14,'text_end':27,'excerpt':'SESIÓN 1: Uno'}

def raw():
    return {'dossier':{'source_sha256':SHA,'version':1,'page_count':2,
                      'general_fields':{'proyecto':{'value':'Uno','status':'supported','review':'pending','evidence':[copy.deepcopy(EV)]}},
                      'sessions':[]}, 'claims':[], 'verification':{'items':[]}}

class MetricsTests(unittest.TestCase):
    def test_literal(self): self.assertEqual(validate_citation(EV,SOURCE),[])
    def test_empty_and_malformed_citation(self):
        for ev in (None,[],True,False,'Uno',3,{}, {'excerpt':'   '}): self.assertTrue(validate_citation(ev,SOURCE))
    def test_strict_page_types(self):
        for page in (True,False,'1',1.0,0,-1,3,None):
            self.assertIn('page_type_or_range',validate_citation({**EV,'page_number':page},SOURCE))
    def test_wrong_sha(self):
        for sha in ('b'*64,SHA.upper(),'','a'*63,None,True):
            self.assertTrue(validate_citation({**EV,'document_sha256':sha},SOURCE))
    def test_quote_other_page_is_invalid(self):
        self.assertIn('excerpt_not_literal_on_page',validate_citation({**EV,'excerpt':'Dos'},SOURCE))
    def test_no_normalization(self):
        self.assertTrue(validate_citation({**EV,'excerpt':'uno'},SOURCE))
    def test_cross_page_quote_is_invalid(self):
        self.assertTrue(validate_citation({**EV,'excerpt':'leer.Proyecto: Dos'},SOURCE))
    def test_anchor_valid(self): self.assertEqual(validate_anchor(ANCHOR,SOURCE),[])
    def test_bool_string_anchor_integer_fields(self):
        for key in ('schema_version','page_number','occurrence','text_start','text_end'):
            for bad in (True,False,str(ANCHOR[key]),float(ANCHOR[key]),None):
                with self.subTest(key=key,bad=bad): self.assertTrue(validate_anchor({**ANCHOR,key:bad},SOURCE))
    def test_anchor_offset_bounds(self):
        for start,end in ((-1,2),(2,2),(8,3),(0,1000)):
            self.assertIn('offset_range',validate_anchor({**ANCHOR,'text_start':start,'text_end':end},SOURCE))
    def test_shifted_offset(self):
        self.assertIn('excerpt_offset_mismatch',validate_anchor({**ANCHOR,'text_start':15,'text_end':28},SOURCE))
    def test_occurrence_semantics_not_invented(self):
        # Literal/offset integrity does not know whether occurrence should equal 1.
        self.assertEqual(validate_anchor({**ANCHOR,'occurrence':2},SOURCE),[])
    def test_zero_denominator_is_na(self):
        self.assertIsNone(rate(0,0,'citations')['value'])
        self.assertEqual(rate(0,0,'citations')['display_status'],'N/A')
        with self.assertRaises(ValueError): rate(True,1,'items')
    def test_partial_valid_field_m3_pass_m4_fail(self):
        value=raw(); value['dossier']['general_fields']['proyecto']['evidence'].append({**EV,'page_number':2})
        scored=score(value,SOURCE,'B3')
        self.assertEqual(scored['metrics']['M3_fields']['numerator'],1)
        self.assertEqual(scored['metrics']['M4']['numerator'],0)
        self.assertEqual(scored['metrics']['M6']['numerator'],1)
    def test_review_pending_is_not_abstention(self):
        scored=score(raw(),SOURCE,'B0')
        self.assertEqual(scored['M8']['candidate_fields'],1)
        self.assertEqual(scored['M8']['abstaining_emitted_field_slots'],0)
    def test_ambiguous_wrong_candidate_still_counted(self):
        value=raw(); f=value['dossier']['general_fields']['proyecto']; f['status']='ambiguous'; f['value']='Wrong'
        self.assertEqual(score(value,SOURCE,'B2')['M8']['candidate_fields'],1)
    def test_no_output_remains_fixed_document_denominator(self):
        scored=score({},SOURCE,'B0','timeout')
        self.assertEqual(scored['metrics']['M1']['denominator'],1)
        self.assertEqual(scored['metrics']['M1']['numerator'],0)
        self.assertEqual(scored['metrics']['M7']['denominator'],1)
        self.assertIsNone(scored['metrics']['M3_citations']['value'])
        self.assertEqual(scored['M8']['no_dossier_output'],1)
        self.assertEqual(scored['M8']['execution_failure'],1)
        self.assertEqual(scored['reference']['human'],'not_evaluable')
    def test_malformed_evidence_not_silently_dropped(self):
        value=raw(); value['dossier']['general_fields']['proyecto']['evidence']='broken'
        scored=score(value,SOURCE,'B0')
        self.assertEqual(scored['M8']['citations_emitted'],1)
        self.assertEqual(scored['M8']['invalid_citations'],1)
    def test_malformed_field_counted(self):
        value=raw(); value['dossier']['general_fields']['proyecto']=True
        scored=score(value,SOURCE,'B0')
        self.assertEqual(scored['M8']['fields_emitted'],1)
        self.assertEqual(scored['M8']['malformed_fields'],1)
    def test_verifier_never_truth(self):
        value=raw(); value['dossier']['general_fields']['proyecto']['evidence']=[{**EV,'page_number':2}]
        value['verification']={'items':[{'path':'general_fields/proyecto/evidence/0','status':'checked'}]}
        scored=score(value,SOURCE,'B3')
        self.assertEqual(scored['metrics']['M3_citations']['numerator'],0)
        self.assertEqual(scored['M8']['strong_audit_fields'],1)
    def test_claims_evidence_separate_denominator(self):
        value=raw(); value['claims']=[{'evidence':[EV]}]
        scored=score(value,SOURCE,'B0')
        self.assertEqual(scored['metrics']['M3_citations']['denominator'],1)
        self.assertEqual(scored['M8']['claim_citations'],1)
    def test_units_missing_anchor_not_dropped(self):
        value=raw(); value['dossier']['sessions']=[{'session_id':'s1','fields':{},'pages':[1]}]
        scored=score(value,SOURCE,'B0')
        self.assertEqual(scored['metrics']['M5_units']['denominator'],1)
        self.assertEqual(scored['metrics']['M5_units']['numerator'],0)
    def test_list_field_not_semantically_certified(self):
        value=raw(); value['dossier']['general_fields']['proyecto']['value']=['Uno','Dos']
        scored=score(value,SOURCE,'B3')
        self.assertEqual(scored['metrics']['M4']['numerator'],1)
        self.assertEqual(scored['reference']['human'],'not_evaluable')
    def test_macro_excludes_na_but_records_n(self):
        first=score(raw(),SOURCE,'B3',document_id='a',family_id='f',split='R')
        second=score({},SOURCE,'B3','timeout',document_id='b',family_id='f',split='R')
        agg=aggregate([first,second])[0]
        self.assertEqual(agg['metrics']['M1']['micro']['denominator'],2)
        self.assertEqual(agg['metrics']['M3_citations']['macro_document_evaluable_n'],1)
        self.assertEqual(agg['documents_no_output'],1)
    def test_source_reader_independent(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'test.pdf'; data=pdf_bytes([['Uno'],['Dos']]); path.write_bytes(data)
            source=read_source(path,sha_bytes(data),2)
            self.assertIn('Uno',source['pages'][0]['text'])
            self.assertNotIn('Dos',source['pages'][0]['text'])
            with self.assertRaises(ValueError): read_source(path,'b'*64,2)
            with self.assertRaises(ValueError): read_source(path,sha_bytes(data),3)

class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runtime = Runtime(ROOT.parents[1], Path(self.temporary.name))

    def test_canonicalization_exact_paths_only(self):
        value=raw(); value['dossier'].update(created_at='one',updated_at='two',history=[{'action':'prepare','timestamp':'three'}, {'action':'other','timestamp':'keep'}])
        value['dossier']['general_fields']['proyecto']['created_at']='keep'
        copy_before=copy.deepcopy(value); canon=canonical_output(value)
        self.assertEqual(value,copy_before)
        self.assertNotIn('created_at',canon['dossier'])
        self.assertEqual(canon['dossier']['general_fields']['proyecto']['created_at'],'keep')
        self.assertEqual(canon['dossier']['history'][1]['timestamp'],'keep')
    def test_canonicalization_preserves_unexpected_history_schema(self):
        for history in (None, 7, True, 'history', {'timestamp': 'keep'}):
            value = {'dossier': {'history': history}}
            original = copy.deepcopy(value)
            with self.subTest(history=history):
                self.assertEqual(canonical_output(value), original)
                self.assertEqual(value, original)

    def test_adapter_preserves_values_and_types(self):
        value=raw(); value['dossier']['general_fields']['proyecto']['evidence']=[{**EV,'page_number':True}]
        before=copy.deepcopy(value); view=adapt(value,'B3')
        self.assertIs(view['citations'][0]['raw']['page_number'],True)
        self.assertEqual(before,value)
    def test_unready_freeze_rejected_without_sources(self):
        path=self.runtime.workdir/'freeze.json'; write_json(path,{'ready_to_run':False})
        with self.assertRaises(ValueError): load_freeze(path,self.runtime)
    def test_quarantine_rejected_before_read(self):
        row={'document_id':'Q','family_id':'Q','split':'D','page_count':2,
             'path':str(self.runtime.workdir/'quarantine'/'MUST_NOT_OPEN.pdf'),'bytes':0,'file_sha256':'a'*64,
             'selection_status':'included'}
        config=read_json(ROOT/'config.proposed.json')
        with self.assertRaisesRegex(ValueError,'Quarantine'):
            validate_rows([row],config,self.runtime)
    def test_nonincluded_rejected_before_read(self):
        row={'document_id':'Q','family_id':'Q','split':'D','page_count':2,
             'path':str(self.runtime.workdir/'MUST_NOT_OPEN.pdf'),'bytes':0,'file_sha256':'a'*64,
             'selection_status':'candidate'}
        with self.assertRaisesRegex(ValueError,'explicitly included'):
            validate_rows([row],read_json(ROOT/'config.proposed.json'),self.runtime)
    def test_json_duplicate_and_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'value.json'
            for text in ('{"x":1,"x":2}','{"x":NaN}'):
                path.write_text(text)
                with self.assertRaises(ValueError): read_json(path)
    def test_guard_blocks_dns_and_socket_and_subprocess(self):
        for statement in ('socket.getaddrinfo("example.com",443)','socket.socket()','subprocess.run(["true"])'):
            code='import sys;sys.path.insert(0,'+repr(str(ROOT.parents[1]))+'); import socket,subprocess; from scripts.benchmark_curriculum.offline_guard import install,OfflineViolation; events=install();\ntry:\n '+statement+'\nexcept OfflineViolation:\n print("BLOCKED",len(events))\nelse:\n raise RuntimeError("guard failed")'
            run=subprocess.run([str(PYTHON),'-c',code],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr); self.assertIn('BLOCKED 1',run.stdout)
    def test_guard_blocks_write_outside_run(self):
        with tempfile.TemporaryDirectory() as td:
            code='import sys;sys.path.insert(0,'+repr(str(ROOT.parents[1]))+');from scripts.benchmark_curriculum.offline_guard import install,WriteBoundaryViolation; install('+repr(td)+');\ntry:\n open("/tmp/harness-should-not-write", "w")\nexcept WriteBoundaryViolation:\n print("BLOCKED")\nelse:\n raise RuntimeError("guard failed")'
            run=subprocess.run([str(PYTHON),'-c',code],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr); self.assertIn('BLOCKED',run.stdout)
    def test_timeout_retained(self):
        with tempfile.TemporaryDirectory() as td:
            status=bounded([str(PYTHON),'-c','import time;time.sleep(5)'],td,.05)
            self.assertTrue(status['timeout']); self.assertNotEqual(status['returncode'],0)
    def test_order_rotation_repeatable(self):
        rows=[{'document_id':x} for x in ('c','a','b')]
        self.assertEqual(make_order(rows),make_order(rows[::-1]))
        self.assertEqual([r['version'] for r in make_order(rows)[:6]],['B0','B2','B3','B2','B3','B0'])

if __name__=='__main__': unittest.main()
