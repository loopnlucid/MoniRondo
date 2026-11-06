from dataclasses import replace

import pytest
from helpers import FakeDisplays, FakeWindows, monitors, window

from monirondo.engine import SwapEngine, unchanged
from monirondo.geometry import (
    outer_rect_for_visible,
    screen_rect_to_placement,
    transfer_rect,
    transfer_tile,
)
from monirondo.i18n import tr
from monirondo.models import MonitorInfo, Rect, SwapAction
from monirondo.planner import plan_moves


def snapped(hwnd, monitor, left=0., right=.5, top=0., bottom=1.):
    work = monitor.work
    visible = Rect(work.left + round(left * work.width), work.top + round(top * work.height),
                   work.left + round(right * work.width), work.top + round(bottom * work.height))
    outer = Rect(visible.left - 8, visible.top, visible.right + 8, visible.bottom + 8)
    original = window(hwnd, monitor)
    # WINDOWPLACEMENT can retain the fullscreen/large pre-snap restore geometry.
    return replace(original, rect=outer, visible_rect=visible, normal_screen=monitor.work,
                   placement=replace(original.placement, normal=screen_rect_to_placement(monitor.work, monitor)))


@pytest.mark.parametrize('mode', ['keep_size_fit_if_needed', 'proportional'])
@pytest.mark.parametrize('slot', [(0., .5, 0., 1.), (.5, 1., 0., 1.), (0., .5, 0., .5),
                                  (.5, 1., .5, 1.), (1 / 3, 2 / 3, 0., 1.), (0., 2 / 3, 0., 1.)])
@pytest.mark.parametrize('dpi', [96, 144])
def test_snapped_slots_preserve_relative_edges_and_invisible_borders(mode, slot, dpi):
    source = MonitorInfo('a', 'a', 'A', Rect(0, 0, 1920, 1080), Rect(0, 40, 1920, 1080), dpi=96)
    target = MonitorInfo('b', 'b', 'B', Rect(-2560, -1440, 0, 0), Rect(-2560, -1440, 0, -40), dpi=dpi)
    before = snapped(1, source, *slot)
    move = plan_moves(SwapAction('c', 'C', 'cycle'), [source, target], [before], mode=mode).moves[0]
    left, right, top, bottom = slot
    visible = Rect(target.work.left + round(left * target.work.width), target.work.top + round(top * target.work.height),
                   target.work.left + round(right * target.work.width), target.work.top + round(bottom * target.work.height))
    assert move.target_visible == visible
    border = round(8 * dpi / 96)
    assert move.normal_screen == Rect(visible.left - border, visible.top, visible.right + border, visible.bottom + border)


@pytest.mark.parametrize('mode', ['keep_size_fit_if_needed', 'proportional'])
def test_free_normal_window_uses_actual_rectangle_instead_of_latent_restore(mode):
    layout = monitors(2)
    w = window(1, layout[0])
    w = replace(w, normal_screen=layout[0].work)
    move = plan_moves(SwapAction('c', 'C', 'cycle'), layout, [w], mode=mode).moves[0]
    assert move.normal_screen == transfer_rect(w.rect, layout[0].work, layout[1].work, mode)
    assert move.normal_screen.width < layout[1].work.width


def test_arbitrary_free_window_is_not_forced_into_a_snap_slot():
    work = Rect(0, 0, 1920, 1040)
    assert transfer_tile(Rect(150, 80, 900, 780), Rect(158, 80, 892, 772), work, work) is None


def test_visible_slot_can_be_corrected_using_measured_target_frame_after_dpi_change():
    target = Rect(960, 510, 1920, 1020)
    # The target application has already changed its size and its actual 125 %
    # frame differs from the initial estimate made on the source monitor.
    current_visible = Rect(959, 511, 2561, 1371)
    current_outer = Rect(949, 511, 2571, 1381)
    assert outer_rect_for_visible(target, current_outer, current_visible) == Rect(950, 510, 1930, 1030)
    assert outer_rect_for_visible(target, current_visible, current_outer) is None


def test_unachievable_tiled_size_is_reported_and_actual_result_can_be_undone():
    class MinimumHeightWindows(FakeWindows):
        def move(self, move, exact=None):
            super().move(move, exact)
            if exact is None:
                w = self.items[move.before.hwnd]
                self.items[w.hwnd] = replace(w, rect=replace(w.rect, bottom=w.rect.bottom + 200),
                                            visible_rect=replace(w.visible_rect, bottom=w.visible_rect.bottom + 200))

    layout = monitors(2)
    before = snapped(1, layout[0], .5, 1., .5, 1.)
    windows, engine = MinimumHeightWindows([before]), SwapEngine()
    displays = FakeDisplays(layout)
    result = engine.run(SwapAction('c', 'C', 'cycle'), displays, windows)
    assert result.moved == 1 and len(result.errors) == 1
    assert result.errors[0] == tr('engine.tile_not_kept')
    assert result.entries[0].after == windows.items[before.hwnd]
    undo = engine.run(SwapAction('u', 'Undo', 'undo'), displays, windows)
    assert undo.moved == 1 and not undo.errors
    assert windows.items[before.hwnd] == before


def test_snap_undo_restores_the_visible_split_and_ignores_changed_latent_restore_rect():
    layout = monitors(2)
    before = [snapped(1, layout[0]), snapped(2, layout[0], .5, 1.)]
    windows, engine = FakeWindows(before), SwapEngine()
    displays = FakeDisplays(layout)
    assert engine.run(SwapAction('c', 'C', 'cycle'), displays, windows).moved == 2
    assert engine.run(SwapAction('u', 'U', 'undo'), displays, windows).moved == 2
    assert windows.items == {w.hwnd: w for w in before}
    # Native SetWindowPos can clear the old Snap restore metadata while keeping
    # exactly the original visible rectangle. This is still a successful Undo.
    restored = replace(before[0], normal_screen=before[0].rect,
                       placement=replace(before[0].placement, normal=before[0].rect))
    assert unchanged(before[0], restored)
    assert not unchanged(before[0], replace(restored, rect=restored.rect.translate(20, 0)))


def test_repeated_cycles_keep_left_and_right_halves_without_drift():
    a = MonitorInfo('a', 'a', 'A', Rect(-1920, 0, 0, 1080), Rect(-1920, 40, 0, 1080), dpi=96)
    b = MonitorInfo('b', 'b', 'B', Rect(0, -1440, 2560, 0), Rect(0, -1440, 2560, -48), dpi=144)
    c = MonitorInfo('c', 'c', 'C', Rect(0, 0, 1080, 1920), Rect(0, 0, 1080, 1880), dpi=96)
    layout = [a, b, c]
    windows, engine = FakeWindows([snapped(1, a), snapped(2, a, .5, 1.)]), SwapEngine()
    original = [w.rect for w in windows.items.values()]
    for _ in range(30):
        result = engine.run(SwapAction('c', 'C', 'cycle'), FakeDisplays(layout), windows)
        assert result.moved == 2 and not result.errors
    assert [w.rect for w in windows.items.values()] == original
