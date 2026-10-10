from src.core.models import AggregationConfig
from src.pipeline.track_aggregator import TrackAggregator


def make_config(**overrides) -> AggregationConfig:
    values = dict(merge_gap_seconds=2.0, min_segment_seconds=1.0)
    values.update(overrides)
    return AggregationConfig(**values)


def test_same_track_survives_detection_dropout():
    """The user's reported sawtooth: person present 0-2s, detector loses them
    3-5s, back 6-8s. One track = one segment, not two."""
    agg = TrackAggregator(make_config())
    for ts in (0.0, 1.0, 2.0, 6.0, 7.0, 8.0):
        agg.accumulate(ts, True, 0.9, track_id=1)
    segs = agg.finalize()
    assert len(segs) == 1
    assert segs[0].start_time == 0.0
    assert segs[0].end_time == 8.0
    assert segs[0].detection_count == 6
    assert segs[0].source_key == 1


def test_two_overlapping_tracks_two_segments():
    """Two people co-present: each gets their own enter/exit record."""
    agg = TrackAggregator(make_config(min_segment_seconds=0.0))
    for ts in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0):
        agg.accumulate(ts, True, 0.8, track_id=1)
    for ts in (3.0, 4.0, 5.0, 6.0, 7.0, 8.0):
        agg.accumulate(ts, True, 0.9, track_id=2)
    segs = agg.finalize()
    assert len(segs) == 2
    assert (segs[0].start_time, segs[0].end_time) == (0.0, 5.0)
    assert (segs[1].start_time, segs[1].end_time) == (3.0, 8.0)
    # Distinct source keys keep captures attributable per person
    assert segs[0].source_key != segs[1].source_key


def test_untracked_detections_fall_back_to_presence_groups():
    """Detections without tracker ids must never be dropped: they group by
    the same merge-gap rule as the legacy aggregator."""
    agg = TrackAggregator(make_config(min_segment_seconds=0.0))
    for ts in (0.0, 1.0, 2.0):
        agg.accumulate(ts, True, 0.9)  # no track id
    for ts in (10.0, 11.0):  # 8s gap > merge_gap: separate burst
        agg.accumulate(ts, True, 0.9)
    segs = agg.finalize()
    assert len(segs) == 2
    assert segs[0].source_key != segs[1].source_key


def test_mixed_tracked_and_untracked_keys_stay_unique():
    agg = TrackAggregator(make_config(min_segment_seconds=0.0))
    agg.accumulate(0.0, True, 0.9, track_id=5)
    agg.accumulate(1.0, True, 0.9)  # anonymous
    segs = agg.finalize()
    assert len(segs) == 2
    assert segs[0].source_key != segs[1].source_key


def test_short_tracks_dropped_by_min_segment():
    """Short AND low-confidence bursts are filtered (noise). Short bursts with
    a confident peak are rescued instead -- see the rescue tests below."""
    agg = TrackAggregator(make_config())  # min 1.0s, rescue 0.5
    agg.accumulate(0.0, True, 0.4, track_id=1)
    agg.accumulate(0.33, True, 0.4, track_id=2)
    assert agg.finalize() == []


def test_non_person_frames_are_ignored():
    """accumulate() is only fed detections; absence must not close a track."""
    agg = TrackAggregator(make_config())
    agg.accumulate(0.0, True, 0.9, track_id=1)
    for ts in (1.0, 2.0, 3.0):  # detector found nothing
        assert agg.accumulate(ts, False, 0.0) is None
    agg.accumulate(4.0, True, 0.9, track_id=1)
    segs = agg.finalize()
    assert len(segs) == 1
    assert segs[0].end_time == 4.0


def test_short_track_rescued_by_high_confidence():
    """Audit finding: a 3-detection 0.64s track peaking at conf 0.72 used to
    vanish without any capture. The rescue rule keeps it."""
    agg = TrackAggregator(make_config())  # min 1.0s, rescue 0.5
    for ts in (0.0, 0.33, 0.64):
        agg.accumulate(ts, True, 0.72, track_id=1)
    segs = agg.finalize()
    assert len(segs) == 1
    assert segs[0].max_confidence == 0.72


def test_short_low_conf_track_still_filtered():
    """Noise blips below the rescue line stay out."""
    agg = TrackAggregator(make_config())
    for ts in (0.0, 0.33, 0.64):
        agg.accumulate(ts, True, 0.45, track_id=1)
    assert agg.finalize() == []


def test_single_frame_at_rescue_threshold_kept():
    agg = TrackAggregator(make_config())
    agg.accumulate(0.0, True, 0.61, track_id=1)
    segs = agg.finalize()
    assert len(segs) == 1


def test_rescue_disabled_when_threshold_above_one():
    """rescue_conf > 1.0 disables the rule (pure duration filtering)."""
    agg = TrackAggregator(make_config(min_segment_rescue_conf=1.1))
    for ts in (0.0, 0.33, 0.64):
        agg.accumulate(ts, True, 0.9, track_id=1)
    assert agg.finalize() == []
