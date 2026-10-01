"""Optional frozen AI-reference agreement, NOT human or semantic accuracy.

Universe: one document-level overview slot per proyecto/proposito/finalidad/
campos_formativos, first three physical pages. No session/occurrence matching.
Reference must be built before output inspection; disagreements become unknown.
"""
from __future__ import annotations
import argparse
import unicodedata
from collections import Counter
from scripts.benchmark_curriculum.common import read_json, write_json, sha_file
from scripts.benchmark_curriculum.adapter import nonempty
from scripts.benchmark_curriculum.metrics import rate
FIELDS=('proyecto','proposito','finalidad','campos_formativos')
STATUSES=('present','absent','uncertain','not_applicable')
NORMALIZATION='Unicode NFC; split/join whitespace; casefold, in that order; no punctuation, accents, synonyms or source repair'

def text_key(value):
    if not isinstance(value,str): return None
    return ' '.join(unicodedata.normalize('NFC',value).split()).casefold()

def field_key(field,value):
    if field=='campos_formativos':
        if not isinstance(value,list) or any(not isinstance(v,str) or not v.strip() for v in value): return None
        return sorted(set(text_key(v) for v in value))
    return text_key(value)

def combine(annotations_a,annotations_b):
    # This function accepts annotation records only, never product output.
    if not isinstance(annotations_a,list) or not isinstance(annotations_b,list):
        raise ValueError('Annotation inputs must be lists of document records')
    if len({r['document_id'] for r in annotations_a})!=len(annotations_a) or len({r['document_id'] for r in annotations_b})!=len(annotations_b):
        raise ValueError('Duplicate annotation document')
    aa={r['document_id']:r for r in annotations_a}; bb={r['document_id']:r for r in annotations_b}
    if aa.keys()!=bb.keys(): raise ValueError('Annotator universes differ')
    result=[]
    for did in sorted(aa):
        a,b=aa[did],bb[did]
        if a.get('reference_kind')!='weak_reference_ai' or b.get('reference_kind')!='weak_reference_ai':
            raise ValueError('Only explicitly labelled AI references supported')
        if a.get('document_sha256')!=b.get('document_sha256'): raise ValueError('Reference source SHA mismatch')
        if a.get('annotator_id')==b.get('annotator_id'): raise ValueError('Two distinct annotator IDs required')
        fields={}
        for name in FIELDS:
            av=a.get('overview_fields',{}).get(name,{})
            bv=b.get('overview_fields',{}).get(name,{})
            ast,bst=av.get('status'),bv.get('status')
            key='values' if name=='campos_formativos' else 'value'
            ak,bk=field_key(name,av.get(key)),field_key(name,bv.get(key))
            agree=ast==bst and ast in STATUSES
            reasons=[]
            if not agree: reasons.append('status_disagreement_or_missing')
            if ast=='uncertain' or bst=='uncertain': reasons.append('annotator_uncertain')
            if agree and ast=='present' and (ak is None or bk is None or not ak or ak!=bk):
                reasons.append('value_disagreement_or_missing')
            if agree and ast in ('absent','not_applicable') and (nonempty(av.get(key)) or nonempty(bv.get(key))):
                reasons.append('nonempty_value_for_nonpresent_reference')
            # Page identity is conservative for singleton overview strings.
            if agree and ast=='present' and name!='campos_formativos':
                ap,bp=av.get('page'),bv.get('page')
                if type(ap) is not int or type(bp) is not int or ap!=bp or not 1<=ap<=3:
                    reasons.append('overview_page_disagreement_or_outside_panel')
            if agree and ast=='present' and name=='campos_formativos':
                for annotation in (av,bv):
                    evidence=annotation.get('evidence')
                    if not isinstance(evidence,list) or not evidence:
                        reasons.append('formative_fields_evidence_missing')
                        continue
                    for item in evidence:
                        page=item.get('page') if isinstance(item,dict) else item[0] if isinstance(item,list) and item else None
                        if type(page) is not int or not 1<=page<=3:
                            reasons.append('formative_fields_evidence_outside_overview_or_malformed')
            fields[name]={'status':'unknown' if reasons else ast,'comparison_key':ak if not reasons and ast=='present' else None,
                          'value':av.get(key) if not reasons and ast=='present' else None,
                          'reasons':reasons,'annotator_statuses':[ast,bst],
                          'page':av.get('page') if name!='campos_formativos' else None}
        result.append({'document_id':did,'document_sha256':a['document_sha256'],
                       'reference_kind':'weak_reference_ai','overview_fields':fields})
    return {'schema_version':'weak-reference-ai-agreement-v1','reference_kind':'weak_reference_ai',
            'normalization':NORMALIZATION,'semantic_accuracy':False,'human_reference':False,
            'reference_policy':'Two blinded AI annotations; disagreements become unknown, no adjudicated human truth',
            'scope':'Four document overview slots on first three physical pages; interior panel and units not scored',
            'documents':result}

