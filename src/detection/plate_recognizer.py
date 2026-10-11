"""License plate recognition on the vehicle plate close-up.

Backed by HyperLPR3 (mainland blue/green/yellow plus Hong Kong and Macao
plate types). Recognition failure yields an empty number with the
detection confidence -- never a placeholder string (decision 2026-10-11).
"""

import numpy as np

from src.core.models import PlateResult

# hyperlpr3.common.typedef constants, mirrored to avoid importing internals
_PLATE_TYPE_NAMES = {
    -1: "unknown",
    0: "blue",
    1: "yellow_single",
    2: "white_single",
    3: "green",  # 新能源
    4: "black_hk_macao",
    5: "hk_single",
    6: "hk_double",
    7: "macao_single",
    8: "macao_double",
    9: "yellow_double",
}


class PlateRecognizer:
    def __init__(self):
        import hyperlpr3 as lpr3

        self._catcher = lpr3.LicensePlateCatcher()

    def recognize(self, vehicle_crop: np.ndarray) -> PlateResult:
        """Read the plate inside a cropped vehicle image.

        Returns the highest-confidence read; when nothing plate-like is
        found the number is None and confidence 0.0 (the caller still saves
        the close-up image for manual identification).
        """
        try:
            results = self._catcher(vehicle_crop)
        except Exception:
            # OCR backend hiccup must never fail the analysis job
            return PlateResult(number=None, confidence=0.0)
        if not results:
            return PlateResult(number=None, confidence=0.0)

        # hyperlpr3 result: [plate_code, rec_confidence, plate_type, det_box]
        code, conf, plate_type, box = results[0]
        for row in results[1:]:
            if row[1] > conf:
                code, conf, plate_type, box = row[0], row[1], row[2], row[3]
        number = (code or "").strip() or None
        return PlateResult(
            number=number,
            confidence=float(conf),
            plate_type=_PLATE_TYPE_NAMES.get(int(plate_type)),
            plate_box=_sanitize_box(box, vehicle_crop.shape),
        )


def _sanitize_box(box, shape) -> tuple[int, int, int, int] | None:
    try:
        x1, y1, x2, y2 = (int(round(v)) for v in box[:4])
    except (TypeError, ValueError, IndexError):
        return None
    h, w = shape[:2]
    x1, y1 = max(0, min(x1, w)), max(0, min(y1, h))
    x2, y2 = max(0, min(x2, w)), max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)
