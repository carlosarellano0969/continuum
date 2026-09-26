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


def test_format_cost_uses_four_decimals_under_a_cent() -> None:
    assert format_cost(0.003107) == "$0.0031"
    assert format_cost(0.0099) == "$0.0099"


def test_format_cost_never_shows_zero_for_a_nonzero_value() -> None:
    for value in (0.003107, 0.0001, 0.009999):
        rendered = format_cost(value)
        assert rendered != "$0.00", rendered


def test_format_cost_uses_two_decimals_at_or_above_a_cent() -> None:
    assert format_cost(0.01) == "$0.01"
    assert format_cost(1.5) == "$1.50"


def test_format_cost_zero_is_still_zero() -> None:
    assert format_cost(0.0) == "$0.00"


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


def test_bench_run_task_limit_uses_first_n_tasks_in_fixed_order(client: TestClient) -> None:
    all_tasks = load_tasks()
    first = client.post("/api/bench/run", json={"arms": ["continuum"], "task_limit": 4})
    assert first.status_code == 200
    body = first.json()
    assert body["task_count"] == 4
    assert len(body["rows"]) == 4
    assert [row["task_id"] for row in body["rows"]] == [task["task_id"] for task in all_tasks[:4]]

    # Reproducible: a second run with the same limit picks the same tasks.
    second = client.post("/api/bench/run", json={"arms": ["continuum"], "task_limit": 4})
    assert [row["task_id"] for row in second.json()["rows"]] == [row["task_id"] for row in body["rows"]]


def test_bench_run_without_task_limit_records_full_task_count(client: TestClient) -> None:
    response = client.post("/api/bench/run", json={})
    assert response.status_code == 200
    assert response.json()["task_count"] == 12


def test_bench_run_task_limit_out_of_range_returns_422(client: TestClient) -> None:
    assert client.post("/api/bench/run", json={"task_limit": 0}).status_code == 422
    assert client.post("/api/bench/run", json={"task_limit": 13}).status_code == 422


def test_bench_runs_summary_includes_per_arm_display_fields(client: TestClient) -> None:
    created = client.post("/api/bench/run", json={"arms": ["continuum"], "task_limit": 2})
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    listing = client.get("/api/bench/runs")
    assert listing.status_code == 200
    items = listing.json()["items"]
    summary = next(item for item in items if item["run_id"] == run_id)

    assert summary["task_count"] == 2
    assert "rows" not in summary
    aggregate = summary["aggregates"]["continuum"]
    for key in ("correct_pct", "cost_usd", "wall_ms", "vector_calls", "tokens", "display"):
        assert key in aggregate, key
    for key in ("cost", "wall", "vector_calls", "tokens"):
        assert key in aggregate["display"], key


def test_bench_run_unknown_arm_returns_409(client: TestClient) -> None:
    response = client.post("/api/bench/run", json={"arms": ["not_a_real_arm"]})
    assert response.status_code == 409


def test_bench_run_missing_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/bench/runs/does-not-exist")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "text",
    [
        "ACTION: fast_financing_information\nShare the financing overview now.",
        "**Action:** `fast_financing_information` - share it now.",
        "action = 'FAST_FINANCING_INFORMATION'.",
    ],
)
def test_extract_action_reads_the_labelled_action_line(text: str) -> None:
    assert extract_action(text) == "fast_financing_information"


def test_extract_action_ignores_unknown_labels_and_falls_back_to_keywords() -> None:
    text = "ACTION: call_them_later. A needs-based pricing explanation fits best."
    assert extract_action(text) == "needs_based_pricing_explanation"


def test_extract_action_paraphrase_without_label_is_not_scored() -> None:
    assert extract_action("Offer them some payment options soon.") == "none_detected"


def test_bench_run_adapts_policy_before_measuring_and_keeps_answer_text(client: TestClient) -> None:
    response = client.post("/api/bench/run", json={"arms": ["continuum"], "task_limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["adapted"] is True
    assert body["active_policy_version"] == 2
    for row in body["rows"]:
        assert row["policy_version"] == 2
        assert row["recommendation"]
        assert "rationale" in row


def test_bench_run_without_adapt_measures_the_seeded_policy(client: TestClient) -> None:
    response = client.post("/api/bench/run", json={"arms": ["continuum"], "task_limit": 1, "adapt": False})
    assert response.status_code == 200
    assert response.json()["active_policy_version"] == 1
