from typing import Annotated

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .adapters import (
    ChatModel,
    DeterministicChatModel,
    DeterministicEmbedder,
    Embedder,
    OllamaAdapter,
    OllamaChatModel,
    OllamaEmbedder,
    OpenRouterChatModel,
    VoyageEmbedder,
)
from .bench import BenchHarness
from .config import Settings
from .errors import ConflictError, ContinuumError, DependencyError, NotFoundError
from .models import (
    BenchRunRequest,
    DemoResetRequest,
    Identity,
    MemoryCreate,
    OutcomeCreate,
    ProposalDecisionRequest,
    RecommendationRequest,
)
from .repository import InMemoryRepository, MongoRepository, Repository
from .service import ContinuumService


def _build_chat_model(settings: Settings, ollama: OllamaAdapter) -> ChatModel:
    if settings.model_provider == "openrouter":
        return OpenRouterChatModel(
            settings.openrouter_api_key,
            model=settings.openrouter_chat_model,
            fallback_model=settings.openrouter_chat_model_fallback,
            max_output_tokens=settings.ollama_max_output_tokens,
            reasoning_effort=settings.ollama_reasoning_effort,
        )
    if settings.model_provider == "deterministic":
        return DeterministicChatModel()
    return OllamaChatModel(ollama)


def _build_embedder(settings: Settings, ollama: OllamaAdapter) -> Embedder:
    if settings.embed_provider == "voyage":
        return VoyageEmbedder(
            settings.endpoint,
            settings.model_api_key,
            model=settings.voyage_embed_model,
            dimensions=settings.embed_dimensions,
        )
    if settings.embed_provider == "deterministic":
        return DeterministicEmbedder()
    return OllamaEmbedder(ollama)


