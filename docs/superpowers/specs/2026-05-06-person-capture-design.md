# Person Capture Feature Design

## Overview

Add the ability to capture and save images of detected persons during video analysis. For each time segment where a person is detected, save 3 representative frames (highest confidence) as both cropped person regions and annotated full frames.

## Requirements

- **Save content**: Both cropped person regions AND annotated full frames (with bounding boxes)
- **Selection strategy**: Top-3 frames per segment by confidence score
- **Save location**: Same directory as video file, in a subfolder named `captures_YYYY-MM-DD_HHMMSS`
- **File naming**: `seg{segment_index}_{sequence}_{timestamp}s_crop_p{person}.jpg` and `..._annotated.jpg`
- **Web display**: Show captured images in the job detail page, grouped by segment
- **Database**: SQLite `captures` table in the existing database

## Architecture

### Data Flow

```
Inference Thread                     Main Thread (after inference)
    │                                       │
    ▼                                       ▼
SegmentCaptureCollector              CaptureSaver
  - Maintains top-3 candidates       - Crops person regions
    per segment by confidence        - Draws bounding box annotations
  - Outputs candidates when          - Saves to disk
    pipeline completes                 │
    │                                  ▼
    ▼                         Saves to: video_dir/captures_TIMESTAMP/
Candidates list ──────────▶   ├── seg0_00_05.2s_crop_p0.jpg
                               ├── seg0_00_05.2s_annotated.jpg
                               ├── seg0_01_06.8s_crop_p0.jpg
                               └── ...
```

### Components

#### 1. SegmentCaptureCollector (`src/pipeline/capture_collector.py`)

Collects candidate frames during inference. Maintains a per-segment buffer sorted by confidence.

```python
@dataclass
class CaptureCandidate:
    frame_index: int
    timestamp: float
    confidence: float
    image: np.ndarray
    boxes: list[tuple[int, int, int, int]]

@dataclass
class SegmentCaptureData:
    segment_index: int
    start_time: float
    end_time: float
    candidates: list[CaptureCandidate]  # max 3, sorted by confidence desc

class SegmentCaptureCollector:
    def __init__(self, max_per_segment: int = 3): ...
    def add_candidate(self, segment_key: int, frame_index: int, 
                      timestamp: float, confidence: float,
                      image: np.ndarray, boxes: list[tuple[int,int,int,int]]): ...
    def get_all_captures(self) -> list[SegmentCaptureData]: ...
```

**Memory**: ~6MB per 1080p frame, 3 frames per segment = ~18MB per segment. 10 segments = ~180MB, well within limits.

#### 2. CaptureSaver (`src/pipeline/capture_saver.py`)

Saves cropped and annotated images to disk.

```python
class CaptureSaver:
    def __init__(self, output_dir: str): ...
    def save_segment_captures(self, data: SegmentCaptureData) -> list[CaptureResult]: ...
    def _save_crops(self, frame, boxes, base_path): ...
    def _save_annotated(self, frame, boxes, path): ...
```

#### 3. Database Model (`src/storage/database.py`)

```python
class CaptureModel(Base):
    __tablename__ = "captures"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    segment_index = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    crop_path = Column(String, nullable=False)
    annotated_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

#### 4. Repository (`src/storage/repository.py`)

```python
class CaptureRepository:
    async def bulk_create(self, job_id: str, captures: list[CaptureCreate])
    async def list_by_job(self, job_id: str) -> list[CaptureModel]
    async def list_by_segment(self, job_id: str, segment_index: int) -> list[CaptureModel]
    async def delete_by_job(self, job_id: str)
```

#### 5. API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jobs/{id}/captures` | GET | List all captures for a job |
| `/api/jobs/{id}/segments/{seg_id}/captures` | GET | List captures for a specific segment |
| `/api/captures/{id}/image?type=crop\|annotated` | GET | Serve image file (FileResponse) |

#### 6. Pipeline Changes

**SegmentAggregator**: Add `_segment_counter` and return `segment_key` from `accumulate()`.

**PipelineCoordinator**: 
- Initialize `SegmentCaptureCollector` alongside `SegmentAggregator`
- Pass `segment_key` from aggregator to collector during inference
- Return `PipelineResult(segments, captures)` instead of just segments

**PipelineResult**:
```python
@dataclass
class PipelineResult:
    segments: list[TimeSegment]
    captures: list[SegmentCaptureData]
```

#### 7. Frontend

**CaptureGallery.vue**: New component displaying captured images grouped by segment.
- Shows crop and annotated views
- Click to view full-size image
- Displays timestamp and confidence per image

**JobDetail.vue**: Add CaptureGallery below SegmentTable.

**API Client**: Add `getCaptures(jobId)` and `Capture` interface.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/pipeline/capture_collector.py` | NEW | SegmentCaptureCollector |
| `src/pipeline/capture_saver.py` | NEW | CaptureSaver for disk I/O |
| `src/pipeline/coordinator.py` | MODIFY | Integrate collector, return PipelineResult |
| `src/pipeline/segment_aggregator.py` | MODIFY | Add segment_key return |
| `src/core/models.py` | MODIFY | Add PipelineResult, CaptureResult |
| `src/storage/database.py` | MODIFY | Add CaptureModel |
| `src/storage/repository.py` | MODIFY | Add CaptureRepository |
| `src/web/routes/jobs.py` | MODIFY | Use CaptureSaver in _run_analysis |
| `src/web/routes/results.py` | MODIFY | Add capture endpoints |
| `src/web/schemas.py` | MODIFY | Add CaptureResponse |
| `src/web/app.py` | MODIFY | Add capture_repo to app.state |
| `frontend/src/api/client.ts` | MODIFY | Add Capture interface and API |
| `frontend/src/components/CaptureGallery.vue` | NEW | Display captured images |
| `frontend/src/components/JobDetail.vue` | MODIFY | Add CaptureGallery |
| `frontend/src/stores/jobs.ts` | MODIFY | Add captures state |
| `tests/test_capture_collector.py` | NEW | Unit tests for collector |
| `tests/test_capture_saver.py` | NEW | Unit tests for saver |
| `tests/test_api.py` | MODIFY | Add capture API tests |
