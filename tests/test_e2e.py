"""End-to-end tests over a synthetic video.

Two levels:
- Pipeline: real OpenCVFrameReader + PipelineCoordinator against a video
  written by cv2.VideoWriter, with a content-based fake detector (bright
  frame = person present). Exercises reader, sampler, queue, aggregator
  and capture collector together.
- API: the real app with a fake detector injected via app.state.
  detector_factory; POST /api/jobs runs the actual _run_analysis
  (real reader, real pipeline, real CaptureSaver writing to
  data/captures/{job_id}) and the whole HTTP -> pipeline -> DB -> disk
  chain is asserted, including capture image serving and delete cleanup.
"""

import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import DATA_DIR, load_config
from src.core.interfaces import DetectionEngine, FrameDetection
from src.core.models import (
    AggregationConfig,
    DetectionConfig,
    PipelineConfig,
    SamplingConfig,
)
from src.pipeline.coordinator import PipelineCoordinator
from src.storage.database import Base
from src.storage.repository import CaptureRepository, JobRepository, SegmentRepository
from src.video.reader import OpenCVFrameReader
from src.video.sampler import compute_frame_indices
from src.web.app import create_app

W, H = 64, 48
FPS = 10.0
N_FRAMES = 30
PERSON_FIRST, PERSON_LAST = 10, 29  # bright frames = "person" frames


def write_synthetic_video(path: Path, person_first=PERSON_FIRST, person_last=PERSON_LAST):
    """30 frames @ 10fps; frames in [person_first, person_last] are white."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H))
    if not writer.isOpened():
        pytest.skip("MJPG/AVI codec unavailable in this OpenCV build")
    for i in range(N_FRAMES):
        bright = person_first <= i <= person_last
        frame = np.full((H, W, 3), 255 if bright else 0, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    if not path.exists() or path.stat().st_size == 0:
        pytest.skip("VideoWriter produced no file")


class BrightFrameDetector(DetectionEngine):
    """Fake detector: a bright frame counts as a confident person detection."""

    def __init__(self, threshold: float = 127.0):
        self._threshold = threshold

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def detect(self, frames):
        return [
            FrameDetection(
                has_person=float(f.mean()) > self._threshold,
                confidence=0.9,
                boxes=[(8, 8, 24, 24)],
            )
            for f in frames
        ]


def test_pipeline_end_to_end_synthetic_video(tmp_path):
    video = tmp_path / "synthetic.avi"
    write_synthetic_video(video)

    sampling = SamplingConfig(fps=10.0)  # -> every frame
    detection = DetectionConfig(batch_size=8)
    aggregation = AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=0.5)
    pipeline_cfg = PipelineConfig(frame_queue_size=32, num_decode_threads=1)

    coordinator = PipelineCoordinator(
        reader_factory=OpenCVFrameReader,
        video_path=str(video),
        detector=BrightFrameDetector(),
        sampling_config=sampling,
        detection_config=detection,
        aggregation_config=aggregation,
        pipeline_config=pipeline_cfg,
    )

    indices = compute_frame_indices(FPS, sampling.fps, N_FRAMES)
    assert len(indices) == N_FRAMES

    result = coordinator.run(indices, FPS)

    assert result.dropped_frames == 0
    assert len(result.segments) == 1
    seg = result.segments[0]
    assert seg.start_time == pytest.approx(1.0)  # frame 10
    assert seg.end_time == pytest.approx(2.9)  # frame 29
    assert seg.detection_count == 20

    assert len(result.captures) == 1
    cap = result.captures[0]
    assert cap.segment_index == 1
    # Appearance and departure captures
    assert [c.timestamp for c in cap.candidates] == [pytest.approx(1.0), pytest.approx(2.9)]


@pytest_asyncio.fixture
async def e2e_client(tmp_path):
    """App with a real DB and fake detector factory, for the API-level E2E."""
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
    import asyncio

    app.state.analysis_semaphore = asyncio.Semaphore(config.pipeline.max_concurrent_jobs)
    app.state.job_progress = {}
    app.state.detector_factory = BrightFrameDetector

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.test_app = app
        yield ac


@pytest.mark.asyncio
async def test_api_end_to_end_synthetic_video(e2e_client, tmp_path):
    video = tmp_path / "synthetic.avi"
    write_synthetic_video(video)

    resp = await e2e_client.post("/api/jobs", json={"file_path": str(video)})
    assert resp.status_code == 201
    job_id = resp.json()["id"]

    capture_dir = DATA_DIR / "captures" / job_id
    try:
        # Background task has completed by now (ASGITransport awaits it)
        resp = await e2e_client.get(f"/api/jobs/{job_id}")
        job = resp.json()
        assert job["status"] == "completed", job
        assert job["dropped_frames"] == 0
        assert job["total_segments"] == 1
        # sampling fps 3 over 10fps video: step 3 -> person frames 12..27,
        # i.e. 6 detections spanning [1.2, 2.7]
        assert job["total_person_time"] == pytest.approx(1.5)
        assert job["video_metadata"]["total_frames"] == 30
        assert job["video_metadata"]["fps"] == pytest.approx(10.0)

        resp = await e2e_client.get(f"/api/jobs/{job_id}/segments")
        segments = resp.json()
        assert len(segments) == 1
        assert segments[0]["start_time"] == pytest.approx(1.2)
        assert segments[0]["end_time"] == pytest.approx(2.7)
        assert segments[0]["detection_count"] == 6

        resp = await e2e_client.get(f"/api/jobs/{job_id}/captures")
        captures = resp.json()
        assert len(captures) == 2  # appearance + departure
        assert [c["segment_index"] for c in captures] == [1, 1]
        assert [c["timestamp"] for c in captures] == [pytest.approx(1.2), pytest.approx(2.7)]

        # Capture images are servable and decode as real JPEGs
        for c in captures:
            for url in (c["crop_url"], c["annotated_url"]):
                resp = await e2e_client.get(url)
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("image/")
                img = cv2.imdecode(np.frombuffer(resp.content, np.uint8), cv2.IMREAD_COLOR)
                assert img is not None

        # Files physically live under data/captures/{job_id}
        assert capture_dir.is_dir()
        assert len(list(capture_dir.glob("*.jpg"))) > 0
    finally:
        # Deleting the job must clean up its capture directory
        resp = await e2e_client.delete(f"/api/jobs/{job_id}")
        assert resp.status_code == 204
        assert not capture_dir.exists()
        shutil.rmtree(capture_dir, ignore_errors=True)
