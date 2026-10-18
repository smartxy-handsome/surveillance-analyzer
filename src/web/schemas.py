from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from typing import Literal

from src.core.models import DETECTION_TARGET_CLASSES


class JobCreateRequest(BaseModel):
    file_path: str
    detection_target: str = "person"

    @field_validator("detection_target")
    @classmethod
    def _validate_target(cls, v: str) -> str:
        if v not in DETECTION_TARGET_CLASSES:
            allowed = ", ".join(sorted(DETECTION_TARGET_CLASSES))
            raise ValueError(f"detection_target must be one of: {allowed}")
        return v


class VideoMetadataResponse(BaseModel):
    duration: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    total_frames: int | None = None


class JobProgress(BaseModel):
    processed: int
    total: int
    percent: float


class JobResponse(BaseModel):
    id: str
    filename: str
    status: str
    created_at: datetime
    detection_target: str = "person"
    video_metadata: VideoMetadataResponse | None = None
    total_segments: int = 0
    total_person_time: float = 0.0
    processing_time_seconds: float | None = None
    dropped_frames: int | None = None
    queue_position: int | None = None
    progress: JobProgress | None = None


class SegmentResponse(BaseModel):
    id: int
    start_time: float
    end_time: float
    start_time_formatted: str
    end_time_formatted: str
    duration_seconds: float
    detection_count: int
    avg_confidence: float
    max_confidence: float


class ProgressEvent(BaseModel):
    frames_processed: int
    total_frames: int
    percent: float


class CaptureResponse(BaseModel):
    id: int
    segment_index: int
    timestamp: float
    timestamp_formatted: str
    confidence: float
    crop_url: str
    annotated_url: str | None = None
    kind: str = "appearance"
    target: str = "person"


class VehicleEventResponse(BaseModel):
    id: int
    enter_time: float
    exit_time: float
    enter_time_formatted: str
    exit_time_formatted: str
    duration_seconds: float
    detection_count: int
    avg_confidence: float
    max_confidence: float
    plate_number: str | None = None
    plate_confidence: float | None = None
    plate_type: str | None = None
    enter_capture: CaptureResponse | None = None
    exit_capture: CaptureResponse | None = None
    plate_capture: CaptureResponse | None = None


class ReviewMarkRequest(BaseModel):
    target_type: Literal["capture", "segment", "vehicle_event"]
    target_id: int
    verdict: Literal["good", "bad"]


class ReviewMarkResponse(BaseModel):
    target_type: str
    target_id: int
    verdict: str


class MissedEventRequest(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    note: str | None = None


class MissedEventResponse(BaseModel):
    id: int
    start_seconds: float
    end_seconds: float
    note: str | None = None
