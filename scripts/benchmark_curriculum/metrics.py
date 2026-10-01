"""Independent strict M scorer. Imports no AulaLista module or segmenter.

The pypdf library/version is shared intentionally. Mechanical source truth is
read afresh from PDF bytes, not product pages, verifier decisions or regexes.
No semantic fidelity or occurrence correspondence is inferred here.
"""
from __future__ import annotations
import argparse
import io
import re
import resource
from collections import Counter
from pathlib import Path
from scripts.benchmark_curriculum.common import read_json, write_json, sha_bytes
from scripts.benchmark_curriculum.adapter import adapt


def rate(numerator,denominator,unit):
    if type(numerator) is not int or type(denominator) is not int or not 0<=numerator<=denominator:
        raise ValueError('Invalid rate counts')
    return {'numerator':numerator,'denominator':denominator,'unit':unit,
            'value':numerator/denominator if denominator else None,
            'display_status':'evaluated' if denominator else 'N/A',
            'reference_status':'independent_mechanical_text_only'}

def read_source(path, expected_sha=None, expected_page_count=None):
    from pypdf import PdfReader
    content=Path(path).read_bytes()
    sha=sha_bytes(content)
    if expected_sha is not None and sha!=expected_sha: raise ValueError('Frozen PDF bytes SHA mismatch')
    result={'document_sha256':sha,'bytes':len(content),'pages':[],'read_errors':[]}
    reader=PdfReader(io.BytesIO(content),strict=False)
    result['page_count']=len(reader.pages)
    if expected_page_count is not None and result['page_count']!=expected_page_count:
        raise ValueError('Frozen physical page count mismatch')
    for number,page in enumerate(reader.pages,1):
        try:
            text=page.extract_text() or ''
            error=None
        except Exception as exc:
            text=''
            error={'page_number':number,'type':type(exc).__name__,'message':str(exc)}
            result['read_errors'].append(error)
        result['pages'].append({'page_number':number,'text':text,'text_sha256':sha_bytes(text.encode('utf-8')),
                                'read_error':error})
    return result

def validate_citation(value,source):
    errors=[]
    if not isinstance(value,dict): return ['citation_not_object']
    sha=value.get('document_sha256')
    if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{64}',sha): errors.append('sha_type_or_format')
    if sha!=source['document_sha256']: errors.append('sha_mismatch')
    page=value.get('page_number')
    page_ok=type(page) is int and 1<=page<=len(source['pages'])
    if not page_ok: errors.append('page_type_or_range')
    quote=value.get('excerpt')
    if not isinstance(quote,str) or not quote.strip(): errors.append('excerpt_empty_or_type')
    elif page_ok:
        if source['pages'][page-1].get('read_error'):
            errors.append('source_text_unavailable')
        elif quote not in source['pages'][page-1]['text']:
            errors.append('excerpt_not_literal_on_page')
    if 'text_start' in value or 'text_end' in value:
        errors.extend(validate_offsets(value,source,page_ok))
    return errors

def validate_offsets(value,source,page_ok):
    start,end=value.get('text_start'),value.get('text_end')
    if type(start) is not int or type(end) is not int: return ['offset_type']
    if not page_ok: return []
    text=source['pages'][value['page_number']-1]['text']
    if not 0<=start<end<=len(text): return ['offset_range']
    return [] if value.get('excerpt')==text[start:end] else ['excerpt_offset_mismatch']

def validate_anchor(value,source):
    if not isinstance(value,dict): return ['anchor_not_object']
    errors=validate_citation(value,source)
    if type(value.get('schema_version')) is not int or value.get('schema_version')!=1:
        errors.append('schema_version_type_or_value')
    if type(value.get('occurrence')) is not int or value.get('occurrence',0)<1:
        errors.append('occurrence_type_or_value')
    if not isinstance(value.get('kind'),str) or not value['kind'].strip(): errors.append('kind_empty_or_type')
    if 'text_start' not in value or 'text_end' not in value: errors.append('offsets_missing')
    return errors

