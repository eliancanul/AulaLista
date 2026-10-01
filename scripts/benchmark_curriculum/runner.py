"""Portable reproducible runner. New corpus requires an externally closed freeze."""
from __future__ import annotations
import argparse
import datetime as dt
import os
import signal
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from scripts.benchmark_curriculum.common import *
from scripts.benchmark_curriculum.metrics import score, rate


def iso(): return dt.datetime.now(dt.timezone.utc).isoformat()

def bounded(command,out,timeout,python=PYTHON):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    started=iso(); start=time.monotonic()
    with (out/'stdout.log').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
        proc=subprocess.Popen(command,cwd=out,env=child_env(out,python),stdout=stdout,stderr=stderr,start_new_session=True)
        timed_out=False
        try: code=proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True; os.killpg(proc.pid,signal.SIGKILL); code=proc.wait()
    return {'started_at_utc':started,'finished_at_utc':iso(),'wall_seconds':time.monotonic()-start,
            'returncode':code,'timeout':timed_out}

def verify_snapshots(runtime):
    index=read_json(runtime.snapshots/'index.json')
    for version,commit in COMMITS.items():
        record=read_json(runtime.snapshots/f'{version}.manifest.json')
        if record['commit']!=commit or index[version]['commit']!=commit:
            raise ValueError('Snapshot commit differs from preregistered comparison')
        if sha_bytes(canonical_bytes(record['files']))!=index[version]['file_manifest_sha256']:
            raise ValueError('Snapshot file manifest differs from index')
        if tree_manifest(runtime.snapshots/version)!=record['files']:
            raise ValueError(f'Snapshot bytes changed: {version}')
        if sha_file(runtime.snapshots/version/'requirements.lock')!=sha_file(runtime.private_path('requirements.lock')):
            raise ValueError('Dependency lock drift')

def validate_rows(rows,config,runtime,preflight=False):
    if not isinstance(rows,list): raise ValueError("Corpus must be a list of document records")
    seen=set(); totals=0
    for row in rows:
        if not isinstance(row,dict): raise ValueError('Malformed corpus row')
        did=row.get('document_id')
        if not isinstance(did,str) or not did or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in did):
            raise ValueError('Unsafe or missing document_id')
        if did in seen: raise ValueError('Duplicate document_id')
        seen.add(did)
        if type(row.get('page_count')) is not int or not (1 if preflight else 2)<=row['page_count']<=config['max_pages_per_pdf']:
            raise ValueError('Physical page count outside frozen limits')
        reject_quarantine(row['path'])
        if not Path(row['path']).is_absolute():
            raise ValueError('Input path must be absolute; use relative_private_path in a frozen manifest')
        path=runtime.private_path(row['path'])
        if not preflight and row.get('selection_status')!='included':
            raise ValueError('Only explicitly included sources may run')
        if type(row.get('bytes')) is not int or row['bytes'] < 0:
            raise ValueError('Invalid input byte count')
        if not path.is_file() or path.stat().st_size!=row['bytes'] or sha_file(path)!=row['file_sha256']:
            raise ValueError(f'Input bytes mismatch for {did}')
        if row['bytes']>config['max_input_bytes']: raise ValueError('PDF byte limit exceeded')
        totals+=row['page_count']
        if not preflight:
            if row.get('rights',{}).get('status')!='approved' or not row.get('rights',{}).get('private_processing_basis'):
                raise ValueError('Rights approval or processing basis absent')
            if row.get('pii',{}).get('status')!='no_detected': raise ValueError('PII screening not cleared')
            if not row.get('family_id') or row.get('split') not in ('D','H','R','T','X','feasibility_prospective'):
                raise ValueError('Family/split not frozen')
    if len(rows)>config['max_documents'] or totals>config['max_total_pages']:
        raise ValueError('Corpus budget exceeded')
    if not rows: raise ValueError('Empty corpus')

