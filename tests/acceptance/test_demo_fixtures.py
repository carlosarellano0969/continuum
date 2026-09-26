from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from scripts import generate_demo_data as generator


REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "data" / "demo"
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def walk(value):
    yield value
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class DemoFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DEMO_DIR / "manifest.json").read_text(encoding="utf-8"))
        cls.interactions = read_jsonl(DEMO_DIR / "interactions.jsonl")
        cls.memories = read_jsonl(DEMO_DIR / "memories.jsonl")
        cls.retrieval = json.loads((DEMO_DIR / "retrieval_cases.json").read_text(encoding="utf-8"))

    def test_checked_in_fixture_matches_generator_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as temporary:
            generated_dir = Path(temporary)
            generator.generate(
                generated_dir,
                seed=self.manifest["seed"],
                count=self.manifest["interaction_count"],
            )
            for filename in (
                "interactions.jsonl",
                "memories.jsonl",
                "retrieval_cases.json",
                "manifest.json",
            ):
                self.assertEqual(
                    (DEMO_DIR / filename).read_bytes(),
                    (generated_dir / filename).read_bytes(),
                    f"{filename} is stale; regenerate the checked-in fixture",
                )

    def test_manifest_counts_and_hashes_match(self):
        self.assertGreaterEqual(len(self.interactions), generator.MIN_COUNT)
        self.assertLessEqual(len(self.interactions), generator.MAX_COUNT)
        self.assertEqual(len(self.interactions), self.manifest["interaction_count"])
        files = {entry["path"]: entry for entry in self.manifest["files"]}
        for filename, expected_records in {
            "interactions.jsonl": len(self.interactions),
            "memories.jsonl": len(self.memories),
            "retrieval_cases.json": len(self.retrieval["cases"]),
        }.items():
            content = (DEMO_DIR / filename).read_bytes()
            self.assertEqual(files[filename]["bytes"], len(content))
            self.assertEqual(files[filename]["records"], expected_records)
            self.assertEqual(files[filename]["sha256"], hashlib.sha256(content).hexdigest())

    def test_interaction_ids_timestamps_and_scope_are_stable(self):
        ids = [item["interaction_id"] for item in self.interactions]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [f"ix-{number:04d}" for number in range(1, len(ids) + 1)])
        for item in self.interactions:
            self.assertEqual(item["organization_id"], "demo-org")
            self.assertEqual(item["agent_id"], "demo-agent")
            self.assertTrue(item["occurred_at"].endswith("Z"))
            self.assertEqual(item["data_classification"], "synthetic_non_sensitive")

    def test_two_patterns_are_strong_and_distractor_is_insufficient(self):
        patterns = self.manifest["patterns"]
        for name in (
            generator.PATTERN_FINANCING,
            generator.PATTERN_DISCOUNT,
        ):
            pattern = patterns[name]
            self.assertEqual(pattern["evidence_strength"], "strong")
            self.assertGreaterEqual(
                pattern["baseline"]["count"], pattern["minimum_group_size"]
            )
            self.assertGreaterEqual(
                pattern["candidate"]["count"], pattern["minimum_group_size"]
            )
            self.assertGreaterEqual(
                pattern["absolute_success_lift"],
                pattern["minimum_absolute_success_lift"],
            )

        distractor = patterns[generator.PATTERN_DISTRACTOR]
        distractor_total = distractor["baseline"]["count"] + distractor["candidate"]["count"]
        self.assertEqual(distractor["evidence_strength"], "insufficient")
        self.assertLess(distractor_total, 20)
        self.assertLessEqual(distractor_total, distractor["maximum_total_evidence"])

    def test_manifest_and_interactions_match_approved_pattern_scope(self):
        patterns = self.manifest["patterns"]
        self.assertEqual(
            set(patterns),
            {
                "financing_pricing_fast_information",
                "generic_discount_first_underperformance",
                "small_sample_source_uplift",
            },
        )

        financing = patterns["financing_pricing_fast_information"]
        self.assertEqual(financing["baseline_action"], "deferred_financing_follow_up")
        self.assertEqual(financing["candidate_action"], "fast_financing_information")

        discount = patterns["generic_discount_first_underperformance"]
        self.assertEqual(discount["baseline_action"], "generic_discount_first_reply")
        self.assertEqual(discount["candidate_action"], "needs_based_pricing_explanation")
        self.assertLess(
            discount["baseline"]["success_rate"], discount["candidate"]["success_rate"]
        )

        source_items = [
            item
            for item in self.interactions
            if item["pattern_tag"] == "small_sample_source_uplift"
        ]
        self.assertTrue(source_items)
        self.assertTrue(
            all(
                item["observations"]["lead_source"] == "regional_partner_directory"
                for item in source_items
            )
        )
        self.assertLess(len(source_items), 20)

    def test_fixture_contains_no_sensitive_fields_or_obvious_identifiers(self):
        prohibited = set(self.manifest["safety"]["prohibited_fields"])
        for value in walk({
            "interactions": self.interactions,
            "memories": self.memories,
            "retrieval": self.retrieval,
        }):
            if isinstance(value, str):
                self.assertNotIn(value.lower(), prohibited)
                self.assertIsNone(EMAIL_RE.search(value))
                self.assertIsNone(SSN_RE.search(value))
                self.assertIsNone(PHONE_RE.search(value))

    def test_known_answer_retrieval_cases_resolve_to_memory_fixtures(self):
        memory_ids = {memory["id"] for memory in self.memories}
        self.assertEqual(len(memory_ids), len(self.memories))
        case_ids = set()
        for case in self.retrieval["cases"]:
            self.assertNotIn(case["case_id"], case_ids)
            case_ids.add(case["case_id"])
            required = set(case["required_memory_ids"])
            allowed = set(case["allowed_support_memory_ids"])
            forbidden = set(case["forbidden_memory_ids"])
            self.assertTrue(required)
            self.assertTrue(required <= memory_ids)
            self.assertTrue(allowed <= memory_ids)
            self.assertTrue(forbidden <= memory_ids)
            self.assertFalse(required & forbidden)
            self.assertLessEqual(len(required | allowed), case["max_results"])

    def test_generator_rejects_counts_outside_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            with self.assertRaises(ValueError):
                generator.generate(target, count=generator.MIN_COUNT - 1)
            with self.assertRaises(ValueError):
                generator.generate(target, count=generator.MAX_COUNT + 1)

    def test_generator_supports_both_count_boundaries(self):
        for count in (generator.MIN_COUNT, generator.MAX_COUNT):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temporary:
                manifest = generator.generate(Path(temporary), seed=7, count=count)
                self.assertEqual(manifest["interaction_count"], count)
                for pattern_name in (
                    generator.PATTERN_FINANCING,
                    generator.PATTERN_DISCOUNT,
                ):
                    pattern = manifest["patterns"][pattern_name]
                    self.assertGreaterEqual(
                        pattern["baseline"]["count"], pattern["minimum_group_size"]
                    )
                    self.assertGreaterEqual(
                        pattern["candidate"]["count"], pattern["minimum_group_size"]
                    )
                    self.assertGreaterEqual(
                        pattern["absolute_success_lift"],
                        pattern["minimum_absolute_success_lift"],
                    )
                distractor = manifest["patterns"][generator.PATTERN_DISTRACTOR]
                total = distractor["baseline"]["count"] + distractor["candidate"]["count"]
                self.assertLess(total, 20)


if __name__ == "__main__":
    unittest.main()
