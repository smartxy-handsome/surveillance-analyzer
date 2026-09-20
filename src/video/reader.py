import cv2
import numpy as np

from src.core.interfaces import FrameReader, VideoMetadata


class OpenCVFrameReader(FrameReader):
    """Frame reader that decodes sequentially instead of seeking.

    Random ``CAP_PROP_POS_FRAMES`` seeks are unreliable on long-GOP HEVC
    surveillance footage: the decoder lands mid-GOP without its reference
    frames ("Could not find ref with POC") and returns corrupted frames.
    This reader therefore keeps a cursor of the decoder position and moves
    forward with ``grab()``; a backwards request reopens the video and
    decodes from the start, which is the only reliable path.
    """

    def __init__(self):
        self._cap: cv2.VideoCapture | None = None
        self._path: str | None = None
        self._cursor = 0  # index of the next frame the decoder will return

    def open(self, path: str) -> VideoMetadata:
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {path}")
        self._path = path
        self._cursor = 0

        fps = self._cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0.0

        return VideoMetadata(
            path=path,
            total_frames=total_frames,
            fps=fps,
            width=width,
            height=height,
            duration_seconds=duration,
        )

    def read_frame(self, index: int) -> tuple[bool, np.ndarray | None]:
        if self._cap is None:
            raise RuntimeError("No video opened")

        if index < self._cursor:
            # Backwards jump: seeking is unreliable, reopen and decode from the start.
            self._cap.release()
            self._cap = cv2.VideoCapture(self._path)
            if not self._cap.isOpened():
                raise FileNotFoundError(f"Cannot open video: {self._path}")
            self._cursor = 0

        while self._cursor < index:
            if not self._cap.grab():
                return False, None
            self._cursor += 1

        ok, frame = self._cap.read()
        if ok:
            self._cursor += 1
        return ok, frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
