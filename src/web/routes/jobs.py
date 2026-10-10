import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from src.core.timeutil import utcnow
from src.web.schemas import JobCreateRequest, JobProgress, JobResponse, VideoMetadataResponse


def _get_progress(app, job_id: str) -> JobProgress | None:
    entry = getattr(app.state, "job_progress", {}).get(job_id)
    return JobProgress(**entry) if entry else None


def _remove_capture_dir(job_id: str) -> None:
    import shutil

    from src.core.config import DATA_DIR

    shutil.rmtree(DATA_DIR / "captures" / job_id, ignore_errors=True)


async def _queue_positions(job_repo, job_ids: list[str]) -> dict[str, int]:
    """1-based FIFO position of each pending job in the analysis queue.

    The semaphore releases waiters in acquisition order, and background tasks
    acquire in job-creation order, so position = rank by created_at among
    pending jobs (earliest first). Jobs not pending (or not found) get no entry.
    """
    pending = await job_repo.list(status="pending", limit=10000)
    ordered = sorted(pending, key=lambda j: j.created_at or datetime.min)
    positions = {j.id: i for i, j in enumerate(ordered, start=1)}
    return {job_id: positions[job_id] for job_id in job_ids if job_id in positions}


def create_jobs_router() -> APIRouter:
    router = APIRouter(tags=["jobs"])

    @router.post("/jobs", response_model=JobResponse, status_code=201)
    async def create_job(
        request: Request, body: JobCreateRequest, background_tasks: BackgroundTasks
    ):
        config = request.app.state.config
        job_repo = request.app.state.job_repo

        file_path = Path(body.file_path)
        try:
            st = file_path.stat()
        except OSError:
            raise HTTPException(400, f"File not found: {body.file_path}")
        # A directory renamed to ".mp4" would otherwise pass validation here
        # and only blow up deep inside the analysis job.
        if not file_path.is_file():
            raise HTTPException(400, f"Not a file: {body.file_path}")

        ext = file_path.suffix.lower()
        if ext not in config.video.supported_formats:
            raise HTTPException(400, f"Unsupported format: {ext}")

        size_mb = st.st_size / (1024 * 1024)
        if size_mb > config.video.max_file_size_mb:
            raise HTTPException(
                400,
                f"File exceeds max size ({size_mb:.0f} MB > {config.video.max_file_size_mb} MB)",
            )

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

        # Optional injection point: tests set app.state.detector_factory to
        # substitute a fake DetectionEngine for end-to-end runs.
        detector_factory = getattr(request.app.state, "detector_factory", None)
        background_tasks.add_task(_run_analysis, job_id, request.app, detector_factory)

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
        positions = await _queue_positions(job_repo, [j.id for j in jobs])
        return [
            JobResponse(
                id=j.id,
                filename=j.filename,
                status=j.status,
                created_at=j.created_at or utcnow(),
                total_segments=j.total_segments or 0,
                total_person_time=j.total_person_time or 0.0,
                processing_time_seconds=j.processing_time_seconds,
                dropped_frames=j.dropped_frames,
                queue_position=positions.get(j.id),
                progress=_get_progress(request.app, j.id),
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
        position = (await _queue_positions(job_repo, [job.id])).get(job.id)
        return JobResponse(
            id=job.id,
            filename=job.filename,
            status=job.status,
            created_at=job.created_at or utcnow(),
            total_segments=job.total_segments or 0,
            total_person_time=job.total_person_time or 0.0,
            processing_time_seconds=job.processing_time_seconds,
            dropped_frames=job.dropped_frames,
            queue_position=position,
            progress=_get_progress(request.app, job.id),
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
        # A running analysis holds the semaphore and keeps writing rows and
        # files; deleting mid-run would strand the pipeline and orphan files.
        if job.status == "processing":
            raise HTTPException(409, "Job is currently processing; wait for it to finish")
        await capture_repo.delete_by_job(job_id)
        await segment_repo.delete_by_job(job_id)
        await job_repo.delete(job_id)
        _remove_capture_dir(job_id)

    @router.get("/system/paths")
    async def get_system_paths():
        """Return default system paths (Desktop, Downloads, etc.)"""

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


async def _run_analysis(job_id: str, app, detector_factory=None):
    """Run the full analysis pipeline for a job.

    ``detector_factory`` is injectable so tests can substitute a fake
    DetectionEngine without loading the real YOLO model (or needing a GPU).
    """
    async with app.state.analysis_semaphore:
        import time as time_mod

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
            # The job may have been deleted while queued behind the semaphore;
            # bail out instead of burning a slot on an AttributeError below.
            if await job_repo.get(job_id) is None:
                return

            await job_repo.update_status(job_id, "processing")
            job = await job_repo.get(job_id)

            # Read metadata with a temporary reader
            meta_reader = OpenCVFrameReader(hw_accel=config.video.hw_accel)
            meta = meta_reader.open(job.file_path)
            meta_reader.close()

            await job_repo.update_video_metadata(
                job_id, meta.duration_seconds, meta.fps, meta.width, meta.height, meta.total_frames
            )

            frame_indices = compute_frame_indices(meta.fps, config.sampling.fps, meta.total_frames)

            if detector_factory is None:
                from src.detection.yolo_detector import YOLOv8Detector

                detector_factory = lambda: YOLOv8Detector(  # noqa: E731
                    model_name=config.detection.model_name,
                    device=config.detection.device,
                    target_classes=config.detection.target_classes,
                    confidence_threshold=config.detection.confidence_threshold,
                    batch_size=config.detection.batch_size,
                    imgsz=config.detection.imgsz,
                    use_tracker=config.aggregation.use_tracking,
                )

            detector = detector_factory()

            coordinator = PipelineCoordinator(
                reader_factory=lambda: OpenCVFrameReader(hw_accel=config.video.hw_accel),
                video_path=job.file_path,
                detector=detector,
                sampling_config=config.sampling,
                detection_config=config.detection,
                aggregation_config=config.aggregation,
                pipeline_config=config.pipeline,
            )

            t0 = time_mod.monotonic()

            def progress_callback(processed: int, total: int) -> None:
                # Runs on the worker thread; a plain dict write is GIL-safe.
                app.state.job_progress[job_id] = {
                    "processed": processed,
                    "total": total,
                    "percent": round(processed / total * 100, 1) if total else 0.0,
                }

            # coordinator.run is synchronous (thread joins inside); run it on a
            # worker thread so the event loop keeps serving requests and the
            # progress polling can actually get responses.
            result = await asyncio.to_thread(
                coordinator.run, frame_indices, meta.fps, progress_callback
            )
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
                output_dir = get_capture_output_dir(job.file_path, job_id)
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
            await job_repo.update_summary(
                job_id, len(segments), total_person_time, elapsed, result.dropped_frames
            )
            await job_repo.update_status(job_id, "completed")
        except Exception as e:
            await job_repo.update_status(job_id, "failed", str(e))
        finally:
            app.state.job_progress.pop(job_id, None)
