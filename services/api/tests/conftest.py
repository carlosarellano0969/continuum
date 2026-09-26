from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from continuum_api.adapters import DeterministicChatModel, DeterministicEmbedder
from continuum_api.config import Settings
from continuum_api.main import create_app
from continuum_api.repository import InMemoryRepository


@pytest.fixture
def repository() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def client(repository: InMemoryRepository) -> TestClient:
    settings = Settings(ollama_base_url=None)
    app = create_app(
        settings=settings,
        repository=repository,
        chat_model=DeterministicChatModel(),
        embedder=DeterministicEmbedder(),
    )
    return TestClient(app)


@pytest.fixture
def seeded(client: TestClient) -> TestClient:
    response = client.post("/api/demo/reset", json={"seed": 77})
    assert response.status_code == 200
    return client

