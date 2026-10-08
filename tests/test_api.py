import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import load_config
from src.storage.database import Base
from src.storage.repository import CaptureRepository, JobRepository, SegmentRepository
from src.web.app import create_app


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    config = load_config("config/default.yaml")

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = create_app(lifespan_fn=noop_lifespan)
    app.state.config = config
    app.state.job_repo = JobRepository(session_factory)
    app.state.segment_repo = SegmentRepository(session_factory)
    app.state.capture_repo = CaptureRepository(session_factory)
    app.state.session_factory = session_factory
    app.state.analysis_semaphore = asyncio.Semaphore(config.pipeline.max_concurrent_jobs)
    app.state.job_progress = {}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.test_app = app  # exposed for tests that need direct repo access
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_create_job(client, tmp_path):
    video = tmp_path / "test.mp4"
    video.write_bytes(b"\x00" * 100)
    resp = await client.post("/api/jobs", json={"file_path": str(video)})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] is not None
    assert data["filename"] == "test.mp4"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_create_job_file_not_found(client):
    resp = await client.post("/api/jobs", json={"file_path": "Z:\\nonexistent\\video.mp4"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_job_unsupported_format(client, tmp_path):
    txt = tmp_path / "test.txt"
    txt.write_text("hello")
    resp = await client.post("/api/jobs", json={"file_path": str(txt)})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_jobs(client):
    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_job_progress_exposed(client, tmp_path, monkeypatch):
    """Analysis progress written by the pipeline callback is exposed on the
    job response as {processed, total, percent}."""
    from src.web.routes import jobs as jobs_module

    async def fake_run(job_id, app, detector_factory=None):
        app.state.job_progress[job_id] = {"processed": 5, "total": 10, "percent": 50.0}

    monkeypatch.setattr(jobs_module, "_run_analysis", fake_run)

    video = tmp_path / "test.mp4"
    video.write_bytes(b"\x00" * 100)
    resp = await client.post("/api/jobs", json={"file_path": str(video)})
    assert resp.status_code == 201
    assert resp.json()["progress"] is None  # nothing processed at creation time
    job_id = resp.json()["id"]

    resp = await client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["progress"] == {"processed": 5, "total": 10, "percent": 50.0}

    resp = await client.get("/api/jobs")
    progress_by_id = {j["id"]: j["progress"] for j in resp.json()}
    assert progress_by_id[job_id] == {"processed": 5, "total": 10, "percent": 50.0}


@pytest.mark.asyncio
async def test_get_job_not_found(client):
    resp = await client.get("/api/jobs/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_job_not_found(client):
    resp = await client.delete("/api/jobs/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_segments_not_found(client):
    resp = await client.get("/api/jobs/nonexistent/segments")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_browse_root(client):
    resp = await client.get("/api/browse", params={"path": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_browse_directory(client, tmp_path):
    (tmp_path / "test.mp4").write_bytes(b"\x00" * 10)
    (tmp_path / "subdir").mkdir()
    resp = await client.get("/api/browse", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    data = resp.json()
    names = [i["name"] for i in data["items"]]
    assert "test.mp4" in names
    assert "subdir" in names


@pytest.mark.asyncio
async def test_browse_not_found(client):
    resp = await client.get("/api/browse", params={"path": "Z:\\nonexistent"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_job_removes_capture_dir(client, tmp_path, monkeypatch):
    """Deleting a job removes its capture directory from data/captures/."""
    from src.core.config import DATA_DIR
    from src.web.routes import jobs as jobs_module

    async def fake_run(job_id, app, detector_factory=None):
        pass

    monkeypatch.setattr(jobs_module, "_run_analysis", fake_run)

    video = tmp_path / "test.mp4"
    video.write_bytes(b"\x00" * 100)
    resp = await client.post("/api/jobs", json={"file_path": str(video)})
    job_id = resp.json()["id"]

    # Simulate captures having been written for this job
    d = DATA_DIR / "captures" / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "seg1_00_1.0s_annotated.jpg").write_bytes(b"img")

    resp = await client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 204
    assert not d.exists()


@pytest.mark.asyncio
async def test_delete_job_rejects_processing(client, tmp_path):
    """A processing job cannot be deleted (would strand the pipeline)."""
    from src.web.routes import jobs as jobs_module
    from src.storage.repository import JobCreate

    video = tmp_path / "test.mp4"
    video.write_bytes(b"\x00" * 100)
    job_id = "proc-job-1"
    await client.test_app.state.job_repo.create(
        JobCreate(
            id=job_id,
            filename="test.mp4",
            file_path=str(video.resolve()),
            sampling_fps=3.0,
            model_name="yolov8n.pt",
            confidence_threshold=0.5,
            merge_gap_seconds=2.0,
            min_segment_seconds=1.0,
        )
    )
    await client.test_app.state.job_repo.update_status(job_id, "processing")

    resp = await client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 409
    # Job must still exist
    resp = await client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
