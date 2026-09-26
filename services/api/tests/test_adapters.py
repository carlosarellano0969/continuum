from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
import pytest

from continuum_api.adapters import OllamaAdapter, OpenRouterChatModel, VoyageEmbedder
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


def _voyage_embedder(**overrides) -> VoyageEmbedder:
    params = {
        "endpoint": "ai.mongodb.test",
        "api_key": "test-key",
        "model": "voyage-4-large",
        "dimensions": 8,
        "timeout_seconds": 0.5,
    }
    params.update(overrides)
    return VoyageEmbedder(**params)


def test_voyage_embedder_is_unconfigured_without_endpoint_or_key() -> None:
    embedder = _voyage_embedder(endpoint=None, api_key=None)
    assert embedder.configured is False
    assert asyncio.run(embedder.health()) == "unconfigured"


def test_voyage_embed_returns_finite_vector_and_records_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    vector = [index / 8 for index in range(8)]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://ai.mongodb.test/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body == {"input": ["financing question"], "model": "voyage-4-large"}
        return httpx.Response(200, json={"data": [{"embedding": vector}], "usage": {"total_tokens": 5}})

    _install_transport(monkeypatch, handler)
    embedder = _voyage_embedder()
    result = asyncio.run(embedder.embed("financing question"))
    assert result == vector
    assert embedder.last_usage_tokens == 5


def test_voyage_health_ok_when_dimensions_match(monkeypatch: pytest.MonkeyPatch) -> None:
    vector = [0.1] * 8
    _install_transport(
        monkeypatch, lambda _: httpx.Response(200, json={"data": [{"embedding": vector}], "usage": {}})
    )
    assert asyncio.run(_voyage_embedder().health()) == "ok"


@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},
        {"data": [{"embedding": [0.1, 0.2]}]},
        {"data": [{"embedding": [0.1] * 7 + [float("nan")]}]},
        {},
    ],
)
def test_voyage_embed_rejects_missing_or_malformed_vectors(
    monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    _install_transport(monkeypatch, lambda _: httpx.Response(200, json=payload))
    with pytest.raises(DependencyError, match="Voyage embedding request failed"):
        asyncio.run(_voyage_embedder().embed("unsafe"))


def test_voyage_embed_raises_on_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_transport(monkeypatch, lambda _: httpx.Response(503))
    with pytest.raises(DependencyError, match="Voyage embedding request failed"):
        asyncio.run(_voyage_embedder().embed("unsafe"))


def _openrouter_chat(**overrides) -> OpenRouterChatModel:
    params = {
        "api_key": "test-key",
        "model": "openai/gpt-oss-20b",
        "fallback_model": "anthropic/claude-haiku-4.5",
        "max_output_tokens": 512,
        "reasoning_effort": "low",
        "timeout_seconds": 0.5,
    }
    params.update(overrides)
    return OpenRouterChatModel(**params)


def test_openrouter_is_unconfigured_without_api_key() -> None:
    chat = _openrouter_chat(api_key=None)
    assert chat.configured is False
    assert asyncio.run(chat.health()) == "unconfigured"
    with pytest.raises(DependencyError, match="OpenRouter is unconfigured"):
        asyncio.run(chat.recommend("scenario", None, _policy(), []))


def test_openrouter_recommend_returns_typed_result_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    content = json.dumps({"recommendation": "  Escalate safely.  ", "rationale": "  Policy requires review.  "})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "openai/gpt-oss-20b"
        assert body["usage"] == {"include": True}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140, "cost": 0.002},
            },
        )

    _install_transport(monkeypatch, handler)
    chat = _openrouter_chat()
    result = asyncio.run(chat.recommend("scenario", None, _policy(), []))
    assert result == ("Escalate safely.", "Policy requires review.")
    assert chat.last_usage == {
        "prompt_tokens": 100,
        "completion_tokens": 40,
        "total_tokens": 140,
        "cost_usd": 0.002,
    }


def test_openrouter_falls_back_to_second_model_on_primary_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    content = json.dumps({"recommendation": "Fallback answer.", "rationale": "From the fallback model."})
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["model"])
        if body["model"] == "openai/gpt-oss-20b":
            return httpx.Response(503)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {}})

    _install_transport(monkeypatch, handler)
    chat = _openrouter_chat()
    result = asyncio.run(chat.recommend("scenario", None, _policy(), []))
    assert result == ("Fallback answer.", "From the fallback model.")
    assert calls == ["openai/gpt-oss-20b", "anthropic/claude-haiku-4.5"]


def test_openrouter_raises_when_both_models_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_transport(monkeypatch, lambda _: httpx.Response(503))
    with pytest.raises(DependencyError, match="OpenRouter chat request failed"):
        asyncio.run(_openrouter_chat().recommend("scenario", None, _policy(), []))
