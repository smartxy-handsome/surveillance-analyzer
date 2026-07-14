from abc import ABC, abstractmethod
from dataclasses import dataclass

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
