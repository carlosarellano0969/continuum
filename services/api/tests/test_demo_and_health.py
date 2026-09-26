import pytest
from fastapi.testclient import TestClient

from continuum_api.config import Settings
from continuum_api import main as main_module
from continuum_api.main import create_app
from continuum_api.repository import InMemoryRepository


def test_default_cors_origins_support_both_local_dev_hosts(monkeypatch):
    monkeypatch.delenv("CONTINUUM_CORS_ORIGINS", raising=False)

    assert Settings.from_env().cors_origins == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )


def test_invalid_numeric_environment_values_use_safe_defaults(monkeypatch) -> None:
    monkeypatch.setenv("MONGODB_TIMEOUT_MS", "invalid")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "invalid")

    settings = Settings.from_env()

    assert settings.mongodb_timeout_ms == 4_000
    assert settings.ollama_timeout_seconds == 60.0


def test_cors_preflight_accepts_both_local_dev_hosts() -> None:
    app = create_app(settings=Settings(ollama_base_url=None), repository=InMemoryRepository())
    client = TestClient(app)

    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.options(
            "/api/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_health_reports_unconfigured_dependencies_without_crashing() -> None:
    app = create_app(settings=Settings(ollama_base_url=None), repository=InMemoryRepository())
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unconfigured"
    assert body["services"] == {
        "api": "ok",
        "mongodb": "unconfigured",
        "ollama": "unconfigured",
        "embedding_model": "unconfigured",
        "chat_model": "unconfigured",
    }


def test_configured_atlas_initialization_failure_is_not_silently_downgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingMongoRepository:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("atlas unavailable")

    monkeypatch.setattr(main_module, "MongoRepository", FailingMongoRepository)

    with pytest.raises(RuntimeError, match="atlas unavailable"):
        create_app(settings=Settings(mongodb_uri="mongodb://configured.example"))


def test_reset_is_deterministic_idempotent_and_summary_is_complete(client: TestClient) -> None:
    default_reset = client.post("/api/demo/reset")
    assert default_reset.status_code == 200
    first = client.post("/api/demo/reset", json={"seed": 42})
    assert first.status_code == 200
    assert first.json()["active_policy_version"] == 1
    assert first.json()["counts"] == {
        "memories": 6,
        "policies": 1,
        "decisions": 3,
        "outcomes": 3,
        "proposals": 1,
        "audit_events": 2,
    }
    first_memories = client.get("/api/memories").json()["items"]
    assert "mem-demo-fast-financing-information" in {memory["id"] for memory in first_memories}

    client.post(
        "/api/memories",
        json={"content": "temporary", "type": "episodic", "provenance": "test", "confidence": 0.5},
    )
    second = client.post("/api/demo/reset", json={"seed": 42})
    second_memories = client.get("/api/memories").json()["items"]

    assert second.json() == first.json()
    assert second_memories == first_memories
    summary = client.get("/api/demo/summary").json()
    assert summary["active_policy"]["version"] == 1
    assert summary["pending_proposal"]["state"] == "pending"
    assert summary["latest_decision"]["id"].startswith("dec_")


def test_reset_rejects_caller_selected_scope(client: TestClient) -> None:
    tenant_b = {"X-Organization-ID": "other-org", "X-Agent-ID": "other-agent"}
    assert client.post("/api/demo/reset", json={"seed": 1}).status_code == 200
    rejected = client.post("/api/demo/reset", json={"seed": 2}, headers=tenant_b)

    assert rejected.status_code == 403
    assert "restricted" in rejected.json()["detail"]
    assert client.get("/api/memories", headers=tenant_b).json()["total"] == 0
    assert client.get("/api/memories").json()["total"] == 6


def test_validation_errors_use_string_detail(client: TestClient) -> None:
    response = client.post(
        "/api/memories",
        json={"content": "", "type": "episodic", "provenance": "test", "confidence": 2},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
