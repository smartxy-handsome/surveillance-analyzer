"""Upgrade path for databases created before dropped_frames existed."""

import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.storage.database import Base, JobModel, init_db


@pytest.mark.asyncio
async def test_init_db_adds_missing_column_to_old_database(tmp_path):
    """A pre-dropped_frames database gains the column in place, data intact.

    The "old" schema is produced by building today's tables then dropping the
    new column -- exactly what a database written by the previous release
    looks like when this release's init_db runs against it.
    """
    db_path = tmp_path / "old.db"

    # Build the current schema, then remove the post-release columns to
    # simulate a database written by the previous release.
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE jobs DROP COLUMN dropped_frames"))
        await conn.execute(text("ALTER TABLE jobs DROP COLUMN detection_target"))
    await engine.dispose()

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (id, filename, file_path, status, sampling_fps, model_name,"
        " confidence_threshold, merge_gap_seconds, min_segment_seconds)"
        " VALUES ('old-1', 'a.mp4', 'D:\\a.mp4', 'completed', 3.0, 'yolov8n.pt',"
        " 0.5, 2.0, 1.0)"
    )
    conn.commit()
    conn.close()

    # The upgrade: init_db on the old database
    session_factory = await init_db(f"sqlite+aiosqlite:///{db_path}")

    # Old row survived, new columns readable (detection_target defaulted)
    async with session_factory() as session:
        job = await session.get(JobModel, "old-1")
        assert job is not None
        assert job.status == "completed"
        assert job.dropped_frames is None
    assert job.detection_target == "person"

    # Re-running init_db (server restart) is a no-op, not an error
    session_factory = await init_db(f"sqlite+aiosqlite:///{db_path}")
    async with session_factory() as session:
        await session.execute(text("SELECT dropped_frames FROM jobs WHERE id='old-1'"))


@pytest.mark.asyncio
async def test_init_db_fresh_database_has_column(tmp_path):
    """create_all alone yields the new column on a fresh database."""
    session_factory = await init_db(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    async with session_factory() as session:
        await session.execute(text("SELECT dropped_frames FROM jobs LIMIT 1"))
