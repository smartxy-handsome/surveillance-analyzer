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
    def test_add_single_candidate(self, sample_frame, sample_boxes):
        """Should store a single candidate."""
        collector = SegmentCaptureCollector(max_per_segment=3)
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

    def test_respects_max_per_segment(self, sample_frame, sample_boxes):
        """Should only keep max_per_segment candidates."""
        collector = SegmentCaptureCollector(max_per_segment=2)

        # Add 3 candidates with different confidences
        collector.add_candidate(1, 100, 5.0, 0.7, sample_frame, sample_boxes)
        collector.add_candidate(1, 200, 10.0, 0.9, sample_frame, sample_boxes)
        collector.add_candidate(1, 300, 15.0, 0.8, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert len(captures) == 1
        assert len(captures[0].candidates) == 2
        # Should keep the two highest confidence (0.9 and 0.8)
        confidences = [c.confidence for c in captures[0].candidates]
        assert confidences == [0.9, 0.8]

    def test_replaces_lower_confidence_when_full(self, sample_frame, sample_boxes):
        """Should replace lowest confidence candidate when a higher one arrives."""
        collector = SegmentCaptureCollector(max_per_segment=3)

        # Fill with 3 candidates
        collector.add_candidate(1, 100, 5.0, 0.7, sample_frame, sample_boxes)
        collector.add_candidate(1, 200, 10.0, 0.8, sample_frame, sample_boxes)
        collector.add_candidate(1, 300, 15.0, 0.9, sample_frame, sample_boxes)

        # Add one with higher confidence than lowest (0.7)
        collector.add_candidate(1, 400, 20.0, 0.85, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert len(captures[0].candidates) == 3
        confidences = [c.confidence for c in captures[0].candidates]
        assert confidences == [0.9, 0.85, 0.8]

    def test_ignores_lower_confidence_when_full(self, sample_frame, sample_boxes):
        """Should ignore candidates with lower confidence than all current ones."""
        collector = SegmentCaptureCollector(max_per_segment=3)

        # Fill with 3 candidates
        collector.add_candidate(1, 100, 5.0, 0.7, sample_frame, sample_boxes)
        collector.add_candidate(1, 200, 10.0, 0.8, sample_frame, sample_boxes)
        collector.add_candidate(1, 300, 15.0, 0.9, sample_frame, sample_boxes)

        # Add one with lower confidence than all
        collector.add_candidate(1, 400, 20.0, 0.5, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert len(captures[0].candidates) == 3
        confidences = [c.confidence for c in captures[0].candidates]
        assert confidences == [0.9, 0.8, 0.7]

    def test_multiple_segments(self, sample_frame, sample_boxes):
        """Should track candidates for multiple segments independently."""
        collector = SegmentCaptureCollector(max_per_segment=2)

        collector.add_candidate(1, 100, 5.0, 0.9, sample_frame, sample_boxes)
        collector.add_candidate(2, 200, 10.0, 0.8, sample_frame, sample_boxes)
        collector.add_candidate(1, 300, 15.0, 0.7, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert len(captures) == 2

        # Find segment 1 and segment 2
        seg1 = next(c for c in captures if c.segment_index == 1)
        seg2 = next(c for c in captures if c.segment_index == 2)

        assert len(seg1.candidates) == 2
        assert len(seg2.candidates) == 1

    def test_candidates_sorted_by_confidence_desc(self, sample_frame, sample_boxes):
        """Candidates should be sorted by confidence descending."""
        collector = SegmentCaptureCollector(max_per_segment=3)

        collector.add_candidate(1, 100, 5.0, 0.5, sample_frame, sample_boxes)
        collector.add_candidate(1, 200, 10.0, 0.9, sample_frame, sample_boxes)
        collector.add_candidate(1, 300, 15.0, 0.7, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        confidences = [c.confidence for c in captures[0].candidates]
        assert confidences == sorted(confidences, reverse=True)

    def test_empty_collector(self):
        """Should return empty list when no candidates added."""
        collector = SegmentCaptureCollector(max_per_segment=3)
        captures = collector.get_all_captures()
        assert captures == []

    def test_segment_metadata(self, sample_frame, sample_boxes):
        """Should store segment start/end times from first candidate."""
        collector = SegmentCaptureCollector(max_per_segment=3)

        # First candidate sets the segment times
        collector.add_candidate(1, 100, 5.0, 0.9, sample_frame, sample_boxes)

        captures = collector.get_all_captures()
        assert captures[0].start_time == 5.0
        # end_time is set when finalize is called, not during add_candidate
        # This will be handled by the coordinator
