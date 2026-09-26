from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from .errors import DependencyError
from .models import Memory, Policy


class _ChatResponse(BaseModel):
    """The only model-authored shape allowed to cross the adapter boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)

    recommendation: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500, strict=True),
    ]
    rationale: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=700, strict=True),
    ]


class Embedder(Protocol):
    model_name: str
    configured: bool

    async def health(self) -> str: ...
    async def embed(self, text: str) -> list[float]: ...


class ChatModel(Protocol):
    model_name: str
    configured: bool

    async def health(self) -> str: ...
    async def recommend(
        self,
        scenario: str,
        customer: dict[str, Any] | None,
        policy: Policy,
        memories: list[Memory],
    ) -> tuple[str, str]: ...


class DeterministicEmbedder:
    model_name = "deterministic-local-v1"
    configured = True

    async def health(self) -> str:
        return "ok"

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.strip().lower().encode("utf-8")).digest()
        return [round((value - 127.5) / 127.5, 6) for value in digest]


class DeterministicChatModel:
    model_name = "deterministic-fallback-v1"
    configured = True

    async def health(self) -> str:
        return "ok"

    async def recommend(
        self,
        scenario: str,
        customer: dict[str, Any] | None,
        policy: Policy,
        memories: list[Memory],
    ) -> tuple[str, str]:
        customer_hint = ""
        if customer:
            stable_customer = ", ".join(f"{key}={customer[key]}" for key in sorted(customer))
            customer_hint = f" Customer context: {stable_customer}."
        evidence = "; ".join(memory.content for memory in memories[:2]) or "No matching memory was found."
        recommendation = f"Apply policy v{policy.version}: {policy.rule}"
        rationale = f"For '{scenario}', the governing rule is explicit. Evidence: {evidence}.{customer_hint}".strip()
        return recommendation, rationale


class OllamaAdapter:
    def __init__(
        self,
        base_url: str | None,
        chat_model: str,
        embed_model: str,
        timeout_seconds: float,
        context_window: int = 4_096,
        max_output_tokens: int = 512,
        reasoning_effort: str = "low",
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 3.0))
        self.context_window = context_window
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self._embedding_dimensions: int | None = (
            768 if "nomic-embed-text" in embed_model.casefold() else None
        )

    async def health(self) -> str:
        if not self.base_url:
            return "unconfigured"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError("model inventory must be an object")
            models = payload.get("models")
            if not isinstance(models, list):
                raise ValueError("missing model list")
            available: set[str] = set()
            for model in models:
                if not isinstance(model, dict):
                    raise ValueError("invalid model entry")
                for key in ("name", "model"):
                    value = model.get(key)
                    if isinstance(value, str) and value:
                        available.add(value)
            if self.chat_model not in available or self.embed_model not in available:
                return "degraded"
            return "ok"
        except (httpx.HTTPError, ValueError, TypeError):
            return "degraded"

    async def embed(self, text: str) -> list[float]:
        if not self.base_url:
            raise DependencyError("Ollama is unconfigured")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.embed_model, "input": text},
                )
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError("embedding response must be an object")
            embeddings = payload.get("embeddings")
            if not embeddings or not isinstance(embeddings[0], list):
                raise ValueError("missing embeddings")
            vector = embeddings[0]
            if not vector:
                raise ValueError("empty embedding")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            ):
                raise ValueError("embedding values must be finite numbers")
            if self._embedding_dimensions is None:
                self._embedding_dimensions = len(vector)
            if len(vector) != self._embedding_dimensions:
                raise ValueError(
                    f"embedding dimension mismatch: expected {self._embedding_dimensions}, got {len(vector)}"
                )
            return [float(value) for value in vector]
        except (httpx.HTTPError, ValueError, TypeError, KeyError, OverflowError) as exc:
            raise DependencyError(f"Ollama embedding request failed: {exc.__class__.__name__}") from exc

    async def recommend(
        self,
        scenario: str,
        customer: dict[str, Any] | None,
        policy: Policy,
        memories: list[Memory],
    ) -> tuple[str, str]:
        if not self.base_url:
            raise DependencyError("Ollama is unconfigured")
        evidence = [
            {"id": memory.id, "content": memory.content, "confidence": memory.confidence}
            for memory in memories
        ]
        prompt = {
            "scenario": scenario,
            "customer": customer,
            "policy": {"version": policy.version, "rule": policy.rule, "risk": policy.risk},
            "memories": evidence,
            "instruction": (
                "Return only a JSON object with string keys recommendation and rationale. "
                "Ground the answer in the supplied policy and memories. Never invent rates, payment amounts, "
                "discounts, eligibility, approvals, or other financial terms. If verified terms are absent, "
                "recommend the next safe step or a qualified human handoff."
            ),
        }
        response_schema = {
            "type": "object",
            "properties": {
                "recommendation": {"type": "string", "maxLength": 500},
                "rationale": {"type": "string", "maxLength": 700},
            },
            "required": ["recommendation", "rationale"],
            "additionalProperties": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.chat_model,
                        "stream": False,
                        "think": self.reasoning_effort,
                        "format": response_schema,
                        "messages": [{"role": "user", "content": json.dumps(prompt, sort_keys=True)}],
                        "options": {
                            "temperature": 0,
                            "num_ctx": self.context_window,
                            "num_predict": self.max_output_tokens,
                        },
                    },
                )
                response.raise_for_status()
                body = response.json()
            content = body["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("chat content must be a JSON string")
            result = _ChatResponse.model_validate_json(content)
            return result.recommendation, result.rationale
        except (httpx.HTTPError, ValueError, TypeError, KeyError, ValidationError) as exc:
            raise DependencyError(f"Ollama chat request failed: {exc.__class__.__name__}") from exc


class OllamaEmbedder:
    def __init__(self, adapter: OllamaAdapter) -> None:
        self._adapter = adapter
        self.model_name = adapter.embed_model
        self.configured = bool(adapter.base_url)

    async def health(self) -> str:
        return await self._adapter.health()

    async def embed(self, text: str) -> list[float]:
        return await self._adapter.embed(text)


class OllamaChatModel:
    def __init__(self, adapter: OllamaAdapter) -> None:
        self._adapter = adapter
        self.model_name = adapter.chat_model
        self.configured = bool(adapter.base_url)

    async def health(self) -> str:
        return await self._adapter.health()

    async def recommend(
        self,
        scenario: str,
        customer: dict[str, Any] | None,
        policy: Policy,
        memories: list[Memory],
    ) -> tuple[str, str]:
        return await self._adapter.recommend(scenario, customer, policy, memories)
