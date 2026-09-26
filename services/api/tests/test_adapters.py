from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
import pytest

from continuum_api.adapters import OllamaAdapter
from continuum_api.errors import DependencyError
from continuum_api.models import Policy


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)


def _adapter(embed_model: str = "nomic-embed-text:latest") -> OllamaAdapter:
    return OllamaAdapter(
        "http://ollama.test",
        "gpt-oss:20b",
        embed_model,
        timeout_seconds=0.5,
    )


def _policy() -> Policy:
    return Policy(
        id="pol_1",
        logical_policy_id="support",
        organization_id="demo-org",
        agent_id="demo-agent",
        version=1,
        status="active",
        rule="Escalate high-risk requests.",
        risk="medium",
        evidence_ids=[],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_health_requires_both_configured_models(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "gpt-oss:20b"},
                    {"model": "nomic-embed-text:latest"},
                ]
            },
        )

    _install_transport(monkeypatch, handler)
    assert asyncio.run(_adapter().health()) == "ok"


@pytest.mark.parametrize(
    "payload",
    [
        {"models": [{"name": "gpt-oss:20b"}]},
        {"models": [{"name": "nomic-embed-text:latest"}]},
        {"models": "not-a-list"},
        {"models": ["not-an-object"]},
        {},
    ],
)
def test_health_degrades_for_missing_or_malformed_model_inventory(
    monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    _install_transport(monkeypatch, lambda _: httpx.Response(200, json=payload))
    assert asyncio.run(_adapter().health()) == "degraded"


def test_health_degrades_on_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_transport(monkeypatch, lambda _: httpx.Response(503))
    assert asyncio.run(_adapter().health()) == "degraded"


def test_health_degrades_for_non_object_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_transport(monkeypatch, lambda _: httpx.Response(200, json=[]))
    assert asyncio.run(_adapter().health()) == "degraded"


def test_nomic_embedding_accepts_finite_768_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    vector = [index / 768 for index in range(768)]
    _install_transport(monkeypatch, lambda _: httpx.Response(200, json={"embeddings": [vector]}))
    result = asyncio.run(_adapter().embed("safe text"))
    assert result == vector
    assert all(isinstance(value, float) for value in result)


@pytest.mark.parametrize(
    "vector",
    [
        [],
        [0.0] * 767,
        [0.0] * 767 + [float("nan")],
        [0.0] * 767 + [float("inf")],
        [0.0] * 767 + [True],
        [0.0] * 767 + ["0.5"],
    ],
)
def test_embedding_rejects_empty_wrong_dimension_or_nonfinite_values(
    monkeypatch: pytest.MonkeyPatch, vector: list
) -> None:
    _install_transport(monkeypatch, lambda _: httpx.Response(200, json={"embeddings": [vector]}))
    with pytest.raises(DependencyError, match="Ollama embedding request failed"):
        asyncio.run(_adapter().embed("unsafe vector"))


def test_non_nomic_embedding_dimension_is_fixed_by_first_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(([0.1, 0.2, 0.3], [0.1, 0.2]))

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [next(responses)]})

    _install_transport(monkeypatch, handler)
    adapter = _adapter(embed_model="custom-embed:latest")
    assert asyncio.run(adapter.embed("first")) == [0.1, 0.2, 0.3]
    with pytest.raises(DependencyError, match="Ollama embedding request failed"):
        asyncio.run(adapter.embed("second"))


def test_embedding_rejects_non_object_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_transport(monkeypatch, lambda _: httpx.Response(200, json=[]))
    with pytest.raises(DependencyError, match="Ollama embedding request failed"):
        asyncio.run(_adapter().embed("unsafe payload"))


def test_chat_accepts_only_bounded_typed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    content = json.dumps(
        {"recommendation": "  Escalate safely.  ", "rationale": "  Policy requires review.  "}
    )
    _install_transport(
        monkeypatch,
        lambda _: httpx.Response(200, json={"message": {"content": content}}),
    )

    result = asyncio.run(_adapter().recommend("scenario", None, _policy(), []))
    assert result == ("Escalate safely.", "Policy requires review.")


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        json.dumps({"recommendation": 7, "rationale": "valid"}),
        json.dumps({"recommendation": "valid", "rationale": 7}),
        json.dumps({"recommendation": "valid", "rationale": "valid", "extra": "forbidden"}),
        json.dumps({"recommendation": " ", "rationale": "valid"}),
        json.dumps({"recommendation": "x" * 501, "rationale": "valid"}),
        json.dumps({"recommendation": "valid", "rationale": "x" * 701}),
    ],
)
def test_chat_schema_failures_become_dependency_errors(
    monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    _install_transport(
        monkeypatch,
        lambda _: httpx.Response(200, json={"message": {"content": content}}),
    )
    with pytest.raises(DependencyError, match="Ollama chat request failed"):
        asyncio.run(_adapter().recommend("scenario", None, _policy(), []))


def test_chat_rejects_non_string_content(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_transport(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json={
                "message": {
                    "content": {"recommendation": "valid", "rationale": "valid"}
                }
            },
        ),
    )
    with pytest.raises(DependencyError, match="Ollama chat request failed"):
        asyncio.run(_adapter().recommend("scenario", None, _policy(), []))
