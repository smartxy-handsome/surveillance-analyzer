from src.core.models import AggregationConfig, TimeSegment


class SegmentAggregator:
    def __init__(self, config: AggregationConfig):
        self._config = config
        self._current_start: float | None = None
        self._last_timestamp: float | None = None
        self._current_key: int | None = None
        self._segment_counter: int = 0
        self._count = 0
        self._conf_sum = 0.0
        self._conf_max = 0.0
        self._segments: list[TimeSegment] = []

    def accumulate(self, timestamp: float, has_person: bool, confidence: float) -> int | None:
        if has_person:
            if self._current_start is None:
                self._segment_counter += 1
                self._current_key = self._segment_counter
                self._current_start = timestamp
                self._count = 0
                self._conf_sum = 0.0
                self._conf_max = 0.0
            elif self._last_timestamp is not None:
                gap = timestamp - self._last_timestamp
                if gap > self._config.merge_gap_seconds:
                    self._close_segment()
                    self._segment_counter += 1
                    self._current_key = self._segment_counter
                    self._current_start = timestamp
                    self._count = 0
                    self._conf_sum = 0.0
                    self._conf_max = 0.0

            self._count += 1
            self._conf_sum += confidence
            self._conf_max = max(self._conf_max, confidence)
            self._last_timestamp = timestamp
            return self._current_key
        else:
            if self._current_start is not None and self._last_timestamp is not None:
                gap = timestamp - self._last_timestamp
                if gap > self._config.merge_gap_seconds:
                    self._close_segment()
            return None

    def _close_segment(self) -> None:
        if self._current_start is not None and self._last_timestamp is not None:
            seg = TimeSegment(
                start_time=self._current_start,
                end_time=self._last_timestamp,
                detection_count=self._count,
                avg_confidence=self._conf_sum / self._count if self._count else 0.0,
                max_confidence=self._conf_max,
                source_key=self._current_key,
            )
            if seg.duration >= self._config.min_segment_seconds or (
                seg.max_confidence >= self._config.min_segment_rescue_conf
            ):
                self._segments.append(seg)
        self._current_start = None
        self._last_timestamp = None

    def finalize(self) -> list[TimeSegment]:
        self._close_segment()
        return self._segments
