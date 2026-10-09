from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from src.utils.time_format import seconds_to_hms
from src.web.schemas import CaptureResponse, SegmentResponse


def create_results_router() -> APIRouter:
    router = APIRouter(tags=["results"])

    @router.get("/jobs/{job_id}/segments", response_model=list[SegmentResponse])
    async def get_segments(request: Request, job_id: str):
        job_repo = request.app.state.job_repo
        segment_repo = request.app.state.segment_repo

        job = await job_repo.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")

        segments = await segment_repo.list_by_job(job_id)
        return [
            SegmentResponse(
                id=s.id,
                start_time=s.start_time,
                end_time=s.end_time,
                start_time_formatted=seconds_to_hms(s.start_time),
                end_time_formatted=seconds_to_hms(s.end_time),
                duration_seconds=s.duration,
                detection_count=s.detection_count,
                avg_confidence=s.avg_confidence,
                max_confidence=s.max_confidence,
            )
            for s in segments
        ]

    @router.get("/jobs/{job_id}/captures", response_model=list[CaptureResponse])
    async def get_captures(request: Request, job_id: str):
        job_repo = request.app.state.job_repo
        capture_repo = request.app.state.capture_repo

        job = await job_repo.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")

        captures = await capture_repo.list_by_job(job_id)
        return [
            CaptureResponse(
                id=c.id,
                segment_index=c.segment_index,
                timestamp=c.timestamp,
                timestamp_formatted=seconds_to_hms(c.timestamp),
                confidence=c.confidence,
                crop_url=f"/api/captures/{c.id}/image?type=crop",
                annotated_url=f"/api/captures/{c.id}/image?type=annotated",
            )
            for c in captures
        ]

    @router.get("/captures/{capture_id}/image")
    async def get_capture_image(request: Request, capture_id: int, type: str = Query(default="crop")):
        capture_repo = request.app.state.capture_repo

        capture = await capture_repo.get(capture_id)
        if not capture:
            raise HTTPException(404, "Capture not found")

        if type == "crop":
            file_path = capture.crop_path
        elif type == "annotated":
            file_path = capture.annotated_path
        else:
            raise HTTPException(400, "Invalid type. Must be 'crop' or 'annotated'")

        if not file_path:
            raise HTTPException(404, "Image file not found")

        return FileResponse(file_path, media_type="image/jpeg")

    return router
