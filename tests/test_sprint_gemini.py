import copy
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.sprint_eval.gemini import (
    ExperimentCase, GeminiAdapter, ProviderError, _NoRedirect, _request_json,
    run_contract_fixture, _digest, main,
)


MODEL = "gemini-test-fixture"
CASE = ExperimentCase("synthetic-1", [{"id": "s1", "text": "1ro. Leer un cuento.", "page": 1}])
SCHEMA = {"type": "object"}


def output():
    return {**copy.deepcopy(CASE.payload()), "fields": [
        {"key": "grado", "value": "1ro", "status": "extracted", "evidence_ids": ["s1"]},
        {"key": "nivel", "value": None, "status": "unknown", "evidence_ids": []},
    ], "missing_questions": ["¿Cuál es el nivel escolar?"], "draft": {
        "title": "Leemos un cuento", "objective": "Comentar un cuento",
        "materials": [], "steps": [], "assessment": "Conversación",
        "source_ids": ["s1"], "revision": 1, "approval_status": "pending"}}


def response(value=None):
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": json.dumps(output() if value is None else value)}]}}],
        "modelVersion": "fixture-version", "usageMetadata": {
            "promptTokenCount": 100, "candidatesTokenCount": 40,
            "thoughtsTokenCount": 20, "totalTokenCount": 160}}


class Transport:
    def __init__(self, generation=None, pages=None):
        self.calls = []
        self.pages = list(pages) if pages is not None else [{"models": [
            {"name": "models/" + MODEL, "supportedGenerationMethods": ["generateContent"]}]}]
        self.generation = generation if generation is not None else response()

    def __call__(self, method, path, key, body, timeout):
        self.calls.append((method, path, body, timeout))
        value = self.pages.pop(0) if method == "GET" else self.generation
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


