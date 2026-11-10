"""Cleans up the 3D thumbnails: flattens the grey background gradient and crops the empty space.

The CAD system renders every part on a vertical grey-to-white gradient with a lot of
empty space around it. On a white card that shows up as a grey band, so the gradient is
divided out (it becomes plain white) and the image is cropped to the part itself.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtGui import QImage

# Columns at the left and right edge that are used to measure the background of each row.
EDGE_FRACTION = 0.03
# The background is a smooth curve over the height. Rows that deviate more than this from it
# (a part reaching the edge) are ignored when the curve is fitted.
CURVE_DEGREE = 5
TOLERANCE = 6.0
# A pixel counts as part of the object when it is darker than this after flattening (0-255).
OBJECT_THRESHOLD = 232
# Empty space kept around the object, as a fraction of its largest side.
MARGIN = 0.06
# The crop is never smaller than this fraction of the image, so a tiny part is not blown up blurry.
MIN_CROP = 0.4
# Images with less object than this fraction of pixels are left alone (nothing to crop to).
MIN_OBJECT_PIXELS = 4


def _to_array(image: QImage) -> np.ndarray:
    rgb = image.convertToFormat(QImage.Format.Format_RGB888)
    width, height, stride = rgb.width(), rgb.height(), rgb.bytesPerLine()
    buffer = np.frombuffer(rgb.constBits().asstring(stride * height), dtype=np.uint8)
    return buffer.reshape(height, stride)[:, : width * 3].reshape(height, width, 3)


def _from_array(pixels: np.ndarray) -> QImage:
    pixels = np.ascontiguousarray(pixels)
    height, width, _ = pixels.shape
    # copy() detaches the QImage from the numpy buffer.
    return QImage(pixels.data, width, height, width * 3, QImage.Format.Format_RGB888).copy()


def _background(pixels: np.ndarray) -> np.ndarray:
    """The background colour of every row. Shape (height, 3).

    Measured at the left and right edge, then replaced by a smooth curve through the rows
    that look like background. A long part that touches both edges would otherwise be
    mistaken for background in the rows it covers.
    """
    height, width, _ = pixels.shape
    edge = max(2, int(width * EDGE_FRACTION))
    samples = np.concatenate([pixels[:, :edge], pixels[:, width - edge :]], axis=1)
    rows = np.median(samples, axis=1)

    position = np.linspace(-1.0, 1.0, height)
    degree = min(CURVE_DEGREE, height - 1)
    keep = np.ones(height, dtype=bool)
    model = rows
    for _ in range(5):
        coefficients = np.polynomial.polynomial.polyfit(position[keep], rows[keep], degree)
        model = np.polynomial.polynomial.polyval(position, coefficients).T
        deviation = np.abs(rows - model).max(axis=1)
        limit = max(TOLERANCE, 3.0 * float(np.median(deviation[keep])))
        closer = deviation <= limit
        if closer.sum() <= degree + 1 or np.array_equal(closer, keep):
            break
        keep = closer
    return model


def flatten(pixels: np.ndarray) -> np.ndarray:
    """Divide out the background so that it becomes white and the object keeps its shading."""
    background = np.maximum(_background(pixels), 1.0)[:, None, :]
    flat = pixels.astype(np.float32) * (255.0 / background)
    return np.clip(flat, 0, 255).astype(np.uint8)


def _object_box(flat: np.ndarray) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the object, right and bottom exclusive. None when there is none."""
    mask = flat.min(axis=2) < OBJECT_THRESHOLD
    if mask.sum() < MIN_OBJECT_PIXELS:
        return None
    columns = np.flatnonzero(mask.sum(axis=0) > 0)
    rows = np.flatnonzero(mask.sum(axis=1) > 0)
    return int(columns[0]), int(rows[0]), int(columns[-1]) + 1, int(rows[-1]) + 1


def _widen(low: int, high: int, size: int, minimum: int) -> tuple[int, int]:
    """Grow the range low..high around its centre to at least `minimum`, staying inside 0..size."""
    missing = minimum - (high - low)
    if missing > 0:
        low -= missing // 2
        high += missing - missing // 2
        if low < 0:
            low, high = 0, high - low
        if high > size:
            low, high = low - (high - size), size
    return max(0, low), min(size, high)


def tidy(image: QImage) -> QImage:
    """The image without its background gradient, cropped to the object. The original on any problem."""
    if image.isNull() or image.width() < 8 or image.height() < 8:
        return image
    try:
        flat = flatten(_to_array(image))
        box = _object_box(flat)
        if box is None:
            return image
        left, top, right, bottom = box
        margin = int(round(max(right - left, bottom - top) * MARGIN)) + 2
        height, width, _ = flat.shape
        left, right = _widen(left - margin, right + margin, width, int(width * MIN_CROP))
        top, bottom = _widen(top - margin, bottom + margin, height, int(height * MIN_CROP))
        return _from_array(flat[top:bottom, left:right])
    except (ValueError, TypeError, RuntimeError):
        return image
