import cv2
import numpy as np

from src.core.interfaces import FrameReader, VideoMetadata


class OpenCVFrameReader(FrameReader):
    def __init__(self):
        self._cap: cv2.VideoCapture | None = None

    def open(self, path: str) -> VideoMetadata:
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {path}")

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
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self._cap.read()
        return ok, frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
