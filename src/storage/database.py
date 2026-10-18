from sqlalchemy import Column, DateTime, Float, Integer, String, Text, UniqueConstraint
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
    detection_target = Column(String, nullable=False, default="person")

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
    kind = Column(String, nullable=False, default="appearance")
    # Namespace split for 'both' jobs: person segments and vehicle events both
    # count from 1, so captures must be attributable to their consumer.
    target = Column(String, nullable=False, default="person")
    created_at = Column(DateTime, default=utcnow)


class VehicleEventModel(Base):
    __tablename__ = "vehicle_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    enter_time = Column(Float, nullable=False)
    exit_time = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)
    detection_count = Column(Integer, nullable=False)
    avg_confidence = Column(Float, nullable=False)
    max_confidence = Column(Float, nullable=False)
    plate_number = Column(String, nullable=True)
    plate_confidence = Column(Float, nullable=True)
    plate_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class ReviewMarkModel(Base):
    """Human verdict on one analysis output (capture, segment or vehicle event).

    verdict is 'good' (real person / real event) or 'bad' (false positive).
    Re-reviewing the same target replaces the verdict (unique constraint).
    """

    __tablename__ = "review_marks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=False)  # capture | segment | vehicle_event
    target_id = Column(Integer, nullable=False)
    verdict = Column(String, nullable=False)  # good | bad
    created_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_review_target"),
    )


class MissedEventModel(Base):
    """A real person appearance the user spotted while watching the video
    that the system failed to record -- the ground truth for recall."""

    __tablename__ = "missed_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    start_seconds = Column(Float, nullable=False)
    end_seconds = Column(Float, nullable=False)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)


async def init_db(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        # Only create tables if they don't exist (don't drop existing data)
        await conn.run_sync(Base.metadata.create_all)
        # create_all does not add columns to existing tables; add ones introduced
        # after the first release so old databases keep working in place.
        for table, column in [
            ("jobs", Column("dropped_frames", Integer, nullable=True)),
            ("jobs", Column("detection_target", String, nullable=False, default="person")),
            ("captures", Column("kind", String, nullable=False, default="appearance")),
            ("captures", Column("target", String, nullable=False, default="person")),
        ]:
            await conn.run_sync(
                lambda sync_conn, t=table, c=column: _add_column_if_missing(sync_conn, t, c)
            )
    return async_sessionmaker(engine, expire_on_commit=False)


def _add_column_if_missing(sync_conn, table: str, column: Column) -> None:
    from sqlalchemy import text

    # PRAGMA instead of Inspector: within the engine.begin() transaction the
    # inspector's reflection can serve stale schema info right after an ALTER,
    # turning a restart into a spurious "duplicate column name" crash.
    rows = sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    existing = {row[1] for row in rows}
    if column.name in existing:
        return
    col_type = column.type.compile(sync_conn.engine.dialect)
    ddl = f"ALTER TABLE {table} ADD COLUMN {column.name} {col_type}"
    # SQLite refuses NOT NULL additions without a default on non-empty tables.
    if column.nullable is False:
        ddl += " NOT NULL"
    if column.default is not None and hasattr(column.default, "arg"):
        arg = column.default.arg
        ddl += f" DEFAULT '{arg}'" if isinstance(arg, str) else f" DEFAULT {arg}"
    sync_conn.execute(text(ddl))
