#!/usr/bin/env python3
"""Run the harness bench against a live Continuum API and print a summary.

Calls ``POST /api/bench/run`` with a generous timeout (a full 3-arm run over
all 12 tasks takes minutes, not seconds) and prints one summary line per arm
plus the run_id, so it can be pasted into a demo log or CI artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api"
REQUEST_TIMEOUT_SECONDS = 900.0
ALL_ARMS = ("out_of_box", "context_stuffing", "continuum")


def _post_bench_run(
    base_url: str,
    *,
    arms: list[str] | None,
    repeats: int,
    task_limit: int | None,
    organization_id: str,
    agent_id: str,
    timeout: float,
) -> dict[str, Any]:
    body: dict[str, Any] = {"repeats": repeats}
    if arms is not None:
        body["arms"] = arms
    if task_limit is not None:
        body["task_limit"] = task_limit
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/bench/run",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Organization-ID": organization_id,
            "X-Agent-ID": agent_id,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} from {request.full_url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"cannot reach {request.full_url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"request timed out after {timeout:.0f}s: {request.full_url}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-JSON response from {request.full_url}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected a JSON object from {request.full_url}")
    return payload


def _print_summary(document: dict[str, Any]) -> None:
    aggregates: dict[str, Any] = document.get("aggregates", {})
    for arm in document.get("arms", list(aggregates.keys())):
        aggregate = aggregates.get(arm, {})
        cost = float(aggregate.get("cost_usd", 0.0))
        correct_pct = aggregate.get("correct_pct", 0.0)
        wall = aggregate.get("display", {}).get("wall", f"{aggregate.get('wall_ms', 0)}ms")
        vector_calls = aggregate.get("vector_calls", 0)
        tokens = aggregate.get("tokens", 0)
        print(
            f"arm={arm} correct={correct_pct}% cost=${cost:.4f} wall={wall} "
            f"vector_calls={vector_calls} tokens={tokens}"
        )
    print(f"run_id={document.get('run_id', '')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the harness bench (POST /api/bench/run) and print a per-arm summary."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BASE_URL", os.environ.get("CONTINUUM_API_BASE_URL", DEFAULT_BASE_URL)),
        help=f"API base URL (default: BASE_URL, CONTINUUM_API_BASE_URL, or {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--arms",
        default=None,
        help=f"comma-separated arm list (default: all three, {','.join(ALL_ARMS)})",
    )
    parser.add_argument(
        "--task-limit",
        type=int,
        default=None,
        help="use only the first N tasks in fixed order, 1-12 (default: all 12)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="repeat the whole task set this many times per arm, 1-5 (default: 1)",
    )
    parser.add_argument(
        "--organization-id",
        default=os.environ.get("CONTINUUM_ORG_ID", "demo-org"),
        help="tenant organization header (default: CONTINUUM_ORG_ID or demo-org)",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("CONTINUUM_AGENT_ID", "demo-agent"),
        help="tenant agent header (default: CONTINUUM_AGENT_ID or demo-agent)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()] if args.arms else None
    try:
        document = _post_bench_run(
            args.base_url,
            arms=arms,
            repeats=args.repeats,
            task_limit=args.task_limit,
            organization_id=args.organization_id,
            agent_id=args.agent_id,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except RuntimeError as exc:
        print(f"bench run failed: {exc}", file=sys.stderr)
        return 1
    _print_summary(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
