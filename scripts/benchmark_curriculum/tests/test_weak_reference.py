import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from scripts.benchmark_curriculum.weak_reference import combine,evaluate,field_key,text_key,FIELDS

def annotation(who):
    return {'document_id':'SYNTH','document_sha256':'a'*64,'annotator_id':who,
            'reference_kind':'weak_reference_ai','overview_fields':{
                'proyecto':{'status':'present','value':'Árbol del barrio','page':1},
                'proposito':{'status':'absent','value':None,'page':None},
                'finalidad':{'status':'uncertain','value':None,'page':None},
                'campos_formativos':{'status':'not_applicable','values':[]}}}

class WeakReferenceTests(unittest.TestCase):
    def test_nfc_whitespace_casefold_only(self):
        self.assertEqual(text_key(' ÁRBOL\n del  barrio '),text_key('Árbol del barrio'))
        self.assertNotEqual(text_key('árbol.'),text_key('árbol'))
        self.assertNotEqual(text_key('arbol'),text_key('árbol'))
    def test_disagreement_becomes_unknown(self):
        a,b=annotation('A'),annotation('B'); b['overview_fields']['proyecto']['value']='Otro'
        ref=combine([a],[b])['documents'][0]
        self.assertEqual(ref['overview_fields']['proyecto']['status'],'unknown')
    def test_page_disagreement_becomes_unknown(self):
        a,b=annotation('A'),annotation('B'); b['overview_fields']['proyecto']['page']=2
        ref=combine([a],[b])['documents'][0]
        self.assertEqual(ref['overview_fields']['proyecto']['status'],'unknown')
    def test_empty_run_not_rewarded(self):
        ref=combine([annotation('A')],[annotation('B')])['documents'][0]
        out=evaluate({},ref,'a'*64,'timeout')
        self.assertEqual(out['counts']['A'],1); self.assertEqual(out['counts']['C'],0)
        self.assertIsNone(out['metrics']['selective_normalized_agreement']['value'])
        self.assertFalse(out['semantic_accuracy'])
    def test_pending_is_candidate_and_wrong_counts(self):
        ref=combine([annotation('A')],[annotation('B')])['documents'][0]
        raw={'dossier':{'general_fields':{'proyecto':{'value':'Otro','review':'pending','status':'ambiguous'},
                                        'proposito':{'value':'No respaldado','review':'pending'}}}}
        out=evaluate(raw,ref,'a'*64)
        self.assertEqual(out['counts']['W'],1); self.assertEqual(out['counts']['negative_with_candidate'],1)
        self.assertEqual(out['counts']['N_unknown'],1); self.assertEqual(out['counts']['N_not_applicable'],1)
    def test_sha_must_match(self):
        ref=combine([annotation('A')],[annotation('B')])['documents'][0]
        with self.assertRaises(ValueError): evaluate({},ref,'b'*64)
    def test_same_annotator_rejected(self):
        with self.assertRaises(ValueError): combine([annotation('A')],[annotation('A')])
    def test_reference_universes_must_match(self):
        with self.assertRaises(ValueError): combine([annotation('A')],[])
    def test_set_equality_no_vocabulary_repair(self):
        self.assertEqual(field_key('campos_formativos',['Lenguajes','Ética']),field_key('campos_formativos',['Ética','lenguajes']))
        self.assertNotEqual(field_key('campos_formativos',['Lenguaje']),field_key('campos_formativos',['Lenguajes']))

if __name__=='__main__': unittest.main()
