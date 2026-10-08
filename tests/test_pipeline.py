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
        (True, 0.95),  # 6s  — blip B
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
