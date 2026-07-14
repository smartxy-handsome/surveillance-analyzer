from datetime import datetime

from pydantic import BaseModel


class JobCreateRequest(BaseModel):
    file_path: str


class VideoMetadataResponse(BaseModel):
    duration: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    total_frames: int | None = None


class JobResponse(BaseModel):
    id: str
    filename: str
    status: str
    created_at: datetime
    video_metadata: VideoMetadataResponse | None = None
    total_segments: int = 0
    total_person_time: float = 0.0
    processing_time_seconds: float | None = None


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
    annotated_url: str
