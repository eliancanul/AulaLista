#!/usr/bin/env python3
"""Synthetic fixed-opportunity annex-mention evaluation; not requirement or suitability."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.evaluate_activity_session import _locations, validate_reference


def _valid_source_span(pages, span):
    """Check scorer coordinates without consulting product extraction/matching."""
    if not isinstance(span, dict):
        return False
    page, start, end = (span.get(key) for key in ('page', 'start', 'end'))
    return (type(page) is int and 1 <= page <= len(pages)
            and type(start) is int and type(end) is int
            and 0 <= start < end <= len(pages[page - 1])
            and ('quote' not in span or pages[page - 1][start:end] == span['quote']))


def validate_annex_reference(document):
    # The activity/session anchor contract is shared, but multiple different
    # annex targets for one physical activity are legitimate opportunities.
    unique, seen_activities, seen_relations, seen_ids, parents = [], set(), set(), set(), {}
    for relation in document['relations']:
        number = relation['annex_number']
        if (not isinstance(number, str) or not number.isascii() or not number.isdigit()
                or (number.lstrip('0') or '0') != number):
            raise ValueError('Expected canonical explicit annex number')
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
        mention = relation['mention']
        # Independent annotation-contract check, not the product mention parser.
        # This evaluator covers explicit numbered mentions only. Discourse
        # references require a separate antecedent-aware annotation contract.
        quote = mention['quote']
        lexical = re.fullmatch(r'anexos?\s+([0-9]+(?:(?:\s*,\s*|\s+(?:y|e)\s+|\s*&\s*)[0-9]+)*)', quote.strip(), re.I)
        numbers = {value.lstrip('0') or '0' for value in re.findall(r'[0-9]+', lexical.group(1))} if lexical else set()
        if number not in numbers:
            raise ValueError('Explicit annex mention must contain its annotated number')
        # A literal slice can still truncate a token (anexo 1 inside anexo 12)
        # or start inside a word (preanexo 1). Check the original neighbours,
        # including when annotation padding was stripped for lexical matching.
        page = document['pages'][mention['page'] - 1]
        start = mention['start'] + len(quote) - len(quote.lstrip())
        end = mention['end'] - (len(quote) - len(quote.rstrip()))
        if ((start and re.match(r'\w', page[start - 1]))
                or (end < len(page) and re.match(r'\w', page[end]))
                or re.match(r'[.:/\-][0-9]', page[end:])):
            raise ValueError('Explicit annex mention must cover complete tokens')
        if (mention['page'] != activity['page'] or not activity['start'] <= mention['start'] < mention['end'] <= activity['end']
                or document['pages'][mention['page'] - 1][mention['start']:mention['end']] != mention['quote']):
            raise ValueError('Annex mention must be exact and inside its activity')
        if position not in seen_activities:
            unique.append(relation)
            seen_activities.add(position)
    validate_reference({**document, 'relations': unique})


def predict(document):
    """Adapt textual links, independently of operational requirement claims.

    A negated/conditional reference can be a real textual mention without being
    an instruction to obtain or use the resource. This scorer measures the former.
    """
    from curriculum.source_interpreter import CurriculumSourceInterpreter
    pages = document['pages']
    sha = hashlib.sha256(json.dumps(pages, ensure_ascii=False).encode()).hexdigest()
    sessions = CurriculumSourceInterpreter._detect_sessions(pages, sha, [], {})
    predictions = []
    for session in sessions:
        annexes = {ref.reference_id: ref for ref in session.annex_references}
        for activity in session.activities:
            for annex_id in activity.annex_ids:
                annex = annexes.get(annex_id)
                locations = []
                for evidence in activity.evidence[:1]:
                    if evidence.document_sha256 == sha:
                        locations.extend(_locations(pages, evidence.page_number, evidence.excerpt))
                citations = []
                for evidence in getattr(activity, 'annex_evidence', {}).get(annex_id, []):
                    if evidence.document_sha256 != sha:
                        continue
                    found = _locations(pages, evidence.page_number, evidence.excerpt)
                    if len(found) == 1:
                        citations.extend(found)
                anchor = session.header_anchor
                predictions.append(dict(activity_spans=locations if len(locations) == 1 else [],
                                        session_anchor={'page': anchor['page_number'], 'start': anchor['text_start']} if anchor else None,
                                        annex_number=annex.annex_number if annex else None, citation_spans=citations,
                                        abstained=False, scope_pages=sorted({span['page'] for span in locations})))
    return predictions


def score(document, predictions):
    validate_annex_reference(document)
    sessions = {s['id']: s['anchor'] for s in document['sessions']}
    scope = set(document.get('scored_pages', range(1, len(document['pages']) + 1)))
    included, excluded, uncertain = [], 0, 0
    for prediction in predictions:
        # Declared scope cannot erase a scored-page location or conceal invalid
        # provenance. The adapter may retain scope for ambiguous locations even
        # when it cannot supply a unique identifying activity span.
        spans = prediction['activity_spans']
        pages = {span['page'] for span in spans if _valid_source_span(document['pages'], span)}
        unknown_scope = any(not _valid_source_span(document['pages'], span) for span in spans)
        for page in prediction.get('scope_pages', []):
            if type(page) is int and 1 <= page <= len(document['pages']):
                pages.add(page)
            else:
                unknown_scope = True
        if pages and pages.isdisjoint(scope) and not unknown_scope:
            excluded += 1
        else:
            included.append(prediction)
            uncertain += unknown_scope or not pages
    predictions = included
    assignments = {r['id']: [] for r in document['relations']}
    counts = dict(excluded_context_predictions=excluded, uncertain_scope_predictions=uncertain, expected=len(assignments), correct=0, incorrect=0, omitted=0, abstained=0,
                  extras=0, duplicates=0, asserted=sum(not p['abstained'] for p in predictions), supported=0)
    for prediction in predictions:
        matches = [r for r in document['relations'] if r['annex_number'] == prediction['annex_number'] and any(
            _valid_source_span(document['pages'], span)
            and span['page'] == r['activity']['page'] and r['activity']['start'] <= span['start'] < span['end'] <= r['activity']['end']
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
            predicted_anchor = found[0]['session_anchor']
            correct = (isinstance(predicted_anchor, dict)
                       and all(type(predicted_anchor.get(key)) is int for key in ('page', 'start'))
                       and predicted_anchor == {'page': anchor['page'], 'start': anchor['start']})
            counts['correct' if correct else 'incorrect'] += 1
            mention = relation['mention']
            if correct and any(_valid_source_span(document['pages'], span)
                               and span['page'] == mention['page'] and span['start'] <= mention['start'] < mention['end'] <= span['end']
                               for span in found[0]['citation_spans']):
                counts['supported'] += 1
    assert counts['expected'] == sum(counts[k] for k in ('correct', 'incorrect', 'omitted', 'abstained'))
    return counts


def ratios(counts):
    return {**counts, 'recall': counts['correct'] / counts['expected'] if counts['expected'] else None,
            'precision': counts['correct'] / counts['asserted'] if counts['asserted'] else None,
            'supported_recall': counts['supported'] / counts['expected'] if counts['expected'] else None}


def evaluate(reference):
    # Reject the complete reference before running any product prediction.
    for document in reference['documents']:
        validate_annex_reference(document)
    docs = [{'id': d['id'], **ratios(score(d, predict(d)))} for d in reference['documents']]
    totals = {k: sum(d[k] for d in docs) for k in ('expected', 'correct', 'incorrect', 'omitted', 'abstained', 'extras', 'duplicates', 'asserted', 'supported', 'excluded_context_predictions', 'uncertain_scope_predictions')}
    return {'evaluator_version': 'activity-annex.v3', 'reference_kind': reference['reference_kind'], 'scope': reference['scope'], 'total': ratios(totals), 'documents': docs,
            'prediction_contract': 'Activity annex_ids are textual associations, not operational requiere_anexo claims; this predictor does not infer abstentions.',
            'evidence_metric': 'supported counts coverage of an independently validated explicit label/number span; not semantic necessity',
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
