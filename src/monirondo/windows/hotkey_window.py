"""Own Win32 recipient for global hotkeys, independent of Qt widget HWND changes."""
import logging
import os
import uuid
from typing import Any

import win32api
import win32con
import win32gui
from PySide6.QtCore import QObject, Signal

from monirondo import APP_NAME
from monirondo.hotkeys import HotkeyRegistry
from monirondo.windows.native import register_hotkey, unregister_hotkey

log = logging.getLogger(__name__)


class HotkeyWindow(QObject):
    triggered = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.received_count = 0
        self.hwnd = 0
        self.module = win32api.GetModuleHandle(None)
        self.class_name = f"{APP_NAME}.Hotkeys.{os.getpid()}.{uuid.uuid4().hex}"
        wc: Any = win32gui.WNDCLASS()  # pywin32 stubs incorrectly mark these writable fields read-only.
        wc.hInstance = self.module
        wc.lpszClassName = self.class_name
        wc.lpfnWndProc = self._window_proc
        self.atom = win32gui.RegisterClass(wc)
        try:
            self.hwnd = win32gui.CreateWindowEx(win32con.WS_EX_TOOLWINDOW, self.class_name, f"{APP_NAME} Hotkeys",
                                               0, 0, 0, 0, 0, 0, 0, self.module, None)
        except Exception:
            win32gui.UnregisterClass(self.atom, self.module)
            raise
        self.registry = HotkeyRegistry(
            lambda i, mods, vk: bool(register_hotkey(self.hwnd, i, mods, vk)),
            lambda i: unregister_hotkey(self.hwnd, i),
        )

    def _window_proc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message == win32con.WM_HOTKEY:
            action = self.registry.action_for(wparam)
            if action:
                self.received_count += 1
                log.info("hotkey_received action=%s", action)
                self.triggered.emit(action)
            return 0
        return int(win32gui.DefWindowProc(hwnd, message, wparam, lparam))

    def close(self) -> None:
        if self.hwnd:
            self.registry.close()
            win32gui.DestroyWindow(self.hwnd)
            self.hwnd = 0
            win32gui.UnregisterClass(self.atom, self.module)