def make_order(rows):
    result=[]; versions=list(COMMITS)
    for i,row in enumerate(sorted(rows,key=lambda r:r['document_id'])):
        for version in versions[i%3:]+versions[:i%3]:
            result.append({'document_id':row['document_id'],'version':version})
    return result

def validate_config(config):
    for key in ('timeout_seconds_per_document','source_reader_timeout_seconds','memory_limit_bytes','source_reader_memory_limit_bytes',
                'max_input_bytes','max_pages_per_pdf','max_total_pages','max_documents'):
        if type(config.get(key)) is not int or config[key]<=0: raise ValueError(f'Invalid {key}')
    if type(config.get('repetitions')) is not int or type(config.get('parallel_workers')) is not int or config.get('repetitions')!=2 or config.get('parallel_workers')!=1:
        raise ValueError('Frozen runner requires two serial full repetitions')
    if config.get('volatile_paths')!=VOLATILE_PATHS or config.get('selection') is not None or config.get('job') is not None:
        raise ValueError('Unapproved canonicalization/selection config')
    if config.get('generation') is not False or config.get('infrastructure_retries')!=0:
        raise ValueError('Generation/retries forbidden')

def load_freeze(path,runtime):
    path=runtime.private_path(path)
    freeze=read_json(path)
    if freeze.get('ready_to_run') is not True or freeze.get('rights_pii_gate_passed') is not True:
        raise ValueError('Freeze not ready or rights/PII gate incomplete')
    if freeze.get('harness_version')!=HARNESS_VERSION:
        raise ValueError('Freeze does not identify this portable harness release')
    if freeze.get('source_commits')!=COMMITS or freeze.get('new_corpus_product_tuning_permitted') is not False:
        raise ValueError('Frozen code/tuning constraint differs')
    if freeze.get('phase') not in ('M_only','M_plus_weak_reference_ai'):
        raise ValueError('Supported phases: M_only or M_plus_weak_reference_ai; never H accuracy')
    for field in ('freeze_timestamp_utc','responsible_custodian','prior_output_exposure','historical_novelty_limitation'):
        if not freeze.get(field): raise ValueError(f'Unresolved freeze field: {field}')
    required=('snapshot_index','protocol','candidate_registry','corpus_manifest','family_mapping','split','exposure_ledger','panel',
              'scorer','output_adapter','mutation_pool','environment_manifest','run_configuration','run_order',
              'task_applicability','harness_code_manifest')
    if freeze.get('phase')=='M_plus_weak_reference_ai':
        required += ('weak_reference_ai','annotation_spec')
        if freeze.get('weak_reference_ai_outputs_seen_before_freeze') is not False:
            raise ValueError('Weak reference must be frozen before product outputs')
    artifacts=freeze.get('artifacts',{})
    paths={}
    for key in required:
        item=artifacts.get(key)
        if not isinstance(item,dict): raise ValueError(f'Missing frozen artifact: {key}')
        if not isinstance(item.get('path'),str) or not item['path']:
            raise ValueError(f'Missing frozen artifact path: {key}')
        artifact=Path(path).resolve().parent/item['path']
        reject_quarantine(artifact)
        artifact=artifact.resolve()
        code_artifacts={'scorer':ROOT/'metrics.py','output_adapter':ROOT/'adapter.py','mutation_pool':ROOT/'mutation_pool.json'}
        if key in code_artifacts and artifact!=code_artifacts[key]:
            raise ValueError(f'Unexpected harness artifact path: {key}')
        if key not in (*code_artifacts, 'protocol', 'run_configuration'):
            runtime.private_path(artifact)
        if sha_file(artifact)!=item.get('sha256'): raise ValueError(f'Frozen artifact hash mismatch: {key}')
        legacy_key=key+'_sha256'
        if legacy_key in freeze and freeze[legacy_key]!=item['sha256']:
            raise ValueError(f'Conflicting freeze hash: {key}')
        paths[key]=artifact
    manifest=read_json(paths['harness_code_manifest'])
    for relative,digest in manifest.items():
        file=(ROOT/relative).resolve()
        if ROOT not in file.parents or sha_file(file)!=digest: raise ValueError('Harness source drift')
    expected_code_files=set(read_json(ROOT/'code_files.json'))
    if set(manifest)!=expected_code_files:
        raise ValueError('Frozen code manifest does not cover the complete declared harness')
    if paths['snapshot_index'] != runtime.snapshots/'index.json':
        raise ValueError('Unexpected snapshot index path')
    from scripts.benchmark_curriculum.setup_snapshots import environment_manifest
    actual=environment_manifest(runtime); frozen=read_json(paths['environment_manifest'])
    if actual!=frozen: raise ValueError('Python or installed environment drift')
    config=read_json(paths['run_configuration']); validate_config(config)
    if freeze.get('timeout_seconds_per_document')!=config['timeout_seconds_per_document'] or freeze.get('memory_limit_bytes')!=config['memory_limit_bytes']:
        raise ValueError('Freeze resource settings conflict')
    rows=read_json(paths['corpus_manifest'])
    if isinstance(rows,dict): rows=rows['documents']
    for row in rows:
        if 'path' not in row:
            row['path']=str((paths['corpus_manifest'].parent/row['relative_private_path']).resolve())
    validate_rows(rows,config,runtime)
    order=read_json(paths['run_order'])
    if order!=make_order(rows): raise ValueError('Run order differs from deterministic plan')
    weak = read_json(paths['weak_reference_ai']) if 'weak_reference_ai' in paths else None
    if weak is not None:
        if not isinstance(weak,dict): raise ValueError('Malformed weak reference')
        if weak.get('reference_kind')!='weak_reference_ai' or weak.get('semantic_accuracy') is not False:
            raise ValueError('Weak reference incorrectly labeled')
        documents=weak.get('documents')
        if not isinstance(documents,list) or any(not isinstance(r,dict) for r in documents):
            raise ValueError('Malformed weak reference universe')
        ref_ids={r['document_id']:r.get('document_sha256') for r in documents}
        if len(ref_ids)!=len(documents): raise ValueError('Duplicate weak reference document')
        if ref_ids != {r['document_id']:r['file_sha256'] for r in rows}:
            raise ValueError('Weak reference and corpus universes differ')
    return freeze,config,rows,order,weak

