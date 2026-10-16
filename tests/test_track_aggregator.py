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
    agg = TrackAggregator(make_config(min_segment_seconds=0.0, min_detections=1))
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


def test_single_frame_dropped_even_when_confident():
    """Temporal confirmation (user-validated 2026-10-12): one detection is
    one-frame flicker (headlight glints, poles) and never becomes a record."""
    agg = TrackAggregator(make_config())
    agg.accumulate(0.0, True, 0.61, track_id=1)
    assert agg.finalize() == []


def test_two_frames_at_rescue_threshold_kept():
    agg = TrackAggregator(make_config())
    agg.accumulate(0.0, True, 0.61, track_id=1)
    agg.accumulate(0.33, True, 0.61, track_id=1)
    assert len(agg.finalize()) == 1


def test_rescue_disabled_when_threshold_above_one():
    """rescue_conf > 1.0 disables the rule (pure duration filtering)."""
    agg = TrackAggregator(make_config(min_segment_rescue_conf=1.1))
    for ts in (0.0, 0.33, 0.64):
        agg.accumulate(ts, True, 0.9, track_id=1)
    assert agg.finalize() == []


# --- ID-switch record merging -------------------------------------------

BOX_A = (100, 100, 140, 220)  # same body under two IDs
BOX_FAR = (900, 100, 940, 220)  # a different body elsewhere in frame


def test_overlapping_tracks_same_body_merge():
    """Tracker re-IDs a standing person: two overlapping records with
    coincident boxes collapse into one, and key_map reports the absorption."""
    agg = TrackAggregator(make_config())
    for ts in (0.0, 1.0, 2.0, 3.0):
        agg.accumulate(ts, True, 0.8, track_id=1, box=BOX_A)
    for ts in (3.3, 4.0, 5.0):
        agg.accumulate(ts, True, 0.9, track_id=2, box=BOX_A)
    segs = agg.finalize()
    assert len(segs) == 1
    assert segs[0].start_time == 0.0 and segs[0].end_time == 5.0
    assert segs[0].detection_count == 7
    assert agg.key_map == {2: 1}


def test_overlapping_tracks_different_bodies_not_merged():
    """Two real people co-present far apart must stay separate records."""
    agg = TrackAggregator(make_config())
    for ts in (0.0, 1.0, 2.0, 3.0):
        agg.accumulate(ts, True, 0.8, track_id=1, box=BOX_A)
    for ts in (3.3, 4.0, 5.0):
        agg.accumulate(ts, True, 0.9, track_id=2, box=BOX_FAR)
    segs = agg.finalize()
    assert len(segs) == 2
    assert agg.key_map == {}


def test_sequential_tracks_same_spot_small_gap_merge():
    """Track dies and a new one is born at the same position within the gap:
    leave-and-return under a fresh ID is one presence."""
    agg = TrackAggregator(make_config())
    for ts in (0.0, 1.0, 2.0):
        agg.accumulate(ts, True, 0.8, track_id=1, box=BOX_A)
    for ts in (3.3, 4.3):
        agg.accumulate(ts, True, 0.8, track_id=2, box=BOX_A)  # 1.3s gap
    segs = agg.finalize()
    assert len(segs) == 1
    assert segs[0].end_time == 4.3


def test_sequential_tracks_gap_too_long_not_merged():
    agg = TrackAggregator(make_config())
    for ts in (0.0, 1.0, 2.0):
        agg.accumulate(ts, True, 0.8, track_id=1, box=BOX_A)
    for ts in (6.0, 7.0):
        agg.accumulate(ts, True, 0.8, track_id=2, box=BOX_A)  # 4s gap > 2s
    segs = agg.finalize()
    assert len(segs) == 2


def test_merge_disabled_at_zero_iou():
    agg = TrackAggregator(make_config(record_merge_iou=0.0))
    for ts in (0.0, 1.0, 2.0):
        agg.accumulate(ts, True, 0.8, track_id=1, box=BOX_A)
    for ts in (3.3, 4.0, 5.0):
        agg.accumulate(ts, True, 0.9, track_id=2, box=BOX_A)
    assert len(agg.finalize()) == 2


def test_chained_id_switches_collapse_onto_first():
    """A->B->C on the same body: all three become one record keyed by A."""
    agg = TrackAggregator(make_config())
    for ts in (0.0, 1.0):
        agg.accumulate(ts, True, 0.8, track_id=1, box=BOX_A)
    for ts in (2.0, 3.0):
        agg.accumulate(ts, True, 0.8, track_id=2, box=BOX_A)
    for ts in (4.0, 5.0):
        agg.accumulate(ts, True, 0.8, track_id=3, box=BOX_A)
    segs = agg.finalize()
    assert len(segs) == 1
    assert segs[0].source_key == 1
    assert segs[0].detection_count == 6
    assert agg.key_map == {2: 1, 3: 1}


# --- vehicle-path reuse (same aggregator, vehicle track ids) -------------

def test_vehicle_tracks_aggregate_identically():
    """The vehicle consumer reuses TrackAggregator: enter/exit/merge all hold."""
    agg = TrackAggregator(make_config())
    for ts in (0.0, 1.0, 2.0):
        agg.accumulate(ts, True, 0.8, track_id=10, box=(0, 0, 200, 120))
    segs = agg.finalize()
    assert len(segs) == 1
    assert segs[0].start_time == 0.0 and segs[0].end_time == 2.0
