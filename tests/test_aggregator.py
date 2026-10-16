from src.pipeline.segment_aggregator import SegmentAggregator
from src.core.models import AggregationConfig


def test_no_detections():
    agg = SegmentAggregator(AggregationConfig())
    assert agg.finalize() == []


def test_single_detection():
    # min_detections=1 isolates this test from the temporal confirmation rule
    agg = SegmentAggregator(AggregationConfig(min_segment_seconds=0.0, min_detections=1))
    agg.accumulate(1.0, True, 0.9)
    segments = agg.finalize()
    assert len(segments) == 1
    assert segments[0].start_time == 1.0
    assert segments[0].end_time == 1.0
    assert segments[0].detection_count == 1


def test_continuous_detections():
    agg = SegmentAggregator(AggregationConfig(min_segment_seconds=0.0))
    for t in [1.0, 1.5, 2.0, 2.5, 3.0]:
        agg.accumulate(t, True, 0.9)
    segments = agg.finalize()
    assert len(segments) == 1
    assert segments[0].start_time == 1.0
    assert segments[0].end_time == 3.0
    assert segments[0].detection_count == 5


def test_merge_gap():
    # Gap of 1.5s < merge_gap of 2.0s -> should merge
    config = AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=0.0)
    agg = SegmentAggregator(config)
    agg.accumulate(1.0, True, 0.9)
    agg.accumulate(2.5, True, 0.9)
    segments = agg.finalize()
    assert len(segments) == 1


def test_no_merge_large_gap():
    # Gap of 5.0s > merge_gap of 2.0s -> separate segments
    config = AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=0.0, min_detections=1)
    agg = SegmentAggregator(config)
    agg.accumulate(1.0, True, 0.9)
    agg.accumulate(6.0, True, 0.9)
    segments = agg.finalize()
    assert len(segments) == 2


def test_min_segment_filter():
    # Short AND low-confidence segments are discarded; a confident peak is
    # rescued (min_segment_rescue_conf) -- 宁可多截不要漏截.
    config = AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=3.0)
    agg = SegmentAggregator(config)
    agg.accumulate(1.0, True, 0.4)
    agg.accumulate(2.0, True, 0.4)  # segment is 1s long < 3s min, peak < 0.5
    segments = agg.finalize()
    assert len(segments) == 0


def test_min_segment_rescue_keeps_confident_short_segment():
    config = AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=3.0)
    agg = SegmentAggregator(config)
    agg.accumulate(1.0, True, 0.9)
    agg.accumulate(2.0, True, 0.9)  # 1s < 3s min, but peak 0.9 >= 0.5
    segments = agg.finalize()
    assert len(segments) == 1
    assert segments[0].max_confidence == 0.9


def test_min_segment_keeps_long():
    config = AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=1.0)
    agg = SegmentAggregator(config)
    for t in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]:
        agg.accumulate(t, True, 0.9)
    segments = agg.finalize()
    assert len(segments) == 1
    assert segments[0].duration >= 1.0


def test_mixed_detections():
    config = AggregationConfig(merge_gap_seconds=2.0, min_segment_seconds=0.0)
    agg = SegmentAggregator(config)
    agg.accumulate(1.0, True, 0.9)
    agg.accumulate(2.0, False, 0.0)
    agg.accumulate(3.0, True, 0.8)
    segments = agg.finalize()
    # gap from 1.0 to 3.0 is 2.0, which equals merge_gap -> merged
    assert len(segments) == 1


def test_confidence_averaging():
    agg = SegmentAggregator(AggregationConfig(min_segment_seconds=0.0))
    agg.accumulate(1.0, True, 0.6)
    agg.accumulate(2.0, True, 0.8)
    segments = agg.finalize()
    assert segments[0].avg_confidence == 0.7
    assert segments[0].max_confidence == 0.8
