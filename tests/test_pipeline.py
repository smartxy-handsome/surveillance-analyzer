import threading
import numpy as np
from unittest.mock import MagicMock

from src.pipeline.coordinator import PipelineCoordinator
from src.core.interfaces import FrameDetection, FrameData, VideoMetadata
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
