import numpy as np
from ultralytics import YOLO

from src.core.interfaces import DetectionEngine, FrameDetection


class YOLOv8Detector(DetectionEngine):
    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        device: str = "cuda:0",
        target_classes: list[int] | None = None,
        confidence_threshold: float = 0.5,
        batch_size: int = 8,
    ):
        self._model_name = model_name
        self._device = device
        self._target_classes = target_classes or [0]
        self._confidence_threshold = confidence_threshold
        self._batch_size = batch_size
        self._model: YOLO | None = None

    def load(self) -> None:
        self._model = YOLO(self._model_name)

    def detect(self, frames: list[np.ndarray]) -> list[FrameDetection]:
        if self._model is None:
            raise RuntimeError("Model not loaded")

        results = self._model.predict(
            source=frames,
            conf=self._confidence_threshold,
            classes=self._target_classes,
            verbose=False,
        )

        detections: list[FrameDetection] = []
        for result in results:
            if len(result.boxes) == 0:
                detections.append(FrameDetection(has_person=False, confidence=0.0, boxes=[]))
                continue

            best_conf = 0.0
            boxes_list = []
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf < self._confidence_threshold:
                    continue
                best_conf = max(best_conf, conf)
                xyxy = box.xyxy[0].cpu().numpy().astype(int).tolist()
                boxes_list.append(tuple(xyxy))

            if boxes_list:
                detections.append(
                    FrameDetection(has_person=True, confidence=best_conf, boxes=boxes_list)
                )
            else:
                detections.append(FrameDetection(has_person=False, confidence=0.0, boxes=[]))

        return detections

    def unload(self) -> None:
        self._model = None
