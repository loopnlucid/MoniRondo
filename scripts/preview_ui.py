"""Offscreen visual QA for every UI language; no hotkeys or native window movements.

Usage: python scripts/preview_ui.py [language ...]   (default: all supported languages)
Screenshots are written to artifacts/preview/<language>/.
"""
import os
import sys
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from monirondo.config import Configuration
from monirondo.hotkeys import hotkey_label
from monirondo.i18n import SUPPORTED, set_language, tr
from monirondo.models import MonitorInfo, Rect
from monirondo.ui.action_editor import ActionEditor
from monirondo.ui.main_window import STYLE, MainWindow

app = QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeuib.ttf')
QFontDatabase.addApplicationFont('C:/Windows/Fonts/seguisym.ttf')
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
layout = [MonitorInfo(str(i), f'DISPLAY{i + 1}', name, bounds, bounds, i == 1, dpi)
          for i, (name, bounds, dpi) in enumerate([
              ('Dell UltraSharp', Rect(-1920, 0, 0, 1080), 96),
              ('LG UltraFine', Rect(0, 0, 2560, 1440), 144),
              ('Samsung Portrait', Rect(2560, -300, 3640, 1620), 120),
          ])]

for language in sys.argv[1:] or SUPPORTED:
    set_language(language)
    output = Path('artifacts/preview') / language
    output.mkdir(parents=True, exist_ok=True)
    config = Configuration()
    config.app.language = language
    window = MainWindow(config)
    window.monitors = layout
    window.diagram.monitors = layout
    window.monitor_table.setRowCount(3)
    for i, m in enumerate(layout):
        for j, text in enumerate([str(i + 1) + (f" · {tr('monitors.primary')}" if m.primary else ''), m.name,
                                  f'{m.bounds.width} × {m.bounds.height}', f'{round(m.dpi / 96 * 100)} %',
                                  tr('monitors.stable')]):
            window.monitor_table.setItem(i, j, QTableWidgetItem(text))
    window.action_table.setRowCount(3)
    for i, a in enumerate(config.actions):
        for j, text in enumerate([a.name, tr(f'actions.type.{a.type}'), tr('actions.assignment.spatial'),
                                  hotkey_label(a.hotkey), tr('actions.status.ready')]):
            window.action_table.setItem(i, j, QTableWidgetItem(text))
    window.show()
    for i, name in enumerate(['monitors', 'actions', 'general', 'diagnostics']):
        window.tabs.setCurrentIndex(i)
        app.processEvents()
        window.grab().save(str(output / f'{name}.png'))
    dialog = ActionEditor(layout)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(output / 'editor.png'))
    dialog.close()
    window.allow_close = True
    window.close()
    print(output)
