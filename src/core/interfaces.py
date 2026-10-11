from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class VideoMetadata:
    path: str
    total_frames: int
    fps: float
    width: int
    height: int
    duration_seconds: float


@dataclass
class FrameDetection:
    has_person: bool
    confidence: float
    boxes: list[tuple[int, int, int, int]]  # (x1, y1, x2, y2)
    # Per-box tracker identity from ByteTrack, parallel to `boxes`. Empty when
    # the detector runs without tracking (legacy boolean aggregation path).
    track_ids: list[int] = field(default_factory=list)
    # Per-box COCO class id, parallel to `boxes`. Empty means "all person"
    # (legacy single-target mode). Person dispatch uses class 0; the vehicle
    # path consumes classes 2/5/7 (car/bus/truck).
    class_ids: list[int] = field(default_factory=list)


@dataclass
class FrameData:
    index: int
    timestamp: float
    image: np.ndarray


class FrameReader(ABC):
    @abstractmethod
    def open(self, path: str) -> VideoMetadata:
        ...

    @abstractmethod
    def read_frame(self, index: int) -> tuple[bool, np.ndarray | None]:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


class DetectionEngine(ABC):
    @abstractmethod
    def load(self) -> None:
        ...

    @abstractmethod
    def detect(self, frames: list[np.ndarray]) -> list[FrameDetection]:
        ...

    @abstractmethod
    def unload(self) -> None:
        ...
