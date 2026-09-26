#!/usr/bin/env python3
"""Precompute Voyage embeddings for a bench task file.

The hosted embeddings key allows 3 requests per minute, and every Continuum bench
row embeds its task text. Run this once per task file; the API's embedder loads any
``data/*/*embeddings.<model>.json`` file at startup and skips the network for them.

Example:
    python scripts/embed_bench_tasks.py --tasks data/bench/tasks_holdout.json \
        --out data/bench/holdout_task_embeddings.voyage-4-large.json \
        --env-file ../Secrets/atlas-credentials.env
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from continuum_api.adapters import VoyageEmbedder  # noqa: E402
from continuum_api.bench import labelled_scenario  # noqa: E402
from continuum_api.errors import DependencyError  # noqa: E402

SECONDS_BETWEEN_CALLS = 21.0


def load_env_file(path: Path) -> None:
    """Set KEY=VALUE lines as environment variables without echoing any value."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--model", default="voyage-4-large")
    args = parser.parse_args()
    if not args.out.name.endswith(f"embeddings.{args.model}.json"):
        print(f"--out must end with embeddings.{args.model}.json so the API loads it", file=sys.stderr)
        return 2
    if args.env_file:
        load_env_file(args.env_file)

    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
    existing = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    vectors: dict[str, list[float]] = dict(existing.get("vectors", {}))
    embedder = VoyageEmbedder(
        os.getenv("ENDPOINT"),
        os.getenv("MODEL_API_KEY"),
        model=args.model,
        dimensions=int(os.getenv("EMBED_DIMENSIONS", "1024")),
    )
    if not embedder.configured:
        print("ENDPOINT and MODEL_API_KEY are required (pass --env-file)", file=sys.stderr)
        return 2

    todo = []
    for task in tasks:
        text = labelled_scenario(task)
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if key not in vectors:
            todo.append((task["task_id"], key, text))
    print(f"{len(tasks)} tasks, {len(todo)} to embed, ~{len(todo) * SECONDS_BETWEEN_CALLS / 60:.0f} min")

    for index, (task_id, key, text) in enumerate(todo):
        started = time.monotonic()
        for attempt in range(3):
            try:
                vectors[key] = await embedder.embed(text)
                break
            except DependencyError as exc:
                print(f"{task_id}: {exc}; retrying in 30s", flush=True)
                await asyncio.sleep(30)
        else:
            print(f"{task_id}: giving up", file=sys.stderr)
            continue
        args.out.write_text(
            json.dumps(
                {
                    "model": args.model,
                    "dimensions": len(vectors[key]),
                    "source": f"{args.tasks.as_posix()} via bench.labelled_scenario",
                    "note": "Precomputed so bench runs do not spend the 3 RPM embeddings cap; keyed by sha256 of the embedded text.",
                    "vectors": vectors,
                }
            ),
            encoding="utf-8",
        )
        print(f"[{index + 1}/{len(todo)}] {task_id} ok", flush=True)
        if index + 1 < len(todo):
            await asyncio.sleep(max(0.0, SECONDS_BETWEEN_CALLS - (time.monotonic() - started)))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
