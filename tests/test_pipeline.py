import pytest
import numpy as np
from unittest.mock import MagicMock

from src.pipeline.coordinator import PipelineCoordinator
from src.core.interfaces import FrameDetection
from src.core.models import (
    AggregationConfig,
    DetectionConfig,
    PipelineConfig,
    SamplingConfig,
)


def test_pipeline_processes_frames():
    """Pipeline with mock detector produces correct segments."""
    detections = [
        FrameDetection(has_person=True, confidence=0.9, boxes=[]),
        FrameDetection(has_person=False, confidence=0.0, boxes=[]),
        FrameDetection(has_person=True, confidence=0.8, boxes=[]),
        FrameDetection(has_person=False, confidence=0.0, boxes=[]),
        FrameDetection(has_person=True, confidence=0.7, boxes=[]),
    ]
    call_count = 0

    def mock_detect(frames):
        nonlocal call_count
        result = [detections[call_count]]
        call_count += 1
        return result

    mock_detector = MagicMock()
    mock_detector.detect.side_effect = mock_detect
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    def mock_read_frame(index):
        return True, dummy_frame

    mock_reader = MagicMock()
    mock_reader.read_frame.side_effect = mock_read_frame

    def reader_factory():
        return mock_reader

    sampling = SamplingConfig(fps=1.0)
    detection = DetectionConfig(batch_size=1)
    aggregation = AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=0.0)
    pipeline_cfg = PipelineConfig(frame_queue_size=16, num_decode_threads=1)

    coordinator = PipelineCoordinator(
        reader_factory=reader_factory,
        video_path="test.mp4",
        detector=mock_detector,
        sampling_config=sampling,
        detection_config=detection,
        aggregation_config=aggregation,
        pipeline_config=pipeline_cfg,
    )

    frame_indices = [0, 1, 2, 3, 4]
    video_fps = 1.0
    result = coordinator.run(frame_indices, video_fps)

    assert len(result.segments) >= 1
    assert result.segments[0].detection_count == 3


def test_pipeline_empty_video():
    mock_detector = MagicMock()
    mock_detector.detect.return_value = []
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    mock_reader = MagicMock()

    def reader_factory():
        return mock_reader

    coordinator = PipelineCoordinator(
        reader_factory=reader_factory,
        video_path="test.mp4",
        detector=mock_detector,
        sampling_config=SamplingConfig(),
        detection_config=DetectionConfig(),
        aggregation_config=AggregationConfig(),
        pipeline_config=PipelineConfig(num_decode_threads=1),
    )

    result = coordinator.run([], 30.0)
    assert result.segments == []
    assert result.captures == []
    assert result.dropped_frames == 0


def test_pipeline_dropped_frames_end_pipeline_and_counted():
    """Decode failures must not strand the inference thread.

    Dropped frames never enter the queue, so the worker's exit condition has
    to be "decode finished AND queue drained" -- not a processed-frame count.
    The run must return (not hang until join timeout) and report the drops.
    """
    plan = [True, True, False, False, True]  # False = read_frame fails
    read_count = 0
    detect_count = 0

    def mock_read_frame(index):
        nonlocal read_count
        ok = plan[read_count]
        read_count += 1
        return (ok, np.zeros((10, 10, 3), dtype=np.uint8) if ok else None)

    mock_reader = MagicMock()
    mock_reader.read_frame.side_effect = mock_read_frame

    def mock_detect(frames):
        nonlocal detect_count
        detect_count += 1
        return [FrameDetection(has_person=True, confidence=0.9, boxes=[]) for _ in frames]

    mock_detector = MagicMock()
    mock_detector.detect.side_effect = mock_detect
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    coordinator = PipelineCoordinator(
        reader_factory=lambda: mock_reader,
        video_path="test.mp4",
        detector=mock_detector,
        sampling_config=SamplingConfig(fps=1.0),
        detection_config=DetectionConfig(batch_size=1),
        aggregation_config=AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=0.0),
        pipeline_config=PipelineConfig(frame_queue_size=16, num_decode_threads=1),
    )

    # 5 frames requested, 3 decoded, 2 dropped. Must terminate quickly.
    result = coordinator.run(list(range(5)), 1.0)

    assert read_count == 5
    assert detect_count == 3
    assert result.dropped_frames == 2
    # The 1s->4s timestamp jump created by the drops exceeds merge_gap_seconds,
    # so the aggregator correctly closes the first burst and opens a second.
    assert len(result.segments) == 2