def aggregate(scores):
    by_group=defaultdict(list)
    for row in scores: by_group[(row['split'],row['version'])].append(row)
    result=[]
    for (split,version),rows in sorted(by_group.items()):
        item={'split':split,'version':version,'document_count':len(rows),
              'family_count':len({r['family_id'] for r in rows}), 'metrics':{},
              'documents_failed':sum(r['outcome']!='completed' for r in rows),
              'documents_no_output':sum(r['M8']['no_dossier_output'] for r in rows)}
        for key in rows[0]['metrics']:
            parts=[r['metrics'][key] for r in rows]
            families=defaultdict(list)
            for row in rows: families[row['family_id']].append(row['metrics'][key])
            fvalues=[]
            for values in families.values():
                n=sum(x['numerator'] for x in values); d=sum(x['denominator'] for x in values)
                if d: fvalues.append(n/d)
            values=[p['value'] for p in parts if p['value'] is not None]
            item['metrics'][key]={'micro':rate(sum(p['numerator'] for p in parts),sum(p['denominator'] for p in parts),parts[0]['unit']),
                                 'macro_document':sum(values)/len(values) if values else None,'macro_document_evaluable_n':len(values),
                                 'macro_family':sum(fvalues)/len(fvalues) if fvalues else None,'macro_family_evaluable_n':len(fvalues)}
        result.append(item)
    return result

