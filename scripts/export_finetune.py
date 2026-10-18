"""Export a YOLO fine-tuning dataset from human review verdicts.

Reads the review marks recorded in the web UI (segment verdicts good/bad)
and turns them into a YOLO-format dataset:

- good segments  -> frames sampled inside the segment, pseudo-labeled with
  the current model's person boxes (class 0)
- bad segments   -> frames sampled inside the segment with EMPTY label
  files: the false-positive object is visible but unlabeled, which is
  exactly the hard-negative signal YOLO needs (pole/reflection ≠ person)

Known limitation: on good frames every person-class detection >= the
confidence threshold becomes a label, so a co-occurring static false
positive would be mislabeled. Per-box review would fix that; segment
verdicts are the v1 trade-off.

Usage:
  uv run python scripts/export_finetune.py --job-id <id> [--output DIR]
      [--frames-per-good 8] [--frames-per-bad 4] [--include-unreviewed]

Then: uv run yolo detect train model=yolov8m.pt data=<out>/dataset.yaml ...
"""

import argparse
import random
import sqlite3
from pathlib import Path

import cv2
import yaml

from src.detection.yolo_detector import YOLOv8Detector
from src.video.reader import OpenCVFrameReader

DB_PATH = Path("data/results.db")
PERSON_CLASS_ID = 0


def load_segments_and_marks(job_id: str, include_unreviewed: bool):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        segments = list(
            conn.execute("SELECT * FROM segments WHERE job_id = ? ORDER BY start_time", (job_id,))
        )
        marks = {
            row["target_id"]: row["verdict"]
            for row in conn.execute(
                "SELECT * FROM review_marks WHERE job_id = ? AND target_type = 'segment'",
                (job_id,),
            )
        }
    finally:
        conn.close()

    if include_unreviewed:
        # Unreviewed segments inherit the confirmed tier as a weak 'good'.
        return [
            (seg, marks.get(seg["id"], "good" if seg["max_confidence"] >= 0.5 else None))
            for seg in segments
        ]
    return [(seg, marks.get(seg["id"])) for seg in segments]


def sample_indices(start: float, end: float, fps: float, count: int) -> list[int]:
    if end <= start:
        return [int(start * fps)]
    step = (end - start) / count
    return [int((start + step * (i + 0.5)) * fps) for i in range(count)]


def yolo_line(box_xyxy, img_w: int, img_h: int) -> str:
    x1, y1, x2, y2 = box_xyxy
    cx = (x1 + x2) / 2 / img_w
    cy = (y1 + y2) / 2 / img_h
    w = (x2 - x1) / img_w
    h = (y2 - y1) / img_h
    return f"{PERSON_CLASS_ID} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--frames-per-good", type=int, default=8)
    parser.add_argument("--frames-per-bad", type=int, default=4)
    parser.add_argument(
        "--include-unreviewed",
        action="store_true",
        help="Also export unreviewed segments (confirmed tier as weak good).",
    )
    args = parser.parse_args()

    out_dir = Path(args.output or f"data/finetune/{args.job_id}")
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (args.job_id,)).fetchone()
    finally:
        conn.close()
    if job is None:
        raise SystemExit(f"Job {args.job_id} not found in {DB_PATH}")

    pairs = load_segments_and_marks(args.job_id, args.include_unreviewed)
    good = [seg for seg, v in pairs if v == "good"]
    bad = [seg for seg, v in pairs if v == "bad"]
    print(f"segments: {len(good)} good, {len(bad)} bad "
          f"({len(pairs) - len(good) - len(bad)} unreviewed -> skipped)")

    detector = YOLOv8Detector(
        model_name=job["model_name"] or "yolov8m.pt",
        device="cuda:0",
        target_classes=[PERSON_CLASS_ID],
        confidence_threshold=job["confidence_threshold"] or 0.6,
        imgsz=1280,
        use_tracker=False,
        half=True,
    )
    detector.load()

    reader = OpenCVFrameReader(hw_accel=True)
    meta = reader.open(job["file_path"])
    fps = meta.fps
    img_w, img_h = meta.width, meta.height

    written = 0
    index_groups = []
    for seg in good:
        index_groups.append((seg["id"], sample_indices(seg["start_time"], seg["end_time"], fps, args.frames_per_good), True))
    for seg in bad:
        index_groups.append((seg["id"], sample_indices(seg["start_time"], seg["end_time"], fps, args.frames_per_bad), False))

    for seg_id, indices, is_good in sorted(index_groups, key=lambda g: g[1][0] if g[1] else 0):
        for idx in indices:
            ok, frame = reader.read_frame(idx)
            if not ok or frame is None:
                continue
            detection = detector.detect([frame])[0]
            name = f"job{args.job_id}_seg{seg_id}_f{idx}"
            image_path = images_dir / f"{name}.jpg"
            label_path = labels_dir / f"{name}.txt"
            cv2.imwrite(str(image_path), frame)
            lines = []
            if is_good:
                lines = [yolo_line(box, img_w, img_h) for box in detection.boxes]
            label_path.write_text("\n".join(lines), encoding="utf-8")
            written += 1
    reader.close()
    detector.unload()

    # Deterministic-ish train/val split.
    names = sorted(p.stem for p in images_dir.glob("*.jpg"))
    random.seed(42)
    shuffled = names[:]
    random.shuffle(shuffled)
    val_n = max(1, len(shuffled) // 10)
    (out_dir / "val.txt").write_text(
        "\n".join(f"./images/{n}.jpg" for n in shuffled[:val_n]), encoding="utf-8"
    )
    (out_dir / "train.txt").write_text(
        "\n".join(f"./images/{n}.jpg" for n in shuffled[val_n:]), encoding="utf-8"
    )
    dataset_yaml = {
        "path": str(out_dir.resolve()),
        "train": "train.txt",
        "val": "val.txt",
        "names": {0: "person"},
    }
    (out_dir / "dataset.yaml").write_text(yaml.safe_dump(dataset_yaml), encoding="utf-8")

    print(f"exported {written} images to {out_dir}")
    print(f"train: {len(shuffled) - val_n}, val: {val_n}")
    print(f"fine-tune with: uv run yolo detect train model=yolov8m.pt data={out_dir / 'dataset.yaml'} epochs=60 imgsz=1280")


if __name__ == "__main__":
    main()
