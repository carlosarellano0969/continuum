#!/usr/bin/env python3
"""Reset a running Continuum API demo tenant through its public HTTP API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000/api"
DEFAULT_SEED = 20260924


def _request(
    base_url: str,
    path: str,
    *,
    method: str,
    timeout: float,
    organization_id: str,
    agent_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
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
        raise RuntimeError(f"request timed out after {timeout:.1f}s: {request.full_url}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-JSON response from {request.full_url}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected a JSON object from {request.full_url}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset the configured Continuum demo tenant deterministically."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BASE_URL", os.environ.get("CONTINUUM_API_BASE_URL", DEFAULT_BASE_URL)),
        help=f"API base URL (default: BASE_URL, CONTINUUM_API_BASE_URL, or {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=int(os.environ.get("CONTINUUM_DEMO_SEED", DEFAULT_SEED)),
        help=f"demo seed (default: CONTINUUM_DEMO_SEED or {DEFAULT_SEED})",
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
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--with-summary",
        action="store_true",
        help="also fetch and print /demo/summary after reset",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.timeout <= 0:
        print("--timeout must be greater than zero", file=sys.stderr)
        return 2
    try:
        start = time.time()
        reset = _request(
            args.base_url,
            "/demo/reset",
            method="POST",
            timeout=args.timeout,
            organization_id=args.organization_id,
            agent_id=args.agent_id,
            body={"seed": args.seed},
        )
        output: dict[str, Any] = {"reset": reset}
        if args.with_summary:
            output["summary"] = _request(
                args.base_url,
                "/demo/summary",
                method="GET",
                timeout=args.timeout,
                organization_id=args.organization_id,
                agent_id=args.agent_id,
            )
        elapsed = time.time() - start
        output["elapsed_seconds"] = round(elapsed, 2)
    except RuntimeError as exc:
        print(f"reset failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
