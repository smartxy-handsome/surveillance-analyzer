import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


from src.core.interfaces import DetectionEngine, FrameData, FrameReader
from src.core.models import (
    AggregationConfig,
    DetectionConfig,
    PipelineConfig,
    PipelineResult,
    SamplingConfig,
    SegmentCaptureData,
    TimeSegment,
    VehicleEventData,
)
from src.pipeline.capture_collector import MAX_PLATE_CANDIDATES, SegmentCaptureCollector
from src.pipeline.frame_queue import FrameQueue
from src.pipeline.segment_aggregator import SegmentAggregator
from src.pipeline.track_aggregator import TrackAggregator

# COCO classes routed to the vehicle consumer (car / bus / truck)
VEHICLE_CLASS_IDS = frozenset({2, 5, 7})


def _box_area(boxes: list[tuple[int, int, int, int]]) -> int:
    return max(((x2 - x1) * (y2 - y1) for x1, y1, x2, y2 in boxes), default=0)


class PipelineCoordinator:
    def __init__(
        self,
        reader_factory: Callable[[], FrameReader],
        video_path: str,
        detector: DetectionEngine,
        sampling_config: SamplingConfig,
        detection_config: DetectionConfig,
        aggregation_config: AggregationConfig,
        pipeline_config: PipelineConfig,
        detection_target: str = "person",
    ):
        self._reader_factory = reader_factory
        self._video_path = video_path
        self._detector = detector
        self._sampling = sampling_config
        self._detection = detection_config
        self._aggregation = aggregation_config
        self._pipeline = pipeline_config
        self._detection_target = detection_target

    def run(
        self,
        frame_indices: list[int],
        video_fps: float,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> PipelineResult:
        if not frame_indices:
            return PipelineResult(segments=[], captures=[], dropped_frames=0)

        self._detector.load()
        queue = FrameQueue(maxsize=self._pipeline.frame_queue_size)
        # Tracking mode: segments follow ByteTrack identities (one track = one
        # enter/exit); detections without an id fall back to presence-based
        # grouping inside TrackAggregator. Legacy boolean mode otherwise.
        if self._aggregation.use_tracking:
            aggregator = TrackAggregator(self._aggregation)
        else:
            aggregator = SegmentAggregator(self._aggregation)
        collector = SegmentCaptureCollector()
        # The vehicle path always tracks: per-vehicle enter/exit records are
        # the entire point (person presence stays free to use legacy mode).
        vehicle_agg = (
            TrackAggregator(self._aggregation) if self._detection_target in ("vehicle", "both") else None
        )
        vehicle_collector = SegmentCaptureCollector() if vehicle_agg is not None else None
        stop_event = threading.Event()
        total = len(frame_indices)

        # Split indices into chunks for decode threads
        n_threads = min(self._pipeline.num_decode_threads, len(frame_indices))
        chunks = [[] for _ in range(n_threads)]
        for i, idx in enumerate(frame_indices):
            chunks[i % n_threads].append(idx)

        def decode_worker(indices: list[int]) -> int:
            reader = self._reader_factory()
            dropped = 0
            try:
                reader.open(self._video_path)
                for idx in indices:
                    if stop_event.is_set():
                        break
                    timestamp = idx / video_fps
                    ok, frame = reader.read_frame(idx)
                    if ok and frame is not None:
                        queue.put(FrameData(index=idx, timestamp=timestamp, image=frame))
                    else:
                        dropped += 1
            except Exception:
                # Unblock the other decode thread(s) and make the inference
                # worker see a clean shutdown instead of waiting on a queue
                # whose producer died.
                stop_event.set()
                raise
            finally:
                reader.close()
            return dropped

        def inference_worker() -> None:
            processed = 0
            while True:
                batch = queue.get_batch(batch_size=self._detection.batch_size, timeout=0.5)
                if not batch:
                    # Counting processed frames cannot detect the end when
                    # decoding drops frames (they never enter the queue), so
                    # the exit condition is "decode finished AND queue empty".
                    if queue.is_done():
                        break
                    continue
                images = [f.image for f in batch]
                results = self._detector.detect(images)
                for frame_data, det in zip(batch, results):
                    if not det.has_person:
                        # Still feeds the legacy boolean gap logic its
                        # absence frames.
                        aggregator.accumulate(frame_data.timestamp, False, 0.0)
                        continue

                    # Legacy/mock shape: presence asserted without boxes.
                    # Count it, but there is nothing to crop.
                    if not det.boxes:
                        aggregator.accumulate(frame_data.timestamp, True, det.confidence)
                        continue

                    # Split the frame's boxes by class: person (0) to the
                    # person consumer, vehicles (2/5/7) to the vehicle one.
                    # Missing class_ids mean legacy single-target (person).
                    person_pairs: list[tuple[int | None, tuple]] = []
                    vehicle_pairs: list[tuple[int | None, tuple]] = []
                    for i, box in enumerate(det.boxes):
                        cid = det.class_ids[i] if i < len(det.class_ids) else 0
                        tid = det.track_ids[i] if i < len(det.track_ids) else None
                        if cid == 0:
                            person_pairs.append((tid, box))
                        elif vehicle_agg is not None and cid in VEHICLE_CLASS_IDS:
                            vehicle_pairs.append((tid, box))

                    if person_pairs:
                        if isinstance(aggregator, TrackAggregator):
                            keys = {
                                aggregator.accumulate(
                                    frame_data.timestamp, True, det.confidence, tid, box=box
                                )
                                for tid, box in person_pairs
                            }
                        else:
                            keys = {aggregator.accumulate(frame_data.timestamp, True, det.confidence)}
                        for segment_key in keys:
                            if segment_key is not None:
                                collector.add_candidate(
                                    segment_key=segment_key,
                                    frame_index=frame_data.index,
                                    timestamp=frame_data.timestamp,
                                    confidence=det.confidence,
                                    image=frame_data.image,
                                    boxes=[box for _, box in person_pairs],
                                )
                    else:
                        aggregator.accumulate(frame_data.timestamp, False, 0.0)

                    if vehicle_agg is not None and vehicle_pairs:
                        vkeys = {
                            vehicle_agg.accumulate(
                                frame_data.timestamp, True, det.confidence, tid, box=box
                            )
                            for tid, box in vehicle_pairs
                        }
                        for segment_key in vkeys:
                            if segment_key is not None:
                                vehicle_collector.add_candidate(
                                    segment_key=segment_key,
                                    frame_index=frame_data.index,
                                    timestamp=frame_data.timestamp,
                                    confidence=det.confidence,
                                    image=frame_data.image,
                                    boxes=[box for _, box in vehicle_pairs],
                                )
                processed += len(batch)
                if progress_callback:
                    progress_callback(processed, total)
            # Dropped frames never enter `processed`, so the last per-batch
            # update may leave the bar short of 100%; close it out here.
            if progress_callback:
                progress_callback(total, total)

        # Start threads
        decode_pool = ThreadPoolExecutor(max_workers=n_threads)
        try:
            futures = [decode_pool.submit(decode_worker, chunk) for chunk in chunks]

            inference_thread = threading.Thread(target=inference_worker, daemon=True)
            inference_thread.start()

            try:
                # Wait for decode to finish; re-raises any decode exception here
                dropped_frames = sum(f.result() for f in futures)
            finally:
                # signal_done must fire even when decode raised, or the
                # inference worker would spin forever on an empty queue.
                queue.signal_done()
                # Once done is signalled the worker exits as soon as the queue
                # drains (at most one get_batch timeout later). Join without
                # timeout: a bounded join silently truncated long CPU-bound runs
                # while the thread kept writing to the aggregator.
                inference_thread.join()
        finally:
            decode_pool.shutdown()
            # Unload even on failure, or the model holds GPU memory forever.
            self._detector.unload()

        segments = aggregator.finalize()
        captures = collector.get_all_captures()
        if isinstance(aggregator, TrackAggregator) and aggregator.key_map:
            captures = self._merge_capture_groups(captures, aggregator.key_map)
        captures = self._align_captures_to_segments(captures, segments)

        vehicle_events: list[VehicleEventData] = []
        if vehicle_agg is not None:
            vehicle_events = self._assemble_vehicle_events(vehicle_agg, vehicle_collector)

        return PipelineResult(
            segments=segments,
            captures=captures,
            dropped_frames=dropped_frames,
            vehicle_events=vehicle_events,
        )

    @staticmethod
    def _assemble_vehicle_events(vehicle_agg, vehicle_collector) -> list[VehicleEventData]:
        """Build per-vehicle enter/exit records from the vehicle track path."""
        segments = vehicle_agg.finalize()
        captures = vehicle_collector.get_all_captures()
        if vehicle_agg.key_map:
            captures = PipelineCoordinator._merge_capture_groups(captures, vehicle_agg.key_map)
        cap_by_key = {cap.segment_index: cap for cap in captures}

        events = []
        for ordinal, seg in enumerate(segments, start=1):
            cap = cap_by_key.get(seg.source_key)
            candidates = list(cap.candidates) if cap else []
            events.append(
                VehicleEventData(
                    ordinal=ordinal,
                    enter_time=seg.start_time,
                    exit_time=seg.end_time,
                    detection_count=seg.detection_count,
                    avg_confidence=seg.avg_confidence,
                    max_confidence=seg.max_confidence,
                    enter_candidate=candidates[0] if candidates else None,
                    exit_candidate=candidates[-1] if len(candidates) > 1 else None,
                    plate_candidates=list(cap.plate_candidates) if cap else [],
                )
            )
        return events

    @staticmethod
    def _merge_capture_groups(captures, key_map: dict[int, int]):
        """Fold capture groups whose keys an ID-switch merge absorbed.

        A merged record keeps its appearance (earliest) and departure
        (latest) captures; the intermediate switch-moment captures of the
        absorbed fragment are dropped.
        """
        grouped: dict[int, SegmentCaptureData] = {}
        for cap in captures:
            final_key = key_map.get(cap.segment_index, cap.segment_index)
            if final_key in grouped:
                grouped[final_key].candidates.extend(cap.candidates)
                grouped[final_key].plate_candidates.extend(cap.plate_candidates)
            else:
                grouped[final_key] = SegmentCaptureData(
                    segment_index=final_key,
                    start_time=cap.start_time,
                    end_time=cap.end_time,
                    candidates=list(cap.candidates),
                    plate_candidates=list(cap.plate_candidates),
                )
        merged = []
        for cap in grouped.values():
            cap.candidates.sort(key=lambda c: c.timestamp)
            if len(cap.candidates) > 2:
                cap.candidates = [cap.candidates[0], cap.candidates[-1]]
            cap.plate_candidates.sort(
                key=lambda c: _box_area(c.boxes), reverse=True
            )
            del cap.plate_candidates[MAX_PLATE_CANDIDATES:]
            cap.start_time = cap.candidates[0].timestamp
            cap.end_time = cap.candidates[-1].timestamp
            merged.append(cap)
        return merged

    @staticmethod
    def _align_captures_to_segments(
        captures: list[SegmentCaptureData], segments: list[TimeSegment]
    ) -> list[SegmentCaptureData]:
        """Keep captures only for bursts that survived aggregation, renumbered.

        The collector keys candidates by the aggregator's transient burst/track
        key, and finalize() drops bursts shorter than ``min_segment_seconds``;
        each surviving TimeSegment carries that key in ``source_key``, so the
        join is exact. Captures whose key did not survive belong to a dropped
        burst and are dropped with it — never re-assigned by time overlap,
        which would misattribute them in overlapping (multi-person) segments.
        """
        key_to_ordinal = {
            seg.source_key: ordinal
            for ordinal, seg in enumerate(segments, start=1)
            if seg.source_key is not None
        }
        aligned = []
        for cap in captures:
            ordinal = key_to_ordinal.get(cap.segment_index)
            if ordinal is not None:
                aligned.append(
                    SegmentCaptureData(
                        segment_index=ordinal,
                        start_time=cap.start_time,
                        end_time=cap.end_time,
                        candidates=cap.candidates,
                    )
                )
        return aligned
