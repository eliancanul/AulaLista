"""Offline contract probe. Authored controls are not interpreter/provider results."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.sprint_eval.corpus import load_corpus, prepare_segment_bridge
from scripts.sprint_eval.rubric import evaluate


def read_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def dependencies(s02, s06):
    return (read_module(s02 / 'curriculum/source_segments.py', 's01_probe_s02'),
            read_module(s06 / 'curriculum/interpretation_schema.py', 's01_probe_s06'))


def control(case, sources, mapping, schema):
    """Complete schema envelope for expected fields, explicitly an authored control."""
    expected = {f['key']: f for f in case['expected_fields']}
    fields = []
    for key in schema.FIELD_QUESTIONS:
        field = copy.deepcopy(expected.get(key, dict(
            key=key, value=None, status='unknown', evidence_ids=[])))
        field['evidence_ids'] = [target for source in field['evidence_ids'] for target in mapping[source]]
        field['reason'] = 'Control sintético de contrato; no es salida del intérprete.'
        fields.append(field)
    return dict(schema_version=1, document_id=case['document_id'], source_segments=sources,
                fields=fields, missing_questions=[schema.FIELD_QUESTIONS[f['key']]
                for f in fields if f['status'] == 'unknown'],
                draft=dict(title=schema.initial_title(next(f for f in fields if f['key'] == 'proyecto')), objective='', materials=[], steps=[], assessment='',
                           source_ids=[], revision=1, approval_status='pending',
                           status=schema.INSUFFICIENT_SOURCE),
                diagnostics=dict(method='local_source_interpreter', provider_status='not_requested',
                                 attempts=0, errors=[], model_winner=None,
                                 source_page_count=max(s['page'] for s in sources), source_warnings=[]))


def verdict(payload, schema):
    try:
        schema.validate_interpretation(payload, expected_document_id=payload['document_id'],
                                       source_segments=payload['source_segments'])
    except schema.InterpretationSchemaError as exc:
        return {'status': 'ISSUES', 'error': str(exc)}
    return {'status': 'PASS'}


def check_case(case, extractor, schema):
    segments = [line for page in case['source_segments'] for line in
                extractor.extracted_page_segments(page['text'], case['document_id'], page['page'])]
    bridge = prepare_segment_bridge(case, segments)
    projected = [{k: s[k] for k in ('id', 'text', 'page')} for s in segments]
    fine_map = {s['id']: [r['s02_id'] for r in bridge['provenance']['mapping']
                          if r['frozen_id'] == s['id']] for s in case['source_segments']}
    fine = control(case, projected, fine_map, schema)
    raw = copy.deepcopy(fine)
    raw['source_segments'] = segments
    page_control = control(case, bridge['model_input']['source_segments'],
                           {s['id']: [s['id']] for s in case['source_segments']}, schema)
    unsupported = [f['key'] for f in fine['fields'] if f['status'] == 'extracted'
                   and not schema.literal_supported(f['value'],
                       [s['text'] for s in projected if s['id'] in f['evidence_ids']], f['key'])]
    return dict(case_id=case['id'], input_sha256=case['input_sha256'],
                source_provenance=case['input_provenance'], segment_count=len(segments),
                raw_s02_schema=verdict(raw, schema), projected_s02_schema=verdict(fine, schema),
                unsupported_split_fields=unsupported, frozen_page_schema=verdict(page_control, schema),
                frozen_rubric=evaluate(case, page_control), bridge=bridge)


def revision(root, paths):
    return {'commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                             text=True).strip(),
            'files': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--s02-root', type=Path, default=ROOT)
    parser.add_argument('--s06-root', type=Path, default=ROOT)
    args = parser.parse_args()
    def provenance():
        return {
            's01': revision(ROOT, ['tests/fixtures/sprint_corpus/freeze.v1.json',
                                  'scripts/sprint_eval/corpus.py',
                                  'tests/fixtures/sprint_corpus/check_compatibility.py',
                                  'curriculum/verification.py',
                                  'curriculum/overview_fields.py', 'curriculum/vocabulary.py']),
            's02': revision(args.s02_root, ['curriculum/source_segments.py']),
            's06': revision(args.s06_root, ['curriculum/interpretation_schema.py']),
        }
    before = provenance()
    extractor, schema = dependencies(args.s02_root, args.s06_root)
    rows = [check_case(c, extractor, schema) for c in load_corpus()['cases']]
    if before != provenance():
        raise ValueError('Dependency changed during probe; rerun on stable revisions')
    result = dict(status='ISSUES', classification='synthetic_contract_controls_only',
                  teacher_validated=False, provider_responses=0,
                  provenance=before,
                  summary={'mapped_cases': len(rows),
                           'projected_schema_pass': sum(r['projected_s02_schema']['status'] == 'PASS' for r in rows),
                           'frozen_schema_pass': sum(r['frozen_page_schema']['status'] == 'PASS' for r in rows),
                           'frozen_rubric_pass': sum(r['frozen_rubric']['status'] == 'PASS' for r in rows)},
                  cases=rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all(r['frozen_page_schema']['status'] == r['frozen_rubric']['status'] == 'PASS' for r in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
