#!/usr/bin/env python3
"""Synthetic fixed-opportunity requires-annex evaluation; not resource suitability."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.evaluate_activity_session import _locations, validate_reference, claim_is_abstention


def validate_annex_reference(document):
    # The activity/session anchor contract is shared, but multiple different
    # annex targets for one physical activity are legitimate opportunities.
    unique, seen_activities, seen_relations, seen_ids, parents = [], set(), set(), set(), {}
    for relation in document['relations']:
        activity = relation['activity']
        position = (activity['page'], activity['start'], activity['end'])
        key = (position, relation['annex_number'])
        if relation['id'] in seen_ids:
            raise ValueError('Duplicate reference ID')
        seen_ids.add(relation['id'])
        validate_reference({**document, 'relations': [relation]})
        validate_reference({**document, 'relations': [{**relation, 'activity': relation['mention']}]})
        if position in parents and parents[position] != relation['session_id']:
            raise ValueError('Conflicting reference parents for one activity')
        parents[position] = relation['session_id']
        if key in seen_relations:
            raise ValueError('Duplicate activity-annex opportunity')
        seen_relations.add(key)
        number = relation['annex_number']
        if not isinstance(number, str) or not number.isascii() or not number.isdigit() or str(int(number)) != number:
            raise ValueError('Expected canonical explicit annex number')
        mention = relation['mention']
        if (mention['page'] != activity['page'] or not activity['start'] <= mention['start'] < mention['end'] <= activity['end']
                or document['pages'][mention['page'] - 1][mention['start']:mention['end']] != mention['quote']):
            raise ValueError('Annex mention must be exact and inside its activity')
        if position not in seen_activities:
            unique.append(relation)
            seen_activities.add(position)
    validate_reference({**document, 'relations': unique})


def predict(document):
    from curriculum.claims import compile_dossier_to_atomic_claims
    from curriculum.source_interpreter import CurriculumSourceInterpreter, ImportDossier
    pages = document['pages']
    sha = hashlib.sha256(json.dumps(pages, ensure_ascii=False).encode()).hexdigest()
    sessions = CurriculumSourceInterpreter._detect_sessions(pages, sha, [], {})
    dossier = ImportDossier(source_sha256=sha, source_name='synthetic-annex-text', page_count=len(pages), sessions=sessions)
    activities = {f'activity:{a.activity_id}': (a, s) for s in sessions for a in s.activities}
    predictions = []
    for claim in compile_dossier_to_atomic_claims(dossier):
        if claim.predicate != 'requiere_anexo':
            continue
        activity, session = activities[claim.subject]
        annex = next((ref for ref in session.annex_references if ref.reference_id == claim.object_value), None)
        locations = []
        for evidence in activity.evidence[:1]:
            locations.extend(_locations(pages, evidence.page_number, evidence.excerpt))
        citations = []
        for evidence in claim.evidence:
            found = _locations(pages, evidence.page_number, evidence.excerpt)
            if len(found) == 1:
                citations.extend(found)
        anchor = session.header_anchor
        predictions.append(dict(activity_spans=locations if len(locations) == 1 else [],
                                session_anchor={'page': anchor['page_number'], 'start': anchor['text_start']} if anchor else None,
                                annex_number=annex.annex_number if annex else None, citation_spans=citations,
                                abstained=claim_is_abstention(claim), scope_pages=sorted({span['page'] for span in locations})))
    return predictions


def score(document, predictions):
    validate_annex_reference(document)
    sessions = {s['id']: s['anchor'] for s in document['sessions']}
    scope = set(document.get('scored_pages', range(1, len(document['pages']) + 1)))
    included, excluded, uncertain = [], 0, 0
    for prediction in predictions:
        pages = set(prediction.get('scope_pages', [span['page'] for span in prediction['activity_spans']]))
        if pages and pages.isdisjoint(scope):
            excluded += 1
        else:
            included.append(prediction)
            uncertain += not bool(pages)
    predictions = included
    assignments = {r['id']: [] for r in document['relations']}
    counts = dict(excluded_context_predictions=excluded, uncertain_scope_predictions=uncertain, expected=len(assignments), correct=0, incorrect=0, omitted=0, abstained=0,
                  extras=0, duplicates=0, asserted=sum(not p['abstained'] for p in predictions), supported=0)
    for prediction in predictions:
        matches = [r for r in document['relations'] if r['annex_number'] == prediction['annex_number'] and any(
            span['page'] == r['activity']['page'] and r['activity']['start'] <= span['start'] < span['end'] <= r['activity']['end']
            for span in prediction['activity_spans'])]
        if len(matches) == 1:
            assignments[matches[0]['id']].append(prediction)
        else:
            counts['extras'] += 1
    for relation in document['relations']:
        found = assignments[relation['id']]
        if not found:
            counts['omitted'] += 1
        elif len(found) > 1:
            counts['incorrect'] += 1
            counts['duplicates'] += len(found) - 1
        elif found[0]['abstained']:
            counts['abstained'] += 1
        else:
            anchor = sessions[relation['session_id']]
            correct = found[0]['session_anchor'] == {'page': anchor['page'], 'start': anchor['start']}
            counts['correct' if correct else 'incorrect'] += 1
            mention = relation['mention']
            if correct and any(span['page'] == mention['page'] and span['start'] <= mention['start'] < mention['end'] <= span['end'] for span in found[0]['citation_spans']):
                counts['supported'] += 1
    assert counts['expected'] == sum(counts[k] for k in ('correct', 'incorrect', 'omitted', 'abstained'))
    return counts


def ratios(counts):
    return {**counts, 'recall': counts['correct'] / counts['expected'] if counts['expected'] else None,
            'precision': counts['correct'] / counts['asserted'] if counts['asserted'] else None,
            'supported_recall': counts['supported'] / counts['expected'] if counts['expected'] else None}


def evaluate(reference):
    docs = [{'id': d['id'], **ratios(score(d, predict(d)))} for d in reference['documents']]
    totals = {k: sum(d[k] for d in docs) for k in ('expected', 'correct', 'incorrect', 'omitted', 'abstained', 'extras', 'duplicates', 'asserted', 'supported', 'excluded_context_predictions', 'uncertain_scope_predictions')}
    return {'evaluator_version': 'activity-annex.v2', 'reference_kind': reference['reference_kind'], 'scope': reference['scope'], 'total': ratios(totals), 'documents': docs,
            'limits': 'Synthetic text only. Candidate textual association, not pedagogical necessity, annex-sheet availability or suitability. No LLM calls.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=ROOT / 'tests/fixtures/interpretation/activity_annex_v1.json')
    parser.add_argument('--product-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.product_root.resolve()))
    raw = args.reference.read_bytes()
    report = evaluate(json.loads(raw))
    report['reference_sha256'] = hashlib.sha256(raw).hexdigest()
    content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(content)
    print(content)


if __name__ == '__main__':
    main()
