import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from src.core.timeutil import utcnow
from src.web.schemas import JobCreateRequest, JobResponse, VideoMetadataResponse


def create_jobs_router() -> APIRouter:
    router = APIRouter(tags=["jobs"])

    @router.post("/jobs", response_model=JobResponse, status_code=201)
    async def create_job(
        request: Request, body: JobCreateRequest, background_tasks: BackgroundTasks
    ):
        config = request.app.state.config
        job_repo = request.app.state.job_repo

        file_path = Path(body.file_path)
        if not file_path.exists():
            raise HTTPException(400, f"File not found: {body.file_path}")

        ext = file_path.suffix.lower()
        if ext not in config.video.supported_formats:
            raise HTTPException(400, f"Unsupported format: {ext}")

        job_id = str(uuid.uuid4())

        from src.storage.repository import JobCreate

        job = await job_repo.create(
            JobCreate(
                id=job_id,
                filename=file_path.name,
                file_path=str(file_path.resolve()),
                sampling_fps=config.sampling.fps,
                model_name=config.detection.model_name,
                confidence_threshold=config.detection.confidence_threshold,
                merge_gap_seconds=config.aggregation.merge_gap_seconds,
                min_segment_seconds=config.aggregation.min_segment_seconds,
            )
        )

        background_tasks.add_task(_run_analysis, job_id, request.app)

        return JobResponse(
            id=job.id,
            filename=job.filename,
            status=job.status,
            created_at=job.created_at or utcnow(),
        )

    @router.get("/jobs", response_model=list[JobResponse])
    async def list_jobs(request: Request, status: str | None = None, limit: int = 50, offset: int = 0):
        job_repo = request.app.state.job_repo
        jobs = await job_repo.list(status=status, limit=limit, offset=offset)
        return [
            JobResponse(
                id=j.id,
                filename=j.filename,
                status=j.status,
                created_at=j.created_at or utcnow(),
                total_segments=j.total_segments or 0,
                total_person_time=j.total_person_time or 0.0,
                processing_time_seconds=j.processing_time_seconds,
                video_metadata=VideoMetadataResponse(
                    duration=j.duration_seconds,
                    fps=j.video_fps,
                    width=j.video_width,
                    height=j.video_height,
                    total_frames=j.total_frames,
                )
                if j.duration_seconds
                else None,
            )
            for j in jobs
        ]

    @router.get("/jobs/{job_id}", response_model=JobResponse)
    async def get_job(request: Request, job_id: str):
        job_repo = request.app.state.job_repo
        job = await job_repo.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return JobResponse(
            id=job.id,
            filename=job.filename,
            status=job.status,
            created_at=job.created_at or utcnow(),
            total_segments=job.total_segments or 0,
            total_person_time=job.total_person_time or 0.0,
            processing_time_seconds=job.processing_time_seconds,
            video_metadata=VideoMetadataResponse(
                duration=job.duration_seconds,
                fps=job.video_fps,
                width=job.video_width,
                height=job.video_height,
                total_frames=job.total_frames,
            )
            if job.duration_seconds
            else None,
        )

    @router.delete("/jobs/{job_id}", status_code=204)
    async def delete_job(request: Request, job_id: str):
        job_repo = request.app.state.job_repo
        segment_repo = request.app.state.segment_repo
        capture_repo = request.app.state.capture_repo
        job = await job_repo.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        await capture_repo.delete_by_job(job_id)
        await segment_repo.delete_by_job(job_id)
        await job_repo.delete(job_id)

    @router.get("/system/paths")
    async def get_system_paths():
        """Return default system paths (Desktop, Downloads, etc.)"""
        import os

        home = Path.home()
        paths = []

        # Common user directories
        common_dirs = [
            ("Desktop", "🖥️"),
            ("Downloads", "📥"),
            ("Documents", "📄"),
            ("Videos", "🎬"),
            ("Pictures", "🖼️"),
            ("Music", "🎵"),
        ]

        for name, icon in common_dirs:
            dir_path = home / name
            if dir_path.exists():
                paths.append({
                    "name": name,
                    "path": str(dir_path),
                    "icon": icon,
                })

        return {"paths": paths, "home": str(home)}

    @router.get("/browse")
    async def browse_directory(request: Request, path: str = Query(default="")):
        config = request.app.state.config
        supported = set(config.video.supported_formats)

        if not path:
            # List drives on Windows
            import string

            drives = []
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if Path(drive).exists():
                    drives.append({"name": drive, "path": drive, "is_dir": True})
            return {"current": "", "parent": None, "items": drives}

        dir_path = Path(path)
        if not dir_path.exists():
            raise HTTPException(400, "Path not found")
        if not dir_path.is_dir():
            raise HTTPException(400, "Not a directory")

        items = []
        try:
            for entry in sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    items.append({"name": entry.name, "path": str(entry), "is_dir": True})
                elif entry.suffix.lower() in supported:
                    size_mb = entry.stat().st_size / (1024 * 1024)
                    items.append({
                        "name": entry.name,
                        "path": str(entry),
                        "is_dir": False,
                        "size_mb": round(size_mb, 1),
                    })
        except PermissionError:
            raise HTTPException(403, "Permission denied")

        # Check if we're at a drive root (e.g., C:\)
        # On Windows, drive root's parent is itself
        if dir_path.parent == dir_path:
            parent = ""  # Empty string means "go back to drive list"
        else:
            parent = str(dir_path.parent)
        return {"current": str(dir_path), "parent": parent, "items": items}

    return router