class GeminiTests(unittest.TestCase):
    def run_fixture(self, transport=None, validate=lambda value: None, cases=None):
        transport = transport or Transport()
        return GeminiAdapter("fake-key", transport=transport).run_corpus(
            cases or [CASE], model=MODEL, schema=SCHEMA, validate=validate)

    def test_missing_credentials_makes_no_request(self):
        transport = Transport()
        with patch.dict("os.environ", {}, clear=True):
            result = GeminiAdapter(transport=transport).preflight(MODEL)
        self.assertEqual(result["reason"], "missing_credentials")
        self.assertEqual(transport.calls, [])

    def test_blocked_real_adapter_records_no_provider_evidence(self):
        with patch.dict("os.environ", {}, clear=True):
            result = GeminiAdapter().run_corpus([CASE], model=MODEL, schema=SCHEMA,
                                                validate=lambda value: None)
        self.assertEqual(result["evidence_kind"], "no_provider_response")
        self.assertEqual(result["real_response_count"], 0)
        row = result["results"][0]
        self.assertEqual(row["reason"], "missing_credentials")
        self.assertIsNone(row["latency_ms"])
        self.assertIsNone(row["cost_usd"])

    def test_display_name_and_path_injection_are_not_model_ids(self):
        for model in ("Gemini 3.8", "gemini-3.8?key=oops", "models/../gemini-test", "gemini-x/y"):
            with self.subTest(model=model):
                transport = Transport()
                result = GeminiAdapter("fake-key", transport=transport).preflight(model)
                self.assertEqual(result["reason"], "exact_model_id_required")
                self.assertEqual(transport.calls, [])

    def test_discovery_paginates_and_resolves_only_exact_name(self):
        transport = Transport(pages=[{"models": [], "nextPageToken": "a&b"}, {
            "models": [{"name": "models/" + MODEL, "version": "test",
                        "supportedGenerationMethods": ["generateContent"]}]}])
        result = GeminiAdapter("fake-key", transport=transport).preflight(MODEL)
        self.assertEqual(result["resolved_model"], "models/" + MODEL)
        self.assertIn("pageToken=a%26b", transport.calls[1][1])

    def test_similar_model_never_becomes_fallback(self):
        result = GeminiAdapter("fake-key", transport=Transport()).preflight("gemini-3.8")
        self.assertEqual(result["reason"], "model_not_listed")
        self.assertIsNone(result["resolved_model"])

    def test_unsupported_model_blocks_generation(self):
        transport = Transport(pages=[{"models": [{"name": "models/" + MODEL,
                                                   "supportedGenerationMethods": ["embedContent"]}]}])
        result = self.run_fixture(transport)
        self.assertEqual(result["results"][0]["reason"], "generate_content_unsupported")
        self.assertEqual(len(transport.calls), 1)

    def test_discovery_cycles_and_malformed_responses_fail_closed(self):
        for pages, reason in [([{"nextPageToken": "loop"}] * 2, "invalid_pagination"),
                              ([{"models": None}], "invalid_discovery_response")]:
            with self.subTest(reason=reason):
                result = GeminiAdapter("fake-key", transport=Transport(pages=pages)).preflight(MODEL)
                self.assertEqual(result["reason"], reason)

    def test_fixture_records_never_claim_provider_results_or_free_cost(self):
        result = self.run_fixture()
        row = result["results"][0]
        self.assertEqual(result["evidence_kind"], "fixture")
        self.assertEqual(result["real_response_count"], 0)
        self.assertFalse(row["provider_response_received"])
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["usage"]["thoughtsTokenCount"], 20)
        self.assertIsNone(row["cost_usd"])
        self.assertEqual(row["cost_status"], "unpriced_usage")
        self.assertEqual(row["model_version"], "fixture-version")
        self.assertEqual(row["source_fidelity"], "references_checked_semantics_require_review")
        self.assertGreaterEqual(row["latency_ms"], 0)

    def test_request_uses_supplied_schema_and_original_sources(self):
        transport = Transport()
        self.run_fixture(transport)
        method, path, body, timeout = transport.calls[1]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "models/" + MODEL + ":generateContent")
        self.assertEqual(body["generationConfig"]["responseJsonSchema"], SCHEMA)
        self.assertEqual(json.loads(body["contents"][0]["parts"][0]["text"]), CASE.payload())
        self.assertEqual(timeout, 30)

    def test_forged_or_changed_sources_and_automatic_approval_are_rejected(self):
        altered = []
        value = output()
        value["source_segments"][0]["text"] = "Inventado"
        altered.append(value)
        value = output()
        value["fields"][0]["evidence_ids"] = ["inventado"]
        altered.append(value)
        value = output()
        value["fields"][0]["evidence_ids"] = []
        altered.append(value)
        value = output()
        value["draft"]["approval_status"] = "approved"
        altered.append(value)
        value = output()
        value["draft"]["source_ids"] = ["inventado"]
        altered.append(value)
        value = output()
        value["document_id"] = "wrong-document"
        altered.append(value)
        for value in altered:
            with self.subTest(value=value):
                row = self.run_fixture(Transport(generation=response(value)))["results"][0]
                self.assertEqual(row["status"], "invalid_output")
                self.assertIsNone(row["output"])

    def test_external_semantic_validator_can_reject_inferred_school_level(self):
        def validate(value):
            raise ValueError("S06 semantic rejection containing private input")
        row = self.run_fixture(validate=validate)["results"][0]
        self.assertEqual(row["status"], "invalid_output")
        self.assertNotIn("private", json.dumps(row))

    def test_truncated_safety_blocked_and_non_json_outputs_are_rejected(self):
        truncated = response()
        truncated["candidates"][0]["finishReason"] = "MAX_TOKENS"
        blocked = {"promptFeedback": {"blockReason": "SAFETY"}}
        malformed = response()
        malformed["candidates"][0]["content"]["parts"][0]["text"] = "not JSON"
        for value in (truncated, blocked, malformed, response([])):
            with self.subTest(value=value):
                row = self.run_fixture(Transport(generation=value))["results"][0]
                self.assertIn(row["status"], ("error", "invalid_output"))
                self.assertIsNone(row["output"])

    def test_thought_parts_are_not_joined_into_json(self):
        value = response()
        value["candidates"][0]["content"]["parts"].insert(0, {"thought": True, "text": "private thought"})
        result = self.run_fixture(Transport(generation=value))
        self.assertEqual(result["results"][0]["status"], "ok")
        self.assertNotIn("private thought", json.dumps(result))

    def test_quota_stops_corpus_without_retry_or_fake_timings(self):
        transport = Transport(generation=ProviderError("quota_exceeded"))
        result = self.run_fixture(transport, cases=[CASE, ExperimentCase("synthetic-2", CASE.source_segments)])
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertEqual(result["results"][1]["status"], "blocked")
        self.assertIsNone(result["results"][1]["latency_ms"])

    def test_no_usage_is_unknown_not_zero(self):
        value = response()
        del value["usageMetadata"]
        row = self.run_fixture(Transport(generation=value))["results"][0]
        self.assertIsNone(row["usage"])
        self.assertIsNone(row["cost_usd"])
        self.assertEqual(row["cost_status"], "usage_unavailable")

    def test_invalid_inputs_do_not_contact_provider(self):
        transport = Transport()
        adapter = GeminiAdapter("fake-key", transport=transport)
        for cases in ([CASE, CASE], [ExperimentCase("bad", [])],
                      [ExperimentCase("bad", CASE.source_segments * 2)]):
            with self.subTest(cases=cases), self.assertRaises(ValueError):
                adapter.run_corpus(cases, model=MODEL, schema=SCHEMA, validate=lambda value: None)
        self.assertEqual(transport.calls, [])

    def test_validator_and_output_budget_are_required(self):
        adapter = GeminiAdapter("fake-key", transport=Transport())
        with self.assertRaises(ValueError):
            adapter.run_corpus([CASE], model=MODEL, schema=SCHEMA, validate=None)
        with self.assertRaises(ValueError):
            adapter.run_corpus([CASE], model=MODEL, schema=SCHEMA, validate=lambda value: None,
                               max_output_tokens=100000)

    def test_http_errors_are_sanitized_and_credentials_stay_in_header(self):
        error = HTTPError("https://example.invalid/?secret", 429, "private", {}, io.BytesIO(b"secret"))
        with patch("scripts.sprint_eval.gemini.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaisesRegex(ProviderError, "^quota_exceeded$"):
                _request_json("GET", "models", "secret", None, 30)
            request = opener.return_value.open.call_args.args[0]
        self.assertNotIn("secret", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "secret")

    def test_redirects_cannot_forward_key(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid"))

    def test_http_transport_rejects_oversized_and_invalid_json(self):
        for raw, reason in [(b"x" * (4 * 1024 * 1024 + 1), "response_too_large"),
                            (b"not-json", "invalid_response"), (b"[]", "invalid_response")]:
            with self.subTest(reason=reason), patch("scripts.sprint_eval.gemini.build_opener") as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = raw
                with self.assertRaisesRegex(ProviderError, "^" + reason + "$"):
                    _request_json("GET", "models", "fake", None, 30)


class ContractVersionTests(unittest.TestCase):
    def test_contract_drift_rejected_before_corpus_or_transport(self):
        for version, published in ((2, 2), (3, 3), (1, 2), (2, 1), (None, 1),
                                   (True, 1), (1, True), (1, None)):
            contract = {"SCHEMA_VERSION": version, "interpretation_json_schema": lambda: {
                "properties": {"schema_version": {"const": published}}}}
            with self.subTest(version=version, published=published), patch(
                "scripts.sprint_eval.gemini.runpy.run_path", return_value=contract
            ) as load, patch("scripts.sprint_eval.gemini.GeminiAdapter") as adapter:
                result = run_contract_fixture(Path("missing-corpus"), Path("schema"))
                self.assertEqual(result["status"], "incompatible_contract")
                self.assertEqual(result["reason"], "unsupported_fixture_schema_version")
                self.assertEqual(result["supported_schema_versions"], [1])
                self.assertEqual(result["results"], [])
                self.assertEqual(result["real_response_count"], 0)
                self.assertEqual(result["contract_schema_version"], version)
                self.assertEqual(result["published_schema_version"], published)
                self.assertEqual(load.call_count, 1)
                adapter.assert_not_called()

    def test_cli_incompatible_contract_is_not_empty_success(self):
        contract = {"SCHEMA_VERSION": 2, "interpretation_json_schema": lambda: {
            "properties": {"schema_version": {"const": 2}}}}
        with patch("scripts.sprint_eval.gemini.runpy.run_path", return_value=contract), patch(
            "sys.argv", ["gemini.py", "--fixture-corpus", "missing", "--schema-root", "schema"]
        ), patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(main(), 2)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["status"], "incompatible_contract")
        self.assertEqual(result["v1_schema_commit"], "1c4bbc27e85706764033ba778451b143f5132706")

    def test_current_published_contract_has_explicit_outcome(self):
        root = Path(__file__).resolve().parents[1]
        schema_root = root if (root / "curriculum/interpretation_schema.py").exists() else root.parent / "S06"
        corpus_root = root if (root / "scripts/sprint_eval/corpus.py").exists() else root.parent / "S01"
        contract = runpy.run_path(str(schema_root / "curriculum/interpretation_schema.py"))
        with patch("scripts.sprint_eval.gemini._request_json", side_effect=AssertionError("Network forbidden")):
            result = run_contract_fixture(corpus_root, schema_root)
        if contract["SCHEMA_VERSION"] == 1:
            self.assertEqual(len(result["results"]), 9)
            self.assertTrue(all(row["status"] == "ok" for row in result["results"]))
        else:
            self.assertEqual(result["status"], "incompatible_contract")
            self.assertEqual(result["contract_schema_version"], contract["SCHEMA_VERSION"])
            self.assertEqual(result["results"], [])


class PublishedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.corpus_root = Path(os.environ.get("S04_CORPUS_ROOT", str(
            root if (root / "scripts/sprint_eval/corpus.py").exists() else root.parent / "S01")))
        cls.schema_root = Path(os.environ.get("S04_SCHEMA_ROOT", str(
            root if (root / "curriculum/interpretation_schema.py").exists() else root.parent / "S06")))
        with patch("scripts.sprint_eval.gemini._request_json", side_effect=AssertionError("Network forbidden")):
            cls.result = run_contract_fixture(cls.corpus_root, cls.schema_root)
        if cls.result.get("status") == "incompatible_contract":
            raise unittest.SkipTest("Legacy v1 checks require S04_SCHEMA_ROOT at "
                                    + cls.result["v1_schema_commit"])
        cls.contract = runpy.run_path(str(cls.schema_root / "curriculum/interpretation_schema.py"))

    def test_published_nine_cases_are_complete_and_fixture_only(self):
        result = self.result
        self.assertEqual(result["real_response_count"], 0)
        self.assertEqual(result["provider_comparison"], "BLOCKED")
        self.assertIsNone(result["model_winner"])
        self.assertEqual([r["case_id"] for r in result["results"]],
                         ["SC01", "SC02", "SC03", "SC04", "SC05", "SC06", "SC07", "SC08", "SC09"])
        for row in result["results"]:
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["evidence_kind"], "fixture")
            self.assertFalse(row["provider_response_received"])
            self.assertIsNone(row["provider_latency_ms"])
            self.assertIsNone(row["cost_usd"])
            self.assertIsNone(row["usage"])
            self.assertEqual(row["semantic_status"], "NOT_EVALUATED")
            self.assertEqual(row["output_sha256"], _digest(row["output"]))
            self.assertTrue(all(f["status"] == "unknown" and f["value"] is None
                                for f in row["output"]["fields"]))

    def test_expected_answers_never_enter_transport(self):
        run = GeminiAdapter.run_corpus
        inputs = []

        def capture(adapter, cases, **kwargs):
            transport = adapter._transport

            def inspect(method, path, key, body, timeout):
                if method == "POST":
                    inputs.append(json.loads(body["contents"][0]["parts"][0]["text"]))
                    self.assertEqual(body["generationConfig"]["responseJsonSchema"],
                                     self.contract["interpretation_json_schema"]())
                return transport(method, path, key, body, timeout)

            adapter._transport = inspect
            return run(adapter, cases, **kwargs)

        with patch.object(GeminiAdapter, "run_corpus", capture):
            run_contract_fixture(self.corpus_root, self.schema_root)
        self.assertEqual(len(inputs), 9)
        self.assertTrue(all(set(value) == {"document_id", "source_segments"} for value in inputs))

    def test_s06_rejects_forgery_approval_and_inferred_level(self):
        baseline = self.result["results"][7]["output"]
        case = ExperimentCase(baseline["document_id"], baseline["source_segments"])

        def validate(value):
            self.contract["validate_interpretation"](
                value, expected_document_id=case.document_id, source_segments=case.source_segments)

        for defect in ("source", "approval", "level", "document"):
            value = copy.deepcopy(baseline)
            if defect == "source":
                value["source_segments"][0]["text"] = "Fuente inventada"
            elif defect == "approval":
                value["draft"]["approval_status"] = "approved"
            elif defect == "document":
                value["document_id"] = "SC09"
            else:
                field = next(f for f in value["fields"] if f["key"] == "nivel_educativo")
                field.update(value="Primaria", status="suggested",
                             evidence_ids=[case.source_segments[0]["id"]])
            with self.subTest(defect=defect):
                result = GeminiAdapter("fixture-only", transport=Transport(generation=response(value))).run_corpus(
                    [case], model=MODEL, schema=self.contract["interpretation_json_schema"](), validate=validate)
                self.assertEqual(result["results"][0]["status"], "invalid_output")
                self.assertIsNone(result["results"][0]["output"])

    def test_cli_produces_json_and_does_not_mix_live_and_fixture_modes(self):
        script = str(Path(__file__).resolve().parents[1] / "scripts/sprint_eval/gemini.py")
        args = [sys.executable, script, "--fixture-corpus", str(self.corpus_root),
                "--schema-root", str(self.schema_root)]
        completed = subprocess.run(args, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(completed.stdout)["evidence_kind"], "fixture")
        rejected = subprocess.run(args + ["--model", "gemini-live"], capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(rejected.stdout, "")


if __name__ == "__main__":
    unittest.main()
