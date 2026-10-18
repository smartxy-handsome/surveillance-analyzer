"""A/B probe: BoT-SORT ReID on/off against a slice of real footage.

Compares person record counts, overlapping (ID-switch duplicate) pairs and
wall time for the same sampled window. Used to validate the tracker yaml in
src/detection/trackers/botsort-reid.yaml and to re-tune it later.

Usage: uv run python scripts/probe_reid.py [start_min] [end_min]
"""

import time

from src.core.models import (
    AggregationConfig,
    DetectionConfig,
    PipelineConfig,
    SamplingConfig,
)
from src.detection.yolo_detector import YOLOv8Detector
from src.pipeline.coordinator import PipelineCoordinator
from src.video.reader import OpenCVFrameReader
from src.video.sampler import compute_frame_indices

VIDEO = r"D:\claude\video.mp4"


def overlap_pairs(segments) -> int:
    ordered = sorted(segments, key=lambda s: s.start_time)
    pairs = 0
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if b.start_time >= a.end_time:
                break
            pairs += 1
    return pairs


def run(use_reid: bool, indices: list[int], fps: float, model_name: str, conf: float) -> None:
    detector = YOLOv8Detector(
        model_name=model_name,
        device="cuda:0",
        target_classes=[0],
        confidence_threshold=conf,
        imgsz=1280,
        use_tracker=True,
        half=True,
        use_reid=use_reid,
    )
    coordinator = PipelineCoordinator(
        reader_factory=lambda: OpenCVFrameReader(hw_accel=True),
        video_path=VIDEO,
        detector=detector,
        sampling_config=SamplingConfig(),
        detection_config=DetectionConfig(),
        aggregation_config=AggregationConfig(),
        pipeline_config=PipelineConfig(),
        detection_target="person",
    )
    t0 = time.time()
    result = coordinator.run(indices, fps)
    segs = result.segments
    wall = time.time() - t0
    span = sum(s.end_time - s.start_time for s in segs)
    print(
        f"reid={use_reid!s:5}  records={len(segs):4}  overlap_pairs={overlap_pairs(segs):3}"
        f"  total_span={span:7.1f}s  detections={sum(s.detection_count for s in segs):5}"
        f"  wall={wall:6.1f}s"
    )
    for s in sorted(segs, key=lambda s: s.start_time):
        print(
            f"  {s.start_time:8.2f} - {s.end_time:8.2f}  det={s.detection_count:3}"
            f"  max_conf={s.max_confidence:.2f}"
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start_min", nargs="?", type=float, default=10.0)
    parser.add_argument("end_min", nargs="?", type=float, default=20.0)
    parser.add_argument("--model", default="yolov8m.pt")
    parser.add_argument("--conf", type=float, default=0.6)
    parser.add_argument("--no-reid", action="store_true")
    args = parser.parse_args()
    start_min, end_min = args.start_min, args.end_min
    model_name, conf, use_reid = args.model, args.conf, not args.no_reid

    reader = OpenCVFrameReader(hw_accel=True)
    meta = reader.open(VIDEO)
    reader.close()
    i0, i1 = int(start_min * 60 * meta.fps), int(end_min * 60 * meta.fps)
    indices = [
        i for i in compute_frame_indices(meta.fps, 3.0, meta.total_frames) if i0 <= i < i1
    ]
    print(f"probe window: {start_min}-{end_min} min, {len(indices)} sampled frames")

    run(use_reid, indices, meta.fps, model_name, conf)


if __name__ == "__main__":
    main()