def paired_differences(scores):
    lookup={(r['document_id'],r['version']):r for r in scores}; results=[]
    for did in sorted({r['document_id'] for r in scores}):
        for before,after in (('B0','B3'),('B2','B3')):
            a,b=lookup[(did,before)],lookup[(did,after)]
            differences={}
            for metric in a['metrics']:
                av,bv=a['metrics'][metric],b['metrics'][metric]
                defined=av['value'] is not None and bv['value'] is not None
                fixed=metric in ('M1','M2','M7') and av['denominator']==bv['denominator']
                differences[metric]={'before':av,'after':bv,
                    'delta_percentage_points':100*(bv['value']-av['value']) if defined else None,
                    'identical_denominator':av['denominator']==bv['denominator'],
                    'denominator_independent_of_output':fixed,
                    'interpretation':'fixed source denominator' if fixed else 'conditional emitted-output denominator; inspect coverage and abstention'}
            results.append({'document_id':did,'split':a['split'],'family_id':a['family_id'],
                            'comparison':before+'->'+after,'outcomes':[a['outcome'],b['outcome']],
                            'metrics':differences,'counts_before':a['M8'],'counts_after':b['M8'],
                            'semantic_transitions':'not_evaluable_without_independent_reference'})
    return results

def execute(config,rows,order,out,mode,runtime,freeze=None,weak=None):
    require_selected_python(runtime)
    out=runtime.private_path(out)
    if out.exists(): raise ValueError('Refusing to overwrite prior run; use a new run directory')
    verify_snapshots(runtime); validate_config(config); validate_rows(rows,config,runtime,preflight=mode=='preflight')
    if order!=make_order(rows): raise ValueError('Run order differs from deterministic plan')
    out.mkdir(parents=True)
    write_json(out/'run_configuration.json',config); write_json(out/'input_manifest.json',rows)
    write_json(out/'run_order.json',order)
    if freeze: write_json(out/'freeze_record.json',freeze)
    if weak: write_json(out/'weak_reference_ai.json',weak)
    receipt={'started_at_utc':iso(),'mode':mode,'run_configuration_sha256':sha_file(out/'run_configuration.json'),
             'run_order_sha256':sha_file(out/'run_order.json'),'input_manifest_sha256':sha_file(out/'input_manifest.json'),
             'ready_to_run_new_corpus':bool(freeze),'status':'running'}
    write_json(out/'run_receipt.json',receipt)
    sources={}
    # Independent reading occurs outside and before product subprocesses.
    for row in rows:
        dest=out/'sources'/row['document_id']; dest.mkdir(parents=True)
        status=bounded(runtime.command('source','--pdf',row['path'],'--sha',row['file_sha256'],
                        '--pages',str(row['page_count']),'--out',str(dest/'source.json'),
                        '--memory',str(config['source_reader_memory_limit_bytes'])),dest,config['source_reader_timeout_seconds'],runtime.python)
        write_json(dest/'status.json',status)
        if status['returncode']!=0 or not (dest/'source.json').exists():
            receipt.update(status='source_reader_failure_before_product_execution',finished_at_utc=iso())
            write_json(out/'run_receipt.json',receipt)
            raise RuntimeError('Independent source reader failed; run stopped, no selective source exclusion')
        sources[row['document_id']]=read_json(dest/'source.json')
    rows_by_id={r['document_id']:r for r in rows}; repetitions=[]; hashes={}; statuses=[]
    for repetition in (1,2):
        scores=[]; weak_scores=[]
        for position,item in enumerate(order):
            did,version=item['document_id'],item['version']; row=rows_by_id[did]
            dest=out/f'repeat_{repetition}'/did/version; dest.mkdir(parents=True)
            status=bounded(runtime.command('worker','--snapshot',str(runtime.snapshots/version),
                            '--pdf',row['path'],'--expected-sha',row['file_sha256'],'--out',str(dest),
                            '--timeout',str(config['timeout_seconds_per_document']),
                            '--memory',str(config['memory_limit_bytes'])),dest,config['timeout_seconds_per_document'],runtime.python)
            ws=read_json(dest/'worker_status.json') if (dest/'worker_status.json').exists() else {}
            outcome='timeout' if status['timeout'] else ws.get('status','worker_crash')
            if status['returncode']!=0 and outcome=='completed':
                outcome='worker_crash'
            status.update(outcome=outcome,document_id=did,version=version,repetition=repetition,position=position,
                          worker=ws,source_sha256=row['file_sha256'])
            write_json(dest/'run_status.json',status); statuses.append(status)
            try:
                raw=read_json(dest/'raw.json') if (dest/'raw.json').exists() else {}
                if not isinstance(raw,dict):
                    raise ValueError('Raw output root must be an object')
            except (ValueError, UnicodeError) as exc:
                # Retain malformed bytes and a failed document in every denominator.
                raw={}
                status['output_error']={'type':type(exc).__name__,'message':str(exc)}
                if outcome not in ('offline_violation','write_boundary_violation','timeout'):
                    outcome='malformed_output'
                    status['outcome']=outcome
                write_json(dest/'run_status.json',status)
            canonical=canonical_output(raw)
            write_json(dest/'canonical.json',canonical)
            digest=sha_file(dest/'canonical.json'); hashes[(repetition,did,version)]=digest
            write_json(dest/'output_hashes.json',{'raw_sha256':sha_file(dest/'raw.json') if (dest/'raw.json').exists() else None,
                                                'canonical_sha256':digest,'volatile_paths':VOLATILE_PATHS})
            scored=score(raw,sources[did],version,outcome,did,row['family_id'],row['split'])
            write_json(dest/'metrics.json',scored); scores.append(scored)
            if weak:
                from scripts.benchmark_curriculum.weak_reference import evaluate
                reference=next(r for r in weak['documents'] if r['document_id']==did)
                w=evaluate(raw,reference,row['file_sha256'],outcome)
                w.update(version=version,split=row['split'],family_id=row['family_id'])
                write_json(dest/'weak_agreement.json',w); weak_scores.append(w)
            if outcome in ('offline_violation','write_boundary_violation'):
                receipt.update(status='aborted_forbidden_operation',finished_at_utc=iso())
                write_json(out/'run_receipt.json',receipt)
                raise RuntimeError('Forbidden operation: entire run aborted, logs retained')
        write_json(out/f'scores_repeat_{repetition}.json',scores)
        write_json(out/f'aggregates_repeat_{repetition}.json',aggregate(scores))
        write_json(out/f'paired_differences_repeat_{repetition}.json',paired_differences(scores))
        if weak: write_json(out/f'weak_agreement_repeat_{repetition}.json',weak_scores)
        repetitions.append(scores)
    checks=[]
    for item in order:
        did,version=item['document_id'],item['version']
        both=[s for s in statuses if s['document_id']==did and s['version']==version]
        checks.append({**item,'canonical_hashes':[hashes[(r,did,version)] for r in (1,2)],
                       'hashes_equal':hashes[(1,did,version)]==hashes[(2,did,version)],
                       'both_completed':all(s['outcome']=='completed' for s in both)})
    write_json(out/'reproducibility.json',{'volatile_paths':VOLATILE_PATHS,'checks':checks,
                                         'reproducibility_established':all(c['hashes_equal'] and c['both_completed'] for c in checks)})
    receipt.update(status='completed',finished_at_utc=iso(),product_runs=len(statuses),
                   successful_runs=sum(s['outcome']=='completed' for s in statuses))
    write_json(out/'run_receipt.json',receipt)
    write_json(out/'resource_summary.json',{'max_wall_seconds':max(s['wall_seconds'] for s in statuses),
                                           'max_rss_bytes':max(s.get('worker',{}).get('maxrss_bytes',0) for s in statuses),
                                           'statuses':statuses})
    verify_snapshots(runtime)
    return receipt
