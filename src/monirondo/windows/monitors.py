import ctypes as C
import hashlib
import logging
import uuid
from ctypes import wintypes as W

import win32api

from monirondo.models import MonitorInfo, Rect
from monirondo.windows.native import DisplayMode, DisplayPath, SourceName, TargetName, bind, user32

log = logging.getLogger(__name__)
SESSION_ID = uuid.uuid4().hex


def display_names() -> dict[str, list[tuple[str, str]]]:
    sizes = bind(user32, "GetDisplayConfigBufferSizes", W.LONG, W.UINT, C.POINTER(W.UINT), C.POINTER(W.UINT))
    query = bind(user32, "QueryDisplayConfig", W.LONG, W.UINT, C.POINTER(W.UINT), C.POINTER(DisplayPath),
                 C.POINTER(W.UINT), C.POINTER(DisplayMode), C.c_void_p)
    info = bind(user32, "DisplayConfigGetDeviceInfo", W.LONG, C.c_void_p)
    for _ in range(4):
        pc, mc = W.UINT(), W.UINT()
        code = sizes(2, C.byref(pc), C.byref(mc))
        if code:
            raise OSError(code, "GetDisplayConfigBufferSizes")
        paths, modes = (DisplayPath * pc.value)(), (DisplayMode * mc.value)()
        code = query(2, C.byref(pc), paths, C.byref(mc), modes, None)
        if code == 122:
            continue
        if code:
            raise OSError(code, "QueryDisplayConfig")
        result: dict[str, list[tuple[str, str]]] = {}
        for p in paths[:pc.value]:
            source, target = SourceName(), TargetName()
            source.header.type, source.header.size = 1, C.sizeof(source)
            source.header.adapter, source.header.id = p.source.adapter, p.source.id
            target.header.type, target.header.size = 2, C.sizeof(target)
            target.header.adapter, target.header.id = p.target.adapter, p.target.id
            if info(C.byref(source)) == 0 and info(C.byref(target)) == 0:
                result.setdefault(source.name, []).append((target.path, target.friendly))
        return result
    raise OSError("Monitor layout keeps changing; please try again")


class MonitorService:
    def enumerate(self) -> list[MonitorInfo]:
        try:
            names = display_names()
        except OSError as exc:
            log.warning("display_identity_unavailable code=%s", getattr(exc, "winerror", exc.errno))
            names = {}
        result: list[MonitorInfo] = []
        for handle, _, _ in win32api.EnumDisplayMonitors():
            info = win32api.GetMonitorInfo(int(handle))
            device = str(info["Device"])
            bounds, work = Rect(*info["Monitor"]), Rect(*info["Work"])
            if bounds.width <= 0 or bounds.height <= 0 or any(m.bounds == bounds for m in result):
                continue  # Clone paths represent one logical desktop area.
            devices = names.get(device, [])
            paths = sorted({p.casefold() for p, _ in devices if p})
            stable = bool(paths) and len(paths) == len(devices)
            identity = "display:" + hashlib.sha256("|".join(paths).encode()).hexdigest() if stable else f"session:{SESSION_ID}:{device}"
            name = " / ".join(dict.fromkeys(n for _, n in devices if n)) or device
            dpi: int | None = None
            try:
                shcore = C.WinDLL("shcore")
                get_dpi = bind(shcore, "GetDpiForMonitor", W.LONG, W.HMONITOR, C.c_int,
                               C.POINTER(W.UINT), C.POINTER(W.UINT))
                x, y = W.UINT(), W.UINT()
                if get_dpi(int(handle), 0, C.byref(x), C.byref(y)) == 0:
                    dpi = x.value
            except (OSError, AttributeError):
                pass
            result.append(MonitorInfo(identity, device, name, bounds, work, bool(info["Flags"] & 1), dpi, stable))
        return sorted(result, key=lambda m: (*m.bounds.center, m.id))
