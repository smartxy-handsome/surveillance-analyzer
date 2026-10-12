from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from src.utils.time_format import seconds_to_hms
from src.web.schemas import CaptureResponse, SegmentResponse, VehicleEventResponse


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
    async def get_captures(
        request: Request,
        job_id: str,
        target: str | None = Query(default=None),
    ):
        job_repo = request.app.state.job_repo
        capture_repo = request.app.state.capture_repo

        job = await job_repo.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")

        captures = await capture_repo.list_by_job(job_id, target=target)
        return [
            CaptureResponse(
                id=c.id,
                segment_index=c.segment_index,
                timestamp=c.timestamp,
                timestamp_formatted=seconds_to_hms(c.timestamp),
                confidence=c.confidence,
                crop_url=f"/api/captures/{c.id}/image?type=crop",
                annotated_url=f"/api/captures/{c.id}/image?type=annotated" if c.annotated_path else None,
                kind=c.kind or "appearance",
                target=c.target or "person",
            )
            for c in captures
        ]

    @router.get("/jobs/{job_id}/vehicle-events", response_model=list[VehicleEventResponse])
    async def get_vehicle_events(request: Request, job_id: str):
        """Per-vehicle enter/exit records with plate readout and the three
        capture images (appearance / departure / plate close-up)."""
        job_repo = request.app.state.job_repo
        event_repo = request.app.state.vehicle_event_repo
        capture_repo = request.app.state.capture_repo

        job = await job_repo.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")

        events = await event_repo.list_by_job(job_id)
        captures = await capture_repo.list_by_job(job_id, target="vehicle")
        # captures.segment_index is the 1-based event ordinal (enter-time order);
        # target='vehicle' keeps person-segment captures from colliding on
        # 'both' jobs where both count from 1.
        by_slot = {
            (c.segment_index, c.kind or "appearance"): c
            for c in captures
        }

        out = []
        for ordinal, e in enumerate(events, start=1):
            def cap(kind: str) -> CaptureResponse | None:
                c = by_slot.get((ordinal, kind))
                if not c:
                    return None
                return CaptureResponse(
                    id=c.id,
                    segment_index=c.segment_index,
                    timestamp=c.timestamp,
                    timestamp_formatted=seconds_to_hms(c.timestamp),
                    confidence=c.confidence,
                    crop_url=f"/api/captures/{c.id}/image?type=crop",
                    annotated_url=f"/api/captures/{c.id}/image?type=annotated" if c.annotated_path else None,
                    kind=c.kind or kind,
                )

            out.append(
                VehicleEventResponse(
                    id=e.id,
                    enter_time=e.enter_time,
                    exit_time=e.exit_time,
                    enter_time_formatted=seconds_to_hms(e.enter_time),
                    exit_time_formatted=seconds_to_hms(e.exit_time),
                    duration_seconds=e.duration,
                    detection_count=e.detection_count,
                    avg_confidence=e.avg_confidence,
                    max_confidence=e.max_confidence,
                    plate_number=e.plate_number,
                    plate_confidence=e.plate_confidence,
                    plate_type=e.plate_type,
                    enter_capture=cap("appearance"),
                    exit_capture=cap("departure"),
                    plate_capture=cap("plate"),
                )
            )
        return out

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
