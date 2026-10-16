from collections import deque

from src.core.models import AggregationConfig, TimeSegment

# Bounded per-track box history (timestamp, box) kept for the ID-switch
# merge check at finalize time. 48 entries cover ~16s at 3fps sampling,
# far beyond the merge-gap window the comparison needs.
RECENT_BOX_MAX = 48


def box_iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = min(ax2, bx2) - max(ax1, bx1)
    ih = min(ay2, by2) - max(ay1, by1)
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / float(area_a + area_b - inter)


class TrackAggregator:
    """Aggregates detections into segments keyed by tracker identity.

    One ByteTrack track = one enter/exit record: a person the detector
    briefly loses mid-walk keeps their track (ByteTrack buffers lost tracks),
    so continuous presence no longer splits into sawtooth segments.

    Detections without a track id (tracker produced none) fall back to
    boolean presence aggregation -- they must never be dropped.

    ID-switch dedup: when the tracker re-IDs the same person, two records
    overlap in time with nearly coincident boxes. finalize() merges such
    records (temporal touch within record_merge_gap_seconds + boundary-box
    IoU >= record_merge_iou) and reports the absorbed keys in ``key_map`` so
    the coordinator can merge their capture groups.

    accumulate() returns the transient segment key used by the capture
    collector; finalize() stamps each surviving TimeSegment with its key in
    ``source_key`` so captures join back without time-span guessing.
    """

    def __init__(self, config: AggregationConfig):
        self._config = config
        self._segment_counter = 0
        self._segments: list[TimeSegment] = []
        # track_id -> state dict
        self._tracks: dict[int, dict] = {}
        # old key -> surviving key after ID-switch merging (set by finalize)
        self.key_map: dict[int, int] = {}
        # Fallback stream for detections without tracker ids
        self._anon_start: float | None = None
        self._anon_last: float | None = None
        self._anon_key: int | None = None
        self._anon_count = 0
        self._anon_conf_sum = 0.0
        self._anon_conf_max = 0.0

    def accumulate(
        self,
        timestamp: float,
        has_person: bool,
        confidence: float,
        track_id: int | None = None,
        box: tuple | None = None,
    ) -> int | None:
        if not has_person:
            return None

        if track_id is not None:
            return self._accumulate_tracked(timestamp, confidence, track_id, box)
        return self._accumulate_anonymous(timestamp, confidence)

    def _accumulate_tracked(
        self, timestamp: float, confidence: float, track_id: int, box: tuple | None
    ) -> int:
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
                "first_box": (timestamp, box) if box is not None else None,
                "recent": deque(maxlen=RECENT_BOX_MAX),
            }
            self._tracks[track_id] = state

        state["last"] = max(state["last"], timestamp)
        state["count"] += 1
        state["conf_sum"] += confidence
        state["conf_max"] = max(state["conf_max"], confidence)
        if box is not None:
            state["recent"].append((timestamp, box))
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

    def _close_anonymous(self) -> None:
        if self._anon_start is not None and self._anon_last is not None:
            self._emit(
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

    def _emit(self, key, start, last, count, conf_sum, conf_max) -> None:
        seg = TimeSegment(
            start_time=start,
            end_time=last,
            detection_count=count,
            avg_confidence=conf_sum / count if count else 0.0,
            max_confidence=conf_max,
            source_key=key,
        )
        # Temporal confirmation first: a single detection is one-frame flicker
        # (headlight glints, poles in IR night mode) and never becomes a
        # record, however confident.
        if count < self._config.min_detections:
            return
        # Rescue rule: short bursts with a confident peak still produce a
        # record and captures -- a detection the old threshold accepted must
        # never disappear for being brief.
        if seg.duration >= self._config.min_segment_seconds or (
            seg.max_confidence >= self._config.min_segment_rescue_conf
        ):
            self._segments.append(seg)

    def _boundary_iou(self, record: dict, track: dict) -> float:
        """IoU between the incoming track's first box and the record's boxes
        nearest in time to it -- the footprint evidence that both IDs trace
        the same body."""
        first = track.get("first_box")
        if first is None:
            return 0.0
        t_ts, t_box = first
        history = record.get("recent") or []
        near = [(ts, box) for ts, box in history if abs(ts - t_ts) <= 2 * self._config.record_merge_gap_seconds]
        if not near and history:
            near = [min(history, key=lambda item: abs(item[0] - t_ts))]
        return max((box_iou(t_box, box) for _, box in near), default=0.0)

    def _merge_id_switches(self, records: list[dict]) -> tuple[list[dict], dict[int, int]]:
        """Merge records that trace the same body under different IDs.

        Records are processed in start order; a record joins an earlier one
        when their time spans touch within the gap AND the boundary boxes
        coincide. Chained switches (A->B->C) collapse onto A. IoU <= 0
        disables merging entirely.
        """
        if self._config.record_merge_iou <= 0:
            return records, {}
        gap = self._config.record_merge_gap_seconds
        merged: list[dict] = []
        key_map: dict[int, int] = {}
        for track in sorted(records, key=lambda r: r["start"]):
            target = None
            for rec in reversed(merged):
                if track["start"] < rec["start"]:
                    continue
                if track["start"] - rec["last"] > gap:
                    continue
                if self._boundary_iou(rec, track) >= self._config.record_merge_iou:
                    target = rec
                    break
            if target is None:
                merged.append(track)
                continue
            key_map[track["key"]] = target["key"]
            target["last"] = max(target["last"], track["last"])
            target["count"] += track["count"]
            target["conf_sum"] += track["conf_sum"]
            target["conf_max"] = max(target["conf_max"], track["conf_max"])
            combined = sorted(
                list(target["recent"]) + list(track["recent"]), key=lambda item: item[0]
            )
            target["recent"] = deque(combined, maxlen=RECENT_BOX_MAX)
        return merged, key_map

    def finalize(self) -> list[TimeSegment]:
        # NOTE: _segments may already hold anonymous bursts closed mid-stream
        # during accumulate(); never reset it here.
        self.key_map = {}

        records, key_map = self._merge_id_switches(list(self._tracks.values()))
        self.key_map = key_map
        for rec in records:
            self._emit(
                key=rec["key"],
                start=rec["start"],
                last=rec["last"],
                count=rec["count"],
                conf_sum=rec["conf_sum"],
                conf_max=rec["conf_max"],
            )

        # Close any open anonymous burst
        self._close_anonymous()

        self._segments.sort(key=lambda s: s.start_time)
        return self._segments
