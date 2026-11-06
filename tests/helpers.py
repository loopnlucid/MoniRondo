from dataclasses import replace

from monirondo.geometry import screen_rect_to_placement
from monirondo.models import MonitorInfo, Move, Placement, Rect, WindowSnapshot, WindowState


def monitors(count=3):
    return [MonitorInfo(str(i), f"DISPLAY{i}", f"Display {i}", Rect((i - 1) * 1920, 0, i * 1920, 1080),
                        Rect((i - 1) * 1920, 40, i * 1920, 1080), i == 1) for i in range(count)]


def window(hwnd, monitor, state=WindowState.NORMAL, **kwargs):
    r = Rect(monitor.work.left + 200, monitor.work.top + 100, monitor.work.left + 700, monitor.work.top + 500)
    return WindowSnapshot(hwnd, 100, 110, 999, "TestWindow", monitor.id, r, r,
                          Placement(screen_rect_to_placement(r, monitor),
                                    {WindowState.NORMAL: 1, WindowState.MAXIMIZED: 3, WindowState.MINIMIZED: 2}[state],
                                    2 if state == WindowState.MINIMIZED else 0), state, **kwargs)


class FakeDisplays:
    def __init__(self, layout):
        self.layout = layout

    def enumerate(self):
        return self.layout.copy()


class FakeWindows:
    def __init__(self, windows):
        self.items = {w.hwnd: w for w in windows}
        self.calls = []
        self.fail = set()
        self.active = 77

    def enumerate(self, monitors):
        return list(self.items.values())

    def snapshot(self, hwnd, monitors, z_index=0):
        return self.items.get(hwnd)

    def foreground(self):
        return self.active

    def restore_focus(self, hwnd):
        self.active = hwnd

    def move(self, move: Move, exact=None):
        if move.before.hwnd in self.fail:
            raise PermissionError("Access denied")
        self.calls.append(move.before.hwnd)
        w = move.before
        if exact:
            self.items[w.hwnd] = exact
        else:
            visible = move.target_visible
            if visible is None and w.visible_rect is not None:
                visible = Rect(move.normal_screen.left + w.visible_rect.left - w.rect.left,
                               move.normal_screen.top + w.visible_rect.top - w.rect.top,
                               move.normal_screen.right + w.visible_rect.right - w.rect.right,
                               move.normal_screen.bottom + w.visible_rect.bottom - w.rect.bottom)
            self.items[w.hwnd] = replace(w, monitor_id=move.target.id, normal_screen=move.normal_screen,
                                        rect=move.normal_screen, visible_rect=visible,
                                        placement=replace(w.placement, normal=screen_rect_to_placement(move.normal_screen, move.target)))

    def wait_after(self, move, monitors, timeout=0.8):
        return self.items.get(move.before.hwnd)

    def wait_all(self, moves, monitors, timeout=0.8):
        return [self.wait_after(move, monitors, timeout) for move in moves]
