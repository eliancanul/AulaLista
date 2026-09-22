#!/usr/bin/env python3
"""Reproducible issue #96 benchmark for the five-page isolated fixture.

The baseline deliberately follows the public pipeline functions used by the
authoring flow.  The candidate uses the public ``build_annex_fast_path``
adapter when the checkout exposes it.  This script does not create a Django
job or write benchmark artifacts: JSON is emitted to stdout so a caller can
redirect it to a reviewable location.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import re
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "output/pdf/prueba-issue-96-paginas-4-a-8.pdf"
DEFAULT_RUNS = 5
EXPECTED_COLOUR_PAIRS = [
    ("a", "verde"),
    ("e", "amarillo"),
    ("i", "rojo"),
    ("o", "azul"),
    ("u", "anaranjado"),
]
EXPECTED_MATCHING_PAIRS = [
    ["a, e, i, o, u", "Vocales minúsculas"],
    ["A, E, I, O, U", "Vocales mayúsculas"],
    ["Vocales minúsculas", "Significa menor"],
    ["Vocales mayúsculas", "Significa mayor"],
]


class BenchmarkDeadline(Exception):
    """Raised by the outer benchmark deadline, before Ollama retries."""


def _normalise(value: object) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", value).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source_text(pages: list[str]) -> str:
    return "\n\n".join(
        f"[página {number}]\n{text}" for number, text in enumerate(pages, start=1)
    )


def _source_sections(source_text: str) -> dict[int, str]:
    markers = list(re.finditer(r"\[página\s+(\d+)\]", source_text, re.I))
    sections: dict[int, str] = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(source_text)
        sections[int(marker.group(1))] = source_text[marker.end() : end].strip()
    return sections


def _source_manifest(source_text: str) -> list[dict[str, Any]]:
    """Parse only explicit ``ANEXO # N`` headers, not inline references."""

    url_re = re.compile(r"https?://[^\s<>()]+", re.I)
    result = []
    for page, text in sorted(_source_sections(source_text).items()):
        header = re.search(r"^\s*ANEXO\s*#\s*(\d+)\b[^\n]*", text, re.I | re.M)
        if not header:
            continue
        urls = [match.rstrip(".,;:)") for match in url_re.findall(text)]
        result.append(
            {
                "number": int(header.group(1)),
                "page": page,
                "source_anchor": header.group(0).strip(),
                "source_url": urls[0] if urls else "",
                "source_urls": urls,
                "source_text": text,
                "source_text_sha256": _text_sha256(text),
            }
        )
    return result


def _colour_mapping(text: str) -> dict[str, str]:
    colours = "verde|amarillo|rojo|azul|anaranjado"
    return {
        vowel.lower(): colour.lower()
        for vowel, colour in re.findall(
            rf"\bVocal\s+([AEIOU])\s+({colours})\b", text, re.I
        )
    }


