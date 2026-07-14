import numpy as np

from src.core.models import CaptureCandidate, SegmentCaptureData


class SegmentCaptureCollector:
    """Collects candidate frames during inference for later capture saving.

    Maintains a per-segment buffer of top-N frames sorted by confidence.
    """

    def __init__(self, max_per_segment: int = 3):
        self._max = max_per_segment
        # segment_key -> sorted list of CaptureCandidate (by confidence desc)
        self._segments: dict[int, list[CaptureCandidate]] = {}
        # segment_key -> (start_time, end_time)
        self._segment_times: dict[int, tuple[float, float]] = {}

    def add_candidate(
        self,
        segment_key: int,
        frame_index: int,
        timestamp: float,
        confidence: float,
        image: np.ndarray,
        boxes: list[tuple[int, int, int, int]],
    ) -> None:
        """Add a candidate frame for a segment.

        Args:
            segment_key: Unique identifier for the current segment
            frame_index: Frame index in the video
            timestamp: Frame timestamp in seconds
            confidence: Detection confidence score
            image: Frame image (numpy array)
            boxes: List of bounding boxes (x1, y1, x2, y2)
        """
        candidate = CaptureCandidate(
            frame_index=frame_index,
            timestamp=timestamp,
            confidence=confidence,
            image=image.copy(),  # Store a copy to avoid reference issues
            boxes=boxes,
        )

        if segment_key not in self._segments:
            self._segments[segment_key] = []
            self._segment_times[segment_key] = (timestamp, timestamp)

        candidates = self._segments[segment_key]

        # Update end time
        start, _ = self._segment_times[segment_key]
        self._segment_times[segment_key] = (start, timestamp)

        # Insert candidate maintaining sorted order (confidence desc)
        if len(candidates) < self._max:
            # Buffer not full, insert in sorted position
            self._insert_sorted(candidates, candidate)
        elif confidence > candidates[-1].confidence:
            # Buffer full but this is better than the worst
            candidates.pop()  # Remove lowest confidence
            self._insert_sorted(candidates, candidate)
        # else: ignore - lower than all current candidates

    def _insert_sorted(
        self, candidates: list[CaptureCandidate], candidate: CaptureCandidate
    ) -> None:
        """Insert candidate in sorted position (confidence descending)."""
        for i, existing in enumerate(candidates):
            if candidate.confidence > existing.confidence:
                candidates.insert(i, candidate)
                return
        candidates.append(candidate)

    def get_all_captures(self) -> list[SegmentCaptureData]:
        """Return all collected captures, one SegmentCaptureData per segment.

        Returns:
            List of SegmentCaptureData, sorted by segment_index
        """
        result = []
        for segment_key, candidates in self._segments.items():
            start_time, end_time = self._segment_times[segment_key]
            result.append(
                SegmentCaptureData(
                    segment_index=segment_key,
                    start_time=start_time,
                    end_time=end_time,
                    candidates=list(candidates),  # Return a copy
                )
            )
        # Sort by segment_index for consistent output
        result.sort(key=lambda x: x.segment_index)
        return result
