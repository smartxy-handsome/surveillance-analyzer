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
from src.storage.repository import (
    CaptureRepository,
    JobRepository,
    MissedEventRepository,
    ReviewMarkRepository,
    SegmentRepository,
    VehicleEventRepository,
)
from src.video.reader import OpenCVFrameReader
from src.video.sampler import compute_frame_indices
from src.web.app import create_app

W, H = 64, 48
FPS = 10.0
N_FRAMES = 30
PERSON_FIRST, PERSON_LAST = 10, 29  # bright frames = "person" frames

# Real-footage fixture (user-provided surveillance clip). Tests using it are
# skipped when the file is absent so the suite still runs anywhere.
REAL_VIDEO = Path(r"D:\claude\video.mp4")

needs_real_video = pytest.mark.skipif(
    not REAL_VIDEO.exists(), reason=f"real test video not found: {REAL_VIDEO}"
)


@pytest.fixture
def real_video_meta():
    reader = OpenCVFrameReader()
    meta = reader.open(str(REAL_VIDEO))
    reader.close()
    return meta


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
    app.state.vehicle_event_repo = VehicleEventRepository(session_factory)
    app.state.review_repo = ReviewMarkRepository(session_factory)
    app.state.missed_event_repo = MissedEventRepository(session_factory)
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


# ---------------------------------------------------------------------------
# Real-footage tests (D:\claude\video.mp4): actual codec, actual frame sizes.
# Only the detector is faked -- the whole decode/sample/aggregate path runs
# against genuine surveillance content. The clip is ~74 minutes, so tests
# slice the first ~20 seconds to stay fast.
# ---------------------------------------------------------------------------

REAL_VIDEO_SECONDS = 20


@needs_real_video
def test_reader_real_video_metadata_and_decode(real_video_meta):
    assert real_video_meta.fps > 0
    assert real_video_meta.total_frames > 0
    assert real_video_meta.width > 0 and real_video_meta.height > 0

    reader = OpenCVFrameReader()
    reader.open(str(REAL_VIDEO))
    try:
        for idx in (0, 8, 100):
            ok, frame = reader.read_frame(idx)
            assert ok and frame is not None
            assert frame.shape[:2] == (real_video_meta.height, real_video_meta.width)
    finally:
        reader.close()


@needs_real_video
def test_pipeline_real_video_first_seconds(real_video_meta):
    """Pipeline mechanics on real footage: no drops, captures match segments.

    The fake detector keys on frame brightness, so segment counts depend on
    the content; the assertions are content-independent invariants.
    """
    sampling = SamplingConfig(fps=3.0)
    detection = DetectionConfig(batch_size=8)
    aggregation = AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=1.0)

    max_index = int(real_video_meta.fps * REAL_VIDEO_SECONDS)
    indices = [i for i in compute_frame_indices(
        real_video_meta.fps, sampling.fps, real_video_meta.total_frames
    ) if i <= max_index]
    assert len(indices) >= 40  # ~20s at 3fps

    coordinator = PipelineCoordinator(
        reader_factory=OpenCVFrameReader,
        video_path=str(REAL_VIDEO),
        detector=BrightFrameDetector(threshold=60),
        sampling_config=sampling,
        detection_config=detection,
        aggregation_config=aggregation,
        pipeline_config=PipelineConfig(frame_queue_size=64, num_decode_threads=1),
    )

    result = coordinator.run(indices, real_video_meta.fps)

    # Real footage must decode cleanly (sequential reader handles long-GOP)
    assert result.dropped_frames == 0
    # Every surviving segment produced a capture group, and nothing else
    assert len(result.captures) == len(result.segments)
    for seg, cap in zip(result.segments, result.captures):
        assert seg.start_time <= cap.candidates[0].timestamp
        assert cap.candidates[-1].timestamp <= seg.end_time


# ---------------------------------------------------------------------------
# Vehicle-path E2E: a synthetic "car" (large bright rectangle on a dark
# background) detected by a class-2 scripted detector, driven through the
# real _run_analysis with plate recognition stubbed to a fake.
# ---------------------------------------------------------------------------


class BrightVehicleDetector(DetectionEngine):
    """Fake vehicle detector: bright frame = a car with a fixed box."""

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def detect(self, frames):
        return [
            FrameDetection(
                has_person=float(f.mean()) > 127.0,
                confidence=0.92,
                boxes=[(20, 40, 100, 100)],
                track_ids=[77] if float(f.mean()) > 127.0 else [],
                class_ids=[2] if float(f.mean()) > 127.0 else [],
            )
            for f in frames
        ]


class FakePlateRecognizer:
    """Deterministic stand-in for HyperLPR3."""

    def __init__(self):
        self.calls = 0

    def recognize(self, vehicle_crop):
        self.calls += 1
        from src.core.models import PlateResult

        return PlateResult(number="京A88888", confidence=0.95, plate_type="blue", plate_box=None)


@pytest.mark.asyncio
async def test_api_end_to_end_vehicle_video(e2e_client, tmp_path):
    video = tmp_path / "vehicle.avi"
    # bright frames 10..19 -> one vehicle present 1.0s-1.9s
    write_synthetic_video(video, person_first=10, person_last=19)

    e2e_client.test_app.state.detector_factory = BrightVehicleDetector
    e2e_client.test_app.state.plate_recognizer_factory = FakePlateRecognizer

    resp = await e2e_client.post(
        "/api/jobs", json={"file_path": str(video), "detection_target": "vehicle"}
    )
    assert resp.status_code == 201
    job_id = resp.json()["id"]
    assert resp.json()["detection_target"] == "vehicle"

    capture_dir = DATA_DIR / "captures" / job_id
    try:
        resp = await e2e_client.get(f"/api/jobs/{job_id}")
        job = resp.json()
        assert job["status"] == "completed", job

        resp = await e2e_client.get(f"/api/jobs/{job_id}/vehicle-events")
        events = resp.json()
        assert len(events) == 1
        ev = events[0]
        # 3fps sampling of the 10fps clip: bright frames 10..19 are seen
        # only at sampled frames 12,15,18 -> t 1.2..1.8
        assert ev["enter_time"] == pytest.approx(1.2)
        assert ev["exit_time"] == pytest.approx(1.8)
        assert ev["plate_number"] == "京A88888"
        assert ev["plate_type"] == "blue"
        assert ev["enter_capture"]["kind"] == "appearance"
        assert ev["exit_capture"]["kind"] == "departure"
        assert ev["plate_capture"]["kind"] == "plate"

        # All three images exist on disk and are servable
        for slot in ("enter_capture", "exit_capture", "plate_capture"):
            url = ev[slot]["crop_url"]
            img = await e2e_client.get(url)
            assert img.status_code == 200
            assert img.headers["content-type"].startswith("image/")

        # No person results in vehicle-only mode
        resp = await e2e_client.get(f"/api/jobs/{job_id}/segments")
        assert resp.json() == []
    finally:
        resp = await e2e_client.delete(f"/api/jobs/{job_id}")
        assert resp.status_code == 204
        assert not capture_dir.exists()
