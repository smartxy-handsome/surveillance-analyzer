from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.core.timeutil import utcnow


class Base(DeclarativeBase):
    pass


class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)

    duration_seconds = Column(Float, nullable=True)
    video_fps = Column(Float, nullable=True)
    video_width = Column(Integer, nullable=True)
    video_height = Column(Integer, nullable=True)
    total_frames = Column(Integer, nullable=True)

    sampling_fps = Column(Float, nullable=False)
    model_name = Column(String, nullable=False)
    confidence_threshold = Column(Float, nullable=False)
    merge_gap_seconds = Column(Float, nullable=False)
    min_segment_seconds = Column(Float, nullable=False)

    total_segments = Column(Integer, default=0)
    total_person_time = Column(Float, default=0.0)
    processing_time_seconds = Column(Float, nullable=True)
    dropped_frames = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class SegmentModel(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)
    detection_count = Column(Integer, nullable=False)
    avg_confidence = Column(Float, nullable=False)
    max_confidence = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class CaptureModel(Base):
    __tablename__ = "captures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    segment_index = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    crop_path = Column(String, nullable=False)
    annotated_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)


async def init_db(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        # Only create tables if they don't exist (don't drop existing data)
        await conn.run_sync(Base.metadata.create_all)
        # create_all does not add columns to existing tables; add ones introduced
        # after the first release so old databases keep working in place.
        for table, column in [("jobs", Column("dropped_frames", Integer, nullable=True))]:
            await conn.run_sync(
                lambda sync_conn, t=table, c=column: _add_column_if_missing(sync_conn, t, c)
            )
    return async_sessionmaker(engine, expire_on_commit=False)


def _add_column_if_missing(sync_conn, table: str, column: Column) -> None:
    from sqlalchemy import inspect, text

    insp = inspect(sync_conn)
    if column.name not in insp.get_columns(table):
        col_type = column.type.compile(sync_conn.engine.dialect)
        sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column.name} {col_type}"))
