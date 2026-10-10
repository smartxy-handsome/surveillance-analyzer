from dataclasses import dataclass, field

import numpy as np


@dataclass
class TimeSegment:
    start_time: float
    end_time: float
    detection_count: int
    avg_confidence: float
    max_confidence: float
    # Aggregator-internal key identifying the source burst/track; captures
    # join back to their segment through it. None for legacy-constructed
    # segments.
    source_key: int | None = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass
class SamplingConfig:
    fps: float = 3.0
    strategy: str = "uniform"


@dataclass
class DetectionConfig:
    # yolov8s + imgsz 1280 measured 2.3x more person detections than
    # yolov8n@640 on real 720p surveillance footage (small/far persons), and
    # the pipeline stays decode-bound so wall time only grows ~1.5x.
    model_name: str = "yolov8s.pt"
    # Low on purpose: recall first (宁可多截不要漏截). The tracker and the
    # min-segment filter absorb the extra noise; short spurious bursts are
    # dropped at aggregation time.
    confidence_threshold: float = 0.3
    device: str = "cuda:0"
    target_classes: list[int] = field(default_factory=lambda: [0])
    batch_size: int = 8
    # Inference input size. Lower (640) on CPU-only machines or close-up
    # cameras; higher finds smaller subjects at ~4x the compute.
    imgsz: int = 1280


@dataclass
class AggregationConfig:
    merge_gap_seconds: float = 2.0
    min_segment_seconds: float = 1.0
    # Group detections by ByteTrack identity instead of frame-level presence:
    # one track = one enter/exit record, so a person briefly lost by the
    # detector mid-walk no longer splits into several sawtooth segments.
    use_tracking: bool = True


@dataclass
class PipelineConfig:
    frame_queue_size: int = 64
    # Must stay 1: parallel decode threads deliver frames out of order, which
    # corrupts the aggregator's gap logic (it assumes chronological arrival).
    num_decode_threads: int = 1
    num_inference_threads: int = 1
    max_concurrent_jobs: int = 1


@dataclass
class VideoConfig:
    supported_formats: list[str] = field(
        default_factory=lambda: [".mp4", ".avi", ".mkv", ".mov"]
    )
    max_file_size_mb: int = 2048
    # Try GPU-assisted decoding (D3D11/DXVA on Windows) and fall back to
    # software automatically when unavailable.
    hw_accel: bool = True


@dataclass
class StorageConfig:
    database_url: str = "sqlite+aiosqlite:///./data/results.db"
    video_storage_dir: str = "./data/videos"


@dataclass
class WebConfig:
    # Listen on loopback by default: the API has no authentication and /browse
    # can list any directory, so binding 0.0.0.0 would expose the whole disk
    # to the LAN. Change explicitly to share on a network.
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])


@dataclass
class AppConfig:
    video: VideoConfig = field(default_factory=VideoConfig)
    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    aggregation: AggregationConfig = field(default_factory=AggregationConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    web: WebConfig = field(default_factory=WebConfig)


@dataclass
class CaptureCandidate:
    """A candidate frame for capture, with detection metadata."""
    frame_index: int
    timestamp: float
    confidence: float
    image: np.ndarray
    boxes: list[tuple[int, int, int, int]]  # (x1, y1, x2, y2)


@dataclass
class SegmentCaptureData:
    """Capture candidates for a single time segment."""
    segment_index: int
    start_time: float
    end_time: float
    candidates: list[CaptureCandidate]


@dataclass
class CaptureResult:
    """Result of saving a capture to disk."""
    segment_index: int
    timestamp: float
    confidence: float
    crop_path: str
    annotated_path: str


@dataclass
class PipelineResult:
    """Result from the detection pipeline."""

    segments: list[TimeSegment]
    captures: list[SegmentCaptureData]
    dropped_frames: int = 0
