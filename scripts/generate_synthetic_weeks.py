#!/usr/bin/env python3
"""Expand an Ollama-reviewed scenario blueprint into a deterministic corpus.

This corpus is additive to ``data/demo``. The checked-in demo fixture remains
the small golden regression set; this generator is for multi-week trend,
retrieval, and persistence stress checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.generate_demo_data import FIXTURE_EPOCH, _metric_bundle, _stable_success, _utc_iso
except ModuleNotFoundError:  # Direct invocation from the scripts directory.
    from generate_demo_data import FIXTURE_EPOCH, _metric_bundle, _stable_success, _utc_iso


DEFAULT_SEED = 20260924
DEFAULT_DAYS = 30
DEFAULT_PER_DAY = 48
FORMAT_VERSION = "continuum.synthetic.weeks.v1"
OLLAMA_MODEL = "gpt-oss:20b"
ADAPTATION_START_DAY = 14
SAFE_SEGMENTS = {"budget_planner", "first_time_buyer", "value_seeker", "feature_comparer", "general_inquiry"}
PREFERRED_POLICY_ACTIONS = {"fast_financing_information", "needs_based_pricing_explanation"}
CONTROL_ACTIONS = {"deferred_financing_follow_up", "generic_discount_first_reply"}
FORBIDDEN_TEXT = re.compile(r"(?:@|\+?\d[\d ()-]{7,}\d|ssn|social security|credit card|password|api[_ -]?key)", re.IGNORECASE)

# Reviewed by the local Ollama worker; kept as data so the expansion remains deterministic.
SCENARIO_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "pattern_tag": "financing_pricing_fast_information",
        "scenario": "A synthetic prospective buyer asks for financing and monthly pricing information.",
        "inquiry_type": "financing_and_pricing",
        "synthetic_segment": "budget_planner",
        "action": "fast_financing_information",
        "preferred": True,
        "outcome_bias": "high_success",
    },
    {
        "pattern_tag": "financing_pricing_fast_information",
        "scenario": "A synthetic prospective buyer asks for financing and monthly pricing information.",
        "inquiry_type": "financing_and_pricing",
        "synthetic_segment": "first_time_buyer",
        "action": "deferred_financing_follow_up",
        "preferred": False,
        "outcome_bias": "moderate_success",
    },
    {
        "pattern_tag": "generic_discount_first_underperformance",
        "scenario": "A synthetic prospective buyer raises a general pricing concern before choosing a next step.",
        "inquiry_type": "pricing_objection",
        "synthetic_segment": "value_seeker",
        "action": "needs_based_pricing_explanation",
        "preferred": True,
        "outcome_bias": "high_success",
    },
    {
        "pattern_tag": "generic_discount_first_underperformance",
        "scenario": "A synthetic prospective buyer raises a general pricing concern before choosing a next step.",
        "inquiry_type": "pricing_objection",
        "synthetic_segment": "feature_comparer",
        "action": "generic_discount_first_reply",
        "preferred": False,
        "outcome_bias": "low_success",
    },
    {
        "pattern_tag": "small_sample_source_uplift",
        "scenario": "A synthetic inquiry arrives from a regional partner directory source.",
        "inquiry_type": "product_research",
        "synthetic_segment": "general_inquiry",
        "action": "source_tailored_reply",
        "preferred": True,
        "outcome_bias": "high_success",
    },
    {
        "pattern_tag": "small_sample_source_uplift",
        "scenario": "A synthetic inquiry arrives from a regional partner directory source.",
        "inquiry_type": "product_research",
        "synthetic_segment": "general_inquiry",
        "action": "standard_source_reply",
        "preferred": False,
        "outcome_bias": "moderate_success",
    },
    {
        "pattern_tag": "background_mix",
        "scenario": "A synthetic prospective buyer asks a feature question.",
        "inquiry_type": "feature_question",
        "synthetic_segment": "general_inquiry",
        "action": "standard_resolution",
        "preferred": False,
        "outcome_bias": "moderate_success",
    },
    {
        "pattern_tag": "background_mix",
        "scenario": "A synthetic prospective buyer asks a availability question.",
        "inquiry_type": "availability_question",
        "synthetic_segment": "feature_comparer",
        "action": "clarifying_question",
        "preferred": False,
        "outcome_bias": "moderate_success",
    },
)

BASELINE_TEMPLATE_INDICES = tuple(range(len(SCENARIO_TEMPLATES)))
# Ollama proposed a phase split; the implementation deliberately retains every
# control template while increasing the two policy-preferred actions.
ADAPTATION_TEMPLATE_INDICES = (0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 1, 3, 4, 5, 6, 7)

BIAS_RATES = {"high_success": 86, "moderate_success": 58, "low_success": 29}


def _write_json(path: Path, value: Any) -> dict[str, Any]:
    content = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(content)
    return {"path": path.name, "bytes": len(content), "records": content.count(b"\n"), "sha256": hashlib.sha256(content).hexdigest()}


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> dict[str, Any]:
    content = ("".join(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n" for value in values)).encode("utf-8")
    path.write_bytes(content)
    return {"path": path.name, "bytes": len(content), "records": len(values), "sha256": hashlib.sha256(content).hexdigest()}


def _interaction(template: dict[str, Any], ordinal: int, occurred_at: datetime, rng: random.Random, seed: int) -> dict[str, Any]:
    rate = BIAS_RATES[template["outcome_bias"]]
    success = _stable_success(ordinal, seed + len(template["action"]), rate)
    preferred = bool(template["preferred"])
    base_handle = 360 if "financing" in template["inquiry_type"] else 350
    observations = {
        "inquiry_type": template["inquiry_type"],
        "synthetic_segment": template["synthetic_segment"],
        "sentiment": rng.choice(("curious", "uncertain", "ready_to_compare")),
        "week_index": ((occurred_at - FIXTURE_EPOCH).days // 7) + 1,
        "trend_phase": "baseline" if (occurred_at - FIXTURE_EPOCH).days < ADAPTATION_START_DAY else "adaptation",
    }
    if template["pattern_tag"] == "small_sample_source_uplift":
        observations["lead_source"] = "regional_partner_directory"
        observations["source_context_available"] = preferred
    if template["inquiry_type"] == "financing_and_pricing":
        observations["asks_monthly_payment_question"] = True
        observations["financing_information_delivery_seconds"] = rng.randint(20, 75) if preferred else rng.randint(240, 720)
    if template["inquiry_type"] == "pricing_objection":
        observations["needs_discovery_complete"] = preferred
        observations["generic_discount_offered_first"] = not preferred
    metrics = _metric_bundle(rng, success, preferred, base_handle)
    metrics["next_step_accepted"] = success
    metrics["week_index"] = observations["week_index"]
    metrics["trend_phase"] = observations["trend_phase"]
    return {
        "interaction_id": f"wk-{ordinal:05d}",
        "organization_id": "demo-org",
        "agent_id": "demo-agent",
        "occurred_at": _utc_iso(occurred_at),
        "scenario": template["scenario"],
        "customer": {
            "synthetic_segment": observations.pop("synthetic_segment"),
            "account_tenure_band": rng.choice(("under_90_days", "90_to_365_days", "over_365_days")),
            "locale": "en-US",
        },
        "observations": observations,
        "policy_version": 1 if observations["trend_phase"] == "baseline" else 2,
        "agent_action": template["action"],
        "result": "resolved" if success else "unresolved",
        "metrics": metrics,
        "pattern_tag": template["pattern_tag"],
        "data_classification": "synthetic_non_sensitive",
    }


def validate_interactions(interactions: list[dict[str, Any]], *, days: int) -> list[str]:
    errors: list[str] = []
    expected_ids = {f"wk-{index:05d}" for index in range(1, len(interactions) + 1)}
    actual_ids = {item.get("interaction_id") for item in interactions}
    if actual_ids != expected_ids:
        errors.append("interaction_id values must be unique and sequential")
    start = FIXTURE_EPOCH
    end = start + timedelta(days=days)
    for item in interactions:
        occurred_at = datetime.fromisoformat(item["occurred_at"].replace("Z", "+00:00"))
        if not start <= occurred_at < end:
            errors.append(f"{item['interaction_id']} is outside the requested date window")
        if item.get("data_classification") != "synthetic_non_sensitive":
            errors.append(f"{item['interaction_id']} has an unsafe data classification")
        if item.get("customer", {}).get("synthetic_segment") not in SAFE_SEGMENTS:
            errors.append(f"{item['interaction_id']} has an unknown synthetic segment")
        content_fields = {key: value for key, value in item.items() if key not in {"occurred_at", "interaction_id"}}
        if FORBIDDEN_TEXT.search(json.dumps(content_fields, sort_keys=True)):
            errors.append(f"{item['interaction_id']} contains a prohibited identifier-like value")
        success = item["result"] == "resolved"
        if success and item["metrics"]["customer_satisfaction"] < 4:
            errors.append(f"{item['interaction_id']} has an inconsistent successful satisfaction score")
    baseline = [item for item in interactions if item["observations"]["trend_phase"] == "baseline"]
    adaptation = [item for item in interactions if item["observations"]["trend_phase"] == "adaptation"]
    if any(item["policy_version"] != 1 for item in baseline):
        errors.append("baseline interactions must use policy version 1")
    if days > ADAPTATION_START_DAY:
        if not adaptation:
            errors.append("an adaptation phase is required after the transition day")
        elif any(item["policy_version"] != 2 for item in adaptation):
            errors.append("adaptation interactions must use policy version 2")
        else:
            baseline_rate = sum(item["agent_action"] in PREFERRED_POLICY_ACTIONS for item in baseline) / len(baseline)
            adaptation_rate = sum(item["agent_action"] in PREFERRED_POLICY_ACTIONS for item in adaptation) / len(adaptation)
            if adaptation_rate <= baseline_rate:
                errors.append("adaptation must increase preferred policy actions")
            if not CONTROL_ACTIONS.issubset({item["agent_action"] for item in adaptation}):
                errors.append("adaptation must retain nonpreferred control actions")
    return sorted(set(errors))


def _summary(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    count = len(rows)
    resolved = sum(item["result"] == "resolved" for item in rows)
    preferred = sum(item["agent_action"] in PREFERRED_POLICY_ACTIONS for item in rows)
    return {
        "interactions": count,
        "resolved": resolved,
        "resolution_rate": round(resolved / count, 4) if count else 0.0,
        "preferred_policy_actions": preferred,
        "preferred_policy_action_rate": round(preferred / count, 4) if count else 0.0,
    }


def generate(output_dir: Path, *, seed: int = DEFAULT_SEED, days: int = DEFAULT_DAYS, per_day: int = DEFAULT_PER_DAY) -> dict[str, Any]:
    if days < 14:
        raise ValueError("days must be at least 14 for a multi-week corpus")
    if per_day < 8:
        raise ValueError("per_day must be at least 8")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    count = days * per_day
    span_minutes = days * 24 * 60 - 1
    interactions = []
    for ordinal in range(1, count + 1):
        occurred_at = FIXTURE_EPOCH + timedelta(minutes=((ordinal - 1) * span_minutes) // max(count - 1, 1))
        sequence = BASELINE_TEMPLATE_INDICES if (occurred_at - FIXTURE_EPOCH).days < ADAPTATION_START_DAY else ADAPTATION_TEMPLATE_INDICES
        template = SCENARIO_TEMPLATES[sequence[(ordinal - 1) % len(sequence)]]
        interactions.append(_interaction(template, ordinal, occurred_at, rng, seed))
    errors = validate_interactions(interactions, days=days)
    if errors:
        raise ValueError("synthetic corpus validation failed: " + "; ".join(errors[:5]))
    weekly_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    phase_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in interactions:
        week = str(item["observations"]["week_index"])
        weekly_rows[week].append(item)
        phase_rows[item["observations"]["trend_phase"]].append(item)
    manifest = {
        "format_version": FORMAT_VERSION,
        "seed": seed,
        "duration_days": days,
        "interactions_per_day": per_day,
        "interaction_count": count,
        "fixture_epoch": _utc_iso(FIXTURE_EPOCH),
        "policy_transition_day": ADAPTATION_START_DAY + 1,
        "policy_versions": [1, 2] if days > ADAPTATION_START_DAY else [1],
        "generation_is_deterministic": True,
        "scenario_source": "ollama-reviewed-blueprint",
        "scenario_source_model": OLLAMA_MODEL,
        "identity": {"organization_id": "demo-org", "agent_id": "demo-agent"},
        "safety": {
            "data_classification": "synthetic_non_sensitive",
            "validation": "schema, temporal window, categorical values, and identifier-like content",
        },
        "weekly_summary": {
            week: _summary(rows)
            for week, rows in sorted(weekly_rows.items(), key=lambda item: int(item[0]))
        },
        "trend_summary": {
            phase: _summary(rows)
            for phase, rows in sorted(phase_rows.items())
        },
        "files": [],
    }
    manifest["files"] = [_write_jsonl(output_dir / "interactions.jsonl", interactions)]
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a deterministic multi-week synthetic Continuum corpus.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/synthetic_weeks"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--per-day", type=int, default=DEFAULT_PER_DAY)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest = generate(args.output_dir, seed=args.seed, days=args.days, per_day=args.per_day)
    print(f"generated {manifest['interaction_count']} synthetic interactions across {manifest['duration_days']} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
