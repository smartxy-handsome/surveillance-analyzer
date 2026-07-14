from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from src.detection.yolo_detector import YOLOv8Detector
from src.detection.classifier import PersonClassifier


def _make_mock_result(has_person: bool, conf: float = 0.9):
    result = MagicMock()
    if has_person:
        box = MagicMock()
        box.cls = [MagicMock(__float__=lambda self: 0.0)]  # class 0 = person
        box.conf = [MagicMock(__float__=lambda self: conf)]
        box.xyxy = [MagicMock(cpu=MagicMock(numpy=MagicMock(return_value=np.array([10, 20, 100, 200]))))]
        result.boxes = [box]
    else:
        result.boxes = []
    return result


@patch("src.detection.yolo_detector.YOLO")
def test_load_model(mock_yolo_cls):
    mock_model = MagicMock()
    mock_yolo_cls.return_value = mock_model

    detector = YOLOv8Detector(model_name="yolov8n.pt", device="cuda:0", target_classes=[0])
    detector.load()

    mock_yolo_cls.assert_called_once_with("yolov8n.pt")


@patch("src.detection.yolo_detector.YOLO")
def test_detect_person_present(mock_yolo_cls):
    mock_model = MagicMock()
    mock_yolo_cls.return_value = mock_model
    mock_result = _make_mock_result(True, 0.85)
    mock_model.predict.return_value = [mock_result]

    detector = YOLOv8Detector(model_name="yolov8n.pt", device="cuda:0", target_classes=[0])
    detector.load()
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    results = detector.detect([frame])

    assert len(results) == 1
    assert results[0].has_person is True
    assert results[0].confidence == pytest.approx(0.85)


@patch("src.detection.yolo_detector.YOLO")
def test_detect_no_person(mock_yolo_cls):
    mock_model = MagicMock()
    mock_yolo_cls.return_value = mock_model
    mock_result = _make_mock_result(False)
    mock_model.predict.return_value = [mock_result]

    detector = YOLOv8Detector(model_name="yolov8n.pt", device="cuda:0", target_classes=[0])
    detector.load()
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    results = detector.detect([frame])

    assert len(results) == 1
    assert results[0].has_person is False
    assert results[0].confidence == 0.0


@patch("src.detection.yolo_detector.YOLO")
def test_detect_batch(mock_yolo_cls):
    mock_model = MagicMock()
    mock_yolo_cls.return_value = mock_model
    mock_model.predict.return_value = [
        _make_mock_result(True, 0.9),
        _make_mock_result(False),
        _make_mock_result(True, 0.7),
    ]

    detector = YOLOv8Detector(model_name="yolov8n.pt", device="cuda:0", target_classes=[0])
    detector.load()
    frames = [np.zeros((1080, 1920, 3), dtype=np.uint8) for _ in range(3)]
    results = detector.detect(frames)

    assert len(results) == 3
    assert results[0].has_person is True
    assert results[1].has_person is False
    assert results[2].has_person is True


@patch("src.detection.yolo_detector.YOLO")
def test_detect_below_threshold(mock_yolo_cls):
    mock_model = MagicMock()
    mock_yolo_cls.return_value = mock_model
    # Person detected with confidence 0.3, threshold is 0.5
    mock_result = _make_mock_result(True, 0.3)
    mock_model.predict.return_value = [mock_result]

    detector = YOLOv8Detector(
        model_name="yolov8n.pt", device="cuda:0", target_classes=[0], confidence_threshold=0.5
    )
    detector.load()
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    results = detector.detect([frame])

    assert results[0].has_person is False


def test_classifier_person_present():
    from src.core.interfaces import FrameDetection

    classifier = PersonClassifier(confidence_threshold=0.5)
    det = FrameDetection(has_person=True, confidence=0.9, boxes=[(10, 20, 100, 200)])
    assert classifier.classify(det) is True


def test_classifier_no_person():
    from src.core.interfaces import FrameDetection

    classifier = PersonClassifier(confidence_threshold=0.5)
    det = FrameDetection(has_person=False, confidence=0.0, boxes=[])
    assert classifier.classify(det) is False
