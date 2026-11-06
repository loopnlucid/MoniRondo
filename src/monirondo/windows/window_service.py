import ctypes as C
import logging
import os
import time
from ctypes import wintypes as W
from dataclasses import dataclass
from pathlib import PureWindowsPath

import pywintypes
import win32api
import win32con
import win32gui
import win32process

from monirondo.geometry import (
    assign_monitor,
    outer_rect_for_visible,
    placement_rect_to_screen,
    screen_rect_to_placement,
)
from monirondo.models import MonitorInfo, Move, Placement, Rect, WindowSnapshot, WindowState
from monirondo.windows.native import (
    NativePlacement,
    close_handle,
    get_attribute,
    get_dpi_awareness,
    get_process_times,
    get_window_dpi,
    get_window_dpi_context,
    is_zoomed,
    open_process,
    process_session,
    query_process_name,
    set_placement,
    set_window_pos,
)
from monirondo.windows.virtual_desktops import VirtualDesktopManager

log = logging.getLogger(__name__)
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "DV2ControlHost",
                 "Windows.UI.Core.CoreWindow", "MultitaskingViewFrame", "XamlExplorerHostIslandWindow",
                 "tooltips_class32", "SysShadow", "#32768", "TaskManagerWindow"}


@dataclass
class _Settling:
    move: Move
    submitted: float
    dpi_change: bool
    needs_target_dpi: bool
    stable_since: float
    shape: tuple[Rect, Rect | None] | None = None
    dpi_since: float | None = None
    corrections: int = 0
    done: bool = False


def process_info(pid: int) -> tuple[int, str] | None:
    handle = open_process(0x1000, False, pid)
    if not handle:
        return None
    try:
        created, exited, kernel, user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
        if not get_process_times(handle, C.byref(created), C.byref(exited), C.byref(kernel), C.byref(user)):
            return None
        name, size = C.create_unicode_buffer(32768), W.DWORD(32768)
        if not query_process_name(handle, 0, name, C.byref(size)):
            return None
        return (created.dwHighDateTime << 32) | created.dwLowDateTime, name.value
    finally:
        close_handle(handle)


