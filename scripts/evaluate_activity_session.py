#!/usr/bin/env python3
"""Fixed-opportunity development evaluation, NOT pedagogical validation.

Consumes extracted page text; it does not test PDF extraction. Gold anchors are
independently authored. Matching never imports the product's session scanner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _locations(pages, page_number, quote):
    if type(page_number) is not int or not (1 <= page_number <= len(pages)) or not isinstance(quote, str) or not quote:
        return []
    text, result, start = pages[page_number - 1], [], 0
    while (start := text.find(quote, start)) >= 0:
        result.append({'page': page_number, 'start': start, 'end': start + len(quote)})
        start += 1
    return result


def claim_is_abstention(claim):
    """Human review is governance, not a model's decision to withhold a target."""
    metadata = getattr(claim, 'metadata', {})
    basis = metadata.get('basis') if isinstance(metadata, dict) else None
    return basis == 'abstained' or getattr(claim, 'object_value', None) is None


def predict(document):
    from curriculum.claims import compile_dossier_to_atomic_claims
    from curriculum.source_interpreter import CurriculumSourceInterpreter, ImportDossier
    pages = document['pages']
    sha = hashlib.sha256(json.dumps(pages, ensure_ascii=False).encode()).hexdigest()
    sessions = CurriculumSourceInterpreter._detect_sessions(pages, sha, [], {})
    dossier = ImportDossier(source_sha256=sha, source_name='development-text-snapshot', page_count=len(pages), sessions=sessions)
    anchors = {f'session:{s.session_id}': s.header_anchor for s in sessions}
    descriptions = {f'activity:{a.activity_id}': a.description for s in sessions for a in s.activities}
    output = []
    for claim in compile_dossier_to_atomic_claims(dossier):
        if claim.predicate != 'pertenece_a_sesion':
            continue
        locations = _locations(pages, claim.page_number, claim.excerpt)
        # More than one location is unresolved provenance. Do not choose the
        # location closest to the predicted parent (that would reward leakage).
        anchor = anchors.get(claim.object_value)
        description_locations = _locations(pages, claim.page_number, descriptions.get(claim.subject, ''))
        coverage = []
        for evidence in claim.evidence:
            evidence_locations = _locations(pages, evidence.page_number, evidence.excerpt)
            if len(evidence_locations) == 1:
                coverage.extend(evidence_locations)
        coverage.extend(description_locations if len(description_locations) == 1 else [])
        output.append({
            'id': claim.claim_id,
            'activity_spans': locations if len(locations) == 1 else [],
            'coverage_spans': coverage,
            'session_anchor': {'page': anchor['page_number'], 'start': anchor['text_start']} if anchor else None,
            'abstained': claim_is_abstention(claim),
            'unresolved_provenance': len(locations) != 1,
            'scope_pages': sorted({location['page'] for location in locations}),
        })
    return output


def validate_reference(document):
    pages = document['pages']
    if not pages or any(not isinstance(page, str) for page in pages):
        raise ValueError('Reference requires original page text')
    seen = set()
    for item in document['sessions'] + document['relations']:
        if not item['id'] or item['id'] in seen:
            raise ValueError('Duplicate or empty reference ID')
        seen.add(item['id'])
        anchor = item.get('anchor', item.get('activity'))
        if not (type(anchor['page']) is int and 1 <= anchor['page'] <= len(pages)
                and type(anchor['start']) is int and type(anchor['end']) is int
                and 0 <= anchor['start'] < anchor['end'] <= len(pages[anchor['page'] - 1])
                and pages[anchor['page'] - 1][anchor['start']:anchor['end']] == anchor['quote']):
            raise ValueError('Reference span does not reproduce exact original text')
    scope = document.get('scored_pages', list(range(1, len(pages) + 1)))
    if not isinstance(scope, list) or not scope or any(type(n) is not int or not 1 <= n <= len(pages) for n in scope):
        raise ValueError('Invalid scoring-page scope')
    if any(r['activity']['page'] not in scope for r in document['relations']):
        raise ValueError('Reference opportunity outside declared scoring scope')
    session_ids = {s['id'] for s in document['sessions']}
    spans = set()
    for relation in document['relations']:
        if relation['session_id'] not in session_ids:
            raise ValueError('Unknown reference session')
        span = relation['activity']
        key = (span['page'], span['start'], span['end'])
        if key in spans:
            raise ValueError('Duplicate reference opportunity')
        spans.add(key)


