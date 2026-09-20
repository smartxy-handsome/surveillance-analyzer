import numpy as np
import pytest

from src.pipeline.capture_collector import SegmentCaptureCollector


@pytest.fixture
def sample_frame():
    """Create a sample 100x100 RGB frame."""
    return np.zeros((100, 100, 3), dtype=np.uint8)


@pytest.fixture
def sample_boxes():
    """Sample bounding boxes."""
    return [(10, 10, 50, 50)]


class TestSegmentCaptureCollector:
    """Capture policy: keep one capture when the person appears (first
    detection) and one when they leave (last detection) per segment."""

    def test_add_single_candidate(self, sample_frame, sample_boxes):
        """A single detection yields a single capture."""
        collector = SegmentCaptureCollector()
        collector.add_candidate(
            segment_key=1,
            frame_index=100,
            timestamp=5.0,
            confidence=0.9,
            image=sample_frame,
            boxes=sample_boxes,
        )

        captures = collector.get_all_captures()
        assert len(captures) == 1
        assert captures[0].segment_index == 1
        assert len(captures[0].candidates) == 1
        assert captures[0].candidates[0].confidence == 0.9

    def test_keeps_first_and_last_detection(self, sample_frame, sample_boxes):
        """Multiple detections keep only the first (appearance) and last
        (departure) candidates, ordered by timestamp."""
        collector = SegmentCaptureCollector()

        collector.add_candidate(1, 100, 5.0, 0.5, sample_frame, sample_boxes)
        collector.add_candidate(1, 200, 10.0, 0.9, sample_frame, sample_boxes)
        collector.add_candidate(1, 300, 15.0, 0.7, sample_frame, sample_boxes)
        collector.add_candidate(1, 400, 20.0, 0.6, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert len(captures[0].candidates) == 2
        timestamps = [c.timestamp for c in captures[0].candidates]
        assert timestamps == [5.0, 20.0]

    def test_intermediate_confident_frame_is_dropped(self, sample_frame, sample_boxes):
        """A high-confidence middle frame does not replace first/last."""
        collector = SegmentCaptureCollector()

        collector.add_candidate(1, 100, 5.0, 0.5, sample_frame, sample_boxes)
        collector.add_candidate(1, 200, 10.0, 0.99, sample_frame, sample_boxes)
        collector.add_candidate(1, 300, 15.0, 0.6, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        timestamps = [c.timestamp for c in captures[0].candidates]
        assert timestamps == [5.0, 15.0]

    def test_single_detection_segment_keeps_one(self, sample_frame, sample_boxes):
        """A segment with only one detection keeps exactly one capture."""
        collector = SegmentCaptureCollector()

        collector.add_candidate(1, 100, 5.0, 0.9, sample_frame, sample_boxes)
        collector.add_candidate(1, 100, 5.0, 0.7, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert len(captures[0].candidates) == 1

    def test_multiple_segments(self, sample_frame, sample_boxes):
        """Segments are tracked independently."""
        collector = SegmentCaptureCollector()

        collector.add_candidate(1, 100, 5.0, 0.9, sample_frame, sample_boxes)
        collector.add_candidate(2, 200, 10.0, 0.8, sample_frame, sample_boxes)
        collector.add_candidate(1, 300, 15.0, 0.7, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert len(captures) == 2

        seg1 = next(c for c in captures if c.segment_index == 1)
        seg2 = next(c for c in captures if c.segment_index == 2)

        assert [c.timestamp for c in seg1.candidates] == [5.0, 15.0]
        assert [c.timestamp for c in seg2.candidates] == [10.0]

    def test_candidates_sorted_by_timestamp_asc(self, sample_frame, sample_boxes):
        """Candidates are ordered appearance -> departure (timestamp asc)."""
        collector = SegmentCaptureCollector()

        collector.add_candidate(1, 100, 5.0, 0.5, sample_frame, sample_boxes)
        collector.add_candidate(1, 300, 15.0, 0.9, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        timestamps = [c.timestamp for c in captures[0].candidates]
        assert timestamps == sorted(timestamps)

    def test_empty_collector(self):
        """Should return empty list when no candidates added."""
        collector = SegmentCaptureCollector()
        captures = collector.get_all_captures()
        assert captures == []

    def test_segment_metadata(self, sample_frame, sample_boxes):
        """Should store segment start/end times from first/last candidates."""
        collector = SegmentCaptureCollector()

        collector.add_candidate(1, 100, 5.0, 0.9, sample_frame, sample_boxes)
        collector.add_candidate(1, 400, 20.0, 0.7, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert captures[0].start_time == 5.0
        assert captures[0].end_time == 20.0

    def test_out_of_order_arrival_keeps_sane_span(self, sample_frame, sample_boxes):
        """Frames may arrive out of order (parallel decode threads): the
        segment span must still be (min timestamp, max timestamp)."""
        collector = SegmentCaptureCollector()

        collector.add_candidate(1, 300, 15.0, 0.9, sample_frame, sample_boxes)
        collector.add_candidate(1, 100, 5.0, 0.7, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert captures[0].start_time == 5.0
        assert captures[0].end_time == 15.0
        timestamps = [c.timestamp for c in captures[0].candidates]
        assert timestamps == [5.0, 15.0]
