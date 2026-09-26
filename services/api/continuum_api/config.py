from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def _integer(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    mongodb_uri: str | None = None
    mongodb_database: str = "continuum_v1"
    mongodb_vector_index: str = "memory_embedding_index"
    mongodb_timeout_ms: int = 4_000
    ollama_base_url: str | None = "http://127.0.0.1:11434"
    ollama_chat_model: str = "gpt-oss:20b"
    ollama_embed_model: str = "nomic-embed-text:latest"
    ollama_context_window: int = 4_096
    ollama_max_output_tokens: int = 512
    ollama_reasoning_effort: str = "low"
    ollama_timeout_seconds: float = 60.0
    organization_id: str = "demo-org"
    agent_id: str = "demo-agent"
    demo_seed: int = 20_260_924
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    model_provider: str = "ollama"
    embed_provider: str = "ollama"
    embed_dimensions: int = 1024
    endpoint: str | None = None
    model_api_key: str | None = None
    voyage_embed_model: str = "voyage-4-large"
    openrouter_api_key: str | None = None
    openrouter_chat_model: str = "openai/gpt-oss-20b"
    openrouter_chat_model_fallback: str = "anthropic/claude-haiku-4.5"

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(
            value.strip()
            for value in os.getenv("CONTINUUM_CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).split(",")
            if value.strip()
        )
        return cls(
            mongodb_uri=os.getenv("MONGODB_URI") or None,
            mongodb_database=os.getenv("MONGODB_DATABASE", "continuum_v1"),
            mongodb_vector_index=os.getenv("MONGODB_VECTOR_INDEX", "memory_embedding_index"),
            mongodb_timeout_ms=_integer("MONGODB_TIMEOUT_MS", 4_000),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434") or None,
            ollama_chat_model=os.getenv("OLLAMA_CHAT_MODEL", "gpt-oss:20b"),
            ollama_embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest"),
            ollama_context_window=_integer("OLLAMA_CONTEXT_WINDOW", 4_096),
            ollama_max_output_tokens=_integer("OLLAMA_MAX_OUTPUT_TOKENS", 512),
            ollama_reasoning_effort=os.getenv("OLLAMA_REASONING_EFFORT", "low"),
            ollama_timeout_seconds=_float("OLLAMA_TIMEOUT_SECONDS", 60.0),
            organization_id=os.getenv("CONTINUUM_ORG_ID", "demo-org"),
            agent_id=os.getenv("CONTINUUM_AGENT_ID", "demo-agent"),
            demo_seed=_integer("CONTINUUM_DEMO_SEED", 20_260_924),
            cors_origins=origins,
            model_provider=os.getenv("MODEL_PROVIDER", "ollama"),
            embed_provider=os.getenv("EMBED_PROVIDER", "ollama"),
            embed_dimensions=_integer("EMBED_DIMENSIONS", 1_024),
            endpoint=os.getenv("ENDPOINT") or None,
            model_api_key=os.getenv("MODEL_API_KEY") or None,
            voyage_embed_model=os.getenv("VOYAGE_EMBED_MODEL", "voyage-4-large"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
            openrouter_chat_model=os.getenv("OPENROUTER_CHAT_MODEL", "openai/gpt-oss-20b"),
            openrouter_chat_model_fallback=os.getenv(
                "OPENROUTER_CHAT_MODEL_FALLBACK", "anthropic/claude-haiku-4.5"
            ),
        )