def _pdf_visual_quality(path: Path) -> dict[str, Any]:
    """Confirm resources, images, content streams, and non-empty rendering."""

    from pypdf import PdfReader

    reader = PdfReader(path)
    page_details = []
    for page in reader.pages:
        resources = page.get("/Resources")
        xobjects = resources.get("/XObject") if resources else None
        image_count = 0
        xobject_count = 0
        if xobjects:
            for reference in xobjects.values():
                try:
                    obj = reference.get_object()
                except Exception:
                    continue
                xobject_count += 1
                if obj.get("/Subtype") == "/Image":
                    image_count += 1
        contents = page.get("/Contents")
        try:
            content_data = contents.get_object().get_data() if contents else b""
            content_bytes = len(content_data)
        except Exception:
            content_data = b""
            content_bytes = 0
        xobject_hashes = []
        if xobjects:
            for name, reference in sorted(xobjects.items(), key=lambda item: str(item[0])):
                try:
                    data = reference.get_object().get_data()
                except Exception:
                    data = b""
                xobject_hashes.append({"name": str(name), "sha256": _text_sha256(data.hex())})
        page_hash_payload = json.dumps(
            {
                "xobjects": xobject_hashes,
                "content_sha256": _text_sha256(content_data.hex()),
            },
            sort_keys=True,
        )
        page_details.append(
            {
                "page": len(page_details) + 1,
                "has_resources": bool(resources),
                "xobject_count": xobject_count,
                "image_count": image_count,
                "content_bytes": content_bytes,
                "xobject_hashes": xobject_hashes,
                "content_sha256": _text_sha256(content_data.hex()),
                "page_sha256": _text_sha256(page_hash_payload),
            }
        )

    render_executable = next(
        (Path(candidate) for candidate in os.environ.get("PATH", "").split(os.pathsep)
         if (Path(candidate) / "pdftoppm").is_file()),
        None,
    )
    render_command = str(render_executable / "pdftoppm") if render_executable else None
    rendered_files: list[dict[str, Any]] = []
    render_error = ""
    if render_command:
        with tempfile.TemporaryDirectory(prefix="issue96-render-") as directory:
            prefix = Path(directory) / "page"
            completed = subprocess.run(
                [render_command, "-png", str(path), str(prefix)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if completed.returncode == 0:
                rendered_files = [
                    {"name": file.name, "bytes": file.stat().st_size}
                    for file in sorted(Path(directory).glob("page-*.png"))
                ]
            else:
                render_error = completed.stderr.strip() or "pdftoppm failed"
    else:
        render_error = "pdftoppm is unavailable"
    checks = {
        "every_page_has_resources": bool(page_details) and all(item["has_resources"] for item in page_details),
        "every_page_has_graphic_xobjects": bool(page_details) and all(item["image_count"] > 0 for item in page_details),
        "every_page_has_non_empty_content_stream": bool(page_details) and all(item["content_bytes"] > 0 for item in page_details),
        "every_page_rendered_to_non_empty_png": len(rendered_files) == len(page_details)
        and all(item["bytes"] > 0 for item in rendered_files),
        "pages_3_to_5_have_resource_hashes": len(page_details) >= 5
        and all(
            item["page_sha256"] and item["xobject_hashes"]
            for item in page_details[2:5]
        ),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "pages": page_details,
        "rendered_files": rendered_files,
        "render_error": render_error,
    }


def _source_quality(source_text: str) -> dict[str, Any]:
    manifest = _source_manifest(source_text)
    by_number = {item["number"]: item for item in manifest}
    annex1 = by_number.get(1, {}).get("source_text", "")
    annex2 = by_number.get(2, {}).get("source_text", "")
    annex3 = by_number.get(3, {}).get("source_text", "")
    blank_lines = [line.strip() for line in annex1.splitlines() if re.search(r"_{2,}", line)]
    blank_slots = sum(len(re.findall(r"_{2,}", line)) for line in blank_lines)
    mapping = _colour_mapping(annex2)
    normalized3 = _normalise(annex3)
    has_upper_vowels = bool(re.search(r"\bA\s*,\s*E\s*,\s*I\s*,\s*O\s*,\s*U\b", annex3))
    has_lower_vowels = bool(re.search(r"\ba\s*,\s*e\s*,\s*i\s*,\s*o\s*,\s*u\b", annex3))
    source_checks = {
        "annex_numbers_are_exactly_1_2_3": [item["number"] for item in manifest]
        == [1, 2, 3],
        "each_annex_has_video_url": all(
            bool(by_number.get(number, {}).get("source_urls")) for number in (1, 2, 3)
        ),
        "source_pages_are_present": [item["page"] for item in manifest] == [3, 4, 5],
        "annex_1_has_three_blank_lines": len(blank_lines) == 3,
        "annex_1_has_five_blank_slots": blank_slots == 5,
        "annex_1_mentions_five_vowels": "cinco vocales" in _normalise(annex1),
        "annex_2_has_exact_colour_pairs": list(mapping.items())
        == [("a", "verde"), ("e", "amarillo"), ("i", "rojo"), ("o", "azul"), ("u", "anaranjado")],
        "annex_3_has_upper_and_lower_groups": has_upper_vowels and has_lower_vowels and all(
            phrase in normalized3
            for phrase in (
                "a, e, i, o, u",
                "vocales mayusculas",
                "vocales minusculas",
                "significa mayor",
                "significa menor",
            )
        ),
    }
    return {
        "pass": all(source_checks.values()),
        "checks": source_checks,
        "manifest": [
            {
                key: item[key]
                for key in (
                    "number",
                    "page",
                    "source_anchor",
                    "source_url",
                    "source_urls",
                    "source_text_sha256",
                )
            }
            for item in manifest
        ],
        "annex_1": {
            "blank_lines": len(blank_lines),
            "blank_slots": blank_slots,
            "blank_lines_text": blank_lines,
            "vowels_instruction": next(
                (
                    line.strip().rstrip(":")
                    for line in annex1.splitlines()
                    if "cinco vocales" in _normalise(line)
                ),
                "",
            ),
        },
        "annex_2": {"mapping": mapping},
        "annex_3": {"has_upper_lower_groups": source_checks["annex_3_has_upper_and_lower_groups"]},
    }


def _proposal_text(proposal: dict[str, Any]) -> str:
    return json.dumps(proposal, ensure_ascii=False)


def _candidate_quality(
    source_quality: dict[str, Any],
    candidate: dict[str, Any],
    *,
    resource_hashes_match: bool = True,
) -> dict[str, Any]:
    expected = {item["number"]: item for item in source_quality["manifest"]}
    activities = candidate.get("activities", [])
    activity_numbers = [item.get("annex", {}).get("number") for item in activities]
    by_number = {item.get("annex", {}).get("number"): item for item in activities}
    candidate_manifest = candidate.get("manifest", [])
    expected_manifest = source_quality["manifest"]
    manifest_fields = ("number", "page", "source_anchor", "source_url", "source_urls")
    manifest_equal = len(candidate_manifest) == len(expected_manifest)
    if manifest_equal:
        for actual, wanted in zip(candidate_manifest, expected_manifest):
            actual_hash = _text_sha256(str(actual.get("source_text", "")))
            manifest_equal = manifest_equal and all(
                actual.get(field) == wanted.get(field) for field in manifest_fields
            ) and actual_hash == wanted.get("source_text_sha256")
            if not manifest_equal:
                break
    checks: dict[str, bool] = {
        "candidate_has_three_activities": len(activities) == 3,
        "candidate_annex_numbers_are_exactly_1_2_3": activity_numbers == [1, 2, 3],
        "candidate_manifest_matches_source_exactly": manifest_equal,
    }
    fill = by_number.get(1, {}).get("annex", {})
    colour = by_number.get(2, {}).get("annex", {})
    matching = by_number.get(3, {}).get("annex", {})
    fill_proposal = by_number.get(1, {}).get("proposal", {})
    colour_proposal = by_number.get(2, {}).get("proposal", {})
    matching_proposal = by_number.get(3, {}).get("proposal", {})
    checks.update(
        {
            "annex_1_three_huecos_five_slots": fill.get("details", {}).get("blank_count")
            == source_quality["annex_1"]["blank_slots"] == 5
            and fill.get("details", {}).get("blanks")
            == source_quality["annex_1"]["blank_lines_text"],
            "annex_2_colour_mapping_preserved": list(colour.get("details", {}).get("mapping", {}).items())
            == EXPECTED_COLOUR_PAIRS
            and len(colour_proposal.get("questions", [])) == 5,
            "annex_3_matching_preserved": matching.get("details", {}).get("pairs", [])
            == EXPECTED_MATCHING_PAIRS
            and len(matching_proposal.get("questions", [])) == 4,
            "candidate_source_text_matches_manifest": all(
                _text_sha256(str(by_number.get(number, {}).get("annex", {}).get("source_text", "")))
                == expected[number]["source_text_sha256"]
                for number in (1, 2, 3)
            ),
            "candidate_source_pages_match_manifest": all(
                by_number.get(number, {}).get("annex", {}).get("source_pages")
                == [expected[number]["page"]]
                for number in (1, 2, 3)
            ),
            "candidate_urls_match_manifest": all(
                by_number.get(number, {}).get("annex", {}).get("source_url")
                == expected[number]["source_url"]
                and by_number.get(number, {}).get("annex", {}).get("source_urls")
                == expected[number]["source_urls"]
                for number in (1, 2, 3)
            ),
            "candidate_pdf_resource_hashes_match_source": resource_hashes_match,
            "annex_1_requires_human_answer_key": fill.get("details", {}).get("requires_human_answer_key") is True,
            "annex_1_has_no_auto_score_or_invented_key": fill.get("details", {}).get("non_evaluable") is True
            and fill.get("auto_score") is not True
            and "answer_key" not in fill
            and not fill_proposal.get("questions")
            and not any(
                "expected" in option
                for question in fill_proposal.get("questions", [])
                for option in question.get("value", {}).get("options", [])
            ),
            "every_question_has_one_expected_option_and_hint": all(
                sum(option.get("expected") is True for option in question.get("value", {}).get("options", [])) == 1
                and bool(question.get("value", {}).get("hints"))
                for item in activities
                if item.get("annex", {}).get("number") != 1
                for question in item.get("proposal", {}).get("questions", [])
            ),
            "annex_2_questions_match_exact_colour_mapping": all(
                _expected_option_text(question) == dict(EXPECTED_COLOUR_PAIRS).get(
                    _question_vowel(question)
                )
                for question in colour_proposal.get("questions", [])
            ),
            "annex_3_questions_match_exact_pairs": all(
                _expected_option_text(question) == pair[1]
                for question, pair in zip(
                    matching_proposal.get("questions", []), EXPECTED_MATCHING_PAIRS
                )
            ),
        }
    )
    return {"pass": all(checks.values()), "checks": checks}


def _question_vowel(question: dict[str, Any]) -> str:
    match = re.search(r"vocal\s+([aeiou])", str(question.get("value", {}).get("prompt", "")), re.I)
    return match.group(1).lower() if match else ""


def _expected_option_text(question: dict[str, Any]) -> str:
    expected = [
        option.get("text", "")
        for option in question.get("value", {}).get("options", [])
        if option.get("expected") is True
    ]
    return expected[0] if len(expected) == 1 else ""


def _mutation_self_test(source_quality: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Prove the semantic gate rejects changed color and matching answers."""

    mutations = {}
    for label, activity_number, question_index in (
        ("colour", 2, 0),
        ("matching", 3, 0),
    ):
        mutated = copy.deepcopy(candidate)
        activity = next(item for item in mutated["activities"] if item["annex"]["number"] == activity_number)
        options = activity["proposal"]["questions"][question_index]["value"]["options"]
        expected = next(option for option in options if option.get("expected") is True)
        replacement = next(option for option in options if option is not expected)
        expected["expected"] = False
        replacement["expected"] = True
        mutations[f"{label}_mutation_rejected"] = not _candidate_quality(
            source_quality, mutated, resource_hashes_match=True
        )["pass"]
    mutations["pass"] = all(mutations.values())
    return mutations


def _visual_hashes(visual_quality: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "page": item["page"],
            "page_sha256": item["page_sha256"],
            "content_sha256": item["content_sha256"],
            "xobject_hashes": item["xobject_hashes"],
        }
        for item in visual_quality.get("pages", [])[2:5]
    ]


def _candidate_result(
    source_quality: dict[str, Any],
    candidate: dict[str, Any],
    visual_reference: dict[str, Any],
    visual_observed: dict[str, Any],
    started: float,
    **extra: Any,
) -> dict[str, Any]:
    hashes_match = _visual_hashes(visual_reference) == _visual_hashes(visual_observed)
    quality = _candidate_quality(
        source_quality, candidate, resource_hashes_match=hashes_match
    )
    mutation = _mutation_self_test(source_quality, candidate)
    quality["mutation_self_test"] = mutation
    quality["pass"] = quality["pass"] and mutation["pass"]
    return {
        "status": "complete"
        if quality["pass"] and source_quality["pass"] and visual_observed["pass"]
        else "quality_failed",
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "llm_call_count": 0,
        "activity_count": len(candidate.get("activities", [])),
        "quality": {
            "source": source_quality,
            "pdf_visual": visual_observed,
            "candidate": quality,
        },
        "resource_hashes_match": hashes_match,
        **extra,
    }


def _metadata(path: Path, pipeline: Any, deadline: float | None) -> dict[str, Any]:
    options = {
        "temperature": 0,
        "stream": False,
        "structured_format": "JSON schema",
        "chat_timeout_seconds": pipeline.CHAT_TIMEOUT_SECONDS,
        "max_attempts": pipeline.MAX_ATTEMPTS,
        "chunk_max_chars": pipeline.CHUNK_MAX_CHARS,
        "benchmark_deadline_seconds": deadline,
    }
    return {
        "pdf": str(path),
        "pdf_sha256": _sha256(path),
        "model": pipeline.llm_model(),
        "ollama_url": pipeline.ollama_url(),
        "options": options,
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
    }


def _deadline(seconds: float):
    def alarm(_signum: int, _frame: Any) -> None:
        raise BenchmarkDeadline(f"benchmark deadline exceeded ({seconds:g}s)")

    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)


def _clear_deadline() -> None:
    signal.setitimer(signal.ITIMER_REAL, 0)


def _run_baseline_once(pipeline: Any, path: Path, deadline: float | None) -> dict[str, Any]:
    started = time.perf_counter()
    pages: list[str] = []
    traces: list[dict[str, Any]] = []
    stages: dict[str, Any] = {}
    timeout_stage = ""
    if deadline:
        _deadline(deadline)
    try:
        stage_start = time.perf_counter()
        pages = pipeline.extract_pdf_pages(path)
        source = _source_text(pages)
        chunks = pipeline.chunk_pages(pages)
        stages["extract_and_chunk_ms"] = round((time.perf_counter() - stage_start) * 1000)
        stage_start = time.perf_counter()
        pipeline.start_llm_trace()
        proposals = [pipeline.identify_topics(chunk) for chunk in chunks]
        stages["identify_topics_ms"] = round((time.perf_counter() - stage_start) * 1000)
        stage_start = time.perf_counter()
        candidates = pipeline.consolidate_topics(proposals)
        topics = pipeline.consolidate_topics_semantic(candidates)
        stages["consolidation_ms"] = round((time.perf_counter() - stage_start) * 1000)
        stage_start = time.perf_counter()
        activities = []
        for topic in topics:
            context = pipeline.context_for_pages(
                source, topic["pagina_inicio"], topic["pagina_fin"]
            )
            subtopics = pipeline.propose_subtopics(topic["titulo"], context)
            for subtopic in subtopics["subtemas"]:
                activities.append(
                    pipeline.propose_activities(
                        subtopic,
                        source,
                        subtopics["actividades_sugeridas"],
                    )
                )
        stages["subtopics_and_activities_ms"] = round((time.perf_counter() - stage_start) * 1000)
        traces = pipeline.stop_llm_trace()
        return {
            "status": "complete",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "stages_ms": stages,
            "llm_call_count": len(traces),
            "llm_trace": traces,
            "activity_count": len(activities),
            "quality": {
                "source": _source_quality(source),
                "generated_text": {"available": bool(activities)},
            },
        }
    except BenchmarkDeadline as error:
        timeout_stage = "subtopics_and_activities" if stages.get("consolidation_ms") else "identify_topics"
        try:
            traces = pipeline.stop_llm_trace()
        except Exception:
            traces = []
        return {
            "status": "timeout_censored",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "stages_ms": stages,
            "llm_call_count": len(traces),
            "llm_trace": traces,
            "timeout_stage": timeout_stage,
            "error": str(error),
            "quality": {"source": _source_quality(_source_text(pages)) if pages else None},
        }
    finally:
        if deadline:
            _clear_deadline()


def _run_candidate_adapter_once(
    pipeline: Any, path: Path, visual_quality: dict[str, Any]
) -> dict[str, Any]:
    started = time.perf_counter()
    pages = pipeline.extract_pdf_pages(path)
    source = _source_text(pages)
    source_quality = _source_quality(source)
    builder = getattr(pipeline, "build_annex_fast_path", None)
    if not callable(builder):
        return {
            "status": "unavailable",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "error": "No public build_annex_fast_path interface is available in this checkout.",
            "quality": {"source": source_quality, "pdf_visual": visual_quality},
        }
    try:
        candidate = builder(source)
    except Exception as error:  # pragma: no cover - defensive adapter boundary
        return {
            "status": "failed",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "error": f"Public build_annex_fast_path raised {type(error).__name__}: {error}",
            "quality": {"source": source_quality, "pdf_visual": visual_quality},
        }
    if candidate is None:
        return {
            "status": "failed",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "error": "Public build_annex_fast_path returned None for this fixture.",
            "quality": {"source": source_quality, "pdf_visual": visual_quality},
        }
    observed_visual = _pdf_visual_quality(path)
    result = _candidate_result(
        source_quality,
        candidate,
        visual_quality,
        observed_visual,
        started,
        stages_ms={"extract_and_fast_path_ms": round((time.perf_counter() - started) * 1000)},
        scope="adapter",
    )
    return result


class _RollbackBenchmark(Exception):
    pass


def _run_candidate_job_once(
    pipeline: Any, path: Path, visual_quality: dict[str, Any]
) -> dict[str, Any]:
    """Exercise the real extract worker and roll back its temporary job."""

    from django.contrib.auth import get_user_model
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db import transaction
    from django.test.utils import override_settings

    from curriculum.models import CurriculumImportJob
    from curriculum.views import _import_action_extract

    started = time.perf_counter()
    source_bytes = path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="issue96-media-") as media_root:
        try:
            with override_settings(MEDIA_ROOT=media_root):
                with transaction.atomic():
                    user = get_user_model().objects.create_user(
                        username=f"issue96-benchmark-{time.time_ns()}", is_staff=True
                    )
                    job = CurriculumImportJob.objects.create(
                        pdf=SimpleUploadedFile(
                            path.name, source_bytes, content_type="application/pdf"
                        ),
                        created_by=user,
                    )
                    _import_action_extract(job, pipeline)
                    job.refresh_from_db()
                    persisted_pdf_path = Path(job.pdf.path)
                    persisted_visual = _pdf_visual_quality(persisted_pdf_path)
                    candidate = {
                        "manifest": pipeline.extract_annex_manifest(job.source_text),
                        "activities": job.activities,
                    }
                    result = _candidate_result(
                        _source_quality(job.source_text),
                        candidate,
                        visual_quality,
                        persisted_visual,
                        started,
                        scope="job",
                        job_status=job.status,
                        job_status_expected=CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
                        persisted_pdf_path=str(persisted_pdf_path),
                        conversion_performed=False,
                        publication_performed=False,
                        llm_trace=job.llm_trace,
                        llm_call_count=len(job.llm_trace or []),
                        stages_ms={"extract_and_worker_ms": round((time.perf_counter() - started) * 1000)},
                    )
                    if job.status != CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED:
                        result["status"] = "quality_failed"
                    raise _RollbackBenchmark
        except _RollbackBenchmark:
            pass
    return result


def _run_candidate_once(
    pipeline: Any,
    path: Path,
    visual_quality: dict[str, Any],
    scope: str,
) -> dict[str, Any]:
    if scope == "adapter":
        return _run_candidate_adapter_once(pipeline, path, visual_quality)
    return _run_candidate_job_once(pipeline, path, visual_quality)


def _summarise(runs: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [run["elapsed_ms"] for run in runs if run.get("status") == "complete"]
    if not complete:
        return {"runs": len(runs), "complete_runs": 0, "median_ms": None, "p95_ms": None}
    percentile = sorted(complete)[min(len(complete) - 1, max(0, int(0.95 * len(complete) + 0.5) - 1))]
    return {
        "runs": len(runs),
        "complete_runs": len(complete),
        "median_ms": round(statistics.median(complete)),
        "p95_ms": percentile,
    }


def _ollama_ps() -> str:
    try:
        return subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, timeout=3, check=False
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--mode", choices=("baseline", "candidate", "both"), default="both")
    parser.add_argument(
        "--candidate-scope",
        choices=("adapter", "job"),
        default="job",
        help="Candidate seam to measure; job is the final gate, adapter is the fast smoke path.",
    )
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument(
        "--baseline-lower-bound-elapsed-ms",
        type=float,
        default=None,
        help="Evidence-backed censored baseline lower bound for conservative comparison only.",
    )
    parser.add_argument(
        "--deadline-seconds",
        type=float,
        default=None,
        help="Outer censoring deadline per run; default is Ollama CHAT_TIMEOUT_SECONDS.",
    )
    parser.add_argument(
        "--quality-only",
        action="store_true",
        help="Run only fixture and candidate quality checks; does not call Ollama.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.pdf if args.pdf.is_absolute() else ROOT / args.pdf
    if not path.is_file():
        print(json.dumps({"status": "error", "error": f"PDF not found: {path}"}))
        return 2
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import django

    django.setup()
    from curriculum import curriculum_import as pipeline

    deadline = args.deadline_seconds
    if deadline is None and not args.quality_only:
        deadline = float(pipeline.CHAT_TIMEOUT_SECONDS)
    pages = pipeline.extract_pdf_pages(path)
    source = _source_text(pages)
    source_quality = _source_quality(source)
    visual_quality = _pdf_visual_quality(path)
    output: dict[str, Any] = {
        "benchmark": "issue-96-annexes",
        "metadata": _metadata(path, pipeline, deadline),
        "ollama_ps": _ollama_ps(),
        "quality_only": args.quality_only,
        "quality": {
            "pass": source_quality["pass"] and visual_quality["pass"],
            "source": source_quality,
            "pdf_visual": visual_quality,
        },
    }
    if args.mode in ("candidate", "both"):
        if args.quality_only:
            candidate_warmup = [
                _run_candidate_once(pipeline, path, visual_quality, args.candidate_scope)
            ]
            candidate_runs: list[dict[str, Any]] = []
        else:
            candidate_warmup = [
                _run_candidate_once(pipeline, path, visual_quality, args.candidate_scope)
                for _ in range(max(0, args.warmup))
            ]
            candidate_runs = [
                _run_candidate_once(pipeline, path, visual_quality, args.candidate_scope)
                for _ in range(max(1, args.runs))
            ]
        output["candidate"] = {
            "warmup": candidate_warmup,
            "runs": candidate_runs,
            "summary": _summarise(candidate_runs or candidate_warmup),
        }
    if args.quality_only:
        return _emit(output)
    if args.mode in ("baseline", "both"):
        for _ in range(max(0, args.warmup)):
            _run_baseline_once(pipeline, path, deadline)
        runs = [_run_baseline_once(pipeline, path, deadline) for _ in range(max(1, args.runs))]
        output["baseline"] = {"runs": runs, "summary": _summarise(runs)}
        candidate_summary = output.get("candidate", {}).get("summary", {})
        baseline_summary = output["baseline"]["summary"]
        if baseline_summary.get("median_ms") and candidate_summary.get("median_ms"):
            output["comparison"] = {
                "median_speedup_percent": round(
                    (1 - candidate_summary["median_ms"] / baseline_summary["median_ms"])
                    * 100,
                    2,
                ),
                "is_final_50_percent_gate": candidate_summary["median_ms"]
                <= baseline_summary["median_ms"] * 0.5,
                "note": "Compare only runs with complete status and the same fixture/options.",
            }
        elif (
            not baseline_summary.get("median_ms")
            and args.baseline_lower_bound_elapsed_ms is not None
            and candidate_summary.get("p95_ms") is not None
        ):
            lower_bound = args.baseline_lower_bound_elapsed_ms
            output["conservative_comparison"] = {
                "baseline_lower_bound_elapsed_ms": lower_bound,
                "candidate_p95_ms": candidate_summary["p95_ms"],
                "proven_at_least_50_percent_faster": candidate_summary["p95_ms"]
                <= lower_bound * 0.5,
                "note": "Censored baseline: no baseline median/p95 or statistical speedup claim is made.",
            }
    return _emit(output)


def _emit(output: dict[str, Any]) -> int:
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
