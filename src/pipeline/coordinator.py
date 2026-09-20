import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from src.core.interfaces import DetectionEngine, FrameData, FrameDetection, FrameReader
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
            return PipelineResult(segments=[], captures=[])

        self._detector.load()
        queue = FrameQueue(maxsize=self._pipeline.frame_queue_size)
        aggregator = SegmentAggregator(self._aggregation)
        collector = SegmentCaptureCollector()
        stop_event = threading.Event()
        total = len(frame_indices)

        # Split indices into chunks for decode threads
        n_threads = min(self._pipeline.num_decode_threads, len(frame_indices))
        chunks = [[] for _ in range(n_threads)]
        for i, idx in enumerate(frame_indices):
            chunks[i % n_threads].append(idx)

        def decode_worker(indices: list[int]) -> None:
            reader = self._reader_factory()
            reader.open(self._video_path)
            try:
                for idx in indices:
                    if stop_event.is_set():
                        break
                    timestamp = idx / video_fps
                    ok, frame = reader.read_frame(idx)
                    if ok and frame is not None:
                        queue.put(FrameData(index=idx, timestamp=timestamp, image=frame))
            finally:
                reader.close()

        def inference_worker() -> None:
            processed = 0
            while not (queue.is_done() and processed >= total):
                batch = queue.get_batch(batch_size=self._detection.batch_size, timeout=0.5)
                if not batch:
                    if queue.is_done() and processed >= total:
                        break
                    continue
                images = [f.image for f in batch]
                results = self._detector.detect(images)
                for frame_data, det in zip(batch, results):
                    segment_key = aggregator.accumulate(
                        frame_data.timestamp, det.has_person, det.confidence
                    )
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

        # Start threads
        decode_pool = ThreadPoolExecutor(max_workers=n_threads)
        futures = [decode_pool.submit(decode_worker, chunk) for chunk in chunks]

        inference_thread = threading.Thread(target=inference_worker, daemon=True)
        inference_thread.start()

        # Wait for decode to finish
        for f in futures:
            f.result()
        queue.signal_done()

        # Wait for inference to finish
        inference_thread.join(timeout=300)

        self._detector.unload()
        segments = aggregator.finalize()
        captures = collector.get_all_captures()
        return PipelineResult(segments=segments, captures=captures)
