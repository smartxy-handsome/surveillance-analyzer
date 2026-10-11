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
    # yolov8m@1280 on real night surveillance footage: 2.5x more confirmed
    # (peak conf >= 0.5) records and 40% fewer suspected ones than yolov8s,
    # at ~1.2x wall time (inference 54fps, still decode-adjacent). yolov8s@640
    # found 2.3x more than yolov8n@640 — upgrade when GPU headroom allows.
    model_name: str = "yolov8m.pt"
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
    # Recall escape hatch (宁可多截不要漏截): a burst shorter than
    # min_segment_seconds is still kept when its peak confidence reaches this.
    # 0.5 = what the pre-tracking configuration accepted; those detections
    # must never vanish without a capture. Noise blips peak lower and stay
    # filtered.
    min_segment_rescue_conf: float = 0.5
    # Group detections by ByteTrack identity instead of frame-level presence:
    # one track = one enter/exit record, so a person briefly lost by the
    # detector mid-walk no longer splits into several sawtooth segments.
    use_tracking: bool = True
    # ID-switch dedup: the tracker occasionally re-IDs the same person,
    # producing overlapping records for one body. Records whose time spans
    # touch within this gap AND whose boundary boxes coincide (IoU below)
    # are merged into one record. IoU 0 disables merging.
    record_merge_gap_seconds: float = 2.0
    record_merge_iou: float = 0.5


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


# Analysis target -> COCO class filter fed to the detector.
# Vehicles = four-wheeled and above (car 2 / bus 5 / truck 7); motorcycles
# and bicycles are deliberately excluded (rider unobstructed -> person
# detection covers them).
DETECTION_TARGET_CLASSES: dict[str, list[int]] = {
    "person": [0],
    "vehicle": [2, 5, 7],
    "both": [0, 2, 5, 7],
}


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
    # Largest-box-area frame for the segment -- the plate close-up source on
    # the vehicle path; None on the person path.
    plate_candidate: CaptureCandidate | None = None


@dataclass
class VehicleEventData:
    """One vehicle's enter/exit record with its capture candidates.

    Assembled by the coordinator from the vehicle-class track; the plate
    candidate is the frame where the vehicle box was largest (closest to
    the camera, most plate pixels).
    """

    ordinal: int
    enter_time: float
    exit_time: float
    detection_count: int
    avg_confidence: float
    max_confidence: float
    enter_candidate: CaptureCandidate | None = None
    exit_candidate: CaptureCandidate | None = None
    plate_candidate: CaptureCandidate | None = None

    @property
    def duration(self) -> float:
        return self.exit_time - self.enter_time


@dataclass
class PlateResult:
    """License plate readout; number is None when recognition failed
    (留空 + 置信度, never a placeholder string)."""

    number: str | None
    confidence: float
    plate_type: str | None = None
    plate_box: tuple[int, int, int, int] | None = None


@dataclass
class CaptureResult:
    """Result of saving a capture to disk."""

    segment_index: int
    timestamp: float
    confidence: float
    crop_path: str
    annotated_path: str
    kind: str = "appearance"  # appearance | departure | plate


@dataclass
class PipelineResult:
    """Result from the detection pipeline."""

    segments: list[TimeSegment]
    captures: list[SegmentCaptureData]
    dropped_frames: int = 0
    vehicle_events: list["VehicleEventData"] = field(default_factory=list)
