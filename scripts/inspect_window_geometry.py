"""Read-only investigation of visible bounds, planned tiles and minimum sizes."""
import ctypes as C
from ctypes import wintypes as W

from monirondo.config import config_path, load_config
from monirondo.models import WindowState
from monirondo.planner import plan_moves
from monirondo.windows.monitors import MonitorService
from monirondo.windows.native import bind, initialize_dpi, user32
from monirondo.windows.window_service import WindowService


class MinMaxInfo(C.Structure):
    _fields_ = [('reserved', W.POINT), ('max_size', W.POINT), ('max_position', W.POINT),
                ('min_track', W.POINT), ('max_track', W.POINT)]


initialize_dpi()
config, _ = load_config(config_path())
layout = MonitorService().enumerate()
service = WindowService(config.app.include_minimized, config.excluded_executables)
send = bind(user32, 'SendMessageTimeoutW', W.LPARAM, W.HWND, W.UINT, W.WPARAM, W.LPARAM,
            W.UINT, W.UINT, C.POINTER(C.c_size_t))
dpi_for_window = bind(user32, 'GetDpiForWindow', W.UINT, W.HWND)
# Microsoft documents this export since Windows 10 1903; resolve optionally
# because older Windows versions need to remain usable for diagnostics.
try:
    is_arranged = bind(user32, 'IsWindowArranged', W.BOOL, W.HWND)
except AttributeError:
    is_arranged = None
try:
    print('Mode:', config.app.geometry_mode)
    for i, m in enumerate(layout):
        print('Display', i, 'work', m.work.tuple(), 'dpi', m.dpi)
    windows = service.enumerate(layout)
    action = next(a for a in config.actions if a.type == 'cycle' and a.enabled)
    moves = {m.before.hwnd: m for m in plan_moves(action, layout, windows, mode=config.app.geometry_mode).moves}
    for index, window in enumerate(windows):
        if window.state != WindowState.NORMAL:
            continue
        info, result = MinMaxInfo(), C.c_size_t()
        success = send(window.hwnd, 0x24, 0, C.addressof(info), 0x23, 120, C.byref(result))
        move = moves.get(window.hwnd)
        print('Window', index, 'display', next(i for i, m in enumerate(layout) if m.id == window.monitor_id),
              'outer', window.rect.tuple(), 'visible', window.visible_rect.tuple() if window.visible_rect else None,
              'min', (info.min_track.x, info.min_track.y) if success else None,
              'dpi', dpi_for_window(window.hwnd),
              'snapped', bool(is_arranged(window.hwnd)) if is_arranged is not None else None,
              'planned_visible', move.target_visible.tuple() if move and move.target_visible else None)
finally:
    service.close()