class WindowService:
    """Create and close on the same worker thread (COM apartment affinity)."""

    def __init__(self, include_minimized: bool = True, excluded: list[str] | None = None,
                 include_own: bool = False) -> None:
        self.include_minimized = include_minimized
        self.excluded = {s.casefold() for s in (excluded or [])}
        self.include_own = include_own  # Only integration tests opt in to own test HWNDs.
        self.move_started: dict[int, float] = {}
        self.desktop = VirtualDesktopManager()
        session = W.DWORD()
        if not process_session(os.getpid(), C.byref(session)):
            raise C.WinError()
        self.session = session.value

    def snapshot(self, hwnd: int, monitors: list[MonitorInfo], z_index: int = 0) -> WindowSnapshot | None:
        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return None
            thread, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == os.getpid() and not self.include_own:
                return None
            session = W.DWORD()
            if not process_session(pid, C.byref(session)) or session.value != self.session:
                return None
            cls = win32gui.GetClassName(hwnd)
            if not cls or cls in SHELL_CLASSES:
                return None
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
            tool = bool(ex & win32con.WS_EX_TOOLWINDOW)
            if ex & 0x08000000 or (tool and not (owner and style & win32con.WS_CAPTION)):
                return None
            cloaked = W.DWORD()
            if get_attribute(hwnd, 14, C.byref(cloaked), C.sizeof(cloaked)) != 0 or cloaked.value:
                return None
            # Fail closed when virtual-desktop membership cannot be confirmed.
            if self.desktop.is_current(hwnd) is not True:
                return None
            proc = process_info(pid)
            if proc is None:
                return None
            created, executable = proc
            if executable.casefold() in self.excluded or PureWindowsPath(executable).name.casefold() in self.excluded:
                return None
            flags, show, minimum, maximum, normal = win32gui.GetWindowPlacement(hwnd)
            state = WindowState.MINIMIZED if win32gui.IsIconic(hwnd) else (
                WindowState.MAXIMIZED if is_zoomed(hwnd) else WindowState.NORMAL)
            if state == WindowState.MINIMIZED and not self.include_minimized:
                return None
            rect = Rect(*win32gui.GetWindowRect(hwnd))
            frame = W.RECT()
            visible_rect = None
            if state == WindowState.NORMAL and get_attribute(hwnd, 9, C.byref(frame), C.sizeof(frame)) == 0:
                candidate = Rect(frame.left, frame.top, frame.right, frame.bottom)
                if candidate.width > 0 and candidate.height > 0:
                    visible_rect = candidate
            # MonitorFromWindow consults the pre-minimized rectangle for iconic windows.
            handle = win32api.MonitorFromWindow(hwnd, 2)
            device = win32api.GetMonitorInfo(int(handle))["Device"]
            mon = next((m for m in monitors if m.device == device), None)
            if mon is None:
                return None
            normal_rect = placement_rect_to_screen(Rect(*normal), mon, tool)
            mon = assign_monitor(normal_rect if state == WindowState.MINIMIZED else rect, monitors)
            normal_rect = placement_rect_to_screen(Rect(*normal), mon, tool)
            root = win32gui.GetAncestor(hwnd, 3) or hwnd  # GA_ROOTOWNER
            return WindowSnapshot(hwnd, pid, thread, created, cls, mon.id, rect, normal_rect,
                                  Placement(Rect(*normal), show, flags, minimum, maximum), state,
                                  bool(ex & win32con.WS_EX_TOPMOST), tool, owner, root, z_index, visible_rect)
        except (pywintypes.error, OSError, ValueError):
            log.debug("snapshot_skipped hwnd=%x", hwnd)
            return None

    def enumerate(self, monitors: list[MonitorInfo]) -> list[WindowSnapshot]:
        handles: list[int] = []
        def collect(hwnd: int, _: object) -> bool:
            handles.append(hwnd)
            return True
        win32gui.EnumWindows(collect, None)
        result = []
        for index, hwnd in enumerate(handles):
            w = self.snapshot(hwnd, monitors, index)
            if w is not None:
                result.append(w)
        return result

    def foreground(self) -> int:
        return int(win32gui.GetForegroundWindow())

    def restore_focus(self, hwnd: int) -> None:
        if hwnd and self.foreground() != hwnd and win32gui.IsWindow(hwnd):
            try:
                win32gui.SetForegroundWindow(hwnd)
            except pywintypes.error:
                log.info("focus_restore_denied")

    def move(self, move: Move, exact: WindowSnapshot | None = None) -> None:
        w, target, screen = move.before, move.target, move.normal_screen
        self.move_started[w.hwnd] = time.monotonic()
        if w.state == WindowState.NORMAL:
            flags = 0x0004 | 0x0010 | 0x0200 | 0x4000  # NOZORDER, NOACTIVATE, NOOWNERZORDER, ASYNC
            if not set_window_pos(w.hwnd, None, screen.left, screen.top, screen.width, screen.height, flags):
                raise C.WinError()
            return
        placement = exact.placement if exact else w.placement
        normal = placement.normal if exact else screen_rect_to_placement(screen, target, w.tool_window)
        p = NativePlacement()
        p.length, p.flags, p.showCmd = C.sizeof(p), placement.flags | 4, placement.show_cmd
        p.minPosition = W.POINT(*placement.min_position)
        # A source-specific maximized position must not pin the window to its old display.
        p.maxPosition = W.POINT(*(placement.max_position if exact else (-1, -1)))
        p.normal = W.RECT(*normal.tuple())
        if w.state == WindowState.MAXIMIZED:
            # SetWindowPlacement alone updates restore geometry but Windows can keep an
            # already zoomed window on its previous monitor. Move its zoomed frame first,
            # without activation/Z-order changes, then set the mapped restore placement.
            handle = win32api.MonitorFromWindow(w.hwnd, 2)
            source_work = Rect(*win32api.GetMonitorInfo(int(handle))["Work"])
            frame = exact.rect if exact else Rect(
                target.work.left + w.rect.left - source_work.left,
                target.work.top + w.rect.top - source_work.top,
                target.work.right + w.rect.right - source_work.right,
                target.work.bottom + w.rect.bottom - source_work.bottom,
            )
            if not set_window_pos(w.hwnd, None, frame.left, frame.top, frame.width, frame.height,
                                  0x0004 | 0x0010 | 0x0200 | 0x4000):
                raise C.WinError()
        if not set_placement(w.hwnd, C.byref(p)):
            raise C.WinError()

    def wait_after(self, move: Move, monitors: list[MonitorInfo], timeout: float = 0.8) -> WindowSnapshot | None:
        result = self.wait_all([move], monitors, timeout)[0]
        if isinstance(result, Exception):
            raise result
        return result

    def wait_all(self, moves: list[Move], monitors: list[MonitorInfo],
                 timeout: float = 0.8) -> list[WindowSnapshot | Exception | None]:
        """Poll every moved window each round; one refusing app cannot consume other apps' retries."""
        end = time.monotonic() + timeout
        states = []
        for move in moves:
            source = next((m for m in monitors if m.id == move.before.monitor_id), None)
            dpi_change = bool(source and source.dpi and move.target.dpi and source.dpi != move.target.dpi
                              and move.before.state == WindowState.NORMAL)
            context = get_window_dpi_context(move.before.hwnd) if dpi_change else None
            states.append(_Settling(move, getattr(self, 'move_started', {}).get(move.before.hwnd, time.monotonic()),
                                    dpi_change, bool(context and get_dpi_awareness(context) == 2), time.monotonic()))
        results: list[WindowSnapshot | Exception | None] = [None] * len(moves)
        while True:
            for index, state in enumerate(states):
                if isinstance(results[index], Exception):
                    continue
                move = state.move
                try:
                    last = self.snapshot(move.before.hwnd, monitors, move.before.z_index)
                    results[index] = last
                    state.done = False
                    if last and last.identity != move.before.identity:
                        state.done = True
                        continue
                    if not last or last.monitor_id != move.target.id or last.state != move.before.state:
                        continue
                    now = time.monotonic()
                    shape = (last.rect, last.visible_rect)
                    if shape != state.shape:
                        state.stable_since, state.shape = now, shape
                    dpi_ready = not state.needs_target_dpi or get_window_dpi(last.hwnd) == move.target.dpi
                    if dpi_ready:
                        if state.dpi_since is None:
                            state.dpi_since = now
                    else:
                        state.dpi_since = None
                    matches = (last.visible_rect.near(move.target_visible, 4)
                               if move.target_visible is not None and last.visible_rect is not None
                               else last.movement_rect.near(move.normal_screen, 4))
                    if matches:
                        # The first correct rectangle can precede WM_DPICHANGED.
                        # Keep observing through the DPI transition and a quiet period.
                        state.done = not state.dpi_change or (dpi_ready and state.dpi_since is not None
                                      and now - state.submitted >= .15 and now - state.stable_since >= .06
                                      and now - state.dpi_since >= .05)
                    elif (last.state == WindowState.NORMAL and (state.dpi_change or move.target_visible is not None)
                          and dpi_ready and now - state.submitted >= (.05 if state.dpi_change else .02)
                          and now - state.stable_since >= .02 and state.corrections < 2 and now < end):
                        desired = move.normal_screen
                        if move.target_visible is not None:
                            if last.visible_rect is None:
                                continue
                            framed = outer_rect_for_visible(move.target_visible, last.rect, last.visible_rect)
                            if framed is None:  # DWM may still describe a previous frame.
                                continue
                            desired = framed
                        if not set_window_pos(last.hwnd, None, desired.left, desired.top, desired.width, desired.height,
                                              0x0004 | 0x0010 | 0x0200 | 0x4000):
                            raise C.WinError()
                        state.corrections += 1
                        state.stable_since, state.shape = now, None
                        log.info('geometry_corrected hwnd=%x attempt=%d requested=%s previous=%s', last.hwnd,
                                 state.corrections, desired.tuple(), last.rect.tuple())
                except Exception as exc:
                    results[index], state.done = exc, True
            remaining = end - time.monotonic()
            if all(state.done for state in states) or remaining <= 0:
                break
            time.sleep(min(0.015, remaining))
        for state, result in zip(states, results, strict=True):
            log.info('geometry_checked hwnd=%x target=%s actual=%s visible_target=%s visible_actual=%s corrections=%d settled=%s',
                     state.move.before.hwnd, state.move.normal_screen.tuple(),
                     result.movement_rect.tuple() if isinstance(result, WindowSnapshot) else None,
                     state.move.target_visible.tuple() if state.move.target_visible else None,
                     result.visible_rect.tuple() if isinstance(result, WindowSnapshot) and result.visible_rect else None,
                     state.corrections, state.done)
        return results

    def close(self) -> None:
        self.desktop.close()
