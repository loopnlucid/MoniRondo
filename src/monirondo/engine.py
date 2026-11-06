import logging
import threading
import time
from typing import Protocol

from monirondo.i18n import tr
from monirondo.models import (
    MonitorInfo,
    Move,
    SwapAction,
    SwapResult,
    UndoEntry,
    WindowSnapshot,
    WindowState,
)
from monirondo.planner import plan_moves

log = logging.getLogger(__name__)


class Displays(Protocol):
    def enumerate(self) -> list[MonitorInfo]: ...


class Windows(Protocol):
    def enumerate(self, monitors: list[MonitorInfo]) -> list[WindowSnapshot]: ...
    def snapshot(self, hwnd: int, monitors: list[MonitorInfo], z_index: int = 0) -> WindowSnapshot | None: ...
    def foreground(self) -> int: ...
    def restore_focus(self, hwnd: int) -> None: ...
    def move(self, move: Move, exact: WindowSnapshot | None = None) -> None: ...
    def wait_all(self, moves: list[Move], monitors: list[MonitorInfo],
                 timeout: float = 0.8) -> list[WindowSnapshot | Exception | None]: ...


def unchanged(a: WindowSnapshot, b: WindowSnapshot) -> bool:
    return (a.identity == b.identity and a.monitor_id == b.monitor_id and a.state == b.state
            and a.topmost == b.topmost and a.owner == b.owner
            and a.movement_rect.near(b.movement_rect)
            and (a.state != WindowState.MINIMIZED or (a.placement.flags & 2) == (b.placement.flags & 2))
            and (a.state != WindowState.MAXIMIZED or a.rect.near(b.rect)))


class SwapEngine:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.undo_entries: list[UndoEntry] = []
        self.undo_layout: dict[str, MonitorInfo] = {}
        self.stop_requested = threading.Event()

    def run(self, action: SwapAction, displays: Displays, windows: Windows,
            mode: str = "keep_size_fit_if_needed") -> SwapResult:
        if not self.lock.acquire(blocking=False):
            return SwapResult(skipped=1, errors=[tr("engine.busy")])
        foreground = windows.foreground()
        started = time.monotonic()
        try:
            monitors = displays.enumerate()
            if action.type == "undo":
                return self._undo(monitors, displays, windows)
            snapshots = windows.enumerate(monitors)
            plan = plan_moves(action, monitors, snapshots, foreground, mode)
            result = SwapResult()
            submitted: list[Move] = []
            for index, move in enumerate(plan.moves):
                try:
                    if self.stop_requested.is_set():
                        break
                    if displays.enumerate() != monitors:
                        result.skipped += len(plan.moves) - index
                        result.errors.append(tr("engine.layout_changed"))
                        break
                    current = windows.snapshot(move.before.hwnd, monitors, move.before.z_index)
                    if not current or not unchanged(move.before, current):
                        result.skipped += 1
                        continue
                    windows.move(move)
                    submitted.append(move)
                except Exception as exc:
                    log.warning("move_failed type=%s code=%s", type(exc).__name__, getattr(exc, "winerror", None))
                    result.skipped += 1
                    result.errors.append(tr("engine.move_failed"))
            # Submit the whole swap before waiting. Slow/rejecting applications share
            # one settling budget instead of delaying every later window by 800 ms.
            submitted_at = time.monotonic()
            observations = windows.wait_all(submitted, monitors, timeout=0.8)
            for move, observation in zip(submitted, observations, strict=True):
                try:
                    if isinstance(observation, Exception):
                        raise observation
                    after = observation
                    if not after or after.identity != move.before.identity:
                        result.skipped += 1
                        result.errors.append(tr("engine.window_gone"))
                        continue
                    if unchanged(move.before, after):
                        result.skipped += 1
                        result.errors.append(tr("engine.move_ignored"))
                        continue
                    # Capture actual results even on partial state/geometry failures, so Undo remains useful.
                    result.entries.append(UndoEntry(move.before, after))
                    result.moved += 1
                    if after.monitor_id != move.target.id or after.state != move.before.state or after.topmost != move.before.topmost:
                        result.errors.append(tr("engine.self_changed"))
                    elif (move.target_visible is not None and after.visible_rect is not None
                          and not after.visible_rect.near(move.target_visible, 4)):
                        result.errors.append(tr("engine.tile_not_kept"))
                    elif (move.target_visible is None and after.state == WindowState.NORMAL
                          and not after.rect.near(move.normal_screen, 4)):
                        result.errors.append(tr("engine.geometry_not_kept"))
                except Exception as exc:
                    log.warning("move_failed type=%s code=%s", type(exc).__name__, getattr(exc, "winerror", None))
                    result.skipped += 1
                    result.errors.append(tr("engine.move_failed"))
            if result.entries:
                self.undo_entries = result.entries.copy()
                self.undo_layout = {m.id: m for m in monitors}
            log.info("swap_finished moved=%d skipped=%d errors=%d submit_ms=%.1f total_ms=%.1f", result.moved,
                     result.skipped, len(result.errors), (submitted_at - started) * 1000,
                     (time.monotonic() - started) * 1000)
            return result
        finally:
            try:
                windows.restore_focus(foreground)
            finally:
                self.lock.release()

    def _undo(self, monitors: list[MonitorInfo], displays: Displays, windows: Windows) -> SwapResult:
        result = SwapResult()
        remaining = []
        submitted: list[tuple[UndoEntry, Move]] = []
        current_displays = {m.id: m for m in monitors}
        for entry in self.undo_entries:
            if self.stop_requested.is_set():
                remaining.extend(self.undo_entries[self.undo_entries.index(entry):])
                break
            before, after = entry.before, entry.after
            target = current_displays.get(before.monitor_id)
            source = current_displays.get(after.monitor_id)
            # Never apply stale coordinates after a resolution/taskbar/layout change.
            if target != self.undo_layout.get(before.monitor_id) or source != self.undo_layout.get(after.monitor_id):
                result.skipped += 1
                remaining.append(entry)
                continue
            if target is None:
                result.skipped += 1
                remaining.append(entry)
                continue
            try:
                if displays.enumerate() != monitors:
                    raise ValueError("Monitor layout changed")
                current = windows.snapshot(before.hwnd, monitors, before.z_index)
                if not current or not unchanged(after, current):
                    result.skipped += 1
                    continue
                move = Move(current, target, before.movement_rect)
                windows.move(move, exact=before)
                submitted.append((entry, move))
            except Exception as exc:
                result.skipped += 1
                result.errors.append(tr("engine.restore_failed"))
                remaining.append(entry)
                log.warning("undo_failed type=%s code=%s", type(exc).__name__, getattr(exc, "winerror", None))
        observations = windows.wait_all([move for _, move in submitted], monitors, timeout=0.8)
        for (entry, _move), observation in zip(submitted, observations, strict=True):
            try:
                if isinstance(observation, Exception):
                    raise observation
                restored = observation
                if restored and unchanged(entry.before, restored):
                    result.moved += 1
                else:
                    result.skipped += 1
                    result.errors.append(tr("engine.restore_incomplete"))
            except Exception as exc:
                result.skipped += 1
                result.errors.append(tr("engine.restore_failed"))
                remaining.append(entry)
                log.warning("undo_failed type=%s code=%s", type(exc).__name__, getattr(exc, "winerror", None))
        self.undo_entries = remaining
        return result
