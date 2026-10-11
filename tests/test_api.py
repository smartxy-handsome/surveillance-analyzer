import asyncio
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import load_config
from src.storage.database import Base
from src.storage.repository import (
    CaptureRepository,
    JobRepository,
    SegmentRepository,
    VehicleEventRepository,
)
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
    app.state.vehicle_event_repo = VehicleEventRepository(session_factory)
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


@pytest.mark.asyncio
async def test_create_job_rejects_oversize_file(client, tmp_path, monkeypatch):
    """Files above video.max_file_size_mb are rejected at submit time."""
    video = tmp_path / "big.mp4"
    video.write_bytes(b"\x00" * 100)

    config = client.test_app.state.config
    monkeypatch.setattr(config.video, "max_file_size_mb", 0)

    resp = await client.post("/api/jobs", json={"file_path": str(video)})
    assert resp.status_code == 400
    assert "max size" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_queue_position_orders_pending_jobs(client, tmp_path):
    """Pending jobs get 1-based FIFO queue positions by creation order.

    Jobs are inserted via the repo (not POST) so no background task runs;
    under ASGITransport a blocked _run_analysis would deadlock the request.
    """
    from src.storage.repository import JobCreate

    repo = client.test_app.state.job_repo
    ids = []
    for i in range(3):
        video = tmp_path / f"q{i}.mp4"
        video.write_bytes(b"\x00" * 100)
        job_id = f"queued-{i}"
        await repo.create(
            JobCreate(
                id=job_id,
                filename=f"q{i}.mp4",
                file_path=str(video.resolve()),
                sampling_fps=3.0,
                model_name="yolov8n.pt",
                confidence_threshold=0.5,
                merge_gap_seconds=2.0,
                min_segment_seconds=1.0,
            )
        )
        ids.append(job_id)

    resp = await client.get("/api/jobs")
    by_id = {j["id"]: j for j in resp.json()}
    # All three are pending; positions must be 1, 2, 3 in creation order
    assert [by_id[j]["queue_position"] for j in ids] == [1, 2, 3]

    # Single-job endpoint agrees with the list endpoint
    for j in ids:
        single = await client.get(f"/api/jobs/{j}")
        assert single.json()["queue_position"] == by_id[j]["queue_position"]

    # Once a job leaves the queue, the others renumber
    await repo.update_status(ids[0], "processing")
    resp = await client.get("/api/jobs")
    by_id = {j["id"]: j for j in resp.json()}
    assert [by_id[j]["queue_position"] for j in ids[1:]] == [1, 2]


def test_create_app_uses_config_cors_origins():
    """create_app(config=...) wires web.cors_origins into the middleware.

    The production entrypoint (src.main) loads the config and passes it here;
    the middleware is built at app-construction time and cannot read
    app.state, so this is the only place the config can reach it.
    """
    from src.core.models import AppConfig, WebConfig
    from src.web.app import create_app

    config = AppConfig(web=WebConfig(cors_origins=["http://example.test:5173"]))
    app = create_app(config=config)
    middleware = next(
        m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"
    )
    assert middleware.kwargs["allow_origins"] == ["http://example.test:5173"]


@pytest.mark.asyncio
async def test_run_analysis_skips_deleted_queued_job(client, tmp_path, monkeypatch):
    """A job deleted while queued is skipped, not crashed, when its turn comes.

    Previously _run_analysis unconditionally dereferenced job.file_path and
    the AttributeError was swallowed into a confusing 'failed' write on a
    row that no longer existed -- while holding a semaphore slot.
    """
    from src.web.routes import jobs as jobs_module
    from src.storage.repository import JobCreate

    async def fake_run(job_id, app, detector_factory=None):
        await jobs_module._run_analysis(job_id, app, detector_factory)

    # No monkeypatch: we want the REAL _run_analysis; the job's file_path
    # points at a real file so only the deleted-row path is exercised.
    video = tmp_path / "q.mp4"
    video.write_bytes(b"\x00" * 100)
    repo = client.test_app.state.job_repo
    job_id = "deleted-queued-1"
    await repo.create(
        JobCreate(
            id=job_id,
            filename="q.mp4",
            file_path=str(video.resolve()),
            sampling_fps=3.0,
            model_name="yolov8n.pt",
            confidence_threshold=0.5,
            merge_gap_seconds=2.0,
            min_segment_seconds=1.0,
        )
    )
    # The job is deleted (by the user) while still pending in the queue
    await repo.delete(job_id)

    # Its turn comes: must return without raising and without writing
    # a 'failed' status for a non-existent row.
    await jobs_module._run_analysis(job_id, client.test_app, None)
    assert await repo.get(job_id) is None


