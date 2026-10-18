"""Precision / recall report from human review verdicts.

Uses the marks recorded in the web UI:
- segment/vehicle_event verdicts: good = real record, bad = false positive
- missed events: real appearances the system never recorded

Recall counts a user-recorded missed event as genuinely missed only when it
does not overlap ANY system segment (a "missed" event drawn over an
existing record is treated as confirmation, not recall loss).

Usage:
  uv run python scripts/evaluate.py [job_id]
Without job_id, reports on the most recent completed job.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/results.db")


def pick_job(conn: sqlite3.Connection, job_id: str | None):
    if job_id:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise SystemExit(f"Job {job_id} not found")
        return row
    row = conn.execute(
        "SELECT * FROM jobs WHERE status = 'completed' ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise SystemExit("No completed jobs in the database")
    return row


def verdicts_by_type(conn: sqlite3.Connection, job_id: str) -> dict[str, dict[int, str]]:
    out: dict[str, dict[int, str]] = {}
    # A database created before the review feature has no table yet; the
    # server builds it on next startup. Treat as "nothing reviewed".
    try:
        rows = conn.execute(
            "SELECT target_type, target_id, verdict FROM review_marks WHERE job_id = ?",
            (job_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return out
    for row in rows:
        out.setdefault(row["target_type"], {})[row["target_id"]] = row["verdict"]
    return out


def report_pr(title: str, records: list[sqlite3.Row], marks: dict[int, str]) -> None:
    total = len(records)
    reviewed = [r for r in records if r["id"] in marks]
    good = sum(1 for r in reviewed if marks[r["id"]] == "good")
    bad = len(reviewed) - good
    precision = good / len(reviewed) if reviewed else None

    print(f"\n== {title} ==")
    print(f"  records: {total} (reviewed {len(reviewed)}, unreviewed {total - len(reviewed)})")
    if reviewed:
        print(f"  real (good): {good}, false positive (bad): {bad}")
        print(f"  precision on reviewed: {precision:.1%}")
    else:
        print("  no review verdicts yet")


def overlaps(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


def main() -> None:
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        job = pick_job(conn, job_id)
        marks = verdicts_by_type(conn, job["id"])

        segments = list(
            conn.execute("SELECT * FROM segments WHERE job_id = ? ORDER BY start_time", (job["id"],))
        )
        events = list(
            conn.execute(
                "SELECT * FROM vehicle_events WHERE job_id = ? ORDER BY enter_time", (job["id"],)
            )
        )
        try:
            missed = list(
                conn.execute(
                    "SELECT * FROM missed_events WHERE job_id = ? ORDER BY start_seconds",
                    (job["id"],),
                )
            )
        except sqlite3.OperationalError:
            missed = []

        print(f"job {job['id']} ({job['filename']}, target={job['detection_target']})")

        report_pr("person segments", segments, marks.get("segment", {}))
        report_pr("vehicle events", events, marks.get("vehicle_event", {}))

        print("\n== recall (person) ==")
        if not missed:
            print("  no missed events recorded yet -- recall unknown")
        else:
            genuinely_missed = [
                m for m in missed
                if not any(
                    overlaps(m["start_seconds"], m["end_seconds"], s["start_time"], s["end_time"])
                    for s in segments
                )
            ]
            confirmed_real = sum(
                1 for r in segments if marks.get("segment", {}).get(r["id"]) == "good"
            )
            denom = confirmed_real + len(genuinely_missed)
            print(f"  user-recorded missed events: {len(missed)}")
            print(f"  genuinely missed (overlap no record): {len(genuinely_missed)}")
            if denom > 0:
                recall = confirmed_real / denom
                print(f"  recall (confirmed real / (confirmed real + genuinely missed)): "
                      f"{recall:.1%}  [{confirmed_real}/{denom}]")
            else:
                print("  no confirmed real records yet -- recall unknown")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
