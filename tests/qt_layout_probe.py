"""Three private Qt tiles and an optional minimum-size blocker, moved by a worker."""

import sys
import time

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from monirondo.engine import SwapEngine
from monirondo.i18n import tr
from monirondo.models import Rect, SwapAction
from monirondo.windows.monitors import MonitorService
from monirondo.windows.native import initialize_dpi, set_window_pos
from monirondo.windows.window_service import WindowService

initialize_dpi()
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
layout = MonitorService().enumerate()
source = max(layout, key=lambda m: m.work.width * m.work.height)
targets = [m for m in layout if m.dpi != source.dpi]
if not targets:
    print('SKIP: no mixed-DPI desktop')
    raise SystemExit(77)
target = min(targets, key=lambda m: m.work.width * m.work.height)
slots = [(0., .5, 0., 1.), (.5, 1., 0., .5), (.5, 1., .5, 1.)]
widgets, handles = [], []
failures = []
blocking_handle = None


def slot_rect(monitor, slot):
    left, right, top, bottom = slot
    w = monitor.work
    return Rect(w.left + round(left * w.width), w.top + round(top * w.height),
                w.left + round(right * w.width), w.top + round(bottom * w.height))


class OurWindows(WindowService):
    def enumerate(self, monitors):
        order = ([blocking_handle] if blocking_handle else []) + handles
        return [w for index, hwnd in enumerate(order)
                if (w := self.snapshot(hwnd, monitors, len(order) - index)) is not None]


class Job(QThread):
    def run(self):
        service = OurWindows(include_own=True)
        try:
            engine, displays = SwapEngine(), MonitorService()
            pair = SwapAction('p', 'Test pair', 'pair', monitor_a_id=source.id, monitor_b_id=target.id)
            undo = SwapAction('u', 'Undo', 'undo')
            # Include both DPI directions, Undo and another full round trip. Check
            # again after Qt has had time to process any late WM_DPICHANGED work.
            for action, destination in [(pair, target), (undo, source), (pair, target), (pair, source)]:
                started = time.monotonic()
                result = engine.run(action, displays, service)
                print(action.type, 'moved', result.moved, 'errors', result.errors,
                      'duration_ms', round((time.monotonic() - started) * 1000), flush=True)
                assert result.moved == 3 + bool(blocking_handle)
                if blocking_handle and destination == target:
                    assert len(result.errors) == 1 and result.errors[0] == tr('engine.geometry_not_kept')
                else:
                    assert not result.errors
                time.sleep(.15)
                for hwnd, slot in zip(handles, slots, strict=True):
                    current = service.snapshot(hwnd, layout)
                    expected = slot_rect(destination, slot)
                    print('expected', expected, 'actual', current.visible_rect if current else None, flush=True)
                    assert current and current.visible_rect and current.visible_rect.near(expected, 4)
        except Exception as exc:
            failures.append(repr(exc))
        finally:
            service.close()


job = Job()


def finish():
    for widget in widgets:
        widget.close()
        widget.deleteLater()
    QTimer.singleShot(80, app.quit)


job.finished.connect(finish)


def place_initial():
    service = OurWindows(include_own=True)
    try:
        for hwnd, slot in zip(handles, slots, strict=True):
            current = service.snapshot(hwnd, layout)
            assert current and current.visible_rect
            visible, outer = current.visible_rect, current.rect
            wanted = slot_rect(source, slot)
            rect = Rect(wanted.left - visible.left + outer.left, wanted.top - visible.top + outer.top,
                        wanted.right + outer.right - visible.right, wanted.bottom + outer.bottom - visible.bottom)
            assert set_window_pos(hwnd, None, rect.left, rect.top, rect.width, rect.height, 0x214)
    except Exception as exc:
        failures.append(repr(exc))
        finish()
    finally:
        service.close()


for index in range(3):
    widget = QWidget()
    widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    widget.setWindowTitle('MonitorSwap DPI layout test')
    panel = QVBoxLayout(widget)
    panel.addWidget(QLabel(f'MonitorSwap test window {index + 1}'))
    widget.show()
    hwnd = int(widget.winId())
    widgets.append(widget)
    handles.append(hwnd)
    assert set_window_pos(hwnd, None, source.work.left + 80, source.work.top + 80, 500, 300, 0x214)
if '--with-blocking-window' in sys.argv:
    # This unrelated app cannot fit on the smaller display at 125 %. It is
    # deliberately processed first, so it previously starved all three tiles.
    blocker = QWidget()
    blocker.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    blocker.setWindowTitle('MonitorSwap minimum size test')
    blocker.setMinimumSize(320, 1000)
    blocker.show()
    widgets.append(blocker)
    blocking_handle = int(blocker.winId())
    assert set_window_pos(blocking_handle, None, source.work.left + 80, source.work.top + 80, 500, 1100, 0x214)
QTimer.singleShot(250, place_initial)
QTimer.singleShot(500, place_initial)
QTimer.singleShot(800, job.start)
app.exec()
print('failures', failures, flush=True)
raise SystemExit(1 if failures else 0)
