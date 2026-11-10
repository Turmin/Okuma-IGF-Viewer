import numpy as np
import pytest
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from okuma_igf_viewer import thumbnails


def render(width=400, height=300, shapes=(), gradient=True):
    """A part on the CAD background: grey at the top fading to white at the bottom."""
    image = QImage(width, height, QImage.Format.Format_RGB888)
    for y in range(height):
        level = int(176 + (255 - 176) * min(1.0, y / (height * 0.8))) if gradient else 255
        for x in range(0, width, 1):
            image.setPixelColor(x, y, QColor(level, level, level))
    painter = QPainter(image)
    for kind, x, y, w, h, color in shapes:
        painter.setPen(QPen(QColor(color), 1))
        painter.setBrush(QColor(color))
        (painter.drawEllipse if kind == "ellipse" else painter.drawRect)(x, y, w, h)
    painter.end()
    return image


def jpeg_roundtrip(image, tmp_path):
    file = tmp_path / "part.jpg"
    assert image.save(str(file), "JPG", 90)
    return QImage(str(file))


def corner_levels(image):
    array = thumbnails._to_array(image)
    return array[:3, :3].mean(), array[-3:, -3:].mean(), array[:3, -3:].mean(), array[-3:, :3].mean()


def test_gradient_becomes_white_and_empty_space_is_cropped(tmp_path):
    source = jpeg_roundtrip(render(shapes=[("ellipse", 150, 100, 100, 90, "#5a6068")]), tmp_path)

    result = thumbnails.tidy(source)

    assert result.width() < source.width() / 2 and result.height() < source.height() / 2
    assert all(level > 245 for level in corner_levels(result))
    # the part is still in there, and still dark
    assert thumbnails._to_array(result).min() < 120


def test_part_is_centred_with_even_margins(tmp_path):
    source = jpeg_roundtrip(render(shapes=[("rect", 100, 60, 60, 120, "#444444")]), tmp_path)

    result = thumbnails.tidy(source)
    mask = thumbnails._to_array(result).min(axis=2) < 200
    rows, columns = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))

    assert abs(rows[0] - (result.height() - 1 - rows[-1])) <= 2
    assert abs(columns[0] - (result.width() - 1 - columns[-1])) <= 2


def test_part_that_touches_the_edges_is_not_cut_off(tmp_path):
    # a long thin rod from corner to corner
    source = render(shapes=[("rect", 0, 140, 400, 12, "#505050")])
    source = jpeg_roundtrip(source, tmp_path)

    result = thumbnails.tidy(source)

    assert result.width() == source.width()
    assert result.height() < source.height() / 2


def test_white_background_is_left_white(tmp_path):
    source = jpeg_roundtrip(render(gradient=False, shapes=[("ellipse", 100, 80, 200, 140, "#3a5f9c")]), tmp_path)

    result = thumbnails.tidy(source)

    assert all(level > 245 for level in corner_levels(result))
    assert thumbnails._to_array(result)[..., 2].min() < 200


def test_image_without_object_is_returned_unchanged():
    source = render()

    result = thumbnails.tidy(source)

    assert (result.width(), result.height()) == (source.width(), source.height())


@pytest.mark.parametrize("size", [(0, 0), (4, 4)])
def test_null_and_tiny_images_are_returned_as_is(size):
    image = QImage(*size, QImage.Format.Format_RGB888) if size[0] else QImage()

    assert thumbnails.tidy(image).size() == image.size()


def test_tiny_part_is_not_zoomed_in_beyond_the_minimum_crop(tmp_path):
    source = jpeg_roundtrip(render(shapes=[("ellipse", 20, 20, 30, 30, "#555555")]), tmp_path)

    result = thumbnails.tidy(source)

    assert result.width() >= int(source.width() * thumbnails.MIN_CROP)
    assert result.height() >= int(source.height() * thumbnails.MIN_CROP)
    assert all(level > 245 for level in corner_levels(result))


def test_widen_keeps_the_range_inside_the_image():
    assert thumbnails._widen(-5, 20, 100, 40) == (0, 40)
    assert thumbnails._widen(80, 105, 100, 40) == (60, 100)
    assert thumbnails._widen(10, 90, 100, 40) == (10, 90)
