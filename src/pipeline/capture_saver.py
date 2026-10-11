from pathlib import Path

import cv2
import numpy as np

from src.core.config import DATA_DIR
from src.core.models import CaptureResult, PlateResult, SegmentCaptureData, VehicleEventData


class CaptureSaver:
    """Saves cropped person images and annotated frames to disk."""

    def __init__(self, output_dir: str):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def save_segment_captures(self, data: SegmentCaptureData) -> list[CaptureResult]:
        """Save all capture candidates for a segment.

        Args:
            data: SegmentCaptureData with candidates to save

        Returns:
            List of CaptureResult with paths to saved files
        """
        results = []

        for i, candidate in enumerate(data.candidates):
            timestamp_str = f"{candidate.timestamp:.1f}s"
            kind = "departure" if i > 0 else "appearance"

            # Save annotated full frame
            annotated_name = (
                f"seg{data.segment_index}_{i:02d}_{timestamp_str}_annotated.jpg"
            )
            annotated_path = self._output_dir / annotated_name
            self._save_annotated(candidate.image, candidate.boxes, annotated_path)

            # Save cropped person regions
            crop_base = f"seg{data.segment_index}_{i:02d}_{timestamp_str}_crop"
            crop_paths = self._save_crops(candidate.image, candidate.boxes, crop_base)

            # Use the first crop path as the primary crop path
            primary_crop_path = crop_paths[0] if crop_paths else ""

            results.append(
                CaptureResult(
                    segment_index=data.segment_index,
                    timestamp=candidate.timestamp,
                    confidence=candidate.confidence,
                    crop_path=str(primary_crop_path),
                    annotated_path=str(annotated_path),
                    kind=kind,
                )
            )

        return results

    def save_vehicle_event(
        self, event: VehicleEventData, recognizer=None
    ) -> tuple[list[CaptureResult], PlateResult | None]:
        """Save a vehicle's three captures: appearance, departure, plate.

        Appearance/departure crop the vehicle box and annotate the full
        frame. The plate capture crops the largest-box-area frame's vehicle
        region and, when a recognizer is provided, the plate inside it;
        recognition failure keeps the image and leaves the number empty.
        """
        results: list[CaptureResult] = []
        enter = event.enter_candidate
        exit = event.exit_candidate or event.enter_candidate
        for kind, cand in (("appearance", enter), ("departure", exit)):
            if cand is None:
                continue
            base = f"evt{event.ordinal}_{kind}_{cand.timestamp:.1f}s"
            annotated_path = self._output_dir / f"{base}_annotated.jpg"
            self._save_annotated(cand.image, cand.boxes, annotated_path)
            crop_paths = self._save_crops(cand.image, cand.boxes, base)
            results.append(
                CaptureResult(
                    segment_index=event.ordinal,
                    timestamp=cand.timestamp,
                    confidence=cand.confidence,
                    crop_path=str(crop_paths[0]) if crop_paths else "",
                    annotated_path=str(annotated_path),
                    kind=kind,
                )
            )

        plate_result: PlateResult | None = None
        plate_cand = event.plate_candidate or enter
        if plate_cand is not None:
            base = f"evt{event.ordinal}_plate_{plate_cand.timestamp:.1f}s"
            vehicle_crop = _crop_first_box(plate_cand.image, plate_cand.boxes)
            if vehicle_crop is not None:
                plate_path = self._output_dir / f"{base}.jpg"
                if recognizer is not None:
                    plate_result = recognizer.recognize(vehicle_crop)
                    if plate_result is not None and plate_result.plate_box is not None:
                        vehicle_crop = _crop_with_margin(vehicle_crop, plate_result.plate_box)
                cv2.imwrite(str(plate_path), vehicle_crop)
                results.append(
                    CaptureResult(
                        segment_index=event.ordinal,
                        timestamp=plate_cand.timestamp,
                        confidence=plate_cand.confidence,
                        crop_path=str(plate_path),
                        annotated_path="",
                        kind="plate",
                    )
                )
        return results, plate_result

    def _save_crops(
        self,
        frame: np.ndarray,
        boxes: list[tuple[int, int, int, int]],
        base_name: str,
    ) -> list[Path]:
        """Crop person regions and save as separate files.

        Args:
            frame: Full video frame
            boxes: List of bounding boxes (x1, y1, x2, y2)
            base_name: Base filename without extension

        Returns:
            List of paths to saved crop files
        """
        paths = []
        for j, (x1, y1, x2, y2) in enumerate(boxes):
            # Ensure coordinates are within frame bounds
            h, w = frame.shape[:2]
            x1 = max(0, min(x1, w))
            y1 = max(0, min(y1, h))
            x2 = max(0, min(x2, w))
            y2 = max(0, min(y2, h))

            # Crop the person region
            crop = frame[y1:y2, x1:x2]

            # Save the crop
            path = self._output_dir / f"{base_name}_p{j}.jpg"
            cv2.imwrite(str(path), crop)
            paths.append(path)

        return paths

    def _save_annotated(
        self,
        frame: np.ndarray,
        boxes: list[tuple[int, int, int, int]],
        path: Path,
    ) -> None:
        """Draw bounding boxes on frame and save.

        Args:
            frame: Full video frame
            boxes: List of bounding boxes (x1, y1, x2, y2)
            path: Output file path
        """
        annotated = frame.copy()

        # Draw bounding boxes
        for x1, y1, x2, y2 in boxes:
            # Green rectangle
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Save the annotated frame
        cv2.imwrite(str(path), annotated)


def get_capture_output_dir(video_path: str, job_id: str) -> str:
    """Generate output directory path for a job's captures.

    Captures live under data/captures/{job_id}/ instead of next to the video:
    the source directory may be read-only, polluting it is unfriendly, and
    keying by job_id lets job deletion clean up with a single rmtree.
    """
    return str(DATA_DIR / "captures" / job_id)


def _crop_first_box(image: np.ndarray, boxes: list[tuple[int, int, int, int]]) -> np.ndarray | None:
    """Crop the largest box region from the frame."""
    if not boxes:
        return None
    h, w = image.shape[:2]
    x1, y1, x2, y2 = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    x1, y1 = max(0, min(x1, w)), max(0, min(y1, h))
    x2, y2 = max(0, min(x2, w)), max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


def _crop_with_margin(
    image: np.ndarray, box: tuple[int, int, int, int], margin: float = 0.1
) -> np.ndarray:
    """Re-crop inside `image` with a relative margin around `box`."""
    h, w = image.shape[:2]
    x1, y1, x2, y2 = box
    mx, my = int((x2 - x1) * margin), int((y2 - y1) * margin)
    x1, y1 = max(0, x1 - mx), max(0, y1 - my)
    x2, y2 = min(w, x2 + mx), min(h, y2 + my)
    if x2 <= x1 or y2 <= y1:
        return image
    return image[y1:y2, x1:x2]
