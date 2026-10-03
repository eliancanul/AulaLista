"""Isolated Luna evaluation boundary. No provider or model alias is assumed."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, Literal


@dataclass(frozen=True)
class FrozenCase:
    document_id: str
    prompt: bytes
    corpus: bytes
    rubric: bytes


@dataclass(frozen=True)
class ProviderReply:
    model: str
    text: str
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class Candidate:
    model: str
    invoke: Callable[[str, bytes], ProviderReply]
    evidence_kind: Literal["provider", "fixture"]


def unavailable_result() -> dict:
    return {
        "candidate": "luna",
        "status": "blocked",
        "provider_evidence": False,
        "requested_model": None,
        "returned_model": None,
        "latency_ms": None,
        "cost_usd": None,
        "validation_errors": [],
        "reason": "No hay una interfaz Luna autorizada con un modelo confirmado.",
        "unblock_owner": "Robert",
        "unblock_action": "Confirmar la interfaz autorizada y el identificador del modelo.",
    }


def _reject_constant(value: str) -> None:
    raise ValueError("non_finite_json")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non_finite_json")
    return number


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def run_case(
    case: FrozenCase,
    candidate: Candidate | None,
    validate: Callable[[dict], list[str]],
    *,
    clock: Callable[[], float] = perf_counter,
) -> dict:
    """Validate via S06's schema/rubric callback; never approve or persist a draft.

    The caller supplies the unchanged shared prompt and frozen inputs. The
    authorized transport owns timeout/cancellation and must not retry silently.
    Validator errors must be safe codes, never source text or credentials.
    """
    result = unavailable_result()
    result.update(
        document_id=case.document_id,
        input_hashes={
            name: hashlib.sha256(value).hexdigest()
            for name, value in (
                ("prompt", case.prompt), ("corpus", case.corpus), ("rubric", case.rubric)
            )
        },
        citations=[],
        usage={"input_tokens": None, "output_tokens": None},
        response_sha256=None,
    )
    if candidate is None:
        return result
    if not candidate.model.strip() or candidate.evidence_kind not in {"provider", "fixture"}:
        raise ValueError("Explicit model and evidence kind are required")
    for key in ("reason", "unblock_owner", "unblock_action"):
        result.pop(key)
    result.update(requested_model=candidate.model, evidence_kind=candidate.evidence_kind)
    started = clock()
    try:
        reply = candidate.invoke(candidate.model, case.prompt)
    except Exception:
        result.update(status="provider_error", failure_code="provider_call_failed")
        result["latency_ms"] = round((clock() - started) * 1000, 3)
        return result
    result["latency_ms"] = round((clock() - started) * 1000, 3)
    if not isinstance(reply, ProviderReply) or not isinstance(reply.text, str):
        result.update(status="provider_error", failure_code="invalid_provider_envelope")
        return result
    result.update(
        returned_model=reply.model,
        request_id=reply.request_id,
    )
    try:
        raw = reply.text.encode("utf-8")
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("response_too_large")
        result["response_sha256"] = hashlib.sha256(raw).hexdigest()
    except (UnicodeError, ValueError):
        result.update(status="invalid_response", validation_errors=["invalid_json"])
        return result
    metadata_errors = []
    for key in ("input_tokens", "output_tokens"):
        value = getattr(reply, key)
        if value is not None and (type(value) is not int or value < 0 or value > 2**63 - 1):
            metadata_errors.append("invalid_" + key)
        else:
            result["usage"][key] = value
    cost = reply.cost_usd
    if cost is not None and (
        type(cost) not in (int, float) or cost < 0 or cost > 1e100 or not math.isfinite(cost)
    ):
        metadata_errors.append("invalid_cost_usd")
    else:
        result["cost_usd"] = cost
    if not isinstance(reply.model, str) or reply.model != candidate.model:
        metadata_errors.append("model_identity_mismatch")
        if not isinstance(reply.model, str):
            result["returned_model"] = None
    if reply.request_id is not None and not isinstance(reply.request_id, str):
        metadata_errors.append("invalid_request_id")
        result["request_id"] = None
    if metadata_errors:
        result.update(status="provider_error", validation_errors=metadata_errors)
        return result
    result["provider_evidence"] = candidate.evidence_kind == "provider"
    try:
        payload = json.loads(
            reply.text, parse_constant=_reject_constant, parse_float=_finite_float,
            object_pairs_hook=_unique_object,
        )
    except (ValueError, RecursionError):
        result.update(status="invalid_response", validation_errors=["invalid_json"])
        return result
    if not isinstance(payload, dict):
        result.update(status="invalid_response", validation_errors=["expected_object"])
        return result
    if payload.get("document_id") != case.document_id:
        result.update(status="invalid_response", validation_errors=["document_id_mismatch"])
        return result
    try:
        errors = validate(payload)
        if not isinstance(errors, list) or any(not isinstance(e, str) for e in errors):
            raise ValueError("invalid_validator_result")
    except Exception:
        result.update(status="evaluator_error", failure_code="validator_failed")
        return result
    result.update(status="invalid_response" if errors else "validated", validation_errors=errors)
    if not errors:
        citations = []
        fields = payload.get("fields", [])
        draft = payload.get("draft", {})
        if not isinstance(fields, list) or not isinstance(draft, dict):
            result.update(status="evaluator_error", failure_code="validator_contract_mismatch")
            return result
        for field in fields:
            if not isinstance(field, dict) or not isinstance(field.get("evidence_ids", []), list):
                result.update(status="evaluator_error", failure_code="validator_contract_mismatch")
                return result
            citations.extend(field.get("evidence_ids", []))
        source_ids = draft.get("source_ids", [])
        if not isinstance(source_ids, list) or any(
            not isinstance(value, str) for value in citations + source_ids
        ):
            result.update(status="evaluator_error", failure_code="validator_contract_mismatch")
            return result
        result["citations"] = sorted(set(citations + source_ids))
    return result


def run_frozen_corpus(
    candidate: Candidate | None,
    directory: Path | None = None,
    *,
    clock: Callable[[], float] = perf_counter,
) -> list[dict]:
    """Run S01's verified inputs through S06's contract and S01's field rubric.

    Only document identity and source segments enter the prompt. Expectations
    stay in the evaluator. Fixture callers must declare their evidence kind.
    """
    from curriculum.interpretation_schema import interpretation_validation_errors
    from scripts.sprint_eval.corpus import DEFAULT_CORPUS, load_corpus
    from scripts.sprint_eval.rubric import evaluate

    directory = DEFAULT_CORPUS if directory is None else Path(directory)
    corpus = load_corpus(directory)
    corpus_bytes = (directory / "cases.v1.json").read_bytes()
    rubric_bytes = (directory / "rubric.v1.json").read_bytes()
    freeze_bytes = (directory / "freeze.v1.json").read_bytes()
    freeze = json.loads(freeze_bytes)
    if json.loads(corpus_bytes) != corpus or any(
        hashlib.sha256(data).hexdigest() != freeze["files"][name]
        for name, data in (("cases.v1.json", corpus_bytes), ("rubric.v1.json", rubric_bytes))
    ):
        raise ValueError("Frozen artifact changed while loading")
    results = []
    for source_case in corpus["cases"]:
        prompt = json.dumps(
            {key: source_case[key] for key in ("document_id", "source_segments")},
            ensure_ascii=False, indent=2,
        ).encode("utf-8")
        case = FrozenCase(source_case["document_id"], prompt, corpus_bytes, rubric_bytes)
        rubric_result = None

        def validate(payload):
            nonlocal rubric_result
            errors = interpretation_validation_errors(
                payload, expected_document_id=source_case["document_id"],
                source_segments=source_case["source_segments"],
            )
            if errors:
                return errors
            rubric_result = evaluate(source_case, payload)
            return rubric_result["issues"]

        result = run_case(case, candidate, validate, clock=clock)
        result.update(
            case_id=source_case["id"], corpus_version=corpus["corpus_version"],
            freeze_sha256=hashlib.sha256(freeze_bytes).hexdigest(),
            rubric_result=rubric_result, semantic_status="NOT_EVALUATED",
            teacher_validated=False,
        )
        results.append(result)
    return results


if __name__ == "__main__":
    print(json.dumps(unavailable_result(), ensure_ascii=False, indent=2))
    raise SystemExit(2)
