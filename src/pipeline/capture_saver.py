from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from src.core.models import CaptureResult, SegmentCaptureData


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
                )
            )

        return results

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


def get_capture_output_dir(video_path: str) -> str:
    """Generate output directory path for captures.

    Args:
        video_path: Path to the video file

    Returns:
        Path to output directory in same location as video
    """
    video_dir = Path(video_path).parent
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return str(video_dir / f"captures_{timestamp}")
