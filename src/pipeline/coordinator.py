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
)
from src.pipeline.capture_collector import SegmentCaptureCollector
from src.pipeline.frame_queue import FrameQueue
from src.pipeline.segment_aggregator import SegmentAggregator
from src.pipeline.track_aggregator import TrackAggregator


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
    ):
        self._reader_factory = reader_factory
        self._video_path = video_path
        self._detector = detector
        self._sampling = sampling_config
        self._detection = detection_config
        self._aggregation = aggregation_config
        self._pipeline = pipeline_config

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
                    # With tracking on, each tracked box joins its own
                    # segment; untracked detections share one fallback key.
                    if det.has_person and det.track_ids:
                        box_by_id = dict(zip(det.track_ids, det.boxes))
                        keys = {
                            aggregator.accumulate(
                                frame_data.timestamp,
                                True,
                                det.confidence,
                                tid,
                                box=box_by_id.get(tid),
                            )
                            for tid in det.track_ids
                        }
                    else:
                        keys = {aggregator.accumulate(frame_data.timestamp, det.has_person, det.confidence)}
                    for segment_key in keys:
                        # Collect candidate frames for capture
                        if det.has_person and segment_key is not None:
                            collector.add_candidate(
                                segment_key=segment_key,
                                frame_index=frame_data.index,
                                timestamp=frame_data.timestamp,
                                confidence=det.confidence,
                                image=frame_data.image,
                                boxes=det.boxes,
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
        return PipelineResult(
            segments=segments, captures=captures, dropped_frames=dropped_frames
        )

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
            else:
                grouped[final_key] = SegmentCaptureData(
                    segment_index=final_key,
                    start_time=cap.start_time,
                    end_time=cap.end_time,
                    candidates=list(cap.candidates),
                )
        merged = []
        for cap in grouped.values():
            cap.candidates.sort(key=lambda c: c.timestamp)
            if len(cap.candidates) > 2:
                cap.candidates = [cap.candidates[0], cap.candidates[-1]]
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
