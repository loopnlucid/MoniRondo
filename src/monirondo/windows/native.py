import ctypes as C
from ctypes import wintypes as W
from typing import Any

user32 = C.WinDLL("user32", use_last_error=True)
kernel32 = C.WinDLL("kernel32", use_last_error=True)
dwmapi = C.WinDLL("dwmapi", use_last_error=True)


def bind(dll: C.WinDLL, name: str, restype: object, *args: object) -> Any:
    fn = getattr(dll, name)
    fn.restype = restype
    fn.argtypes = list(args)
    return fn


class LUID(C.Structure):
    _fields_ = [("low", W.DWORD), ("high", W.LONG)]


class Rational(C.Structure):
    _fields_ = [("numerator", W.UINT), ("denominator", W.UINT)]


class PathSource(C.Structure):
    _fields_ = [("adapter", LUID), ("id", W.UINT), ("mode", W.UINT), ("status", W.UINT)]


class PathTarget(C.Structure):
    _fields_ = [("adapter", LUID), ("id", W.UINT), ("mode", W.UINT), ("technology", W.UINT),
                ("rotation", W.UINT), ("scaling", W.UINT), ("refresh", Rational),
                ("scanline", W.UINT), ("available", W.BOOL), ("status", W.UINT)]


class DisplayPath(C.Structure):
    _fields_ = [("source", PathSource), ("target", PathTarget), ("flags", W.UINT)]


class ModeUnion(C.Union):
    _fields_ = [("raw", C.c_byte * 48), ("alignment", C.c_uint64)]


class DisplayMode(C.Structure):
    _fields_ = [("type", W.UINT), ("id", W.UINT), ("adapter", LUID), ("data", ModeUnion)]


class DeviceHeader(C.Structure):
    _fields_ = [("type", W.UINT), ("size", W.UINT), ("adapter", LUID), ("id", W.UINT)]


class SourceName(C.Structure):
    _fields_ = [("header", DeviceHeader), ("name", W.WCHAR * 32)]


class TargetName(C.Structure):
    _fields_ = [("header", DeviceHeader), ("flags", W.UINT), ("technology", W.UINT),
                ("manufacturer", W.WORD), ("product", W.WORD), ("connector", W.UINT),
                ("friendly", W.WCHAR * 64), ("path", W.WCHAR * 128)]


class NativePlacement(C.Structure):
    _fields_ = [("length", W.UINT), ("flags", W.UINT), ("showCmd", W.UINT),
                ("minPosition", W.POINT), ("maxPosition", W.POINT), ("normal", W.RECT)]


set_window_pos = bind(user32, "SetWindowPos", W.BOOL, W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT)
set_placement = bind(user32, "SetWindowPlacement", W.BOOL, W.HWND, C.POINTER(NativePlacement))
get_attribute = bind(dwmapi, "DwmGetWindowAttribute", W.LONG, W.HWND, W.DWORD, C.c_void_p, W.DWORD)
open_process = bind(kernel32, "OpenProcess", W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
close_handle = bind(kernel32, "CloseHandle", W.BOOL, W.HANDLE)
get_process_times = bind(kernel32, "GetProcessTimes", W.BOOL, W.HANDLE, C.POINTER(W.FILETIME),
                         C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME))
query_process_name = bind(kernel32, "QueryFullProcessImageNameW", W.BOOL, W.HANDLE, W.DWORD,
                          W.LPWSTR, C.POINTER(W.DWORD))
process_session = bind(kernel32, "ProcessIdToSessionId", W.BOOL, W.DWORD, C.POINTER(W.DWORD))
register_hotkey = bind(user32, "RegisterHotKey", W.BOOL, W.HWND, C.c_int, W.UINT, W.UINT)
unregister_hotkey = bind(user32, "UnregisterHotKey", W.BOOL, W.HWND, C.c_int)
is_zoomed = bind(user32, "IsZoomed", W.BOOL, W.HWND)
get_window_dpi = bind(user32, "GetDpiForWindow", W.UINT, W.HWND)
get_window_dpi_context = bind(user32, "GetWindowDpiAwarenessContext", C.c_void_p, W.HWND)
get_dpi_awareness = bind(user32, "GetAwarenessFromDpiAwarenessContext", C.c_int, C.c_void_p)


def initialize_dpi() -> None:
    # Must run before QApplication or any HWND is created. Frozen builds have a manifest too.
    fn = bind(user32, "SetProcessDpiAwarenessContext", W.BOOL, C.c_void_p)
    if not fn(C.c_void_p(-4)):
        # ERROR_ACCESS_DENIED means an executable manifest has already set awareness.
        if C.get_last_error() != 5:
            raise C.WinError(C.get_last_error())
