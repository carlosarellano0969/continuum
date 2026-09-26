import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts import generate_synthetic_weeks as generator

CORPUS_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic_weeks"


class SyntheticWeeksTests(unittest.TestCase):
    def test_checked_in_corpus_matches_the_generator(self):
        with tempfile.TemporaryDirectory() as temporary:
            generator.generate(Path(temporary))
            for name in ("interactions.jsonl", "manifest.json"):
                self.assertEqual(
                    Path(temporary, name).read_bytes(),
                    Path(CORPUS_DIR, name).read_bytes(),
                    f"regenerate {name} with scripts/generate_synthetic_weeks.py",
                )

    def test_default_corpus_is_deterministic_and_spans_multiple_weeks(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = generator.generate(Path(first_dir))
            second = generator.generate(Path(second_dir))
            self.assertEqual(first, second)
            self.assertEqual(first["duration_days"], 30)
            self.assertEqual(first["interaction_count"], 30 * 48)
            self.assertEqual(Path(first_dir, "interactions.jsonl").read_bytes(), Path(second_dir, "interactions.jsonl").read_bytes())
            self.assertEqual(json.loads(Path(first_dir, "manifest.json").read_text(encoding="utf-8")), first)
            self.assertEqual(len(first["files"]), 1)
            interactions_bytes = Path(first_dir, "interactions.jsonl").read_bytes()
            self.assertEqual(first["files"][0]["sha256"], hashlib.sha256(interactions_bytes).hexdigest())

    def test_corpus_has_temporal_window_and_weekly_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = generator.generate(Path(temporary), days=21, per_day=16)
            rows = [json.loads(line) for line in Path(temporary, "interactions.jsonl").read_text(encoding="utf-8").splitlines()]
            timestamps = [datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00")) for row in rows]
            self.assertEqual(len(rows), 336)
            self.assertEqual(timestamps[0], generator.FIXTURE_EPOCH)
            self.assertLess(timestamps[-1], generator.FIXTURE_EPOCH.replace(tzinfo=timezone.utc) + generator.timedelta(days=21))
            self.assertEqual(set(manifest["weekly_summary"]), {"1", "2", "3"})

    def test_corpus_models_a_policy_transition_without_erasing_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = generator.generate(Path(temporary))
            rows = [json.loads(line) for line in Path(temporary, "interactions.jsonl").read_text(encoding="utf-8").splitlines()]
            baseline = [row for row in rows if row["observations"]["trend_phase"] == "baseline"]
            adaptation = [row for row in rows if row["observations"]["trend_phase"] == "adaptation"]
            self.assertEqual({row["policy_version"] for row in baseline}, {1})
            self.assertEqual({row["policy_version"] for row in adaptation}, {2})
            baseline_rate = sum(row["agent_action"] in generator.PREFERRED_POLICY_ACTIONS for row in baseline) / len(baseline)
            adaptation_rate = sum(row["agent_action"] in generator.PREFERRED_POLICY_ACTIONS for row in adaptation) / len(adaptation)
            self.assertGreater(adaptation_rate, baseline_rate)
            self.assertTrue(generator.CONTROL_ACTIONS <= {row["agent_action"] for row in adaptation})
            self.assertEqual(manifest["policy_transition_day"], 15)
            self.assertGreater(
                manifest["trend_summary"]["adaptation"]["preferred_policy_action_rate"],
                manifest["trend_summary"]["baseline"]["preferred_policy_action_rate"],
            )

    def test_validation_rejects_identifier_like_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = generator.generate(Path(temporary), days=14, per_day=8)
            rows = [json.loads(line) for line in Path(temporary, "interactions.jsonl").read_text(encoding="utf-8").splitlines()]
            rows[0]["scenario"] = "Contact synthetic@example.invalid for details"
            errors = generator.validate_interactions(rows, days=manifest["duration_days"])
            self.assertTrue(any("prohibited identifier-like" in error for error in errors))

    def test_every_row_is_explicitly_synthetic_and_schema_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            generator.generate(Path(temporary), days=14, per_day=8)
            rows = [json.loads(line) for line in Path(temporary, "interactions.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(rows)
            self.assertTrue(all(row["data_classification"] == "synthetic_non_sensitive" for row in rows))
            self.assertTrue(all(row["organization_id"] == "demo-org" and row["agent_id"] == "demo-agent" for row in rows))


if __name__ == "__main__":
    unittest.main()
