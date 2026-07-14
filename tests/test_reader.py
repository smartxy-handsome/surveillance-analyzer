from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from src.video.reader import OpenCVFrameReader


def _setup_mock_cv2(mock_cv2):
    """Set up cv2 constants on mock so CAP_PROP_FPS etc. resolve to integers."""
    mock_cv2.CAP_PROP_FPS = 5
    mock_cv2.CAP_PROP_FRAME_COUNT = 7
    mock_cv2.CAP_PROP_FRAME_WIDTH = 3
    mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
    mock_cv2.CAP_PROP_POS_FRAMES = 1


@patch("src.video.reader.cv2")
def test_open_extracts_metadata(mock_cv2):
    _setup_mock_cv2(mock_cv2)
    cap = MagicMock()
    mock_cv2.VideoCapture.return_value = cap
    cap.isOpened.return_value = True
    cap.get.side_effect = lambda prop: {
        5: 30.0,
        7: 300,
        3: 1920,
        4: 1080,
    }.get(prop, 0)

    reader = OpenCVFrameReader()
    meta = reader.open("test.mp4")

    assert meta.total_frames == 300
    assert meta.fps == 30.0
    assert meta.width == 1920
    assert meta.height == 1080
    assert meta.duration_seconds == 10.0


@patch("src.video.reader.cv2")
def test_read_frame_success(mock_cv2):
    _setup_mock_cv2(mock_cv2)
    cap = MagicMock()
    mock_cv2.VideoCapture.return_value = cap
    cap.isOpened.return_value = True
    cap.get.side_effect = lambda prop: {
        5: 30.0, 7: 300, 3: 1920, 4: 1080,
    }.get(prop, 0)
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cap.read.return_value = (True, dummy_frame)

    reader = OpenCVFrameReader()
    reader.open("test.mp4")
    ok, frame = reader.read_frame(10)

    assert ok is True
    assert frame.shape == (1080, 1920, 3)


@patch("src.video.reader.cv2")
def test_read_frame_failure(mock_cv2):
    _setup_mock_cv2(mock_cv2)
    cap = MagicMock()
    mock_cv2.VideoCapture.return_value = cap
    cap.isOpened.return_value = True
    cap.get.side_effect = lambda prop: {
        5: 30.0, 7: 300, 3: 1920, 4: 1080,
    }.get(prop, 0)
    cap.read.return_value = (False, None)

    reader = OpenCVFrameReader()
    reader.open("test.mp4")
    ok, frame = reader.read_frame(999)

    assert ok is False
    assert frame is None


@patch("src.video.reader.cv2")
def test_close_releases_capture(mock_cv2):
    _setup_mock_cv2(mock_cv2)
    cap = MagicMock()
    mock_cv2.VideoCapture.return_value = cap
    cap.isOpened.return_value = True
    cap.get.side_effect = lambda prop: {
        5: 30.0, 7: 300, 3: 1920, 4: 1080,
    }.get(prop, 0)

    reader = OpenCVFrameReader()
    reader.open("test.mp4")
    reader.close()

    cap.release.assert_called_once()
