import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from src.core.config import load_config
from src.storage.database import init_db
from src.storage.repository import CaptureRepository, JobRepository, SegmentRepository
from src.web.routes.jobs import create_jobs_router
from src.web.routes.results import create_results_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config(Path("config/default.yaml"))
    session_factory = await init_db(config.storage.database_url)
    job_repo = JobRepository(session_factory)
    segment_repo = SegmentRepository(session_factory)
    capture_repo = CaptureRepository(session_factory)

    app.state.config = config
    app.state.job_repo = job_repo
    app.state.segment_repo = segment_repo
    app.state.capture_repo = capture_repo
    app.state.session_factory = session_factory
    app.state.analysis_semaphore = asyncio.Semaphore(config.pipeline.max_concurrent_jobs)
    # Ephemeral per-job analysis progress (job_id -> {processed, total, percent});
    # cleared when the job completes or fails.
    app.state.job_progress = {}

    yield


def create_app(lifespan_fn=None) -> FastAPI:
    app = FastAPI(
        title="Surveillance Analyzer",
        version="0.1.0",
        lifespan=lifespan_fn or lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
