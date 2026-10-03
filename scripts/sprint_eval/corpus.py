"""Load the frozen technical corpus; never infer a school level or run a provider."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = ROOT / "tests/fixtures/sprint_corpus"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_corpus(directory: Path = DEFAULT_CORPUS, *, verify_sources: bool = True) -> dict:
    directory = Path(directory)
    lock = json.loads((directory / "freeze.v1.json").read_text())
    for name, expected in lock["files"].items():
        if Path(name).name != name or sha256((directory / name).read_bytes()) != expected:
            raise ValueError(f"Frozen artifact mismatch: {name}")
    corpus = json.loads((directory / "cases.v1.json").read_text())
    if corpus["corpus_version"] != lock["corpus_version"]:
        raise ValueError("Corpus version mismatch")
    cases = corpus["cases"]
    if len(cases) < 6 or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("At least six uniquely identified cases required")
    for case in cases:
        if case["synthetic"] is not True or case["teacher_validated"] is not False:
            raise ValueError(f"Unverified representativeness claim: {case['id']}")
        segments = case["source_segments"]
        ids = {s["id"] for s in segments}
        if len(ids) != len(segments) or not segments:
            raise ValueError("Invalid segment identifiers")
        text = "\n".join(s["text"] for s in segments)
        if sha256(text.encode()) != case["input_sha256"]:
            raise ValueError(f"Input digest mismatch: {case['id']}")
        keys = [f["key"] for f in case["expected_fields"]]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate expected field")
        for field in case["expected_fields"]:
            if field["status"] not in {"extracted", "suggested", "unknown"}:
                raise ValueError("Invalid field status")
            if not set(field["evidence_ids"]).issubset(ids):
                raise ValueError("Dangling expected evidence")
            if field["status"] == "unknown":
                if field["value"] is not None or field["evidence_ids"]:
                    raise ValueError("Unknown field must not assert a value")
            elif not field["evidence_ids"]:
                raise ValueError("Expected claim requires evidence")
        source = case["input_provenance"]
        if source["source_commit"] != corpus["source_commit"]:
            raise ValueError("Source commit mismatch")
        if verify_sources:
            path = (ROOT / source["path"]).resolve()
            if not path.is_relative_to(ROOT):
                raise ValueError("Source outside repository")
            raw = path.read_bytes()
            if sha256(raw) != source["sha256"]:
                raise ValueError(f"Source file drift: {source['path']}")
            first, last = source["lines"]
            if "\n".join(raw.decode().splitlines()[first - 1:last]) != source["source_code"]:
                raise ValueError("Source locator mismatch")
    return corpus


def get_case(case_id: str, directory: Path = DEFAULT_CORPUS) -> dict:
    for case in load_corpus(directory)["cases"]:
        if case["id"] == case_id:
            return case
    raise ValueError(f"Unknown case: {case_id}")


def prepare_segment_bridge(case: dict, segments: list[dict]) -> dict:
    """Verify S02 line anchors against a loaded frozen case before an experiment.

    Returns the unchanged model input and a separate provenance map. This does
    not relabel an existing answer's citations or validate PDF extraction.
    Only one frozen segment per page and unchanged page text are supported.
    """
    frozen = case["source_segments"]
    if sha256("\n".join(s["text"] for s in frozen).encode()) != case["input_sha256"]:
        raise ValueError("Frozen input digest mismatch")
    pages = {s["page"]: s for s in frozen}
    if len(pages) != len(frozen) or any(type(p) is not int or p < 1 for p in pages):
        raise ValueError("Bridge requires one frozen segment per physical page")
    if not isinstance(segments, list) or not segments:
        raise ValueError("S02 segments required")
    rows, seen, cursors = [], set(), {p: 0 for p in pages}
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != {
            "id", "text", "page", "kind", "text_start", "text_end"
        }:
            raise ValueError("Invalid S02 segment shape")
        page = segment["page"]
        if type(page) is not int or page not in pages:
            raise ValueError("S02 page outside frozen input")
        parent = pages[page]
        text = parent["text"]
        start, end = segment["text_start"], segment["text_end"]
        if (type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(text)
                or start < cursors[page]):
            raise ValueError("Invalid, overlapping or reordered S02 offsets")
        if segment["text"] != text[start:end] or not text[start:end].strip():
            raise ValueError("S02 text does not match frozen source")
        if text[cursors[page]:start].strip():
            raise ValueError("S02 omitted non-whitespace source text")
        expected_id = (f"{case['document_id']}:text-v1:{sha256(text.encode())}"
                       f":p{page}:{start}-{end}")
        if segment["id"] != expected_id or expected_id in seen:
            raise ValueError("S02 identity mismatch or duplicate")
        if segment["kind"] not in ("text", "heading_candidate", "table_row_candidate"):
            raise ValueError("Unknown S02 structural hint")
        seen.add(expected_id)
        cursors[page] = end
        rows.append({"s02_id": expected_id, "frozen_id": parent["id"],
                     "page": page, "text_start": start, "text_end": end})
    if any(pages[p]["text"][end:].strip() for p, end in cursors.items()):
        raise ValueError("S02 omitted non-whitespace source text")
    return copy.deepcopy({
        "model_input": {"document_id": case["document_id"], "source_segments": frozen},
        "provenance": {"adapter_version": "s01-s02-bridge-1", "case_id": case["id"],
                       "input_sha256": case["input_sha256"],
                       "s02_source_segments": segments, "mapping": rows},
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--case", help="Emit model input only; exclude expectations and source code")
    args = parser.parse_args()
    corpus = load_corpus(args.corpus)
    if args.case:
        case = next((c for c in corpus["cases"] if c["id"] == args.case), None)
        if case is None:
            parser.error("Unknown case")
        result = {k: case[k] for k in ("document_id", "source_segments")}
    else:
        result = dict(status="PASS", corpus_version=corpus["corpus_version"],
                      cases=len(corpus["cases"]), synthetic=True, teacher_validated=False,
                      source_commit=corpus["source_commit"])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
