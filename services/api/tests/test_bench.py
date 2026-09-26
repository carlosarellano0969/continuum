from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from continuum_api.adapters import DeterministicChatModel, DeterministicEmbedder
from continuum_api.bench import (
    ALL_ARMS,
    aggregate_arm,
    extract_action,
    format_cost,
    format_count,
    format_wall,
    load_tasks,
)
from continuum_api.config import Settings
from continuum_api.main import create_app
from continuum_api.repository import InMemoryRepository


def test_extract_action_matches_known_evidence_phrase() -> None:
    text = "Evidence: providing financing information immediately succeeded for these customers."
    assert extract_action(text) == "fast_financing_information"


def test_extract_action_prefers_standard_reply_when_evidence_notes_insufficiency() -> None:
    text = "Source-tailored replies show a difference, but the sample is insufficient for a policy proposal."
    assert extract_action(text) == "standard_source_reply"


def test_extract_action_defaults_to_none_detected() -> None:
    assert extract_action("Apply general good judgment to this customer request.") == "none_detected"


def test_format_helpers_match_packet_examples() -> None:
    assert format_cost(0.26) == "$0.26"
    assert format_wall(175_000) == "2m 55s"
    assert format_count(5) == "5"
    assert format_count(4251) == "4,251"


def test_aggregate_arm_computes_correct_pct_cost_and_display() -> None:
    rows = [
        {"arm": "out_of_box", "cost_usd": 0.1, "wall_ms": 100, "vector_calls": 0, "total_tokens": 50, "correct": True},
        {"arm": "out_of_box", "cost_usd": 0.2, "wall_ms": 200, "vector_calls": 0, "total_tokens": 70, "correct": False},
        {"arm": "continuum", "cost_usd": 1.0, "wall_ms": 10, "vector_calls": 1, "total_tokens": 10, "correct": True},
    ]
    aggregate = aggregate_arm("out_of_box", rows)
    assert aggregate["correct_pct"] == 50.0
    assert aggregate["cost_usd"] == pytest.approx(0.3)
    assert aggregate["display"]["cost"] == "$0.30"
    assert aggregate["display"]["tokens"] == "120"


def test_tasks_fixture_has_four_per_group_and_no_leaked_action_labels() -> None:
    tasks = load_tasks()
    assert len(tasks) == 12
    assert all(task["synthetic"] is True for task in tasks)
    groups: dict[str, int] = {}
    for task in tasks:
        groups[task["group"]] = groups.get(task["group"], 0) + 1
        # The scenario text alone (no memory evidence) must never trip the
        # action extractor; otherwise every arm would trivially "pass" that
        # task just by echoing the prompt back, which defeats the benchmark.
        assert extract_action(task["scenario"]) == "none_detected", task["task_id"]
    assert groups == {"financing_pricing": 4, "pricing_objection": 4, "distractor_source": 4}


@pytest.fixture
def client() -> TestClient:
    settings = Settings(ollama_base_url=None)
    app = create_app(
        settings=settings,
        repository=InMemoryRepository(),
        chat_model=DeterministicChatModel(),
        embedder=DeterministicEmbedder(),
    )
    return TestClient(app)


def _correct_by_arm(document: dict) -> dict[str, list[bool]]:
    per_arm: dict[str, list[bool]] = {}
    for row in document["rows"]:
        per_arm.setdefault(row["arm"], []).append(row["correct"])
    return per_arm


def test_bench_run_returns_three_arms_times_twelve_rows_and_is_reproducible(client: TestClient) -> None:
    first = client.post("/api/bench/run", json={})
    assert first.status_code == 200
    body = first.json()
    assert len(body["rows"]) == len(ALL_ARMS) * 12
    assert set(body["arms"]) == set(ALL_ARMS)
    assert all(row["synthetic"] for row in body["rows"])
    assert set(body["aggregates"].keys()) == set(ALL_ARMS)

    second = client.post("/api/bench/run", json={})
    assert second.status_code == 200
    assert _correct_by_arm(body) == _correct_by_arm(second.json())

    listing = client.get("/api/bench/runs")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert any(item["run_id"] == body["run_id"] for item in items)
    assert "rows" not in items[0]

    fetched = client.get(f"/api/bench/runs/{body['run_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == body["run_id"]
    assert len(fetched.json()["rows"]) == len(ALL_ARMS) * 12


def test_bench_run_unknown_arm_returns_409(client: TestClient) -> None:
    response = client.post("/api/bench/run", json={"arms": ["not_a_real_arm"]})
    assert response.status_code == 409


def test_bench_run_missing_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/bench/runs/does-not-exist")
    assert response.status_code == 404
