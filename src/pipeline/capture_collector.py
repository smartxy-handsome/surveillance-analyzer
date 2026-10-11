import numpy as np

from src.core.models import CaptureCandidate, SegmentCaptureData


class SegmentCaptureCollector:
    """Collects candidate frames during inference for later capture saving.

    Capture policy: per segment, keep one capture when the person appears
    (first detection) and one when they leave (last detection). A segment
    with a single detection keeps one capture.
    """

    def __init__(self):
        # segment_key -> {"first": CaptureCandidate, "last": CaptureCandidate}
        self._segments: dict[int, dict[str, CaptureCandidate]] = {}
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
        area = _max_box_area(boxes)

        if segment_key not in self._segments:
            self._segments[segment_key] = {
                "first": candidate,
                "last": candidate,
                "best": candidate,
                "best_area": area,
            }
            self._segment_times[segment_key] = (timestamp, timestamp)
            return

        start, end = self._segment_times[segment_key]
        # Frames may arrive out of order (parallel decode threads), so track
        # the segment span by timestamp, not arrival order.
        self._segment_times[segment_key] = (min(start, timestamp), max(end, timestamp))
        # Frames may arrive slightly out of order (parallel decode threads +
        # batched inference), so track appearance/departure by timestamp.
        pair = self._segments[segment_key]
        if timestamp < pair["first"].timestamp:
            pair["first"] = candidate
        if timestamp >= pair["last"].timestamp:
            pair["last"] = candidate
        # Plate close-up source: the frame where the target box was largest
        # (closest to the camera -> most plate/detail pixels).
        if area > pair["best_area"]:
            pair["best"] = candidate
            pair["best_area"] = area

    def get_all_captures(self) -> list[SegmentCaptureData]:
        """Return all collected captures, one SegmentCaptureData per segment.

        Returns:
            List of SegmentCaptureData, sorted by segment_index
        """
        result = []
        for segment_key, pair in self._segments.items():
            start_time, end_time = self._segment_times[segment_key]
            if pair["first"] is pair["last"] or pair["first"].frame_index == pair["last"].frame_index:
                candidates = [pair["first"]]
            else:
                candidates = sorted(
                    [pair["first"], pair["last"]], key=lambda c: c.timestamp
                )
            result.append(
                SegmentCaptureData(
                    segment_index=segment_key,
                    start_time=start_time,
                    end_time=end_time,
                    candidates=candidates,
                    plate_candidate=pair["best"],
                )
            )
        # Sort by segment_index for consistent output
        result.sort(key=lambda x: x.segment_index)
        return result


def _max_box_area(boxes: list[tuple[int, int, int, int]]) -> int:
    return max(((x2 - x1) * (y2 - y1) for x1, y1, x2, y2 in boxes), default=0)
