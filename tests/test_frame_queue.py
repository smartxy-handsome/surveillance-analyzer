import threading
import time
from src.pipeline.frame_queue import FrameQueue
from src.core.interfaces import FrameData
import numpy as np


def _make_frame(index: int, timestamp: float) -> FrameData:
    return FrameData(index=index, timestamp=timestamp, image=np.zeros((10, 10, 3), dtype=np.uint8))


def test_put_and_get_single():
    q = FrameQueue(maxsize=16)
    q.put(_make_frame(0, 0.0))
    batch = q.get_batch(batch_size=1, timeout=1.0)
    assert len(batch) == 1
    assert batch[0].index == 0


def test_get_batch_respects_size():
    q = FrameQueue(maxsize=16)
    for i in range(5):
        q.put(_make_frame(i, float(i)))
    batch = q.get_batch(batch_size=3, timeout=1.0)
    assert len(batch) == 3


def test_get_batch_returns_available():
    q = FrameQueue(maxsize=16)
    q.put(_make_frame(0, 0.0))
    q.put(_make_frame(1, 1.0))
    batch = q.get_batch(batch_size=10, timeout=0.5)
    assert len(batch) == 2


def test_get_batch_empty_after_done():
    q = FrameQueue(maxsize=16)
    q.signal_done()
    batch = q.get_batch(batch_size=4, timeout=0.1)
    assert len(batch) == 0


def test_backpressure():
    q = FrameQueue(maxsize=2)
    q.put(_make_frame(0, 0.0))
    q.put(_make_frame(1, 1.0))

    blocked = threading.Event()
    released = threading.Event()

    def producer():
        blocked.set()
        q.put(_make_frame(2, 2.0))  # Should block until item consumed
        released.set()

    t = threading.Thread(target=producer)
    t.start()
    blocked.wait(timeout=1.0)
    time.sleep(0.1)
    # Producer should still be blocked
    assert not released.is_set()
    # Consume one to release
    q.get_batch(batch_size=1, timeout=1.0)
    released.wait(timeout=2.0)
    assert released.is_set()
    t.join(timeout=3.0)


def test_is_done():
    q = FrameQueue(maxsize=16)
    assert not q.is_done()
    q.signal_done()
    assert q.is_done()
