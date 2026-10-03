"""Shared v2 contract fixtures; no model comparison, provider discovery or network."""
from __future__ import annotations
import copy
import hashlib
import json
from curriculum.interpretation_schema import interpretation_json_schema, interpretation_validation_errors
from curriculum.interpretation_service import interpret_source
from scripts.benchmark_curriculum.fixtures import pdf_bytes
from scripts.sprint_eval.gemini import ExperimentCase, GeminiAdapter
from scripts.sprint_eval.luna import Candidate, FrozenCase, ProviderReply, run_case


def run_fixtures():
    schema = interpretation_json_schema()
    rows = []
    pages = [
        ['Proyecto: La lectura', 'Propósito: Leer y conversar.', 'Grado: 3ro'],
        ['Materiales: Papel', 'Grado: 1ro'],
        ['Nombre del proyecto: El agua', 'Materiales: volcanes'],
    ]
    for index, lines in enumerate(pages, 1):
        content = pdf_bytes([lines])
        baseline = interpret_source(content, document_id=f'offline-v2-{index}')
        case = ExperimentCase(baseline['document_id'], baseline['source_segments'])
        def errors(value):
            return interpretation_validation_errors(value, expected_document_id=case.document_id, source_segments=case.source_segments)
        def validate(value):
            if errors(value):
                raise ValueError('invalid_contract')
        def transport(method, path, key, body, timeout):
            if method == 'GET':
                return {'models': [{'name': 'models/gemini-offline-fixture', 'supportedGenerationMethods': ['generateContent']}]}
            return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(baseline)}]}}]}
        gemini = GeminiAdapter('fixture-only', transport=transport).run_corpus(
            [case], model='gemini-offline-fixture', schema=schema, validate=validate)
        prompt = json.dumps(case.payload(), ensure_ascii=False, sort_keys=True).encode()
        luna = run_case(FrozenCase(case.document_id, prompt, content, json.dumps(schema, sort_keys=True).encode()),
            Candidate('luna-offline-fixture', lambda model, request: ProviderReply(model, json.dumps(baseline)), 'fixture'), errors)
        rows.append({'document_id': case.document_id, 'source_sha256': hashlib.sha256(content).hexdigest(),
                     'schema_status': {'gemini': gemini['results'][0]['status'], 'luna': luna['status']},
                     'gemini': gemini, 'luna': luna, 'semantic_status': 'NOT_EVALUATED'})
    return {'fixture_set': 'synthetic-v2-contract-3', 'schema_version': 2, 'results': rows,
            'evidence_kind': 'fixture', 'real_response_count': 0, 'model_winner': None,
            'provider_comparison': 'NOT_PERFORMED', 'teacher_validated': False,
            'note': 'Schema acceptance only. S01 literal rubric and human semantic review are separate denominators.'}


if __name__ == '__main__':
    print(json.dumps(run_fixtures(), ensure_ascii=False, allow_nan=False, indent=2))
