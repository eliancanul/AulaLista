"""Transport fixtures test the evaluator, never Luna model quality."""

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from scripts.sprint_eval.luna import Candidate, FrozenCase, ProviderReply, run_case, run_frozen_corpus


class LunaBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.case = FrozenCase("doc-1", b"shared prompt", b"frozen source", b"frozen rubric")
        self.payload = {
            "document_id": "doc-1",
            "fields": [{"key": "grado", "value": "1ro", "evidence_ids": ["s1"]}],
            "draft": {"source_ids": ["s1", "s2"], "approval_status": "pending"},
        }

    def run_reply(self, text=None, validator=lambda payload: [], **metadata):
        reply = ProviderReply(
            "fixture-luna", json.dumps(self.payload) if text is None else text, **metadata
        )
        candidate = Candidate("fixture-luna", lambda model, prompt: reply, "fixture")
        times = iter([10.0, 10.125])
        return run_case(self.case, candidate, validator, clock=lambda: next(times))

    def test_unavailable_is_not_zero_cost_or_provider_evidence(self):
        result = run_case(self.case, None, lambda payload: self.fail("must not validate"))
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["provider_evidence"])
        self.assertIsNone(result["cost_usd"])
        self.assertIsNone(result["latency_ms"])

    def test_fixture_records_citations_latency_usage_without_claiming_model_evidence(self):
        result = self.run_reply(input_tokens=10, output_tokens=5)
        self.assertEqual(result["status"], "validated")
        self.assertFalse(result["provider_evidence"])
        self.assertEqual(result["citations"], ["s1", "s2"])
        self.assertEqual(result["latency_ms"], 125)
        self.assertEqual(result["usage"], {"input_tokens": 10, "output_tokens": 5})
        self.assertIsNone(result["cost_usd"])
        self.assertNotIn("draft", result)

    def test_prompt_is_passed_unchanged_once(self):
        calls = []
        def invoke(model, prompt):
            calls.append((model, prompt))
            return ProviderReply(model, json.dumps(self.payload))
        run_case(self.case, Candidate("fixture-luna", invoke, "fixture"), lambda p: [])
        self.assertEqual(calls, [("fixture-luna", b"shared prompt")])

    def test_input_fingerprints_detect_changed_corpus(self):
        first = run_case(self.case, None, lambda p: [])
        second = run_case(replace(self.case, corpus=b"changed"), None, lambda p: [])
        self.assertNotEqual(first["input_hashes"]["corpus"], second["input_hashes"]["corpus"])
        self.assertEqual(first["input_hashes"]["rubric"], second["input_hashes"]["rubric"])

    def test_malformed_json_duplicate_keys_and_nonfinite_values_fail(self):
        for text in ('', 'oops', '{"document_id":"doc-1","x":NaN}',
                     '{"document_id":"doc-1","x":1e999}',
                     '{"document_id":"other","document_id":"doc-1"}'):
            with self.subTest(text=text):
                self.assertEqual(self.run_reply(text)["validation_errors"], ["invalid_json"])

    def test_wrong_document_and_nonobject_fail(self):
        self.assertEqual(self.run_reply('[1]')["validation_errors"], ["expected_object"])
        self.assertEqual(self.run_reply('{}')["validation_errors"], ["document_id_mismatch"])

    def test_canonical_validator_failures_preserved(self):
        errors = ["unsupported_citation", "ambiguous_school_level", "automatic_approval"]
        result = self.run_reply(validator=lambda payload: errors)
        self.assertEqual(result["validation_errors"], errors)
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(result["citations"], [])

    def test_validator_exception_is_not_model_failure_and_hides_secrets(self):
        def fail(payload):
            raise RuntimeError("secret-source")
        result = self.run_reply(validator=fail)
        self.assertEqual(result["status"], "evaluator_error")
        self.assertNotIn("secret-source", json.dumps(result))

    def test_provider_error_hides_credentials_and_does_not_retry(self):
        calls = []
        def fail(model, prompt):
            calls.append(model)
            raise RuntimeError("Bearer secret")
        result = run_case(self.case, Candidate("fixture-luna", fail, "fixture"), lambda p: [])
        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(calls, ["fixture-luna"])
        self.assertNotIn("secret", json.dumps(result))

    def test_model_substitution_is_rejected(self):
        candidate = Candidate("luna", lambda m, p: ProviderReply("other", "{}"), "fixture")
        result = run_case(self.case, candidate, lambda p: [])
        self.assertEqual(result["validation_errors"], ["model_identity_mismatch"])
        self.assertFalse(result["provider_evidence"])

    def test_invalid_usage_and_price_never_become_measurements(self):
        for metadata in ({"input_tokens": True}, {"output_tokens": -1},
                         {"cost_usd": float("nan")}, {"cost_usd": -1}):
            with self.subTest(metadata=metadata):
                self.assertEqual(self.run_reply(**metadata)["status"], "provider_error")

    def test_reported_zero_cost_is_distinct_from_unknown(self):
        self.assertEqual(self.run_reply(cost_usd=0)["cost_usd"], 0)
        self.assertIsNone(self.run_reply()["cost_usd"])

    def test_broken_validator_contract_does_not_pass(self):
        self.assertEqual(self.run_reply(validator=lambda p: None)["status"], "evaluator_error")
        self.payload["fields"] = [None]
        self.assertEqual(self.run_reply()["status"], "evaluator_error")


class LunaFrozenCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import curriculum
        import scripts.sprint_eval

        # Before S20 integrates, explicitly opt into read-only sibling contracts.
        for package, variable, suffix in (
            (scripts.sprint_eval, "S05_CORPUS_WORKTREE", "scripts/sprint_eval"),
            (curriculum, "S05_SCHEMA_WORKTREE", "curriculum"),
        ):
            if variable in os.environ:
                package.__path__.append(str(Path(os.environ[variable]).resolve() / suffix))
        from curriculum.interpretation_schema import FIELD_QUESTIONS, INSUFFICIENT_SOURCE
        from scripts.sprint_eval.corpus import DEFAULT_CORPUS, load_corpus

        cls.directory = DEFAULT_CORPUS
        cls.corpus = load_corpus()
        cls.questions = FIELD_QUESTIONS
        cls.insufficient = INSUFFICIENT_SOURCE

    def fixture(self, case):
        expected = {field["key"]: field for field in case["expected_fields"]}
        fields = [
            {**copy.deepcopy(expected.get(key, {
                "key": key, "value": None, "status": "unknown", "evidence_ids": [],
            })), "reason": "Control sintético del evaluador."}
            for key in self.questions
        ]
        return {
            "schema_version": 1, "document_id": case["document_id"],
            "source_segments": copy.deepcopy(case["source_segments"]), "fields": fields,
            "missing_questions": [self.questions[f["key"]] for f in fields if f["status"] == "unknown"],
            "draft": {"title": __import__("curriculum.interpretation_schema", fromlist=["initial_title"]).initial_title(next(f for f in fields if f["key"] == "proyecto")), "objective": "", "materials": [],
                      "steps": [], "assessment": "", "source_ids": [], "revision": 1,
                      "approval_status": "pending", "status": self.insufficient},
            "diagnostics": {"method": "local_source_interpreter", "provider_status": "not_requested",
                            "attempts": 0, "errors": [], "model_winner": None,
                            "source_page_count": max(s["page"] for s in case["source_segments"]),
                            "source_warnings": []},
        }

    def run_fixtures(self, mutate=lambda payload: None, **metadata):
        cases = {case["document_id"]: case for case in self.corpus["cases"]}
        self.calls = []

        def invoke(model, prompt):
            self.calls.append((model, prompt))
            case = cases[json.loads(prompt)["document_id"]]
            payload = self.fixture(case)
            mutate(payload)
            return ProviderReply(model, json.dumps(payload, ensure_ascii=False), **metadata)

        times = iter(value for index in range(len(cases)) for value in (index, index + .125))
        return run_frozen_corpus(
            Candidate("fixture-luna-corpus", invoke, "fixture"), self.directory,
            clock=lambda: next(times),
        )

    def test_all_nine_cases_validate_with_real_contracts_and_auditable_records(self):
        rows = self.run_fixtures(input_tokens=10, output_tokens=5, cost_usd=0)
        self.assertEqual([r["case_id"] for r in rows], [f"SC{i:02}" for i in range(1, 10)])
        self.assertEqual(len(self.calls), 9)
        for case, row, (_, prompt) in zip(self.corpus["cases"], rows, self.calls):
            with self.subTest(case=case["id"]):
                self.assertEqual(row["status"], "validated")
                self.assertEqual(row["validation_errors"], [])
                self.assertEqual(row["rubric_result"]["status"], "PASS")
                self.assertEqual(row["rubric_result"]["counts"]["field_match"],
                                 [len(case["expected_fields"])] * 2)
                self.assertEqual(json.loads(prompt), {key: case[key] for key in ("document_id", "source_segments")})
                for name, data in (("prompt", prompt),
                                   ("corpus", (self.directory / "cases.v1.json").read_bytes()),
                                   ("rubric", (self.directory / "rubric.v1.json").read_bytes())):
                    self.assertEqual(row["input_hashes"][name], hashlib.sha256(data).hexdigest())
                self.assertEqual(row["response_sha256"], hashlib.sha256(
                    json.dumps(self.fixture(case), ensure_ascii=False).encode()).hexdigest())
                self.assertEqual(row["freeze_sha256"], hashlib.sha256(
                    (self.directory / "freeze.v1.json").read_bytes()).hexdigest())
                self.assertEqual(row["citations"], sorted({s for f in case["expected_fields"] for s in f["evidence_ids"]}))
                self.assertEqual(row["latency_ms"], 125)
                self.assertEqual(row["usage"], {"input_tokens": 10, "output_tokens": 5})
                self.assertEqual(row["cost_usd"], 0)
                self.assertEqual(row["evidence_kind"], "fixture")
                self.assertFalse(row["provider_evidence"])
                self.assertFalse(row["teacher_validated"])
                self.assertEqual(row["semantic_status"], "NOT_EVALUATED")
                self.assertNotIn("source_segments", row)
                self.assertNotIn("draft", row)

    def test_schema_source_and_approval_mutations_are_rejected_for_every_case(self):
        def change_source(p):
            p["source_segments"][0]["text"] += " Fuente inventada."

        def missing_reference(p):
            p["fields"][0].update(value="Inventado", status="suggested", evidence_ids=["absent"])

        def inferred_level(p):
            next(f for f in p["fields"] if f["key"] == "nivel_educativo").update(
                value="Primaria", status="suggested", evidence_ids=[p["source_segments"][0]["id"]])

        mutations = {
            "missing_schema": lambda p: p.pop("schema_version"),
            "wrong_field_type": lambda p: p.update(fields={}),
            "missing_reference": missing_reference,
            "draft_reference": lambda p: p["draft"].update(source_ids=["absent"]),
            "automatic_approval": lambda p: p["draft"].update(approval_status="approved"),
            "changed_source": change_source,
            "inferred_level": inferred_level,
        }
        for name, mutate in mutations.items():
            rows = self.run_fixtures(mutate, input_tokens=12, cost_usd=.01)
            for row in rows:
                with self.subTest(mutation=name, case=row["case_id"]):
                    self.assertEqual(row["status"], "invalid_response")
                    self.assertEqual(row["validation_errors"], ["interpretation_contract_invalid"])
                    self.assertIsNone(row["rubric_result"])
                    self.assertEqual(row["citations"], [])
                    self.assertEqual(row["latency_ms"], 125)
                    self.assertEqual(row["usage"]["input_tokens"], 12)
                    self.assertEqual(row["cost_usd"], .01)
                    self.assertIsNotNone(row["response_sha256"])
                    self.assertFalse(row["provider_evidence"])

    def test_rubric_catches_schema_valid_uncertainty_regression(self):
        def unknown_with_reference(p):
            next(f for f in p["fields"] if f["key"] == "nivel_educativo")["evidence_ids"] = [p["source_segments"][0]["id"]]

        for row in self.run_fixtures(unknown_with_reference):
            self.assertEqual(row["status"], "invalid_response")
            self.assertIn("unknown_asserts_value_or_evidence:nivel_educativo", row["validation_errors"])
            self.assertEqual(row["rubric_result"]["semantic_status"], "NOT_EVALUATED")
            self.assertEqual(row["citations"], [])

    def test_invalid_measurements_keep_all_cases_and_skip_scoring(self):
        for metadata in ({"input_tokens": -1}, {"cost_usd": float("inf")}, {"output_tokens": True}):
            rows = self.run_fixtures(**metadata)
            self.assertEqual(len(rows), 9)
            self.assertEqual(len(self.calls), 9)
            for row in rows:
                self.assertEqual(row["status"], "provider_error")
                self.assertIsNone(row["rubric_result"])
                self.assertFalse(row["provider_evidence"])
                key = next(iter(metadata))
                measurement = row["cost_usd"] if key == "cost_usd" else row["usage"][key]
                self.assertIsNone(measurement)

    def test_unavailable_keeps_nine_unmeasured_rows_without_provider_calls(self):
        rows = run_frozen_corpus(None, self.directory, clock=lambda: self.fail("No call expected"))
        self.assertEqual(len(rows), 9)
        for row in rows:
            self.assertEqual(row["status"], "blocked")
            self.assertIsNone(row["rubric_result"])
            self.assertIsNone(row["latency_ms"])
            self.assertIsNone(row["cost_usd"])
            self.assertFalse(row["provider_evidence"])

    def test_drift_is_rejected_before_invocation(self):
        candidate = Candidate("fixture", lambda *args: self.fail("Must verify before invoking"), "fixture")
        for filename in ("cases.v1.json", "rubric.v1.json"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory(
                dir=os.environ.get("AULALISTA_SCRATCH_DIR")
            ) as temporary:
                directory = Path(temporary) / "corpus"
                shutil.copytree(self.directory, directory)
                with (directory / filename).open("a") as output:
                    output.write(" ")
                with self.assertRaisesRegex(ValueError, "Frozen artifact mismatch"):
                    run_frozen_corpus(candidate, directory)


if __name__ == "__main__":
    unittest.main()
