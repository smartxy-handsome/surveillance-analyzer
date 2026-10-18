import asyncio
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, JSONResponse

from src.core.config import load_config
from src.core.models import AppConfig, WebConfig
from src.storage.database import init_db
from src.storage.repository import (
    CaptureRepository,
    JobRepository,
    MissedEventRepository,
    ReviewMarkRepository,
    SegmentRepository,
    VehicleEventRepository,
)
from src.web.routes.jobs import create_jobs_router
from src.web.routes.results import create_results_router


class APIKeyMiddleware:
    """Reject /api requests lacking the configured X-API-Key.

    Pure ASGI middleware (not BaseHTTPMiddleware) so it cannot interfere
    with background tasks. /health and static assets stay open: the key
    only gates data and job-control endpoints.
    """

    def __init__(self, app, api_key: str):
        self.app = app
        self._api_key = api_key.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api"):
            headers = dict(scope.get("headers", []))
            supplied = headers.get(b"x-api-key", b"")
            if not hmac.compare_digest(supplied, self._api_key):
                response = JSONResponse(
                    {"detail": "Invalid or missing API key"}, status_code=401
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_app may already have installed a config (production path); only
    # load one when absent (e.g. tests injecting their own state).
    if not hasattr(app.state, "config"):
        config = load_config(Path("config/default.yaml"))
        app.state.config = config
    config = app.state.config
    session_factory = await init_db(config.storage.database_url)
    job_repo = JobRepository(session_factory)
    segment_repo = SegmentRepository(session_factory)
    capture_repo = CaptureRepository(session_factory)
    vehicle_event_repo = VehicleEventRepository(session_factory)

    app.state.job_repo = job_repo
    app.state.segment_repo = segment_repo
    app.state.capture_repo = capture_repo
    app.state.vehicle_event_repo = vehicle_event_repo
    app.state.review_repo = ReviewMarkRepository(session_factory)
    app.state.missed_event_repo = MissedEventRepository(session_factory)
    app.state.session_factory = session_factory
    app.state.analysis_semaphore = asyncio.Semaphore(config.pipeline.max_concurrent_jobs)
    # Ephemeral per-job analysis progress (job_id -> {processed, total, percent});
    # cleared when the job completes or fails.
    app.state.job_progress = {}

    yield


def create_app(lifespan_fn=None, config: AppConfig | None = None) -> FastAPI:
    """Create the FastAPI app.

    ``config`` is optional: when given (production path) it drives the CORS
    middleware, which must be constructed before the app starts and therefore
    cannot read app.state. Without it, a config is loaded in lifespan.
    """
    if config is not None:
        cors_origins = config.web.cors_origins
    else:
        cors_origins = WebConfig().cors_origins

    app = FastAPI(
        title="Surveillance Analyzer",
        version="0.1.0",
        lifespan=lifespan_fn or lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if config is not None and config.web.auth_enabled:
        # load_config already rejects an enabled guard with a blank key;
        # this also covers AppConfig built directly in tests.
        if not config.web.auth_api_key:
            raise ValueError("web.auth_enabled requires a non-empty web.auth_api_key")
        app.add_middleware(APIKeyMiddleware, api_key=config.web.auth_api_key)

    if config is not None:
        app.state.config = config

    app.include_router(create_jobs_router(), prefix="/api")
    app.include_router(create_results_router(), prefix="/api")

    @app.get("/health")
    async def health():
        import torch

        return {
            "status": "ok",
            "gpu_available": torch.cuda.is_available(),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }

    # Mount frontend static files (production mode)
    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = frontend_dist / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()