def test_pipeline_decode_exception_propagates_and_unloads():
    """A decode failure must propagate (job -> failed), not strand threads.

    reader.open() raising simulates a video deleted while queued. The
    exception propagates out of run(), the detector is unloaded, and the
    inference worker exits via the queue-done signal instead of spinning.
    """
    mock_detector = MagicMock()
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    def open_raises(path):
        raise FileNotFoundError(f"Cannot open video: {path}")

    mock_reader = MagicMock()
    mock_reader.open.side_effect = open_raises

    coordinator = PipelineCoordinator(
        reader_factory=lambda: mock_reader,
        video_path="missing.mp4",
        detector=mock_detector,
        sampling_config=SamplingConfig(fps=1.0),
        detection_config=DetectionConfig(batch_size=1),
        aggregation_config=AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=0.0),
        pipeline_config=PipelineConfig(frame_queue_size=16, num_decode_threads=1),
    )

    with pytest.raises(FileNotFoundError):
        coordinator.run(list(range(5)), 1.0)

    mock_detector.unload.assert_called_once()


def test_captures_aligned_to_final_segments():
    """Captures exist only for bursts that survived aggregation (duration >=
    min_segment_seconds), renumbered to the final segment's 1-based ordinal.

    Frames at 1 fps: burst A at 0-2s (kept), single-frame blip B at 6s
    (filtered by min_segment_seconds), burst C at 9-11s (kept).
    """
    plan = [
        (True, 0.9),   # 0s  — burst A starts
        (True, 0.8),   # 1s
        (True, 0.7),   # 2s  — burst A ends
        (False, 0.0),  # 3s
        (False, 0.0),  # 4s
        (False, 0.0),  # 5s  — gap closes A (duration 2.0 >= 1.0: kept)
        (True, 0.4),   # 6s  — blip B: short AND below the rescue line
        (False, 0.0),  # 7s
        (False, 0.0),  # 8s
        (True, 0.85),  # 9s  — gap 3s closes B (duration 0: filtered); C starts
        (True, 0.8),   # 10s
        (True, 0.75),  # 11s — C ends
    ]
    call_count = 0

    def mock_detect(frames):
        nonlocal call_count
        has_person, conf = plan[call_count]
        call_count += 1
        return [FrameDetection(has_person=has_person, confidence=conf, boxes=[(1, 1, 2, 2)])]

    mock_detector = MagicMock()
    mock_detector.detect.side_effect = mock_detect
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_reader = MagicMock()
    mock_reader.read_frame.side_effect = lambda index: (True, dummy_frame)

    def reader_factory():
        return mock_reader

    coordinator = PipelineCoordinator(
        reader_factory=reader_factory,
        video_path="test.mp4",
        detector=mock_detector,
        sampling_config=SamplingConfig(fps=1.0),
        detection_config=DetectionConfig(batch_size=1),
        aggregation_config=AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=1.0),
        pipeline_config=PipelineConfig(frame_queue_size=16, num_decode_threads=1),
    )

    result = coordinator.run(list(range(12)), 1.0)

    assert len(result.segments) == 2
    # Only bursts A and C keep captures, renumbered 1..2; blip B is dropped
    assert [c.segment_index for c in result.captures] == [1, 2]
    assert [len(c.candidates) for c in result.captures] == [2, 2]
    assert [c.candidates[0].timestamp for c in result.captures] == [0.0, 9.0]
    assert [c.candidates[-1].timestamp for c in result.captures] == [2.0, 11.0]