@pytest.mark.asyncio
async def test_create_job_with_detection_target(client, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00" * 100)
    resp = await client.post(
        "/api/jobs", json={"file_path": str(video), "detection_target": "vehicle"}
    )
    assert resp.status_code == 201
    assert resp.json()["detection_target"] == "vehicle"

    resp = await client.get(f"/api/jobs/{resp.json()['id']}")
    assert resp.json()["detection_target"] == "vehicle"


@pytest.mark.asyncio
async def test_create_job_rejects_unknown_target(client, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00" * 100)
    resp = await client.post(
        "/api/jobs", json={"file_path": str(video), "detection_target": "bird"}
    )
    assert resp.status_code == 422  # pydantic validation


@pytest.mark.asyncio
async def test_vehicle_events_endpoint_roundtrip(client, tmp_path):
    """Seeded vehicle events + kind-tagged captures come back grouped."""
    from src.storage.repository import (
        CaptureCreate,
        JobCreate,
        VehicleEventCreate,
    )

    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00" * 100)
    repo = client.test_app.state.job_repo
    job_id = "veh-1"
    await repo.create(
        JobCreate(
            id=job_id,
            filename="v.mp4",
            file_path=str(video.resolve()),
            detection_target="vehicle",
            sampling_fps=3.0,
            model_name="yolov8m.pt",
            confidence_threshold=0.3,
            merge_gap_seconds=2.0,
            min_segment_seconds=1.0,
        )
    )
    ve_repo = client.test_app.state.vehicle_event_repo
    await ve_repo.bulk_create(
        job_id,
        [
            VehicleEventCreate(
                enter_time=10.0,
                exit_time=25.0,
                detection_count=12,
                avg_confidence=0.8,
                max_confidence=0.9,
                plate_number="京A12345",
                plate_confidence=0.97,
                plate_type="blue",
            )
        ],
    )
    await client.test_app.state.capture_repo.bulk_create(
        job_id,
        [
            CaptureCreate(
                segment_index=1,
                timestamp=10.0,
                confidence=0.9,
                crop_path="C:\captures\enter.jpg",
                annotated_path="C:\captures\enter_ann.jpg",
                kind="appearance",
            ),
            CaptureCreate(
                segment_index=1,
                timestamp=25.0,
                confidence=0.9,
                crop_path="C:\captures\exit.jpg",
                annotated_path="C:\captures\exit_ann.jpg",
                kind="departure",
            ),
            CaptureCreate(
                segment_index=1,
                timestamp=22.0,
                confidence=0.9,
                crop_path="C:\captures\plate.jpg",
                annotated_path="",
                kind="plate",
            ),
        ],
    )

    resp = await client.get(f"/api/jobs/{job_id}/vehicle-events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    ev = events[0]
    assert ev["enter_time"] == 10.0 and ev["exit_time"] == 25.0
    assert ev["plate_number"] == "京A12345"
    assert ev["plate_type"] == "blue"
    assert ev["enter_capture"]["kind"] == "appearance"
    assert ev["plate_capture"]["kind"] == "plate"
    # plate capture has no annotated image
    assert ev["plate_capture"]["annotated_url"] is None
