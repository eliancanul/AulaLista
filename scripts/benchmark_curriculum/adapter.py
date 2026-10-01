"""Schema-only output projection, version 1.0.0. Never correct values or evidence.

Primary field universe: every member of general_fields and sessions[*].fields
(the product's InterpretedField records). Scalar display strings are inventoried
separately and not silently treated as supported InterpretedFields. Claims are a
separate output view, not added to dossier citation denominators.
"""
from collections import Counter

SUPPORTED_VERSIONS = ('B0','B2','B3')
EXCLUDED_DOSSIER_TREES = {'history','verification_report','original_value'}

def nonempty(value):
    if value is None: return False
    if isinstance(value,str): return bool(value.strip())
    if isinstance(value,(list,dict)): return bool(value)
    return True

def adapt(raw, version):
    if version not in SUPPORTED_VERSIONS: raise ValueError('Unsupported frozen version')
    result={'schema_version':'1.0.0','version':version,'fields':[], 'citations':[], 'anchors':[],
            'units':[], 'scalar_content':[], 'issues':[], 'unassigned_segments_emitted':[],
            'audit_items':[], 'claims':[], 'claim_citations':[]}
    if not isinstance(raw,dict):
        result['issues'].append({'path':'/','error':'malformed_raw_root'})
        return result
    dossier=raw.get('dossier')
    if not isinstance(dossier,dict):
        result['issues'].append({'path':'/dossier','error':'missing_or_malformed_dossier'})
        return result
    def evidence_list(value,path,owner=None,target='citations'):
        if isinstance(value,list):
            for i,ev in enumerate(value):
                result[target].append({'path':f'{path}/{i}','owner':owner,'raw':ev})
        else:
            result[target].append({'path':path,'owner':owner,'raw':value,'container_malformed':True})
            result['issues'].append({'path':path,'error':'evidence_not_list'})
    def add_fields(fields,path,audit_path):
        if not isinstance(fields,dict):
            result['issues'].append({'path':path,'error':'fields_not_object'})
            return
        for name,field in fields.items():
            fpath=f'{path}/{name}'
            record={'path':fpath,'audit_path':f'{audit_path}/{name}','name':name,'raw':field}
            if isinstance(field,dict):
                record.update(value=field.get('value'),status=field.get('status'),review=field.get('review'),
                              origin=field.get('origin'),candidate=nonempty(field.get('value')))
            else:
                record.update(value=None,status=None,review=None,origin=None,candidate=False,malformed=True)
                result['issues'].append({'path':fpath,'error':'field_not_object'})
            result['fields'].append(record)
    add_fields(dossier.get('general_fields'),'/dossier/general_fields','general_fields')
    sessions=dossier.get('sessions')
    if not isinstance(sessions,list):
        result['issues'].append({'path':'/dossier/sessions','error':'sessions_not_list'})
        sessions=[]
    for i,unit in enumerate(sessions):
        path=f'/dossier/sessions/{i}'
        result['units'].append({'path':path,'raw':unit})
        if not isinstance(unit,dict):
            result['issues'].append({'path':path,'error':'unit_not_object'})
            continue
        sid=unit.get('session_id')
        add_fields(unit.get('fields'),path+'/fields',f'sessions/{sid}/fields')
        for key in ('title','project_title','day_of_week'):
            if key in unit:
                result['scalar_content'].append({'path':path+'/'+key,'value':unit[key]})
        ctx=unit.get('project_context')
        if isinstance(ctx,dict) and 'title' in ctx:
            result['scalar_content'].append({'path':path+'/project_context/title','value':ctx['title']})
        for j,activity in enumerate(unit.get('activities',[]) if isinstance(unit.get('activities'),list) else []):
            if isinstance(activity,dict):
                for key in ('title','description'):
                    if key in activity:
                        result['scalar_content'].append({'path':f'{path}/activities/{j}/{key}','value':activity[key]})
        # This is a serialization marker emitted by the product, not re-segmentation.
        notes=unit.get('layout_notes')
        if isinstance(notes,str):
            marker='Tramo sin asignar, página física '
            for j,part in enumerate(notes.split(marker)[1:]):
                result['unassigned_segments_emitted'].append({'unit_path':path,'index':j,'raw':part})
    fields_by_path={f['path']:f for f in result['fields']}
    def visit(value,path):
        if isinstance(value,dict):
            for key,child in value.items():
                cpath=path+'/'+key
                if key in EXCLUDED_DOSSIER_TREES: continue
                if key=='evidence':
                    evidence_list(child,cpath,path if path in fields_by_path else None)
                elif key=='annex_evidence':
                    if isinstance(child,dict):
                        for name,evidence in child.items(): evidence_list(evidence,cpath+'/'+name)
                    else:
                        evidence_list(child,cpath)
                elif key in ('header_anchor','anchor'):
                    if child is not None: result['anchors'].append({'path':cpath,'raw':child})
                else: visit(child,cpath)
        elif isinstance(value,list):
            for i,child in enumerate(value): visit(child,f'{path}/{i}')
    visit(dossier,'/dossier')
    verification=raw.get('verification',dossier.get('verification_report'))
    if isinstance(verification,dict) and isinstance(verification.get('items'),list):
        result['audit_items']=verification['items']
    elif verification is not None:
        result['issues'].append({'path':'/verification','error':'malformed_verification'})
    claims=raw.get('claims')
    if isinstance(claims,list):
        result['claims']=claims
        for i,claim in enumerate(claims):
            if not isinstance(claim,dict):
                result['issues'].append({'path':f'/claims/{i}','error':'malformed_claim'})
                continue
            if 'evidence' in claim:
                evidence_list(claim['evidence'],f'/claims/{i}/evidence',target='claim_citations')
            # Legacy projection only when the evidence key is absent. No coercion.
            elif any(k in claim for k in ('source_doc_sha256','page_number','excerpt')):
                result['claim_citations'].append({'path':f'/claims/{i}/legacy','raw':{
                    'document_sha256':claim.get('source_doc_sha256'),'page_number':claim.get('page_number'),
                    'excerpt':claim.get('excerpt')},'legacy_projection':True})
    return result