def evaluate(raw,reference,source_sha,outcome='completed'):
    if reference.get('reference_kind')!='weak_reference_ai' or reference.get('document_sha256')!=source_sha:
        raise ValueError('Wrong reference kind or document SHA')
    counts=Counter(C=0,W=0,A=0,N_pos=0,N_neg=0,N_unknown=0,N_not_applicable=0,
                   candidates_evaluable=0,negative_with_candidate=0,unknown_with_candidate=0,
                   outside_applicability_with_candidate=0)
    details=[]
    dossier=raw.get('dossier',{}) if isinstance(raw,dict) else {}
    emitted=dossier.get('general_fields',{}) if isinstance(dossier,dict) else {}
    if not isinstance(emitted,dict): emitted={}
    for name in FIELDS:
        ref=reference['overview_fields'].get(name,{'status':'unknown'})
        rawfield=emitted.get(name,{})
        value=rawfield.get('value') if isinstance(rawfield,dict) else None
        candidate=outcome=='completed' and nonempty(value)
        status=ref.get('status','unknown'); result='unknown'
        if status=='present':
            counts['N_pos']+=1
            if not candidate: result='A'; counts['A']+=1
            else:
                counts['candidates_evaluable']+=1
                result='C' if field_key(name,value)==ref.get('comparison_key') else 'W'
                counts[result]+=1
        elif status=='absent':
            counts['N_neg']+=1; result='negative_with_candidate' if candidate else 'negative_abstention'
            counts['negative_with_candidate']+=int(candidate); counts['candidates_evaluable']+=int(candidate)
        elif status=='not_applicable':
            counts['N_not_applicable']+=1; counts['outside_applicability_with_candidate']+=int(candidate)
            result='not_applicable'
        else:
            counts['N_unknown']+=1; counts['unknown_with_candidate']+=int(candidate)
        details.append({'field':name,'reference_status':status,'candidate':candidate,'value':value,'result':result,
                        'raw_status':rawfield.get('status') if isinstance(rawfield,dict) else None})
    assert counts['C']+counts['W']+counts['A']==counts['N_pos']
    metrics={
        'reference_evaluable_coverage':rate(counts['N_pos']+counts['N_neg'],len(FIELDS),'inventoried_AI_overview_slots'),
        'reference_resolved_coverage':rate(counts['N_pos']+counts['N_neg']+counts['N_not_applicable'],len(FIELDS),'inventoried_AI_overview_slots'),
        'response_coverage':rate(counts['C']+counts['W'],counts['N_pos'],'positive_AI_overview_slots'),
        'normalized_agreement_recovery':rate(counts['C'],counts['N_pos'],'positive_AI_overview_slots'),
        'normalized_disagreement':rate(counts['W'],counts['N_pos'],'positive_AI_overview_slots'),
        'abstention_on_AI_present':rate(counts['A'],counts['N_pos'],'positive_AI_overview_slots'),
        'selective_normalized_agreement':rate(counts['C'],counts['C']+counts['W'],'attempted_positive_AI_overview_slots'),
        'candidate_normalized_agreement':rate(counts['C'],counts['candidates_evaluable'],'evaluable_AI_overview_candidates'),
        'emission_on_AI_absent':rate(counts['negative_with_candidate'],counts['N_neg'],'negative_AI_overview_slots'),
    }
    for metric in metrics.values(): metric['reference_status']='weak_reference_ai_not_human'
    return {'document_id':reference['document_id'],'document_sha256':source_sha,'reference_kind':'weak_reference_ai',
            'normalization':NORMALIZATION,'semantic_accuracy':False,'counts':dict(counts),'metrics':metrics,'details':details,
            'unscored':['interior_panel','session_or_project_occurrence','segmentation','physical_relations','semantic_equivalence'],
            'failed_run_policy':'Noncompleted end-to-end run counts A for positive AI-reference slots; partial raw output retained separately'}
