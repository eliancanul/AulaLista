"""Strict field regression checks, separate from human semantic/usefulness review."""
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

from scripts.sprint_eval.corpus import DEFAULT_CORPUS, get_case


def normalized(value):
    if isinstance(value, str):
        return " ".join(unicodedata.normalize("NFC", value).split())
    return value


def evaluate(case: dict, output: object) -> dict:
    """Check the provisional sprint JSON contract without claiming entailment."""
    issues = []
    counts = {"field_match": [0, len(case["expected_fields"])], "reference_integrity": [0, 0]}
    expected = {f["key"]: f for f in case["expected_fields"]}
    sources = {s["id"]: s for s in case["source_segments"]}
    if not isinstance(output, dict):
        return {"status": "ISSUES", "issues": ["output_not_object"],
                "semantic_status": "NOT_EVALUATED", "counts": counts}
    if output.get("document_id") != case["document_id"]:
        issues.append("document_id_mismatch")
    if output.get("source_segments") != case["source_segments"]:
        issues.append("source_segments_changed_or_missing")
    fields = output.get("fields")
    if not isinstance(fields, list):
        fields = []
        issues.append("fields_not_list")
    seen = {}
    unscored = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict) or not isinstance(field.get("key"), str):
            issues.append(f"malformed_field:{index}")
            continue
        key = field["key"]
        if key in seen:
            issues.append(f"duplicate_field:{key}")
            continue
        seen[key] = field
        if not {"key", "value", "status", "evidence_ids"}.issubset(field):
            issues.append(f"incomplete_field:{key}")
        status = field.get("status")
        evidence = field.get("evidence_ids")
        valid_ids = (isinstance(evidence, list) and all(isinstance(e, str) and e in sources for e in evidence))
        if not isinstance(status, str) or status not in {"extracted", "suggested", "unknown"}:
            issues.append(f"invalid_status:{key}")
        if status == "unknown":
            if field.get("value") is not None or evidence != []:
                issues.append(f"unknown_asserts_value_or_evidence:{key}")
        else:
            counts["reference_integrity"][1] += 1
            if valid_ids and evidence:
                counts["reference_integrity"][0] += 1
            else:
                issues.append(f"missing_or_dangling_evidence:{key}")
        if key not in expected:
            unscored.append(key)
    for key, target in expected.items():
        field = seen.get(key)
        if field is None:
            issues.append(f"missing_field:{key}")
            continue
        if (field.get("status") == target["status"]
                and normalized(field.get("value")) == normalized(target["value"])
                and field.get("evidence_ids") == target["evidence_ids"]):
            counts["field_match"][0] += 1
        else:
            issues.append(f"field_mismatch:{key}")
    questions = output.get("missing_questions")
    if not isinstance(questions, list) or not questions or not all(isinstance(q, str) and q.strip() for q in questions):
        issues.append("missing_questions_required")
    draft = output.get("draft")
    if not isinstance(draft, dict):
        issues.append("draft_not_object")
    else:
        if draft.get("approval_status") != "pending":
            issues.append("human_approval_gate")
        if type(draft.get("revision")) is not int or draft["revision"] < 1:
            issues.append("invalid_draft_revision")
        for key in ("title", "objective", "materials", "steps", "assessment"):
            if key not in draft:
                issues.append(f"missing_draft_key:{key}")
        refs = draft.get("source_ids")
        if not isinstance(refs, list) or not all(isinstance(r, str) and r in sources for r in refs):
            issues.append("invalid_draft_source_ids")
    return {"status": "ISSUES" if issues else "PASS", "case_id": case["id"],
            "counts": counts, "issues": issues, "unscored_fields": unscored,
            "semantic_status": "NOT_EVALUATED", "teacher_validated": False,
            "limitations": "PASS checks listed fields and reference structure only. Extra fields, draft content, question relevance and entailment require review."}


def score_review(review: dict) -> dict:
    """Score a recorded evaluator review, not student work or teacher approval."""
    definition = json.loads((DEFAULT_CORPUS / "rubric.v1.json").read_text())
    if not isinstance(review, dict):
        raise ValueError("Review must be an object")
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        raise ValueError("Named evaluator required")
    if review.get("reviewer_kind") not in ("human", "agent"):
        raise ValueError("reviewer_kind must be human or agent")
    case = get_case(review.get("case_id"))
    if review.get("input_sha256") != case["input_sha256"]:
        raise ValueError("Review input digest mismatch")
    digest = review.get("output_sha256", "")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Exact output SHA-256 required")
    scores = review.get("scores", {})
    if not isinstance(scores, dict) or set(scores) != set(definition["dimensions"]):
        raise ValueError("All rubric dimensions required")
    total = 0
    gates = []
    for key, spec in definition["dimensions"].items():
        row = scores[key]
        if not isinstance(row, dict):
            raise ValueError(f"Invalid review dimension: {key}")
        if type(row.get("score")) is not int or row["score"] not in (0, 1, 2):
            raise ValueError(f"Invalid score: {key}")
        if not isinstance(row.get("evidence"), str) or not row["evidence"].strip():
            raise ValueError(f"Review evidence required: {key}")
        total += spec["weight"] * row["score"] / 2
        if spec["hard_gate"] and row["score"] < 2:
            gates.append(key)
    return {"review_score": total, "eligible": not gates, "failed_gates": gates,
            "reviewer_kind": review["reviewer_kind"], "teacher_validated": False,
            "scope": "Recorded evaluator judgment only; no publication authorization or model winner."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = evaluate(get_case(args.case_id), json.loads(args.output.read_text()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