def score(document, predictions):
    """One-to-one conservative alignment; extras/duplicates cannot disappear."""
    validate_reference(document)
    sessions = {s['id']: s['anchor'] for s in document['sessions']}
    scope = set(document.get('scored_pages', range(1, len(document['pages']) + 1)))
    scoped, excluded_context, uncertain_scope = [], 0, 0
    for prediction in predictions:
        pages = set(prediction.get('scope_pages', [span['page'] for span in prediction['activity_spans']]))
        if pages and pages.isdisjoint(scope):
            excluded_context += 1
        else:
            scoped.append(prediction)
            if not pages:
                uncertain_scope += 1
    predictions = scoped
    assignments = {r['id']: [] for r in document['relations']}
    extras = 0
    asserted = sum(not p['abstained'] for p in predictions)
    for prediction in predictions:
        matches = []
        for relation in document['relations']:
            gold = relation['activity']
            if any(span['page'] == gold['page'] and gold['start'] <= span['start'] < span['end'] <= gold['end'] for span in prediction['activity_spans']):
                matches.append(relation)
        if len(matches) == 1:
            assignments[matches[0]['id']].append(prediction)
        else:
            extras += 1
    counts = dict(excluded_context_predictions=excluded_context, uncertain_scope_predictions=uncertain_scope, scope_truncated_relations=sum(bool(r.get('scope_truncated', False)) for r in document['relations']), expected=len(document['relations']), correct=0, incorrect=0, omitted=0, abstained=0,
                  extras=extras, duplicates=0, asserted=asserted, emitted=len(predictions), unresolved_provenance=sum(p.get('unresolved_provenance', False) for p in predictions))
    def nonspace_positions(spans):
        result = set()
        for span in spans:
            page = span['page']
            if type(page) is int and 1 <= page <= len(document['pages']):
                text = document['pages'][page - 1]
                result.update((page, i) for i in range(max(0, span['start']), min(len(text), span['end'])) if not text[i].isspace())
        return result

    counts.update(complete_activity_correct=0, clean_complete_activity_correct=0, coverage_fraction_sum=0.0,
                  matched_text_characters=0, correctly_assigned_text_characters=0,
                  predicted_text_characters=sum(len(nonspace_positions(p.get('coverage_spans', p['activity_spans']))) for p in predictions if not p['abstained']))
    for relation in document['relations']:
        found = assignments[relation['id']]
        if not found:
            counts['omitted'] += 1
        elif len(found) > 1:
            # Conflicting/duplicate claims cannot win by including one right guess.
            counts['incorrect'] += 1
            counts['duplicates'] += len(found) - 1
        elif found[0]['abstained']:
            counts['abstained'] += 1
        else:
            expected = sessions[relation['session_id']]
            anchor = found[0]['session_anchor']
            correct = anchor == {'page': expected['page'], 'start': expected['start']}
            counts['correct' if correct else 'incorrect'] += 1
            gold = relation['activity']
            required = nonspace_positions([gold])
            covered = nonspace_positions(found[0].get('coverage_spans', found[0]['activity_spans']))
            fraction = len(required & covered) / len(required) if required else 0
            counts['coverage_fraction_sum'] += fraction
            counts['matched_text_characters'] += len(required & covered)
            if correct:
                counts['correctly_assigned_text_characters'] += len(required & covered)
            if correct and required and required <= covered:
                counts['complete_activity_correct'] += 1
                if covered == required:
                    counts['clean_complete_activity_correct'] += 1
    assert counts['expected'] == sum(counts[k] for k in ('correct', 'incorrect', 'omitted', 'abstained'))
    return counts


def ratios(counts):
    return {
        **counts,
        'recall': counts['correct'] / counts['expected'] if counts['expected'] else None,
        'precision': counts['correct'] / counts['asserted'] if counts['asserted'] else None,
        'abstention_rate': counts['abstained'] / counts['expected'] if counts['expected'] else None,
        'complete_activity_recall': counts['complete_activity_correct'] / counts['expected'] if counts['expected'] else None,
        'mean_activity_text_coverage': counts['coverage_fraction_sum'] / counts['expected'] if counts['expected'] else None,
        'clean_complete_activity_recall': counts['clean_complete_activity_correct'] / counts['expected'] if counts['expected'] else None,
        'activity_text_precision': counts['matched_text_characters'] / counts['predicted_text_characters'] if counts['predicted_text_characters'] else None,
        'correctly_assigned_text_precision': counts['correctly_assigned_text_characters'] / counts['predicted_text_characters'] if counts['predicted_text_characters'] else None,
    }


def evaluate(reference, predictor=predict):
    documents = [{'id': d['id'], **ratios(score(d, predictor(d)))} for d in reference['documents']]
    keys = ('expected', 'correct', 'incorrect', 'omitted', 'abstained', 'extras', 'duplicates', 'asserted', 'emitted', 'unresolved_provenance', 'complete_activity_correct', 'coverage_fraction_sum', 'clean_complete_activity_correct', 'matched_text_characters', 'correctly_assigned_text_characters', 'predicted_text_characters', 'excluded_context_predictions', 'uncertain_scope_predictions', 'scope_truncated_relations')
    total = {key: sum(d[key] for d in documents) for key in keys}
    return {'evaluator_version': 'activity-session.v4', 'reference_kind': reference['reference_kind'], 'scope': reference['scope'], 'total': ratios(total), 'documents': documents,
            'text_metric_definition': 'activity_text_precision and mean_activity_text_coverage are text-only, independent of parent assignment; use correctly_assigned_text_precision or clean_complete_activity_recall for the joint interpretation.',
            'alignment_contract': 'Primary alignment requires a unique contained identifying span. Overextended identifying spans are extras/omissions; separate coverage_spans may reveal contamination after alignment. This is a strict contract, not adjudication of semantic granularity.',
            'recall_definition': 'Correct fragment-to-session associations / fixed expected activities. Full source-text recovery is reported separately; neither proves pedagogical meaning.',
            'limits': 'AI structural development reference, not teacher gold. Extracted text only, no end-to-end PDF, semantic curriculum or generalization claim. IA API cost/latency N/A.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=ROOT / 'tests/fixtures/interpretation/activity_session_v1.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--product-root', type=Path, default=ROOT, help='Separate product checkout for immutable baseline comparison')
    args = parser.parse_args()
    product_root = args.product_root.resolve()
    if not (product_root / 'curriculum/source_interpreter.py').is_file():
        parser.error('product-root must contain the product checkout')
    sys.path.insert(0, str(product_root))
    raw = args.reference.read_bytes()
    report = evaluate(json.loads(raw))
    report['reference_sha256'] = hashlib.sha256(raw).hexdigest()
    content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(content)
    print(content)


if __name__ == '__main__':
    main()
