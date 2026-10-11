import numpy as np
import torch
from ultralytics import YOLO

from src.core.interfaces import DetectionEngine, FrameDetection


class YOLOv8Detector(DetectionEngine):
    def __init__(
        self,
        model_name: str = "yolov8s.pt",
        device: str = "cuda:0",
        target_classes: list[int] | None = None,
        confidence_threshold: float = 0.5,
        batch_size: int = 8,
        imgsz: int = 1280,
        use_tracker: bool = False,
    ):
        self._model_name = model_name
        self._requested_device = device
        self._device = device
        self._target_classes = target_classes or [0]
        self._confidence_threshold = confidence_threshold
        self._batch_size = batch_size
        self._imgsz = imgsz
        self._use_tracker = use_tracker
        self._model: YOLO | None = None

    def load(self) -> None:
        # A configured CUDA device on a machine without one would make every
        # predict call warn and fall back internally; resolve it once, loudly.
        if self._requested_device.startswith("cuda") and not torch.cuda.is_available():
            print(
                f"warning: device '{self._requested_device}' requested but CUDA is "
                "unavailable; falling back to CPU (expect much slower analysis)"
            )
            self._device = "cpu"
        self._model = YOLO(self._model_name)

    def detect(self, frames: list[np.ndarray]) -> list[FrameDetection]:
        if self._model is None:
            raise RuntimeError("Model not loaded")

        infer = self._model.track if self._use_tracker else self._model.predict
        kwargs = dict(
            conf=self._confidence_threshold,
            classes=self._target_classes,
            imgsz=self._imgsz,
            verbose=False,
        )
        if self._use_tracker:
            # persist=True keeps tracker state across calls so identities
            # survive between batches; frames within a batch are processed
            # in order.
            kwargs["persist"] = True
        results = infer(source=frames, **kwargs)

        detections: list[FrameDetection] = []
        for result in results:
            if len(result.boxes) == 0:
                detections.append(FrameDetection(has_person=False, confidence=0.0, boxes=[]))
                continue

            best_conf = 0.0
            boxes_list = []
            track_ids = []
            class_ids = []
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf < self._confidence_threshold:
                    continue
                best_conf = max(best_conf, conf)
                xyxy = box.xyxy[0].cpu().numpy().astype(int).tolist()
                boxes_list.append(tuple(xyxy))
                if self._use_tracker and box.id is not None:
                    track_ids.append(int(box.id[0]))
                if getattr(box, "cls", None) is not None:
                    class_ids.append(int(box.cls[0]))

            if boxes_list:
                detections.append(
                    FrameDetection(
                        has_person=True,
                        confidence=best_conf,
                        boxes=boxes_list,
                        track_ids=track_ids,
                        class_ids=class_ids,
                    )
                )
            else:
                detections.append(FrameDetection(has_person=False, confidence=0.0, boxes=[]))

        return detections

    def unload(self) -> None:
        self._model = None