def test_tracking_merges_dropout_into_one_segment():
    """Regression for the reported sawtooth: the same person (track 1) is
    detected 0-2s, lost 3-5s, detected again 6-8s. Tracking must yield ONE
    enter/exit record with one capture pair -- not two fragments.
    """
    plan = [
        (True, 1), (True, 1), (True, 1),   # 0-2s
        (False, None), (False, None), (False, None),  # 3-5s dropout
        (True, 1), (True, 1), (True, 1),   # 6-8s, same track
    ]
    call_count = 0

    def mock_detect(frames):
        nonlocal call_count
        has_person, track_id = plan[call_count]
        call_count += 1
        return [
            FrameDetection(has_person=has_person, confidence=0.9, boxes=[(1, 1, 2, 2)], track_ids=[track_id] if track_id else [])
        ]

    mock_detector = MagicMock()
    mock_detector.detect.side_effect = mock_detect
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_reader = MagicMock()
    mock_reader.read_frame.side_effect = lambda index: (True, dummy_frame)

    coordinator = PipelineCoordinator(
        reader_factory=lambda: mock_reader,
        video_path="test.mp4",
        detector=mock_detector,
        sampling_config=SamplingConfig(fps=1.0),
        detection_config=DetectionConfig(batch_size=1),
        aggregation_config=AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=1.0, use_tracking=True),
        pipeline_config=PipelineConfig(frame_queue_size=16, num_decode_threads=1),
    )

    result = coordinator.run(list(range(9)), 1.0)

    assert len(result.segments) == 1
    seg = result.segments[0]
    assert seg.start_time == 0.0 and seg.end_time == 8.0
    assert seg.detection_count == 6
    # One capture pair for the whole presence: appearance at 0s, departure at 8s
    assert len(result.captures) == 1
    assert result.captures[0].segment_index == 1
    assert [c.timestamp for c in result.captures[0].candidates] == [0.0, 8.0]


def test_legacy_boolean_mode_still_splits_on_gap():
    """use_tracking=False keeps the old presence-based behavior: the same
    detections split into two segments across the 4s gap."""
    plan = [(True, 1)] * 3 + [(False, None)] * 3 + [(True, 1)] * 3
    call_count = 0

    def mock_detect(frames):
        nonlocal call_count
        has_person, _ = plan[call_count]
        call_count += 1
        return [FrameDetection(has_person=has_person, confidence=0.9, boxes=[])]

    mock_detector = MagicMock()
    mock_detector.detect.side_effect = mock_detect
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_reader = MagicMock()
    mock_reader.read_frame.side_effect = lambda index: (True, dummy_frame)

    coordinator = PipelineCoordinator(
        reader_factory=lambda: mock_reader,
        video_path="test.mp4",
        detector=mock_detector,
        sampling_config=SamplingConfig(fps=1.0),
        detection_config=DetectionConfig(batch_size=1),
        aggregation_config=AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=1.0, use_tracking=False),
        pipeline_config=PipelineConfig(frame_queue_size=16, num_decode_threads=1),
    )

    result = coordinator.run(list(range(9)), 1.0)
    assert len(result.segments) == 2


def test_short_high_conf_track_still_captures():
    """End-to-end regression for the audit finding: a person visible for only
    2 sampled frames (0.64s < min_segment_seconds) with confident detections
    must produce a segment AND captures, not silently vanish."""
    plan = [(False, None), (True, 1), (True, 1), (False, None)]
    call_count = 0

    def mock_detect(frames):
        nonlocal call_count
        has_person, track_id = plan[call_count]
        call_count += 1
        return [
            FrameDetection(
                has_person=has_person,
                confidence=0.72 if has_person else 0.0,
                boxes=[(1, 1, 20, 40)] if has_person else [],
                track_ids=[track_id] if track_id else [],
            )
        ]

    mock_detector = MagicMock()
    mock_detector.detect.side_effect = mock_detect
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_reader = MagicMock()
    mock_reader.read_frame.side_effect = lambda index: (True, dummy_frame)

    coordinator = PipelineCoordinator(
        reader_factory=lambda: mock_reader,
        video_path="test.mp4",
        detector=mock_detector,
        sampling_config=SamplingConfig(fps=3.0),
        detection_config=DetectionConfig(batch_size=1),
        aggregation_config=AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=1.0),
        pipeline_config=PipelineConfig(frame_queue_size=16, num_decode_threads=1),
    )

    result = coordinator.run(list(range(4)), 3.0)

    assert len(result.segments) == 1
    assert result.segments[0].duration == pytest.approx(1 / 3)
    assert result.segments[0].max_confidence == 0.72
    # And the capture pair exists: appearance + departure on the same track
    assert len(result.captures) == 1
    assert len(result.captures[0].candidates) == 2


