from dataclasses import replace

import pytest
from helpers import FakeDisplays, FakeWindows, monitors, window

from monirondo.engine import SwapEngine
from monirondo.models import SwapAction, WindowState


@pytest.mark.parametrize("state", list(WindowState))
def test_swap_and_undo_restore_exact_state_focus_and_topmost(state):
    layout = monitors()
    original = window(1, layout[0], state, topmost=True)
    windows, displays = FakeWindows([original]), FakeDisplays(layout)
    engine = SwapEngine()
    assert engine.run(SwapAction("c", "C", "cycle"), displays, windows).moved == 1
    assert windows.items[1].monitor_id == "1"
    assert windows.items[1].state == state
    assert engine.run(SwapAction("u", "U", "undo"), displays, windows).moved == 1
    assert windows.items[1] == original
    assert windows.active == 77


@pytest.mark.parametrize("change", ["closed", "moved", "reused", "state", "topmost"])
def test_undo_skips_changed_or_reused_window(change):
    layout = monitors()
    windows, displays = FakeWindows([window(1, layout[0])]), FakeDisplays(layout)
    engine = SwapEngine()
    engine.run(SwapAction("c", "C", "cycle"), displays, windows)
    w = windows.items[1]
    if change == "closed":
        windows.items.clear()
    else:
        args = {"moved": {"rect": w.rect.translate(15, 0)}, "reused": {"pid": 999},
                "state": {"state": WindowState.MINIMIZED}, "topmost": {"topmost": True}}[change]
        windows.items[1] = replace(w, **args)
    assert engine.run(SwapAction("u", "U", "undo"), displays, windows).moved == 0


def test_failed_window_does_not_abort_rest():
    layout = monitors()
    windows = FakeWindows([window(i, layout[0]) for i in range(1, 5)])
    windows.fail.add(2)
    engine = SwapEngine()
    result = engine.run(SwapAction("c", "C", "cycle"), FakeDisplays(layout), windows)
    assert result.moved == 3 and result.skipped == 1
    assert {e.before.hwnd for e in engine.undo_entries} == {1, 3, 4}


def test_undo_after_layout_change_keeps_entry_for_reconnect():
    layout = monitors()
    windows, displays = FakeWindows([window(1, layout[0])]), FakeDisplays(layout)
    engine = SwapEngine()
    engine.run(SwapAction("c", "C", "cycle"), displays, windows)
    displays.layout = layout[1:]
    result = engine.run(SwapAction("u", "U", "undo"), displays, windows)
    assert result.skipped == 1 and engine.undo_entries
    displays.layout = layout
    assert engine.run(SwapAction("u", "U", "undo"), displays, windows).moved == 1


def test_reentrant_action_is_ignored():
    engine = SwapEngine()
    engine.lock.acquire()
    result = engine.run(SwapAction("c", "C", "cycle"), FakeDisplays([]), FakeWindows([]))
    engine.lock.release()
    assert result.skipped == 1 and result.errors


def test_500_swaps_do_not_accumulate_undo_or_drift():
    layout = monitors(8)
    original = [window(i + 1, layout[i % 8]) for i in range(32)]
    windows, displays, engine = FakeWindows(original), FakeDisplays(layout), SwapEngine()
    for _ in range(500):
        assert engine.run(SwapAction("c", "C", "cycle"), displays, windows).moved == 32
        assert len(engine.undo_entries) == 32
        assert engine.run(SwapAction("u", "U", "undo"), displays, windows).moved == 32
        assert not engine.undo_entries
    assert windows.items == {w.hwnd: w for w in original}


def test_all_moves_are_submitted_before_first_result_wait_including_undo():
    layout = monitors(3)
    class CheckBatch(FakeWindows):
        def wait_after(self, move, monitors, timeout=0.8):
            assert len(self.calls) == 6, 'A result wait must not delay later movement requests'
            return super().wait_after(move, monitors, timeout)
    windows = CheckBatch([window(i, layout[i % 3]) for i in range(1, 7)])
    engine, displays = SwapEngine(), FakeDisplays(layout)
    result = engine.run(SwapAction('c', 'C', 'cycle'), displays, windows)
    assert result.moved == 6 and not result.errors
    windows.calls.clear()
    result = engine.run(SwapAction('u', 'U', 'undo'), displays, windows)
    assert result.moved == 6 and not result.errors


def test_slow_windows_share_one_settling_budget(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('monirondo.engine.time.monotonic', lambda: clock[0])
    budgets = []
    layout = monitors(3)
    class SlowWindows(FakeWindows):
        def wait_all(self, moves, monitors, timeout=0.8):
            budgets.append(timeout)
            clock[0] += timeout
            return super().wait_all(moves, monitors, timeout)
    windows = SlowWindows([window(i, layout[i % 3]) for i in range(1, 11)])
    result = SwapEngine().run(SwapAction('c', 'C', 'cycle'), FakeDisplays(layout), windows)
    assert result.moved == 10
    assert sum(budgets) == pytest.approx(0.8)
    assert budgets == [0.8]


def test_layout_change_mid_batch_counts_only_unsubmitted_windows_as_skipped():
    layout = monitors(3)
    displays = FakeDisplays(layout)
    class DockingWindows(FakeWindows):
        def move(self, move, exact=None):
            super().move(move, exact)
            displays.layout = layout[:2]
    windows = DockingWindows([window(i, layout[0]) for i in range(1, 4)])
    result = SwapEngine().run(SwapAction('c', 'C', 'cycle'), displays, windows)
    assert result.moved == 1 and result.skipped == 2
