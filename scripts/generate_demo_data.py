#!/usr/bin/env python3
"""Generate deterministic, non-sensitive Continuum demo evidence.

The output is deliberately independent of MongoDB and Ollama so it can be
reviewed and tested before any external service is configured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SEED = 20260924
DEFAULT_COUNT = 360
MIN_COUNT = 200
MAX_COUNT = 1000
FORMAT_VERSION = "continuum.demo.v1"
FIXTURE_EPOCH = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)

PATTERN_FINANCING = "financing_pricing_fast_information"
PATTERN_DISCOUNT = "generic_discount_first_underperformance"
PATTERN_DISTRACTOR = "small_sample_source_uplift"
PATTERN_BACKGROUND = "background_mix"


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_success(group_index: int, seed: int, rate_percent: int) -> bool:
    """Return a repeatable outcome with a bounded, near-exact success rate."""

    bucket = (group_index * 37 + seed * 17 + 11) % 100
    return bucket < rate_percent


def _metric_bundle(
    rng: random.Random,
    success: bool,
    preferred_action: bool,
    base_handle_seconds: int,
) -> dict[str, Any]:
    satisfaction = rng.choice((4, 5)) if success else rng.choice((1, 2, 3))
    if preferred_action and success:
        satisfaction = min(5, satisfaction + 1)
    return {
        "resolution_success": success,
        "customer_satisfaction": satisfaction,
        "handle_time_seconds": max(
            45,
            base_handle_seconds
            + rng.randint(-35, 35)
            - (55 if preferred_action and success else 0),
        ),
        "recontact_within_7d": (not success) or rng.random() < 0.08,
    }


def _interaction(
    *,
    ordinal: int,
    occurred_at: datetime,
    pattern: str,
    scenario: str,
    observations: dict[str, Any],
    action: str,
    result: str,
    metrics: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    return {
        "interaction_id": f"ix-{ordinal:04d}",
        "organization_id": "demo-org",
        "agent_id": "demo-agent",
        "occurred_at": _utc_iso(occurred_at),
        "scenario": scenario,
        "customer": {
            "synthetic_segment": observations.pop("synthetic_segment"),
            "account_tenure_band": rng.choice(
                ("under_90_days", "90_to_365_days", "over_365_days")
            ),
            "locale": "en-US",
        },
        "observations": observations,
        "policy_version": 1,
        "agent_action": action,
        "result": result,
        "metrics": metrics,
        "pattern_tag": pattern,
        "data_classification": "synthetic_non_sensitive",
    }


def _build_interactions(seed: int, count: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    distractor_count = max(8, min(12, count // 50))
    financing_count = int(count * 0.43)
    discount_count = int(count * 0.37)
    background_count = count - financing_count - discount_count - distractor_count

    pattern_order = (
        [PATTERN_FINANCING] * financing_count
        + [PATTERN_DISCOUNT] * discount_count
        + [PATTERN_DISTRACTOR] * distractor_count
        + [PATTERN_BACKGROUND] * background_count
    )
    rng.shuffle(pattern_order)

    group_indexes: dict[tuple[str, str], int] = defaultdict(int)
    pattern_indexes: dict[str, int] = defaultdict(int)
    interactions: list[dict[str, Any]] = []

    for ordinal, pattern in enumerate(pattern_order, start=1):
        pattern_index = pattern_indexes[pattern]
        pattern_indexes[pattern] += 1
        occurred_at = FIXTURE_EPOCH + timedelta(minutes=(ordinal - 1) * 7)

        if pattern == PATTERN_FINANCING:
            preferred = pattern_index % 2 == 0
            action = "fast_financing_information" if preferred else "deferred_financing_follow_up"
            group_index = group_indexes[(pattern, action)]
            group_indexes[(pattern, action)] += 1
            success = _stable_success(group_index, seed + (3 if preferred else 19), 86 if preferred else 34)
            observations = {
                "synthetic_segment": rng.choice(("budget_planner", "first_time_buyer")),
                "inquiry_type": "financing_and_pricing",
                "asks_monthly_payment_question": True,
                "financing_information_delivery_seconds": (
                    rng.randint(20, 75) if preferred else rng.randint(240, 720)
                ),
                "sentiment": rng.choice(("curious", "ready_to_compare")),
            }
            metrics = _metric_bundle(rng, success, preferred, 360)
            metrics["next_step_accepted"] = success
            scenario = (
                "A synthetic prospective buyer asks for financing and monthly pricing information."
            )

        elif pattern == PATTERN_DISCOUNT:
            preferred = pattern_index % 2 == 0
            action = "needs_based_pricing_explanation" if preferred else "generic_discount_first_reply"
            group_index = group_indexes[(pattern, action)]
            group_indexes[(pattern, action)] += 1
            success = _stable_success(group_index, seed + (7 if preferred else 29), 82 if preferred else 29)
            observations = {
                "synthetic_segment": rng.choice(("value_seeker", "feature_comparer")),
                "inquiry_type": "pricing_objection",
                "needs_discovery_complete": preferred,
                "generic_discount_offered_first": not preferred,
                "sentiment": rng.choice(("uncertain", "comparing_options")),
            }
            metrics = _metric_bundle(rng, success, preferred, 395)
            metrics["next_step_accepted"] = success
            scenario = (
                "A synthetic prospective buyer raises a general pricing concern before choosing a next step."
            )

        elif pattern == PATTERN_DISTRACTOR:
            preferred = pattern_index % 2 == 0
            action = "source_tailored_reply" if preferred else "standard_source_reply"
            group_index = group_indexes[(pattern, action)]
            group_indexes[(pattern, action)] += 1
            # The apparent effect is intentionally large, but the sample is
            # capped below the evidence threshold and must not change policy.
            success = _stable_success(group_index, seed + (13 if preferred else 31), 90 if preferred else 30)
            observations = {
                "synthetic_segment": "general_inquiry",
                "inquiry_type": "product_research",
                "lead_source": "regional_partner_directory",
                "source_context_available": preferred,
                "sentiment": "curious",
            }
            metrics = _metric_bundle(rng, success, preferred, 245)
            metrics["next_step_accepted"] = success
            scenario = "A synthetic inquiry arrives from a regional partner directory source."

        else:
            preferred = False
            action = rng.choice(
                ("standard_resolution", "clarifying_question", "knowledge_article")
            )
            group_index = group_indexes[(pattern, action)]
            group_indexes[(pattern, action)] += 1
            success = _stable_success(group_index, seed + len(action), 58)
            inquiry_type = rng.choice(
                ("feature_question", "availability_question", "general_comparison")
            )
            observations = {
                "synthetic_segment": rng.choice(("general_inquiry", "feature_comparer")),
                "inquiry_type": inquiry_type,
                "lead_source": rng.choice(("direct", "search", "returning_visitor")),
                "sentiment": rng.choice(("neutral", "curious")),
            }
            metrics = _metric_bundle(rng, success, preferred, 330)
            metrics["next_step_accepted"] = success
            scenario = f"A synthetic prospective buyer asks a {inquiry_type.replace('_', ' ')}."

        interactions.append(
            _interaction(
                ordinal=ordinal,
                occurred_at=occurred_at,
                pattern=pattern,
                scenario=scenario,
                observations=observations,
                action=action,
                result="resolved" if success else "unresolved",
                metrics=metrics,
                rng=rng,
            )
        )

    return interactions


def _summarize_pattern(
    interactions: Iterable[dict[str, Any]],
    pattern: str,
    baseline_action: str,
    candidate_action: str,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {baseline_action: [], candidate_action: []}
    for item in interactions:
        if item["pattern_tag"] == pattern and item["agent_action"] in groups:
            groups[item["agent_action"]].append(item)

    def stats(items: list[dict[str, Any]]) -> dict[str, Any]:
        successes = sum(1 for item in items if item["metrics"]["resolution_success"])
        return {
            "count": len(items),
            "successes": successes,
            "success_rate": round(successes / len(items), 4) if items else 0.0,
        }

    baseline = stats(groups[baseline_action])
    candidate = stats(groups[candidate_action])
    return {
        "baseline_action": baseline_action,
        "candidate_action": candidate_action,
        "baseline": baseline,
        "candidate": candidate,
        "absolute_success_lift": round(
            candidate["success_rate"] - baseline["success_rate"], 4
        ),
    }


def _memory(
    memory_id: str,
    content: str,
    memory_type: str,
    confidence: float,
    created_offset_minutes: int,
) -> dict[str, Any]:
    created = _utc_iso(FIXTURE_EPOCH + timedelta(minutes=created_offset_minutes))
    return {
        "id": memory_id,
        "organization_id": "demo-org",
        "agent_id": "demo-agent",
        "content": content,
        "type": memory_type,
        "provenance": "deterministic synthetic aggregate; no production or personal data",
        "confidence": confidence,
        "status": "active",
        "supersedes": None,
        "created_at": created,
        "updated_at": created,
        "embedding_model": "fixture-known-answer-v1",
    }


def _build_memories(patterns: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    financing = patterns[PATTERN_FINANCING]
    discount = patterns[PATTERN_DISCOUNT]
    distractor = patterns[PATTERN_DISTRACTOR]
    return [
        _memory(
            "mem-demo-fast-financing-information",
            (
                "For synthetic financing and pricing inquiries, providing financing information "
                f"immediately succeeded in {financing['candidate']['success_rate']:.0%} of "
                f"{financing['candidate']['count']} interactions versus "
                f"{financing['baseline']['success_rate']:.0%} of {financing['baseline']['count']} "
                "when financing follow-up was deferred."
            ),
            "pattern_evidence",
            0.96,
            1,
        ),
        _memory(
            "mem-demo-discount-first-underperformance",
            (
                "For synthetic general pricing objections, a needs-based pricing explanation "
                f"succeeded in {discount['candidate']['success_rate']:.0%} of "
                f"{discount['candidate']['count']} interactions versus "
                f"{discount['baseline']['success_rate']:.0%} of {discount['baseline']['count']} "
                "when the reply opened with a generic discount. The generic discount-first reply underperformed."
            ),
            "pattern_evidence",
            0.95,
            2,
        ),
        _memory(
            "mem-demo-source-uplift-distractor",
            (
                "Source-tailored replies for regional partner directory inquiries show an apparent synthetic "
                "outcome difference, but the "
                f"sample contains only {distractor['baseline']['count'] + distractor['candidate']['count']} "
                "interactions and is insufficient for a policy proposal."
            ),
            "insufficient_evidence",
            0.32,
            3,
        ),
        _memory(
            "mem-demo-non-financing-boundary",
            "General feature questions without financing or pricing intent are outside the fast-financing pattern boundary.",
            "boundary",
            0.91,
            4,
        ),
        _memory(
            "mem-demo-specific-incentive-boundary",
            "A documented, eligibility-based incentive is distinct from an unsolicited generic discount-first reply.",
            "boundary",
            0.92,
            5,
        ),
        _memory(
            "mem-demo-human-approval",
            "Synthetic pattern evidence may support a proposal, but a human approval is required before policy changes.",
            "governance",
            0.99,
            6,
        ),
    ]


def _build_retrieval_cases() -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "scoring_note": (
            "Required IDs are the known relevant records. Forbidden IDs are deliberate semantic distractors."
        ),
        "cases": [
            {
                "case_id": "financing-pricing-fast-information",
                "query": "A prospective buyer asks about financing and monthly pricing; what response has evidence?",
                "required_memory_ids": ["mem-demo-fast-financing-information"],
                "allowed_support_memory_ids": [
                    "mem-demo-non-financing-boundary",
                    "mem-demo-human-approval",
                ],
                "forbidden_memory_ids": ["mem-demo-source-uplift-distractor"],
                "max_results": 5,
            },
            {
                "case_id": "generic-discount-first",
                "query": "Should an agent lead with a generic discount when a buyer raises a pricing concern?",
                "required_memory_ids": ["mem-demo-discount-first-underperformance"],
                "allowed_support_memory_ids": [
                    "mem-demo-specific-incentive-boundary",
                    "mem-demo-human-approval",
                ],
                "forbidden_memory_ids": ["mem-demo-source-uplift-distractor"],
                "max_results": 5,
            },
            {
                "case_id": "small-sample-source-distractor",
                "query": "Do source-tailored replies work better for regional partner directory inquiries?",
                "required_memory_ids": ["mem-demo-source-uplift-distractor"],
                "allowed_support_memory_ids": ["mem-demo-human-approval"],
                "forbidden_memory_ids": [
                    "mem-demo-fast-financing-information",
                    "mem-demo-discount-first-underperformance",
                ],
                "max_results": 5,
                "expected_evidence_strength": "insufficient",
            },
        ],
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(values: Iterable[dict[str, Any]]) -> bytes:
    return (
        "".join(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
            for value in values
        )
    ).encode("utf-8")


def _write(path: Path, content: bytes, *, records: int | None = None) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": path.name,
        "bytes": len(content),
        "records": content.count(b"\n") if records is None else records,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def generate(output_dir: Path, seed: int = DEFAULT_SEED, count: int = DEFAULT_COUNT) -> dict[str, Any]:
    if not MIN_COUNT <= count <= MAX_COUNT:
        raise ValueError(f"count must be between {MIN_COUNT} and {MAX_COUNT}")

    interactions = _build_interactions(seed, count)
    patterns = {
        PATTERN_FINANCING: _summarize_pattern(
            interactions,
            PATTERN_FINANCING,
            "deferred_financing_follow_up",
            "fast_financing_information",
        ),
        PATTERN_DISCOUNT: _summarize_pattern(
            interactions,
            PATTERN_DISCOUNT,
            "generic_discount_first_reply",
            "needs_based_pricing_explanation",
        ),
        PATTERN_DISTRACTOR: _summarize_pattern(
            interactions,
            PATTERN_DISTRACTOR,
            "standard_source_reply",
            "source_tailored_reply",
        ),
    }
    memories = _build_memories(patterns)
    retrieval_cases = _build_retrieval_cases()

    output_dir = output_dir.resolve()
    file_entries = [
        _write(
            output_dir / "interactions.jsonl",
            _jsonl_bytes(interactions),
            records=len(interactions),
        ),
        _write(
            output_dir / "memories.jsonl",
            _jsonl_bytes(memories),
            records=len(memories),
        ),
        _write(
            output_dir / "retrieval_cases.json",
            _json_bytes(retrieval_cases),
            records=len(retrieval_cases["cases"]),
        ),
    ]

    distribution = dict(sorted(defaultdict(int, {
        name: sum(1 for item in interactions if item["pattern_tag"] == name)
        for name in {
            PATTERN_FINANCING,
            PATTERN_DISCOUNT,
            PATTERN_DISTRACTOR,
            PATTERN_BACKGROUND,
        }
    }).items()))

    manifest = {
        "format_version": FORMAT_VERSION,
        "seed": seed,
        "interaction_count": count,
        "fixture_epoch": _utc_iso(FIXTURE_EPOCH),
        "generation_is_deterministic": True,
        "identity": {"organization_id": "demo-org", "agent_id": "demo-agent"},
        "distribution": distribution,
        "patterns": {
            PATTERN_FINANCING: {
                "evidence_strength": "strong",
                "qualifier": "inquiry_type is financing_and_pricing",
                "approved_interpretation": "financing and pricing inquiries benefit from fast financing information",
                "minimum_group_size": 30,
                "minimum_absolute_success_lift": 0.30,
                **patterns[PATTERN_FINANCING],
            },
            PATTERN_DISCOUNT: {
                "evidence_strength": "strong",
                "qualifier": "inquiry_type is pricing_objection",
                "approved_interpretation": "generic discount-first replies perform worse than needs-based pricing explanations",
                "minimum_group_size": 30,
                "minimum_absolute_success_lift": 0.30,
                **patterns[PATTERN_DISCOUNT],
            },
            PATTERN_DISTRACTOR: {
                "evidence_strength": "insufficient",
                "qualifier": "lead_source is regional_partner_directory",
                "approved_interpretation": "small-sample source effect must not qualify",
                "maximum_total_evidence": 12,
                "insufficient_reason": "deliberately capped below 20 interactions",
                **patterns[PATTERN_DISTRACTOR],
            },
        },
        "known_answer_retrieval_cases": len(retrieval_cases["cases"]),
        "safety": {
            "classification": "synthetic_non_sensitive",
            "contains_real_people": False,
            "contains_credentials": False,
            "contains_health_or_financial_records": False,
            "prohibited_fields": [
                "name",
                "email",
                "phone",
                "address",
                "date_of_birth",
                "ssn",
                "account_number",
                "credential",
            ],
        },
        "files": file_entries,
    }
    _write(output_dir / "manifest.json", _json_bytes(manifest))
    return manifest


def _default_output_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "demo"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic, non-sensitive Continuum demo fixtures."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"PRNG seed (default: {DEFAULT_SEED})")
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"interaction count, {MIN_COUNT}..{MAX_COUNT} (default: {DEFAULT_COUNT})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_output_dir(),
        help="output directory (default: repository data/demo)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest = generate(args.output_dir, seed=args.seed, count=args.count)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"generated {manifest['interaction_count']} interactions in "
        f"{args.output_dir.resolve()} with seed {manifest['seed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
