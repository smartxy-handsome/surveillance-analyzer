from src.core.models import AggregationConfig, TimeSegment


class TrackAggregator:
    """Aggregates detections into segments keyed by tracker identity.

    One ByteTrack track = one enter/exit record: a person the detector
    briefly loses mid-walk keeps their track (ByteTrack buffers lost tracks),
    so continuous presence no longer splits into sawtooth segments.

    Detections without a track id (tracker produced none) fall back to
    boolean presence aggregation -- they must never be dropped.

    accumulate() returns the transient segment key used by the capture
    collector; finalize() stamps each surviving TimeSegment with the same
    key in ``source_key`` so captures join back without time-span guessing.
    """

    def __init__(self, config: AggregationConfig):
        self._config = config
        self._segment_counter = 0
        self._segments: list[TimeSegment] = []
        # track_id -> state dict
        self._tracks: dict[int, dict] = {}
        # Fallback stream for detections without tracker ids
        self._anon_start: float | None = None
        self._anon_last: float | None = None
        self._anon_key: int | None = None
        self._anon_count = 0
        self._anon_conf_sum = 0.0
        self._anon_conf_max = 0.0

    def accumulate(
        self, timestamp: float, has_person: bool, confidence: float, track_id: int | None = None
    ) -> int | None:
        if not has_person:
            return None

        if track_id is not None:
            return self._accumulate_tracked(timestamp, confidence, track_id)
        return self._accumulate_anonymous(timestamp, confidence)

    def _accumulate_tracked(self, timestamp: float, confidence: float, track_id: int) -> int:
        state = self._tracks.get(track_id)
        if state is None:
            self._segment_counter += 1
            state = {
                "key": self._segment_counter,
                "start": timestamp,
                "last": timestamp,
                "count": 0,
                "conf_sum": 0.0,
                "conf_max": 0.0,
            }
            self._tracks[track_id] = state

        state["last"] = max(state["last"], timestamp)
        state["count"] += 1
        state["conf_sum"] += confidence
        state["conf_max"] = max(state["conf_max"], confidence)
        return state["key"]

    def _accumulate_anonymous(self, timestamp: float, confidence: float) -> int | None:
        # Mirror SegmentAggregator's gap logic: a new anonymous burst starts
        # when the previous one is farther back than merge_gap_seconds.
        if self._anon_start is None:
            self._open_anonymous(timestamp)
        elif self._anon_last is not None and timestamp - self._anon_last > self._config.merge_gap_seconds:
            self._close_anonymous()
            self._open_anonymous(timestamp)

        self._anon_count += 1
        self._anon_conf_sum += confidence
        self._anon_conf_max = max(self._anon_conf_max, confidence)
        self._anon_last = timestamp
        return self._anon_key

    def _open_anonymous(self, timestamp: float) -> None:
        self._segment_counter += 1
        self._anon_key = self._segment_counter
        self._anon_start = timestamp
        self._anon_last = timestamp
        self._anon_count = 0
        self._anon_conf_sum = 0.0
        self._anon_conf_max = 0.0

    def _close_anonymous(self) -> TimeSegment | None:
        seg = None
        if self._anon_start is not None and self._anon_last is not None:
            seg = self._emit(
                key=self._anon_key,
                start=self._anon_start,
                last=self._anon_last,
                count=self._anon_count,
                conf_sum=self._anon_conf_sum,
                conf_max=self._anon_conf_max,
            )
        self._anon_start = None
        self._anon_last = None
        self._anon_key = None
        return seg

    def _emit(self, key, start, last, count, conf_sum, conf_max) -> None:
        seg = TimeSegment(
            start_time=start,
            end_time=last,
            detection_count=count,
            avg_confidence=conf_sum / count if count else 0.0,
            max_confidence=conf_max,
            source_key=key,
        )
        # Rescue rule: short bursts with a confident peak still produce a
        # record and captures -- a detection the old threshold accepted must
        # never disappear for being brief.
        if seg.duration >= self._config.min_segment_seconds or (
            seg.max_confidence >= self._config.min_segment_rescue_conf
        ):
            self._segments.append(seg)

    def finalize(self) -> list[TimeSegment]:
        for state in self._tracks.values():
            self._emit(
                key=state["key"],
                start=state["start"],
                last=state["last"],
                count=state["count"],
                conf_sum=state["conf_sum"],
                conf_max=state["conf_max"],
            )
        # Close any open anonymous burst
        self._close_anonymous()

        self._segments.sort(key=lambda s: s.start_time)
        return self._segments
