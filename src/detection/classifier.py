from src.core.interfaces import FrameDetection


class PersonClassifier:
    def __init__(self, confidence_threshold: float = 0.5):
        self._threshold = confidence_threshold

    def classify(self, detection: FrameDetection) -> bool:
        return detection.has_person and detection.confidence >= self._threshold
