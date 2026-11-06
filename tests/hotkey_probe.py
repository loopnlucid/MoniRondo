"""Exercise native message delivery without sending keys or moving user windows."""
import sys
from ctypes import wintypes as W
from types import SimpleNamespace

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from monirondo.app import NativeEvents
from monirondo.models import Hotkey
from monirondo.windows.hotkey_window import HotkeyWindow
from monirondo.windows.native import bind, user32

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
helper = QWidget()
helper.hide()
source = HotkeyWindow()
hwnd = source.hwnd
registry = source.registry
registry.replace('probe', Hotkey(('CTRL', 'ALT', 'SHIFT'), 'F24'))
received = []
source.triggered.connect(received.append, Qt.ConnectionType.QueuedConnection)
events = NativeEvents(SimpleNamespace(refresh_timer=QTimer()))
app.installNativeEventFilter(events)
post = bind(user32, 'PostMessageW', W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
identifier = registry.active['probe'][0]
print('registered', hwnd, identifier, flush=True)
QTimer.singleShot(100, lambda: post(hwnd, 0x0312, identifier, (0x87 << 16) | 7))
QTimer.singleShot(600, app.quit)
app.exec()
source.close()
app.removeNativeEventFilter(events)
helper.close()
print('received', received, flush=True)
sys.exit(0 if received == ['probe'] and source.received_count == 1 else 1)
