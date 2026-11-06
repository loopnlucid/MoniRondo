"""Generate a multi-resolution Windows ICO from the project SVG using Qt."""
import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QIODevice, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

root = Path(__file__).resolve().parents[1]
app = QGuiApplication([])
svg = root / "assets/icon.svg"
renderer = QSvgRenderer(str(svg))
assert renderer.isValid()
images = []
for size in [16, 20, 24, 32, 40, 48, 64, 128, 256]:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    images.append((size, bytes(buffer.data())))
offset = 6 + len(images) * 16
directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
payload = bytearray()
for size, png in images:
    directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
    payload.extend(png)
    offset += len(png)
ico = bytes(directory + payload)
(root / "assets/icon.ico").write_bytes(ico)
resources = root / "src/monirondo/resources"
resources.mkdir(exist_ok=True)
(resources / "icon.ico").write_bytes(ico)
(resources / "icon.svg").write_bytes(svg.read_bytes())
print("MoniRondo icon generated: 16/20/24/32/40/48/64/128/256 px")
