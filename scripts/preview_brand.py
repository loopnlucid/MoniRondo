"""Render the actual ICO at app and tray sizes on light and dark backgrounds."""
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QImage, QPainter

app = QGuiApplication([])
for font_name in ('segoeui.ttf', 'segoeuib.ttf'):
    QFontDatabase.addApplicationFont(f'C:/Windows/Fonts/{font_name}')
root = Path(__file__).resolve().parents[1]
icon = QIcon(str(root / 'assets/icon.ico'))
assert not icon.isNull()
canvas = QImage(1100, 736, QImage.Format.Format_ARGB32)
canvas.fill(QColor('#f3f6fa'))
painter = QPainter(canvas)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.drawPixmap(54, 42, icon.pixmap(180, 180))
painter.setPen(QColor('#14283d'))
painter.setFont(QFont('Segoe UI', 36, QFont.Weight.Bold))
painter.drawText(QRect(270, 54, 760, 78), Qt.AlignmentFlag.AlignVCenter, 'MoniRondo')
painter.setFont(QFont('Segoe UI', 15))
painter.setPen(QColor('#52647b'))
painter.drawText(274, 159, 'Your windows. One keystroke. Another screen.')
sizes = [16, 20, 24, 32, 40, 48, 64, 128]
for row, (color, ink, caption) in enumerate([('#ffffff', '#52647b', 'Light taskbar'),
                                           ('#172033', '#b7c6da', 'Dark taskbar')]):
    top = 264 + row * 220
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(36, top, 1028, 204, 18, 18)
    painter.setPen(QColor(ink))
    painter.setFont(QFont('Segoe UI', 11))
    painter.drawText(58, top + 30, caption)
    for index, size in enumerate(sizes):
        center = 100 + index * 123
        painter.drawPixmap(center - size // 2, top + 103 - size // 2, icon.pixmap(size, size))
        painter.setFont(QFont('Segoe UI', 10))
        painter.drawText(QRect(center - 42, top + 174, 84, 24), Qt.AlignmentFlag.AlignCenter, f'{size} px')
painter.end()
output = root / 'artifacts/preview/monirondo-icon.png'
output.parent.mkdir(parents=True, exist_ok=True)
assert canvas.save(str(output))
assert icon.pixmap(128, 128).save(str(output.with_name('monirondo.png')))
print(output)