def score(raw,source,version,outcome='completed',document_id='unknown',family_id='unknown',split='unknown'):
    view=adapt(raw,version)
    citation_results=[]
    for citation in view['citations']:
        errors=validate_citation(citation['raw'],source)
        if citation.get('container_malformed'): errors.append('evidence_container_not_list')
        citation_results.append({**citation,'errors':errors,'valid':not errors})
    anchor_results=[{**a,'errors':validate_anchor(a['raw'],source)} for a in view['anchors']]
    for a in anchor_results: a['valid']=not a['errors']
    field_results=[]
    for f in view['fields']:
        citations=[c for c in citation_results if c['owner']==f['path']]
        audit=[a for a in view['audit_items'] if isinstance(a,dict) and isinstance(a.get('path'),str)
               and (a['path']==f['audit_path'] or a['path'].startswith(f['audit_path']+'/'))]
        strong_raw=f.get('status')=='supported'
        strong_audit=any(a.get('status')=='checked' for a in audit)
        field_results.append({**f,'citation_count':len(citations),
                              'has_valid_citation':any(c['valid'] for c in citations),
                              'all_citations_valid':bool(citations) and all(c['valid'] for c in citations),
                              'strong_raw':strong_raw,'strong_audit':strong_audit,
                              'strong':strong_raw or strong_audit})
    candidates=[f for f in field_results if f['candidate']]
    strong=[f for f in field_results if f['strong']]
    # Empty supported output is also mechanically unsupported, not quietly discarded.
    bad_strong=[f for f in strong if not f['candidate'] or not f['all_citations_valid']]
    units_valid=sum(any(a['valid'] and a['path']==u['path']+'/header_anchor' for a in anchor_results)
                    for u in view['units'])
    claim_results=[{**c,'errors':validate_citation(c['raw'],source)} for c in view['claim_citations']]
    for c in claim_results:
        if c.get('container_malformed'): c['errors'].append('evidence_container_not_list')
    raw_dossier=raw.get('dossier') if isinstance(raw,dict) else None
    identity_errors=[]
    if isinstance(raw_dossier,dict):
        if raw_dossier.get('source_sha256')!=source['document_sha256']: identity_errors.append('dossier_sha_mismatch')
        if type(raw_dossier.get('version')) is not int or raw_dossier.get('version',0)<1:
            identity_errors.append('dossier_version_type_or_value')
        if type(raw_dossier.get('page_count')) is not int or raw_dossier.get('page_count')!=source['page_count']:
            identity_errors.append('dossier_page_count_mismatch')
        for u in view['units']:
            if isinstance(u['raw'],dict):
                for key in ('pages','continues_on'):
                    values=u['raw'].get(key,[])
                    if not isinstance(values,list) or any(type(p) is not int or not 1<=p<=source['page_count'] for p in values):
                        identity_errors.append(u['path']+'/'+key+':invalid_page_list')
    invalid=bool(identity_errors or any(not c['valid'] for c in citation_results)
                 or any(not a['valid'] for a in anchor_results) or any(c['errors'] for c in claim_results))
    status_counts=lambda items,key:dict(Counter(str(i.get(key,'<missing>')) for i in items if isinstance(i,dict)))
    metrics={
        'M1':rate(int(outcome=='completed' and isinstance(raw_dossier,dict)),1,'PDFs'),
        'M2':rate(sum(bool(p['text'].strip()) for p in source['pages']),source['page_count'],'physical_pages'),
        'M3_citations':rate(sum(c['valid'] for c in citation_results),len(citation_results),'dossier_citations'),
        'M3_fields':rate(sum(f['has_valid_citation'] for f in candidates),len(candidates),'nonempty_interpreted_fields'),
        'M4':rate(sum(f['all_citations_valid'] for f in candidates),len(candidates),'nonempty_interpreted_fields'),
        'M5_anchors':rate(sum(a['valid'] for a in anchor_results),len(anchor_results),'anchors'),
        'M5_units':rate(units_valid,len(view['units']),'emitted_units'),
        'M6':rate(len(bad_strong),len(strong),'strong_interpreted_fields'),
        'M7':rate(int(invalid),1,'PDFs'),
    }
    counts={'fields_emitted':len(field_results),'candidate_fields':len(candidates),
            'abstaining_emitted_field_slots':sum(not f['candidate'] for f in field_results),
            'malformed_fields':sum(bool(f.get('malformed')) for f in field_results),
            'strong_fields':len(strong),'strong_raw_fields':sum(f['strong_raw'] for f in field_results),
            'strong_audit_fields':sum(f['strong_audit'] for f in field_results),
            'strong_invalid_fields':len(bad_strong),'citations_emitted':len(citation_results),
            'invalid_citations':sum(not c['valid'] for c in citation_results),'anchors_emitted':len(anchor_results),
            'units_emitted':len(view['units']),'unassigned_segments_emitted':len(view['unassigned_segments_emitted']),
            'scalar_content_emitted':len(view['scalar_content']),
            'nonempty_scalar_content':sum(nonempty_scalar(v['value']) for v in view['scalar_content']),
            'claims_emitted':len(view['claims']), 'claim_citations':len(claim_results),
            'claim_invalid_citations':sum(bool(c['errors']) for c in claim_results),
            'audit_items':len(view['audit_items']), 'audit_states':status_counts(view['audit_items'],'status'),
            'field_statuses':status_counts(field_results,'status'),'field_review_states':status_counts(field_results,'review'),
            'claim_states':status_counts(view['claims'],'state'),
            'adapter_errors':len(view['issues']),'source_read_errors':len(source.get('read_errors',[])),
            'no_dossier_output':int(not isinstance(raw_dossier,dict)),'execution_failure':int(outcome!='completed')}
    return {'schema_version':'1.0.0','document_id':document_id,'family_id':family_id,'split':split,'version':version,
            'outcome':outcome,'document_count':1,'family_count':1,'metrics':metrics,'M8':counts,
            'reference':{'human':'not_evaluable','weak_reference_ai':'not_evaluable',
                         'reason':'No frozen independent semantic reference scored by this harness'},
            'details':{'fields':field_results,'citations':citation_results,'anchors':anchor_results,
                       'claim_citations':claim_results,'identity_errors':identity_errors,'adapter_issues':view['issues']},
            'limits':['M2 measures independent pypdf text availability, not correct reading or comprehension',
                      'M3/M4 primary field universe is InterpretedField; scalar display content inventoried separately',
                      'No correctness of title, field value, segmentation, occurrence membership or curriculum inferred',
                      'Emitted field-slot abstention is not missing reference opportunities; missing denominator remains unknown',
                      'Unassigned spans count exact serialization markers, not independent detection of omissions']}

def nonempty_scalar(value):
    from scripts.benchmark_curriculum.adapter import nonempty
    return nonempty(value)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pdf',required=True); ap.add_argument('--sha',required=True)
    ap.add_argument('--pages',type=int,required=True); ap.add_argument('--out',required=True)
    ap.add_argument('--memory',type=int,required=True)
    args=ap.parse_args()
    out=Path(args.out).resolve()
    resource.setrlimit(resource.RLIMIT_AS,(args.memory,args.memory))
    from scripts.benchmark_curriculum.offline_guard import install
    install(out.parent)
    write_json(out,read_source(args.pdf,args.sha,args.pages))

if __name__=='__main__': main()
