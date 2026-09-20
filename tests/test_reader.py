import cv2
import numpy as np
import pytest

from src.video.reader import OpenCVFrameReader


def _make_numbered_video(path, width=64, height=48, fps=25, n_frames=60):
    """Write an MP4 where frame i encodes i as binary blocks in the blue channel.

    Bit k of i is a white block at x = k*10, y = 0 (10x10 px). Binary block
    patterns survive lossy codecs far better than flat color levels, so tests
    can identify a decoded frame by matching it against the source frames.
    """
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    frames = []
    for i in range(n_frames):
        img = np.zeros((height, width, 3), dtype=np.uint8)
        for bit in range(6):
            if i & (1 << bit):
                img[0:10, bit * 10 : bit * 10 + 10, 0] = 255
        writer.write(img)
        frames.append(img)
    writer.release()
    return str(path), frames


def _identify_frame(frame, frames) -> int:
    """Return the index of the source frame closest to `frame`."""
    diffs = [np.mean(cv2.absdiff(frame, f)) for f in frames]
    return int(np.argmin(diffs))


@pytest.fixture
def numbered_video(tmp_path):
    return _make_numbered_video(tmp_path / "test.mp4")


class TestOpenCVFrameReaderSequentialAccess:
    """read_frame must return the same frame sequential decoding yields at
    that index. Random CAP_PROP_POS_FRAMES seeks corrupt frames on long-GOP
    HEVC surveillance footage (missing POC references), so the reader must
    decode sequentially instead."""

    def test_sequential_forward_reads_match_source_frames(self, numbered_video):
        path, frames = numbered_video
        reader = OpenCVFrameReader()
        reader.open(path)
        try:
            for idx in [0, 1, 2, 12, 13, 25, 59]:
                ok, frame = reader.read_frame(idx)
                assert ok, f"read_frame({idx}) failed"
                assert _identify_frame(frame, frames) == idx
        finally:
            reader.close()

    def test_repeated_read_at_same_index_is_idempotent(self, numbered_video):
        path, frames = numbered_video
        reader = OpenCVFrameReader()
        reader.open(path)
        try:
            ok1, f1 = reader.read_frame(10)
            ok2, f2 = reader.read_frame(10)
            assert ok1 and ok2
            assert _identify_frame(f1, frames) == 10
            assert _identify_frame(f2, frames) == 10
        finally:
            reader.close()

    def test_backwards_read_reopens_and_matches_source(self, numbered_video):
        path, frames = numbered_video
        reader = OpenCVFrameReader()
        reader.open(path)
        try:
            ok1, late = reader.read_frame(30)
            ok2, early = reader.read_frame(5)  # backwards jump
            assert ok1 and ok2
            assert _identify_frame(late, frames) == 30
            assert _identify_frame(early, frames) == 5
        finally:
            reader.close()

    def test_read_past_end_returns_not_ok(self, numbered_video):
        path, _ = numbered_video
        reader = OpenCVFrameReader()
        reader.open(path)
        try:
            ok, frame = reader.read_frame(10_000)
            assert not ok
            assert frame is None
        finally:
            reader.close()
