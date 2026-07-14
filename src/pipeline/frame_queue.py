import queue
import threading

from src.core.interfaces import FrameData


class FrameQueue:
    def __init__(self, maxsize: int = 64):
        self._queue: queue.Queue[FrameData] = queue.Queue(maxsize=maxsize)
        self._done = threading.Event()

    def put(self, item: FrameData, timeout: float = 30.0) -> None:
        self._queue.put(item, timeout=timeout)

    def get_batch(self, batch_size: int, timeout: float = 1.0) -> list[FrameData]:
        batch: list[FrameData] = []
        try:
            batch.append(self._queue.get(timeout=timeout))
        except queue.Empty:
            return batch
        while len(batch) < batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def signal_done(self) -> None:
        self._done.set()

    def is_done(self) -> bool:
        return self._done.is_set()
