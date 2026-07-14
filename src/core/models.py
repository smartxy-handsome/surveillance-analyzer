from dataclasses import dataclass, field

import numpy as np


@dataclass
class TimeSegment:
    start_time: float
    end_time: float
    detection_count: int
    avg_confidence: float
    max_confidence: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass
class SamplingConfig:
    fps: float = 3.0
    strategy: str = "uniform"


@dataclass
class DetectionConfig:
    model_name: str = "yolov8n.pt"
    confidence_threshold: float = 0.5
    device: str = "cuda:0"
    target_classes: list[int] = field(default_factory=lambda: [0])
    batch_size: int = 8


@dataclass
class AggregationConfig:
    merge_gap_seconds: float = 2.0
    min_segment_seconds: float = 1.0


@dataclass
class PipelineConfig:
    frame_queue_size: int = 64
    num_decode_threads: int = 2
    num_inference_threads: int = 1


@dataclass
class VideoConfig:
    supported_formats: list[str] = field(
        default_factory=lambda: [".mp4", ".avi", ".mkv", ".mov"]
    )
    max_file_size_mb: int = 2048


@dataclass
class StorageConfig:
    database_url: str = "sqlite+aiosqlite:///./data/results.db"
    video_storage_dir: str = "./data/videos"


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
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