def create_app(
    settings: Settings | None = None,
    repository: Repository | None = None,
    chat_model: ChatModel | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if repository is None:
        if settings.mongodb_uri:
            repository = MongoRepository(
                settings.mongodb_uri,
                settings.mongodb_database,
                settings.mongodb_vector_index,
                settings.mongodb_timeout_ms,
            )
        else:
            repository = InMemoryRepository()
    ollama = OllamaAdapter(
        settings.ollama_base_url,
        settings.ollama_chat_model,
        settings.ollama_embed_model,
        settings.ollama_timeout_seconds,
        settings.ollama_context_window,
        settings.ollama_max_output_tokens,
        settings.ollama_reasoning_effort,
    )
    chat_model = chat_model or _build_chat_model(settings, ollama)
    embedder = embedder or _build_embedder(settings, ollama)
    service = ContinuumService(settings, repository, chat_model, embedder)
    large_chat: ChatModel | None = None
    if settings.model_provider == "openrouter":
        # No cross-vendor fallback: a failed call retries the same large model.
        large_chat = OpenRouterChatModel(
            settings.openrouter_api_key,
            model=settings.openrouter_large_model,
            fallback_model=settings.openrouter_large_model,
            max_output_tokens=settings.ollama_max_output_tokens,
            reasoning_effort=settings.ollama_reasoning_effort,
        )
    bench_harness = BenchHarness(service, large_chat=large_chat)

    app = FastAPI(title="Continuum V1 API", version="0.1.0")
    app.state.continuum_service = service
    app.state.bench_harness = bench_harness
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Organization-ID", "X-Agent-ID"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {"msg": "invalid request"}
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = first.get("msg", "invalid request")
        detail = f"{location}: {message}" if location else str(message)
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(ContinuumError)
    async def continuum_error_handler(_: Request, exc: ContinuumError) -> JSONResponse:
        if isinstance(exc, NotFoundError):
            status = 404
        elif isinstance(exc, ConflictError):
            status = 409
        elif isinstance(exc, DependencyError):
            status = 503
        else:
            status = 400
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        try:
            from pymongo.errors import PyMongoError
        except ImportError:  # pragma: no cover - dependency is declared
            PyMongoError = ()  # type: ignore[assignment]
        if PyMongoError and isinstance(exc, PyMongoError):
            return JSONResponse(
                status_code=503,
                content={"detail": "MongoDB operation failed; check Atlas connectivity and configuration"},
            )
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    def get_service(request: Request) -> ContinuumService:
        return request.app.state.continuum_service

    def get_bench(request: Request) -> BenchHarness:
        return request.app.state.bench_harness

    def get_identity(
        organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
        agent_id: Annotated[str | None, Header(alias="X-Agent-ID")] = None,
    ) -> Identity:
        organization_id = (organization_id or settings.organization_id).strip()
        agent_id = (agent_id or settings.agent_id).strip()
        if not organization_id or not agent_id or len(organization_id) > 200 or len(agent_id) > 200:
            raise HTTPException(status_code=422, detail="organization and agent headers must be 1-200 characters")
        return Identity(organization_id=organization_id, agent_id=agent_id)

    Service = Annotated[ContinuumService, Depends(get_service)]
    Bench = Annotated[BenchHarness, Depends(get_bench)]
    Scope = Annotated[Identity, Depends(get_identity)]

    @app.get("/api/health")
    async def health(api: Service) -> dict:
        return await api.health()

    @app.post("/api/demo/reset")
    async def reset_demo(
        identity: Scope,
        api: Service,
        body: DemoResetRequest = Body(default_factory=DemoResetRequest),
    ) -> dict:
        if (
            identity.organization_id != settings.organization_id
            or identity.agent_id != settings.agent_id
        ):
            raise HTTPException(
                status_code=403,
                detail="demo reset is restricted to the configured demo organization and agent",
            )
        return await api.reset_demo(identity, body.seed)

    @app.get("/api/demo/summary")
    def demo_summary(identity: Scope, api: Service) -> dict:
        return api.demo_summary(identity)

    @app.get("/api/memories")
    async def list_memories(
        identity: Scope,
        api: Service,
        memory_type: Annotated[str | None, Query(alias="type", min_length=1)] = None,
        status: Annotated[str | None, Query(min_length=1)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        query: Annotated[str | None, Query(min_length=1, max_length=8_000)] = None,
    ) -> dict:
        items, total = await api.list_memories(identity, memory_type, status, limit, query)
        return {"items": items, "total": total}

    @app.post("/api/memories")
    async def create_memory(body: MemoryCreate, identity: Scope, api: Service):
        return await api.create_memory(identity, body)

    @app.post("/api/recommendations")
    async def recommend(body: RecommendationRequest, identity: Scope, api: Service):
        return await api.recommend(identity, body)

    @app.get("/api/decisions/{decision_id}/explanation")
    def explanation(decision_id: str, identity: Scope, api: Service) -> dict:
        return api.explanation(identity, decision_id)

    @app.post("/api/outcomes")
    def record_outcome(body: OutcomeCreate, identity: Scope, api: Service):
        return api.record_outcome(identity, body)

    @app.get("/api/policies")
    def policies(identity: Scope, api: Service) -> dict:
        active, history = api.repository.get_policies(identity)
        return {"active": active, "history": history}

    @app.get("/api/proposals")
    def proposals(identity: Scope, api: Service) -> dict:
        return {"items": api.repository.list_proposals(identity)}

    @app.post("/api/proposals/analyze")
    def analyze_proposals(identity: Scope, api: Service) -> dict:
        return api.analyze_proposals(identity)

    @app.post("/api/proposals/{proposal_id}/decision")
    def decide_proposal(
        proposal_id: str, body: ProposalDecisionRequest, identity: Scope, api: Service
    ) -> dict:
        return api.decide_proposal(identity, proposal_id, body)

    @app.get("/api/audit-events")
    def audit_events(
        identity: Scope,
        api: Service,
        decision_id: Annotated[str | None, Query(min_length=1)] = None,
        event_type: Annotated[str | None, Query(min_length=1)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict:
        return {
            "items": api.repository.list_audit(
                identity, decision_id=decision_id, event_type=event_type, limit=limit
            )
        }

    @app.post("/api/bench/run")
    async def run_bench(
        identity: Scope,
        bench: Bench,
        body: BenchRunRequest = Body(default_factory=BenchRunRequest),
    ) -> dict:
        return await bench.run(
            identity, body.arms, body.repeats, body.task_limit, body.adapt, task_set=body.task_set
        )

    @app.get("/api/bench/runs")
    def list_bench_runs(identity: Scope, bench: Bench) -> dict:
        return {"items": bench.list_runs(identity)}

    @app.get("/api/bench/runs/{run_id}")
    def get_bench_run(run_id: str, identity: Scope, bench: Bench) -> dict:
        return bench.get_run(identity, run_id)

    return app


app = create_app()
