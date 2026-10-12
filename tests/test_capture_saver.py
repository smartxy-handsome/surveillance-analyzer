import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.core.models import CaptureCandidate, CaptureResult, SegmentCaptureData
from src.pipeline.capture_saver import CaptureSaver


@pytest.fixture
def sample_frame():
    """Create a sample 100x100 RGB frame."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Draw a rectangle to simulate a person
    cv2.rectangle(frame, (10, 10), (50, 50), (255, 0, 0), 2)
    return frame


@pytest.fixture
def sample_boxes():
    """Sample bounding boxes."""
    return [(10, 10, 50, 50)]


@pytest.fixture
def multiple_boxes():
    """Multiple bounding boxes (two people)."""
    return [(10, 10, 40, 40), (60, 60, 90, 90)]


@pytest.fixture
def sample_segment_data(sample_frame, sample_boxes):
    """Sample SegmentCaptureData with 3 candidates."""
    return SegmentCaptureData(
        segment_index=0,
        start_time=5.0,
        end_time=15.0,
        candidates=[
            CaptureCandidate(
                frame_index=100,
                timestamp=5.2,
                confidence=0.95,
                image=sample_frame,
                boxes=sample_boxes,
            ),
            CaptureCandidate(
                frame_index=200,
                timestamp=10.5,
                confidence=0.88,
                image=sample_frame,
                boxes=sample_boxes,
            ),
            CaptureCandidate(
                frame_index=300,
                timestamp=14.8,
                confidence=0.82,
                image=sample_frame,
                boxes=sample_boxes,
            ),
        ],
    )


class TestCaptureSaver:
    def test_save_creates_output_dir(self, sample_segment_data):
        """Should create output directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "captures_test"
            saver = CaptureSaver(str(output_dir))

            results = saver.save_segment_captures(sample_segment_data)

            assert output_dir.exists()
            assert output_dir.is_dir()
            assert len(results) == 3

    def test_save_creates_crop_files(self, sample_segment_data):
        """Should create crop image files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = CaptureSaver(tmpdir)

            results = saver.save_segment_captures(sample_segment_data)

            for result in results:
                assert os.path.exists(result.crop_path)
                # Verify it's a valid image
                img = cv2.imread(result.crop_path)
                assert img is not None

    def test_save_creates_annotated_files(self, sample_segment_data):
        """Should create annotated image files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = CaptureSaver(tmpdir)

            results = saver.save_segment_captures(sample_segment_data)

            for result in results:
                assert os.path.exists(result.annotated_path)
                # Verify it's a valid image
                img = cv2.imread(result.annotated_path)
                assert img is not None

    def test_crop_extracts_person_region(self, sample_frame, sample_boxes):
        """Should crop the person region correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = CaptureSaver(tmpdir)

            segment_data = SegmentCaptureData(
                segment_index=0,
                start_time=0.0,
                end_time=1.0,
                candidates=[
                    CaptureCandidate(
                        frame_index=10,
                        timestamp=0.5,
                        confidence=0.9,
                        image=sample_frame,
                        boxes=sample_boxes,
                    )
                ],
            )

            results = saver.save_segment_captures(segment_data)

            # Load the crop
            crop_img = cv2.imread(results[0].crop_path)
            # Should be 40x40 (from (10,10) to (50,50))
            assert crop_img.shape[0] == 40
            assert crop_img.shape[1] == 40

    def test_annotated_has_bounding_box(self, sample_frame, sample_boxes):
        """Annotated image should have bounding box drawn."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = CaptureSaver(tmpdir)

            segment_data = SegmentCaptureData(
                segment_index=0,
                start_time=0.0,
                end_time=1.0,
                candidates=[
                    CaptureCandidate(
                        frame_index=10,
                        timestamp=0.5,
                        confidence=0.9,
                        image=sample_frame,
                        boxes=sample_boxes,
                    )
                ],
            )

            results = saver.save_segment_captures(segment_data)

            # Load the annotated image
            annotated_img = cv2.imread(results[0].annotated_path)
            # Should be same size as original
            assert annotated_img.shape == sample_frame.shape

    def test_naming_convention(self, sample_segment_data):
        """Files should follow naming convention."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = CaptureSaver(tmpdir)

            results = saver.save_segment_captures(sample_segment_data)

            # Check first result
            crop_name = Path(results[0].crop_path).name
            annotated_name = Path(results[0].annotated_path).name

            assert crop_name.startswith("seg0_00_")
            assert "_crop_p0" in crop_name
            assert crop_name.endswith(".jpg")

            assert annotated_name.startswith("seg0_00_")
            assert "_annotated" in annotated_name
            assert annotated_name.endswith(".jpg")

    def test_multiple_persons_in_frame(self, sample_frame, multiple_boxes):
        """Should create separate crop for each person."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = CaptureSaver(tmpdir)

            segment_data = SegmentCaptureData(
                segment_index=0,
                start_time=0.0,
                end_time=1.0,
                candidates=[
                    CaptureCandidate(
                        frame_index=10,
                        timestamp=0.5,
                        confidence=0.9,
                        image=sample_frame,
                        boxes=multiple_boxes,
                    )
                ],
            )

            results = saver.save_segment_captures(segment_data)

            # Should have 1 result entry
            assert len(results) == 1

            # But there should be 2 crop files (one per person)
            crop_path = Path(results[0].crop_path)
            crop_dir = crop_path.parent
            crop_files = list(crop_dir.glob("*_crop_p*.jpg"))
            assert len(crop_files) == 2

    def test_returns_correct_paths(self, sample_segment_data):
        """Should return CaptureResult with correct paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = CaptureSaver(tmpdir)

            results = saver.save_segment_captures(sample_segment_data)

            for result in results:
                assert isinstance(result, CaptureResult)
                assert result.segment_index == 0
                assert result.timestamp > 0
                assert result.confidence > 0
                assert result.crop_path.endswith(".jpg")
                assert result.annotated_path.endswith(".jpg")


def test_get_capture_output_dir_keyed_by_job_id():
    """Output dir lives under data/captures/{job_id}, not next to the video."""
    from src.pipeline.capture_saver import get_capture_output_dir

    d = get_capture_output_dir(r"D:\videos\footage.mp4", "job-42")
    assert d.replace("\\", "/").endswith("data/captures/job-42")


def _vehicle_event(ordinal=1):
    from src.core.models import CaptureCandidate, VehicleEventData

    frame = np.full((240, 320, 3), 60, dtype=np.uint8)
    cand = CaptureCandidate(
        frame_index=0, timestamp=1.0, confidence=0.9, image=frame, boxes=[(40, 80, 200, 200)]
    )
    return VehicleEventData(
        ordinal=ordinal,
        enter_time=1.0,
        exit_time=3.0,
        detection_count=2,
        avg_confidence=0.9,
        max_confidence=0.9,
        enter_candidate=cand,
        exit_candidate=cand,
        plate_candidates=[cand],
    )


def test_save_vehicle_event_writes_three_kinds():
    """A vehicle event saves appearance + departure + plate captures."""
    from src.pipeline.capture_saver import CaptureSaver

    with tempfile.TemporaryDirectory() as tmpdir:
        saver = CaptureSaver(tmpdir)
        results, plate = saver.save_vehicle_event(_vehicle_event())
        kinds = sorted(r.kind for r in results)
        assert kinds == ["appearance", "departure", "plate"]
        assert plate is None  # no recognizer provided
        for r in results:
            assert Path(r.crop_path).exists()
            if r.kind == "plate":
                assert r.annotated_path == ""
            else:
                assert Path(r.annotated_path).exists()


def test_save_vehicle_event_with_mock_recognizer():
    """A successful plate read tightens the crop around the plate box and is
    returned for DB storage; failure leaves number empty."""
    from src.core.models import PlateResult
    from src.pipeline.capture_saver import CaptureSaver

    class FakeRecognizer:
        def recognize(self, crop):
            h, w = crop.shape[:2]
            return PlateResult(
                number="京A12345",
                confidence=0.97,
                plate_type="blue",
                plate_box=(w // 4, h // 3, w // 2, h // 2),
            )

    with tempfile.TemporaryDirectory() as tmpdir:
        saver = CaptureSaver(tmpdir)
        results, plate = saver.save_vehicle_event(_vehicle_event(), FakeRecognizer())
        assert plate is not None and plate.number == "京A12345"
        plate_row = next(r for r in results if r.kind == "plate")
        assert Path(plate_row.crop_path).exists()


def test_single_frame_event_skips_duplicate_departure():
    """A one-detection event must not write the same image twice."""
    from src.core.models import CaptureCandidate, VehicleEventData

    frame = np.full((120, 160, 3), 90, dtype=np.uint8)
    cand = CaptureCandidate(
        frame_index=0, timestamp=5.0, confidence=0.9, image=frame, boxes=[(10, 20, 100, 100)]
    )
    event = VehicleEventData(
        ordinal=1,
        enter_time=5.0,
        exit_time=5.0,
        detection_count=1,
        avg_confidence=0.9,
        max_confidence=0.9,
        enter_candidate=cand,
        exit_candidate=None,
        plate_candidates=[cand],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        saver = CaptureSaver(tmpdir)
        results, _ = saver.save_vehicle_event(event)
        kinds = sorted(r.kind for r in results)
        assert kinds == ["appearance", "plate"]  # no duplicate departure


def test_plate_recognition_tries_all_candidates_and_keeps_best():
    """Distant plates often read on only one large-area frame: every
    candidate is attempted and the highest-confidence read wins."""
    from src.core.models import CaptureCandidate, PlateResult, VehicleEventData

    frames = [np.full((120, 160, 3), 40 + i * 20, dtype=np.uint8) for i in range(3)]
    cands = [
        CaptureCandidate(
            frame_index=i, timestamp=1.0 + i, confidence=0.9, image=frames[i], boxes=[(10, 20, 110, 100)]
        )
        for i in range(3)
    ]
    event = VehicleEventData(
        ordinal=1,
        enter_time=1.0,
        exit_time=3.0,
        detection_count=3,
        avg_confidence=0.9,
        max_confidence=0.9,
        enter_candidate=cands[0],
        exit_candidate=cands[-1],
        plate_candidates=[cands[2], cands[1], cands[0]],  # largest-area first
    )

    attempts = []

    class FakeRecognizer:
        def recognize(self, crop):
            # identify the frame by brightness
            value = int(crop[0, 0][0])
            attempts.append(value)
            conf = {40: 0.3, 60: 0.2, 80: 0.95}[value]
            return PlateResult(
                number=None if conf < 0.5 else f"PLATE-{value}",
                confidence=conf,
                plate_type="blue",
                plate_box=None,
            )

    with tempfile.TemporaryDirectory() as tmpdir:
        saver = CaptureSaver(tmpdir)
        results, plate = saver.save_vehicle_event(event, FakeRecognizer())

    assert attempts == [80, 60, 40]  # candidates arrive largest-area first
    assert plate is not None and plate.number == "PLATE-80"
    assert plate.confidence == 0.95
