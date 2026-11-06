"""Only the documented IVirtualDesktopManager COM interface; no private desktop APIs."""
import ctypes as C
import uuid
from ctypes import wintypes as W

from monirondo.windows.native import bind


class GUID(C.Structure):
    _fields_ = [("data", C.c_ubyte * 16)]

    @classmethod
    def parse(cls, value: str) -> "GUID":
        return cls((C.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


class VirtualDesktopManager:
    def __init__(self) -> None:
        self.pointer = C.c_void_p()
        self.ole = C.WinDLL("ole32")
        initialize = bind(self.ole, "CoInitializeEx", W.LONG, C.c_void_p, W.DWORD)
        self.initialized = initialize(None, 2) in (0, 1)
        create = bind(self.ole, "CoCreateInstance", W.LONG, C.POINTER(GUID), C.c_void_p,
                      W.DWORD, C.POINTER(GUID), C.POINTER(C.c_void_p))
        clsid = GUID.parse("AA509086-5CA9-4C25-8F95-589D3C07B48A")
        iid = GUID.parse("A5CD92FF-29BE-454C-8D04-D82879FB3F1B")
        self.available = create(C.byref(clsid), None, 1, C.byref(iid), C.byref(self.pointer)) == 0

    def is_current(self, hwnd: int) -> bool | None:
        if not self.available:
            return None
        table = C.cast(self.pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
        method = C.WINFUNCTYPE(W.LONG, C.c_void_p, W.HWND, C.POINTER(W.BOOL))(table[3])
        current = W.BOOL()
        code = method(self.pointer, hwnd, C.byref(current))
        return bool(current.value) if code == 0 else None

    def close(self) -> None:
        if self.pointer:
            table = C.cast(self.pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
            C.WINFUNCTYPE(W.ULONG, C.c_void_p)(table[2])(self.pointer)
            self.pointer = C.c_void_p()
        if self.initialized:
            self.ole.CoUninitialize()
            self.initialized = False