def test_id_switch_captures_fold_into_one_group():
    """A re-ID'd person yields ONE record and ONE capture pair (earliest +
    latest), not four captures across two groups."""
    # track 1 at frames 0-2 (t=0..0.66s), track 2 same body frames 3-5
    plan = [(1, 0.0), (1, 0.33), (1, 0.66), (2, 1.0), (2, 1.33), (2, 1.66)]
    call_count = 0

    def mock_detect(frames):
        nonlocal call_count
        track_id, _ = plan[call_count]
        call_count += 1
        return [
            FrameDetection(
                has_person=True,
                confidence=0.9,
                boxes=[(100, 100, 140, 220)],
                track_ids=[track_id],
            )
        ]

    mock_detector = MagicMock()
    mock_detector.detect.side_effect = mock_detect
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    mock_reader = MagicMock()
    mock_reader.read_frame.side_effect = lambda index: (True, dummy_frame)

    coordinator = PipelineCoordinator(
        reader_factory=lambda: mock_reader,
        video_path="test.mp4",
        detector=mock_detector,
        sampling_config=SamplingConfig(fps=3.0),
        detection_config=DetectionConfig(batch_size=1),
        aggregation_config=AggregationConfig(
            merge_gap_seconds=2.0, min_segment_seconds=0.5, record_merge_iou=0.5
        ),
        pipeline_config=PipelineConfig(frame_queue_size=16, num_decode_threads=1),
    )

    result = coordinator.run(list(range(6)), 3.0)

    assert len(result.segments) == 1
    assert result.segments[0].detection_count == 6
    assert len(result.captures) == 1
    caps = result.captures[0].candidates
    assert [c.timestamp for c in caps] == [0.0, pytest.approx(5 / 3)]


def test_class_dispatch_routes_person_and_vehicle():
    """One inference pass feeding both consumers: person boxes build person
    segments, vehicle boxes build vehicle events, and neither leaks."""
    # person track 1 at t=0..0.66; vehicle track 10 at t=1.0..1.66
    plan = [
        (0, 1), (0, 1), (0, 1),      # person frames
        (2, 10), (2, 10), (2, 10),   # vehicle frames
    ]
    call_count = 0

    def mock_detect(frames):
        nonlocal call_count
        class_id, track_id = plan[call_count]
        call_count += 1
        box = (10, 10, 60, 140) if class_id == 0 else (100, 100, 260, 220)
        return [
            FrameDetection(
                has_person=True,
                confidence=0.9,
                boxes=[box],
                track_ids=[track_id],
                class_ids=[class_id],
            )
        ]

    mock_detector = MagicMock()
    mock_detector.detect.side_effect = mock_detect
    mock_detector.load.return_value = None
    mock_detector.unload.return_value = None

    dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    mock_reader = MagicMock()
    mock_reader.read_frame.side_effect = lambda index: (True, dummy_frame)

    coordinator = PipelineCoordinator(
        reader_factory=lambda: mock_reader,
        video_path="test.mp4",
        detector=mock_detector,
        sampling_config=SamplingConfig(fps=3.0),
        detection_config=DetectionConfig(batch_size=1),
        aggregation_config=AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=0.5),
        pipeline_config=PipelineConfig(frame_queue_size=16, num_decode_threads=1),
        detection_target="both",
    )

    result = coordinator.run(list(range(6)), 3.0)

    # Person side: one segment from the three class-0 frames
    assert len(result.segments) == 1
    assert result.segments[0].detection_count == 3
    # Vehicle side: one event with enter/exit times from class-2 frames
    assert len(result.vehicle_events) == 1
    ev = result.vehicle_events[0]
    assert ev.ordinal == 1
    assert ev.enter_time == pytest.approx(1.0)
    assert ev.exit_time == pytest.approx(5 / 3)
    assert ev.detection_count == 3
    assert ev.enter_candidate is not None and ev.plate_candidates  # best frames kept
