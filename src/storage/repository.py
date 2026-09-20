from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.timeutil import utcnow
from src.storage.database import CaptureModel, JobModel, SegmentModel


@dataclass
class JobCreate:
    id: str
    filename: str
    file_path: str
    sampling_fps: float
    model_name: str
    confidence_threshold: float
    merge_gap_seconds: float
    min_segment_seconds: float


@dataclass
class SegmentCreate:
    start_time: float
    end_time: float
    detection_count: int
    avg_confidence: float
    max_confidence: float


class JobRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def create(self, job: JobCreate) -> JobModel:
        async with self._session_factory() as session:
            model = JobModel(
                id=job.id,
                filename=job.filename,
                file_path=job.file_path,
                sampling_fps=job.sampling_fps,
                model_name=job.model_name,
                confidence_threshold=job.confidence_threshold,
                merge_gap_seconds=job.merge_gap_seconds,
                min_segment_seconds=job.min_segment_seconds,
            )
            session.add(model)
            await session.commit()
            return model

    async def get(self, job_id: str) -> JobModel | None:
        async with self._session_factory() as session:
            result = await session.execute(select(JobModel).where(JobModel.id == job_id))
            return result.scalar_one_or_none()

    async def list(self, status: str | None = None, limit: int = 50, offset: int = 0):
        async with self._session_factory() as session:
            stmt = select(JobModel).order_by(JobModel.created_at.desc())
            if status:
                stmt = stmt.where(JobModel.status == status)
            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_status(self, job_id: str, status: str, error: str | None = None):
        async with self._session_factory() as session:
            job = await session.get(JobModel, job_id)
            if job:
                job.status = status
                job.error_message = error
                if status == "processing":
                    job.started_at = utcnow()
                elif status in ("completed", "failed"):
                    job.completed_at = utcnow()
                await session.commit()

    async def update_video_metadata(
        self, job_id: str, duration: float, fps: float, width: int, height: int, total_frames: int
    ):
        async with self._session_factory() as session:
            job = await session.get(JobModel, job_id)
            if job:
                job.duration_seconds = duration
                job.video_fps = fps
                job.video_width = width
                job.video_height = height
                job.total_frames = total_frames
                await session.commit()

    async def update_summary(
        self,
        job_id: str,
        total_segments: int,
        total_person_time: float,
        processing_time_seconds: float | None = None,
    ):
        async with self._session_factory() as session:
            job = await session.get(JobModel, job_id)
            if job:
                job.total_segments = total_segments
                job.total_person_time = total_person_time
                job.processing_time_seconds = processing_time_seconds
                await session.commit()

    async def delete(self, job_id: str):
        async with self._session_factory() as session:
            job = await session.get(JobModel, job_id)
            if job:
                await session.delete(job)
                await session.commit()


class SegmentRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def bulk_create(self, job_id: str, segments: list[SegmentCreate]):
        async with self._session_factory() as session:
            for seg in segments:
                model = SegmentModel(
                    job_id=job_id,
                    start_time=seg.start_time,
                    end_time=seg.end_time,
                    duration=seg.end_time - seg.start_time,
                    detection_count=seg.detection_count,
                    avg_confidence=seg.avg_confidence,
                    max_confidence=seg.max_confidence,
                )
                session.add(model)
            await session.commit()

    async def list_by_job(self, job_id: str) -> list[SegmentModel]:
        async with self._session_factory() as session:
            stmt = (
                select(SegmentModel)
                .where(SegmentModel.job_id == job_id)
                .order_by(SegmentModel.start_time)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def delete_by_job(self, job_id: str):
        async with self._session_factory() as session:
            stmt = select(SegmentModel).where(SegmentModel.job_id == job_id)
            result = await session.execute(stmt)
            for seg in result.scalars().all():
                await session.delete(seg)
            await session.commit()


@dataclass
class CaptureCreate:
    segment_index: int
    timestamp: float
    confidence: float
    crop_path: str
    annotated_path: str


class CaptureRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def bulk_create(self, job_id: str, captures: list[CaptureCreate]):
        async with self._session_factory() as session:
            for cap in captures:
                model = CaptureModel(
                    job_id=job_id,
                    segment_index=cap.segment_index,
                    timestamp=cap.timestamp,
                    confidence=cap.confidence,
                    crop_path=cap.crop_path,
                    annotated_path=cap.annotated_path,
                )
                session.add(model)
            await session.commit()

    async def list_by_job(self, job_id: str) -> list[CaptureModel]:
        async with self._session_factory() as session:
            stmt = (
                select(CaptureModel)
                .where(CaptureModel.job_id == job_id)
                .order_by(CaptureModel.segment_index, CaptureModel.timestamp)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_by_segment(self, job_id: str, segment_index: int) -> list[CaptureModel]:
        async with self._session_factory() as session:
            stmt = (
                select(CaptureModel)
                .where(
                    CaptureModel.job_id == job_id,
                    CaptureModel.segment_index == segment_index,
                )
                .order_by(CaptureModel.timestamp)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get(self, capture_id: int) -> CaptureModel | None:
        async with self._session_factory() as session:
            return await session.get(CaptureModel, capture_id)

    async def delete_by_job(self, job_id: str):
        async with self._session_factory() as session:
            stmt = select(CaptureModel).where(CaptureModel.job_id == job_id)
            result = await session.execute(stmt)
            for cap in result.scalars().all():
                await session.delete(cap)
            await session.commit()