async def _run_analysis(job_id: str, app):
    async with app.state.analysis_semaphore:
        import time as time_mod

        from src.core.config import load_config
        from src.detection.yolo_detector import YOLOv8Detector
        from src.pipeline.capture_saver import CaptureSaver, get_capture_output_dir
        from src.pipeline.coordinator import PipelineCoordinator
        from src.storage.repository import CaptureCreate, SegmentCreate
        from src.video.reader import OpenCVFrameReader
        from src.video.sampler import compute_frame_indices

        config = app.state.config
        job_repo = app.state.job_repo
        segment_repo = app.state.segment_repo
        capture_repo = app.state.capture_repo

        try:
            await job_repo.update_status(job_id, "processing")
            job = await job_repo.get(job_id)

            # Read metadata with a temporary reader
            meta_reader = OpenCVFrameReader()
            meta = meta_reader.open(job.file_path)
            meta_reader.close()

            await job_repo.update_video_metadata(
                job_id, meta.duration_seconds, meta.fps, meta.width, meta.height, meta.total_frames
            )

            frame_indices = compute_frame_indices(meta.fps, config.sampling.fps, meta.total_frames)

            detector = YOLOv8Detector(
                model_name=config.detection.model_name,
                device=config.detection.device,
                target_classes=config.detection.target_classes,
                confidence_threshold=config.detection.confidence_threshold,
                batch_size=config.detection.batch_size,
            )

            coordinator = PipelineCoordinator(
                reader_factory=OpenCVFrameReader,
                video_path=job.file_path,
                detector=detector,
                sampling_config=config.sampling,
                detection_config=config.detection,
                aggregation_config=config.aggregation,
                pipeline_config=config.pipeline,
            )

            t0 = time_mod.monotonic()
            result = coordinator.run(frame_indices, meta.fps)
            elapsed = time_mod.monotonic() - t0

            segments = result.segments
            captures = result.captures

            if segments:
                await segment_repo.bulk_create(
                    job_id,
                    [
                        SegmentCreate(
                            start_time=s.start_time,
                            end_time=s.end_time,
                            detection_count=s.detection_count,
                            avg_confidence=s.avg_confidence,
                            max_confidence=s.max_confidence,
                        )
                        for s in segments
                    ],
                )

            # Save capture images
            if captures:
                output_dir = get_capture_output_dir(job.file_path)
                saver = CaptureSaver(output_dir)
                all_capture_results = []
                for capture_data in captures:
                    results = saver.save_segment_captures(capture_data)
                    all_capture_results.extend(results)

                # Store capture paths in database
                if all_capture_results:
                    await capture_repo.bulk_create(
                        job_id,
                        [
                            CaptureCreate(
                                segment_index=r.segment_index,
                                timestamp=r.timestamp,
                                confidence=r.confidence,
                                crop_path=r.crop_path,
                                annotated_path=r.annotated_path,
                            )
                            for r in all_capture_results
                        ],
                    )

            total_person_time = sum(s.duration for s in segments)
            await job_repo.update_summary(job_id, len(segments), total_person_time, elapsed)
            await job_repo.update_status(job_id, "completed")
        except Exception as e:
            await job_repo.update_status(job_id, "failed", str(e))
