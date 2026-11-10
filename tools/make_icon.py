"""Regenerates okuma_igf_viewer/assets/app.ico from app.svg (needs Pillow)."""

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from PyQt6.QtCore import QBuffer, QIODevice  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from okuma_igf_viewer import icons  # noqa: E402
from okuma_igf_viewer.paths import assets_dir  # noqa: E402

app = QApplication([])
buffer = QBuffer()
buffer.open(QIODevice.OpenModeFlag.WriteOnly)
icons.app_icon().pixmap(256, 256).save(buffer, "PNG")
image = Image.open(io.BytesIO(bytes(buffer.data())))
target = assets_dir() / "app.ico"
image.save(target, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Wrote {target}")
