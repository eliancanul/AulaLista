"""Validate the frozen synthetic reference without importing any implementation.

This file deliberately uses only stdlib. Run it directly to avoid application or
pytest-plugin initialization. It is not a matcher, prediction adapter or scorer.
"""

import hashlib
import json
from pathlib import Path
import unittest
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests/fixtures/interpretation/session_declarations_mixed_fields_v1.json"
CONTRACT = ROOT / "docs/development/session-declarations-mixed-fields-v1.md"
REFERENCE_SHA256 = "cffc43ca220904ebf38e50b9be8e83a919f1beaeae01cbea07c124508256dc8b"
SOURCE_SHA256 = "570b412ecaed11e286349526a405bcfd68d0a3e546f79c08026bae6e8f95c297"
COUNTS = {"documents": 70, "recoveries": 24, "rejections": 48, "typed_controls": 2}


class MixedFieldsReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference_bytes = REFERENCE.read_bytes()
        cls.reference = json.loads(cls.reference_bytes)
        cls.docs = {doc["id"]: doc for doc in cls.reference["documents"]}

    def assert_span(self, doc, span):
        self.assertEqual(set(span), {"page", "start", "end", "quote"})
        for key in ("page", "start", "end"):
            self.assertIs(type(span[key]), int)
        self.assertIs(type(span["quote"]), str)
        self.assertLessEqual(1, span["page"])
        self.assertLessEqual(span["page"], len(doc["pages"]))
        page = doc["pages"][span["page"] - 1]
        self.assertLessEqual(0, span["start"])
        self.assertLess(span["start"], span["end"])
        self.assertLessEqual(span["end"], len(page))
        self.assertEqual(page[span["start"]:span["end"]], span["quote"])

    def test_frozen_bytes_and_source_first_digest(self):
        self.assertEqual(hashlib.sha256(self.reference_bytes).hexdigest(), REFERENCE_SHA256)
        sources = [{"id": doc["id"], "pages": doc["pages"]}
                   for doc in self.reference["documents"]]
        encoded = json.dumps(sources, ensure_ascii=False, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), SOURCE_SHA256)
        self.assertEqual(self.reference["source_first_sha256"], SOURCE_SHA256)
        contract = CONTRACT.read_text(encoding="utf-8")
        self.assertIn(REFERENCE_SHA256, contract)
        self.assertIn(SOURCE_SHA256, contract)

    def test_strict_top_level_and_document_schema(self):
        self.assertEqual(set(self.reference), {
            "version", "reference_kind", "source_first_sha256", "source_freeze_stage",
            "documents", "default_mixed_fields", "enabled_patch_contract", "counts",
        })
        self.assertEqual(self.reference["version"], "session-declarations-mixed-fields-reference.v1")
        self.assertEqual(self.reference["reference_kind"], "synthetic_source_only")
        self.assertEqual(self.reference["source_freeze_stage"], "sources_written_before_expectations")
        self.assertIs(self.reference["default_mixed_fields"], False)
        self.assertEqual(len(self.docs), len(self.reference["documents"]))
        for doc in self.docs.values():
            with self.subTest(document=doc["id"]):
                self.assertEqual(set(doc), {"id", "tags", "pages", "expected_recoveries",
                                            "expected_rejections", "typed_controls"})
                self.assertIs(type(doc["id"]), str)
                self.assertTrue(doc["id"])
                self.assertTrue(doc["pages"])
                self.assertTrue(all(type(page) is str for page in doc["pages"]))
                self.assertEqual(len(doc["tags"]), len(set(doc["tags"])))
                self.assertTrue(doc["expected_recoveries"] or doc["expected_rejections"]
                                or doc["typed_controls"])

    def test_patch_never_retypes_reassigns_or_creates_claims(self):
        self.assertEqual(self.reference["enabled_patch_contract"], {
            "requires_existing_record": {"kind": None, "decision": "abstained",
                                          "reason": "combined_label", "claim": None},
            "only_added_evidence_role": "value",
            "preserve_record_fields": ["id", "kind", "decision", "reason", "unit", "claim"],
            "preserve_prior_evidence": True,
            "preserve_other_records": True,
            "unit_effect": "preserve_existing",
            "new_units": 0,
            "new_claims": 0,
            "typed_detection_credit": False,
            "limits": {"max_value_codepoints": 2048, "max_nonempty_value_lines": 32},
        })

    def test_all_authored_spans_are_original_exact_slices(self):
        annotation_ids = set()
        for doc in self.docs.values():
            for record in doc["expected_recoveries"]:
                with self.subTest(document=doc["id"], recovery=record["id"]):
                    self.assertEqual(set(record), {"id", "label", "value", "closing_heading",
                                                   "context", "context_reset"})
                    self.assertNotIn(record["id"], annotation_ids)
                    annotation_ids.add(record["id"])
                    for key in ("label", "value", "closing_heading"):
                        self.assert_span(doc, record[key])
                    self.assertIn(record["context"], {
                        "session_metadata", "initial_metadata", "continuation_metadata"})
                    if record["context_reset"] is not None:
                        self.assert_span(doc, record["context_reset"])
                        self.assertEqual(record["context_reset"]["page"], record["label"]["page"])
                        self.assertLessEqual(record["context_reset"]["end"], record["label"]["start"])
                        self.assertEqual(record["context"], "session_metadata")
                    else:
                        self.assertNotEqual(record["context"], "session_metadata")
            for record in doc["expected_rejections"]:
                self.assertEqual(set(record), {"id", "anchor", "category", "expected_effect"})
                self.assertNotIn(record["id"], annotation_ids)
                annotation_ids.add(record["id"])
                self.assert_span(doc, record["anchor"])
                self.assertEqual(record["expected_effect"], "no_value_added")
                self.assertTrue(record["category"])
            for record in doc["typed_controls"]:
                self.assertEqual(set(record), {"kind", "label", "value", "expected_effect"})
                self.assertIn(record["kind"], {"contenido", "pda"})
                self.assert_span(doc, record["label"])
                self.assert_span(doc, record["value"])
                self.assertEqual(record["expected_effect"], "unchanged_by_mixed_fields")

    def test_recoveries_are_complete_page_local_bounded_values(self):
        for doc in self.docs.values():
            for record in doc["expected_recoveries"]:
                with self.subTest(document=doc["id"], recovery=record["id"]):
                    label, value, closer = (record[key] for key in ("label", "value", "closing_heading"))
                    self.assertEqual(label["page"], value["page"])
                    self.assertEqual(value["page"], closer["page"])
                    self.assertLessEqual(label["end"], value["start"])
                    self.assertLess(value["end"], closer["start"])
                    page = doc["pages"][value["page"] - 1]
                    self.assertEqual(page[label["end"]:value["start"]].strip(), "")
                    self.assertEqual(page[value["end"]:closer["start"]].strip(), "")
                    self.assertEqual(label["quote"], label["quote"].strip())
                    self.assertTrue(label["quote"].endswith(":"))
                    text = value["quote"]
                    self.assertEqual(text, text.strip())
                    self.assertLessEqual(len(text), 2048)
                    self.assertLessEqual(sum(bool(line.strip()) for line in text.splitlines()), 32)
                    without_crlf = text.replace("\r\n", "\n")
                    self.assertTrue(all(ch == "\n" or unicodedata.category(ch) not in {"Cc", "Cf"}
                                        for ch in without_crlf))
                    self.assertNotIn("\u2028", text)
                    self.assertNotIn("\u2029", text)

    def test_fixed_denominators_and_positive_negative_tags(self):
        actual = {"documents": len(self.docs), "recoveries": 0, "rejections": 0, "typed_controls": 0}
        for doc in self.docs.values():
            actual["recoveries"] += len(doc["expected_recoveries"])
            actual["rejections"] += len(doc["expected_rejections"])
            actual["typed_controls"] += len(doc["typed_controls"])
            self.assertEqual("positive" in doc["tags"], bool(doc["expected_recoveries"]))
            self.assertEqual("negative" in doc["tags"], bool(doc["expected_rejections"]))
            self.assertEqual("control" in doc["tags"], bool(doc["typed_controls"]))
        self.assertEqual(actual, COUNTS)
        self.assertEqual(self.reference["counts"], COUNTS)

    def test_required_source_diversity_and_safety_challenges(self):
        tags = {tag for doc in self.docs.values() for tag in doc["tags"]}
        self.assertTrue({
            "multimarker", "wrapped", "codes", "sentence", "generic", "crlf", "unicode",
            "nfd", "repeated", "inline_value", "wrapped_metadata", "compositional_closer",
            "no_closure", "cross_page", "interleaving", "typed_child", "inline_mention",
            "table", "quoted", "mismatched_quote", "inherited_quote", "example",
            "nonadoption", "conditional", "negated", "character_limit", "line_limit",
            "control_character", "activity_middle", "spurious_reset", "genuine_reset",
            "activity_context", "no_mixed_reset", "typed_control", "no_unit_inference",
        }.issubset(tags))
        self.assertEqual(len(self.docs["whole_block_2048"]["expected_recoveries"][0]["value"]["quote"]), 2048)
        self.assertIn("á" * 2049, self.docs["over_character_limit"]["pages"][0])
        lines = self.docs["whole_block_32_lines"]["expected_recoveries"][0]["value"]["quote"].splitlines()
        self.assertEqual(len(lines), 32)
        self.assertIn("* Marca 33.", self.docs["over_line_limit"]["pages"][0])

    def test_repetitions_and_multimarkers_are_never_split(self):
        records = self.docs["repeated_values"]["expected_recoveries"]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["value"]["quote"], records[1]["value"]["quote"])
        self.assertNotEqual(records[0]["value"]["start"], records[1]["value"]["start"])
        self.assertNotEqual(records[0]["label"]["start"], records[1]["label"]["start"])
        self.assertNotEqual(records[0]["context_reset"], records[1]["context_reset"])
        multiline = self.docs["multimarker_wrapped"]["expected_recoveries"]
        self.assertEqual(len(multiline), 1)
        self.assertIn("\n- ", multiline[0]["value"]["quote"])
        self.assertIn("\n• ", multiline[0]["value"]["quote"])
        self.assertEqual(self.docs["code_expression"]["expected_recoveries"][0]["value"]["quote"],
                         "AB7(PDA1,PDA2)")
        self.assertIn("\r\n", self.docs["crlf"]["expected_recoveries"][0]["value"]["quote"])
        self.assertIn("n\u0303", self.docs["unicode"]["expected_recoveries"][0]["value"]["quote"])

    def test_resets_are_source_context_only_and_blockers_cross_pages(self):
        reset_doc = self.docs["genuine_session_reset"]
        self.assertEqual(len(reset_doc["expected_rejections"]), 1)
        self.assertEqual(len(reset_doc["expected_recoveries"]), 1)
        self.assertEqual(reset_doc["expected_recoveries"][0]["context_reset"]["quote"], "Sesión 51")
        for key in ("quote_spurious_session", "spurious_metadata_reset", "cross_page_quote_context",
                    "cross_page_activity_context", "activity_context_no_reset"):
            self.assertEqual(self.docs[key]["expected_recoveries"], [])
        fragment = self.docs["cross_page_late_label"]["expected_recoveries"][0]
        self.assertEqual(fragment["context"], "continuation_metadata")
        self.assertIsNone(fragment["context_reset"])
        self.assertEqual(fragment["label"]["page"], 2)
        self.assertNotIn("unit", fragment)
        self.assertNotIn("unit_id", fragment)


if __name__ == "__main__":
    unittest.main()
