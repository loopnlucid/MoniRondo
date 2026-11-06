import ctypes
import sys

import pytest

pytestmark = [pytest.mark.windows, pytest.mark.skipif(sys.platform != 'win32', reason='Windows only')]


def test_native_structure_sizes():
    from monirondo.windows.native import DisplayMode, DisplayPath, NativePlacement, SourceName, TargetName
    assert [ctypes.sizeof(t) for t in (DisplayMode, DisplayPath, NativePlacement, SourceName, TargetName)] == [64, 72, 44, 84, 420]


def test_application_start_background_and_clean_exit(tmp_path):
    import os
    import subprocess
    env = os.environ.copy()
    env.pop('QT_QPA_PLATFORM', None)
    env['APPDATA'] = env['LOCALAPPDATA'] = str(tmp_path)
    result = subprocess.run([sys.executable, '-m', 'monirondo', '--smoke-test'],
                            env=env, capture_output=True, text=True, timeout=25)
    logfile = tmp_path / 'MonitorSwap/logs/monirondo.log'
    logtext = logfile.read_text(encoding='utf-8') if logfile.exists() else ''
    assert result.returncode == 0, (result.stderr, logtext)
    assert 'Traceback' not in logtext and 'native_job_failed' not in logtext


def test_global_hotkey_conflict_across_processes():
    import subprocess

    from monirondo.windows.native import register_hotkey, unregister_hotkey
    # No key presses are synthesized. Only registration/conflict handling is tested.
    vk = next((key for key in range(0x81, 0x88) if register_hotkey(None, 22001, 0x4007, key)), None)
    if vk is None:
        pytest.skip('All probe combinations already reserved by other applications')
    try:
        code = ("from monirondo.windows.native import register_hotkey,unregister_hotkey; "
                f"ok=register_hotkey(None,22002,0x4007,{vk}); "
                "unregister_hotkey(None,22002); raise SystemExit(1 if ok else 0)")
        assert subprocess.run([sys.executable, '-c', code], timeout=10).returncode == 0
    finally:
        unregister_hotkey(None, 22001)


def test_hotkey_window_dispatches_while_settings_are_hidden():
    import os
    import subprocess
    from pathlib import Path
    env = os.environ.copy()
    env.pop('QT_QPA_PLATFORM', None)
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('hotkey_probe.py'))],
                            capture_output=True, text=True, env=env, timeout=15)
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_zero_budget_still_observes_a_window():
    from helpers import monitors, window

    from monirondo.models import Move
    from monirondo.windows.window_service import WindowService
    layout = monitors(2)
    w = window(1, layout[0])
    service = object.__new__(WindowService)
    service.snapshot = lambda *args: w
    assert service.wait_after(Move(w, layout[1], w.normal_screen), layout, timeout=0) is w


@pytest.mark.parametrize('scenario', ['late_dpi_resize', 'minimum_height', 'reused_handle'])
def test_dpi_geometry_settles_with_measured_frames_and_bounded_corrections(monkeypatch, scenario):
    from dataclasses import replace
    from types import SimpleNamespace

    from helpers import monitors, window

    from monirondo.models import Move, Rect
    from monirondo.windows import window_service

    class Clock:
        now = 100.

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = Clock()
    monkeypatch.setattr(window_service, 'time', SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep))
    layout = [replace(m, dpi=dpi) for m, dpi in zip(monitors(2), (96, 120), strict=True)]
    before = window(1, layout[0])
    wanted = Rect(960, 560, 1920, 1080)
    actual_outer = Rect(950, 560, 1930, 1090)
    correct = replace(before, monitor_id=layout[1].id, rect=actual_outer, visible_rect=wanted)
    enlarged = replace(correct, rect=replace(actual_outer, bottom=1490), visible_rect=replace(wanted, bottom=1480))
    if scenario == 'reused_handle':
        enlarged = replace(enlarged, pid=before.pid + 1)
    calls = []

    def snapshot(*_):
        if scenario == 'late_dpi_resize' and (clock.now < 100.085 or calls):
            return correct
        return enlarged

    def position(*args):
        calls.append(args)
        return True

    monkeypatch.setattr(window_service, 'set_window_pos', position)
    service = object.__new__(window_service.WindowService)
    service.move_started, service.snapshot = {before.hwnd: clock.now}, snapshot
    # The initial source-DPI frame estimate is deliberately different. The
    # correction must measure the actual target frame after WM_DPICHANGED.
    move = Move(before, layout[1], Rect(952, 560, 1928, 1088), wanted)
    result = service.wait_after(move, layout)
    if scenario == 'late_dpi_resize':
        assert result is correct and len(calls) == 1
        assert .15 <= clock.now - 100. < .3
    else:
        assert result is enlarged
        assert len(calls) == (2 if scenario == 'minimum_height' else 0)
        assert clock.now - 100. == pytest.approx(.8 if scenario == 'minimum_height' else 0)
    assert all(call[2:6] == (950, 560, 980, 530) for call in calls)
    assert all(call[6] == 0x4214 for call in calls)  # Preserve activation and Z order.


def test_refusing_window_does_not_prevent_later_tiles_from_being_corrected(monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace

    from helpers import FakeDisplays, monitors, window

    from monirondo.engine import SwapEngine
    from monirondo.i18n import tr
    from monirondo.models import Rect, SwapAction
    from monirondo.windows import window_service

    clock = [100.]

    def sleep(seconds):
        clock[0] += seconds

    fake_time = SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep)
    monkeypatch.setattr(window_service, 'time', fake_time)
    monkeypatch.setattr('monirondo.engine.time', fake_time)
    layout = [replace(m, dpi=dpi) for m, dpi in zip(monitors(2), (96, 120), strict=True)]
    before = [window(1, layout[0], z_index=100)]
    for hwnd, top, bottom in [(2, 40, 560), (3, 560, 1080)]:
        visible = Rect(-960, top, 0, bottom)
        before.append(replace(window(hwnd, layout[0]), visible_rect=visible,
                              rect=Rect(visible.left - 8, top, visible.right + 8, bottom + 8)))
    items = {w.hwnd: w for w in before}
    service = object.__new__(window_service.WindowService)
    service.move_started = {}
    service.enumerate = lambda *_: list(items.values())
    service.snapshot = lambda hwnd, *_: items[hwnd]
    service.foreground = lambda: 77
    service.restore_focus = lambda _: None

    def move(request):
        w, r = request.before, request.normal_screen
        service.move_started[w.hwnd] = clock[0]
        visible = request.target_visible
        items[w.hwnd] = replace(w, monitor_id=request.target.id,
                                rect=replace(r, right=r.right + 200, bottom=r.bottom + 180),
                                visible_rect=replace(visible, right=visible.right + 200, bottom=visible.bottom + 180)
                                if visible else None)

    service.move = move
    corrections = []

    def position(hwnd, _, x, y, width, height, flags):
        corrections.append((hwnd, clock[0]))
        if hwnd != 1:  # The first app enforces its minimum size forever.
            r = Rect(x, y, x + width, y + height)
            items[hwnd] = replace(items[hwnd], rect=r,
                                  visible_rect=Rect(r.left + 10, r.top, r.right - 10, r.bottom - 10))
        return True

    monkeypatch.setattr(window_service, 'set_window_pos', position)
    result = SwapEngine().run(SwapAction('c', 'C', 'cycle'), FakeDisplays(layout), service)
    assert items[2].visible_rect == Rect(960, 40, 1920, 560)
    assert items[3].visible_rect == Rect(960, 560, 1920, 1080)
    assert {hwnd for hwnd, _ in corrections} == {1, 2, 3}
    assert clock[0] - 100. == pytest.approx(.8)
    assert result.moved == 3
    assert len(result.errors) == 1 and result.errors[0] == tr('engine.geometry_not_kept')


def test_per_monitor_window_is_not_settled_before_its_target_dpi(monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace

    from helpers import monitors, window

    from monirondo.models import Move
    from monirondo.windows import window_service

    clock = [100.]
    monkeypatch.setattr(window_service, 'time', SimpleNamespace(monotonic=lambda: clock[0],
                        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds)))
    monkeypatch.setattr(window_service, 'get_window_dpi_context', lambda _: 1)
    monkeypatch.setattr(window_service, 'get_dpi_awareness', lambda _: 2)
    monkeypatch.setattr(window_service, 'get_window_dpi', lambda _: 96 if clock[0] < 100.25 else 120)
    layout = [replace(m, dpi=dpi) for m, dpi in zip(monitors(2), (96, 120), strict=True)]
    before = window(1, layout[0])
    after = replace(before, monitor_id=layout[1].id, rect=before.rect.translate(1920, 0))
    service = object.__new__(window_service.WindowService)
    service.move_started, service.snapshot = {before.hwnd: clock[0]}, lambda *_: after
    assert service.wait_after(Move(before, layout[1], after.rect), layout) is after
    assert .3 <= clock[0] - 100. < .4


def test_batch_observation_failure_is_isolated_to_its_window():
    from dataclasses import replace

    from helpers import monitors, window

    from monirondo.models import Move
    from monirondo.windows.window_service import WindowService

    layout = monitors(2)
    before = [window(i, layout[0]) for i in (1, 2)]
    after = replace(before[1], monitor_id=layout[1].id)

    def snapshot(hwnd, *_):
        if hwnd == 1:
            raise PermissionError('Window inaccessible')
        return after

    service = object.__new__(WindowService)
    service.snapshot = snapshot
    results = service.wait_all([Move(w, layout[1], w.rect) for w in before], layout)
    assert isinstance(results[0], PermissionError) and results[1] is after


def test_active_monitor_enumeration_and_window_snapshot_is_read_only():
    from monirondo.windows.monitors import MonitorService
    from monirondo.windows.window_service import WindowService
    monitors = MonitorService().enumerate()
    assert len({m.id for m in monitors}) == len(monitors)
    service = WindowService()
    try:
        windows = service.enumerate(monitors)
        assert len({w.hwnd for w in windows}) == len(windows)
        assert all(w.monitor_id in {m.id for m in monitors} for w in windows)
    finally:
        service.close()


@pytest.mark.interactive
def test_swap_trace_records_requests_results_and_safe_undo_for_own_window(tmp_path):
    import os
    import runpy
    import time
    from pathlib import Path

    import win32con
    import win32gui

    from monirondo.engine import SwapEngine, unchanged
    from monirondo.models import SwapAction
    from monirondo.windows.monitors import MonitorService
    from monirondo.windows.native import initialize_dpi
    from monirondo.windows.window_service import WindowService

    initialize_dpi()
    script = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/trace_swap.py'))
    displays = MonitorService()
    layout = displays.enumerate()
    if len(layout) < 2:
        pytest.skip('Two monitors required')
    source, target = layout[0], layout[1]
    cls = win32gui.WNDCLASS()
    cls.lpszClassName = f'MonitorSwap-Trace-{os.getpid()}'
    cls.lpfnWndProc = win32gui.DefWindowProc
    atom = win32gui.RegisterClass(cls)
    hwnd = win32gui.CreateWindowEx(0, atom, 'MonitorSwap trace test', win32con.WS_OVERLAPPEDWINDOW,
                                  source.work.left + 100, source.work.top + 100, 500, 350, 0, 0, 0, None)
    base = WindowService(include_own=True)
    service = None
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
        deadline = time.monotonic() + 1
        before = None
        while before is None and time.monotonic() < deadline:
            win32gui.PumpWaitingMessages()
            before = base.snapshot(hwnd, layout)
            time.sleep(.02)
        assert before is not None
        trace = script['Trace'](layout, [before])
        service = script['traced_service'](trace, include_own=True)
        service.enumerate = lambda monitors: [w] if (w := service.snapshot(hwnd, monitors)) else []
        engine = SwapEngine()
        with trace:
            trace.phase = 'swap'
            result = engine.run(SwapAction('p', 'P', 'pair', monitor_a_id=source.id, monitor_b_id=target.id),
                                displays, service)
            assert result.moved == 1 and not result.errors
            trace.phase = 'undo'
            undo = engine.run(SwapAction('u', 'U', 'undo'), displays, service)
            assert undo.moved == 1 and not undo.errors
        assert unchanged(before, service.snapshot(hwnd, layout))
        assert any(e['event'] == 'SetWindowPos' and e['window'] == 'F1' for e in trace.events)
        assert any(e['event'] == 'observed_change' for e in trace.events)
        assert len([e for e in trace.events if e['event'] == 'wait_begin']) == 2
        assert trace.raw(hwnd)['visible']['width'] > 0
        script['write_report'](tmp_path, {'version': 'test', 'mode': 'proportional', 'action': 'p',
                                         'executed': True, 'windows': [], 'events': trace.events})
        assert (tmp_path / 'report.md').is_file() and (tmp_path / 'trace.json').is_file()
    finally:
        if service:
            service.close()
        base.close()
        win32gui.DestroyWindow(hwnd)
        win32gui.UnregisterClass(atom, 0)


@pytest.mark.interactive
@pytest.mark.parametrize("state", ["normal", "maximized", "minimized", "minimized-max"])
def test_native_pair_cycle_and_undo_with_our_own_windows_only(state):
    import os
    import time

    import win32con
    import win32gui

    from monirondo.engine import SwapEngine, unchanged
    from monirondo.models import SwapAction, WindowState
    from monirondo.windows.monitors import MonitorService
    from monirondo.windows.native import initialize_dpi
    from monirondo.windows.window_service import WindowService
    initialize_dpi()
    displays = MonitorService()
    layout = displays.enumerate()
    if len(layout) < 2:
        pytest.skip("Two active desktop monitors required")
    handles = []
    class OurWindows(WindowService):
        def enumerate(self, monitors):
            return [w for w in super().enumerate(monitors) if w.hwnd in handles]
    service = OurWindows(include_own=True)
    foreground = service.foreground()
    cls = win32gui.WNDCLASS()
    cls.lpszClassName = f"MonitorSwap-Integration-{os.getpid()}-{state}"
    cls.lpfnWndProc = win32gui.DefWindowProc
    atom = win32gui.RegisterClass(cls)
    try:
        for m in layout:
            hwnd = win32gui.CreateWindowEx(win32con.WS_EX_TOPMOST if not handles else 0, atom, "MonitorSwap integration test", win32con.WS_OVERLAPPEDWINDOW,
                                          m.work.left + 140, m.work.top + 100, 500, 350, 0, 0, 0, None)
            handles.append(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
            if state in ("maximized", "minimized-max"):
                flags, _, mini, maxi, rect = win32gui.GetWindowPlacement(hwnd)
                win32gui.SetWindowPlacement(hwnd, (flags, 3, mini, maxi, rect))
            if state.startswith("minimized"):
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWMINNOACTIVE)
        win32gui.PumpWaitingMessages()
        time.sleep(0.1)
        service.restore_focus(foreground)
        baseline = service.enumerate(layout)
        assert len(baseline) == len(handles), "Test windows must pass actual desktop/filter checks"
        expected = {"normal": WindowState.NORMAL, "maximized": WindowState.MAXIMIZED,
                    "minimized": WindowState.MINIMIZED, "minimized-max": WindowState.MINIMIZED}[state]
        assert all(w.state == expected for w in baseline)
        engine = SwapEngine()
        pair = SwapAction("pair", "Pair", "pair", monitor_a_id=layout[0].id, monitor_b_id=layout[-1].id)
        for action in [pair, SwapAction("c", "Cycle", "cycle"), SwapAction("r", "Reverse", "cycle", direction="backward")]:
            focus_before = service.foreground()
            order_before = [w.hwnd for w in service.enumerate(layout)]
            result = engine.run(action, displays, service)
            win32gui.PumpWaitingMessages()
            assert not result.errors, result.errors
            assert result.moved == (2 if action.type == "pair" else len(handles))
            assert service.foreground() == focus_before
            assert [w.hwnd for w in service.enumerate(layout)] == order_before
            restored = engine.run(SwapAction("u", "Undo", "undo"), displays, service)
            assert restored.moved == result.moved, (restored, state)
            now = {w.hwnd: w for w in service.enumerate(layout)}
            assert all(unchanged(w, now[w.hwnd]) for w in baseline)
    finally:
        for hwnd in handles:
            if win32gui.IsWindow(hwnd):
                win32gui.DestroyWindow(hwnd)
        win32gui.UnregisterClass(atom, 0)
        service.restore_focus(foreground)
        service.close()


@pytest.mark.interactive
@pytest.mark.parametrize('mode', ['keep_size_fit_if_needed', 'proportional'])
def test_native_split_geometry_and_undo_with_different_presnap_restore_bounds(mode, monkeypatch):
    """Native HWND/DWM geometry, simulated pre-Snap metadata; no shell/input automation."""
    import os
    import time

    import win32con
    import win32gui

    from monirondo.engine import SwapEngine, unchanged
    from monirondo.geometry import screen_rect_to_placement
    from monirondo.models import Rect, SwapAction
    from monirondo.planner import monitor_mapping
    from monirondo.windows.monitors import MonitorService
    from monirondo.windows.native import initialize_dpi, set_window_pos
    from monirondo.windows.window_service import WindowService
    initialize_dpi()
    displays = MonitorService()
    layout = displays.enumerate()
    if len(layout) < 2:
        pytest.skip('Two active monitors required')
    handles, origins = [], {}
    class OurWindows(WindowService):
        def enumerate(self, monitors):
            return [w for hwnd in handles if (w := self.snapshot(hwnd, monitors)) is not None]
    service = OurWindows(include_own=True)
    focus = service.foreground()
    cls = win32gui.WNDCLASS()
    cls.lpszClassName = f'MonitorSwap-Split-Test-{os.getpid()}-{mode}'
    cls.lpfnWndProc = win32gui.DefWindowProc
    atom = win32gui.RegisterClass(cls)
    try:
        for monitor in layout:
            for side in range(2):
                hwnd = win32gui.CreateWindowEx(0, atom, 'MonitorSwap layout test', win32con.WS_OVERLAPPEDWINDOW,
                                              monitor.work.left + 80, monitor.work.top + 80, 500, 350, 0, 0, 0, None)
                handles.append(hwnd)
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
                # DWM/virtual-desktop membership is asynchronous for a brand-new
                # HWND. Wait for that setup step, without weakening production filters.
                initial = None
                ready_by = time.monotonic() + 1.0
                while initial is None and time.monotonic() < ready_by:
                    win32gui.PumpWaitingMessages()
                    initial = service.snapshot(hwnd, layout)
                    if initial is None:
                        time.sleep(.01)
                assert initial and initial.visible_rect
                frame, outer = initial.visible_rect, initial.rect
                slot = Rect(monitor.work.left + round(side * .5 * monitor.work.width), monitor.work.top,
                            monitor.work.left + round((side + 1) * .5 * monitor.work.width), monitor.work.bottom)
                requested = Rect(slot.left - (frame.left - outer.left), slot.top - (frame.top - outer.top),
                                 slot.right + (outer.right - frame.right), slot.bottom + (outer.bottom - frame.bottom))
                assert set_window_pos(hwnd, None, requested.left, requested.top, requested.width, requested.height,
                                      0x0004 | 0x0010 | 0x0200)
                origins[hwnd] = (monitor, side)
        win32gui.PumpWaitingMessages()
        time.sleep(.08)
        original_placement = win32gui.GetWindowPlacement
        def presnap_placement(hwnd):
            flags, show, mini, maxi, normal = original_placement(hwnd)
            if hwnd in origins:
                monitor, _ = origins[hwnd]
                normal = screen_rect_to_placement(monitor.work, monitor).tuple()
            return flags, show, mini, maxi, normal
        monkeypatch.setattr(win32gui, 'GetWindowPlacement', presnap_placement)
        before = service.enumerate(layout)
        assert len(before) == len(handles)
        assert all(not w.rect.near(w.normal_screen) for w in before)
        engine = SwapEngine()
        action = SwapAction('c', 'Cycle', 'cycle')
        mapping = monitor_mapping(action, layout)
        result = engine.run(action, displays, service, mode)
        assert result.moved == len(handles) and not result.errors, result
        for hwnd, (source, side) in origins.items():
            target = next(m for m in layout if m.id == mapping[source.id])
            after = service.snapshot(hwnd, layout)
            expected = Rect(target.work.left + round(side * .5 * target.work.width), target.work.top,
                            target.work.left + round((side + 1) * .5 * target.work.width), target.work.bottom)
            assert after and after.visible_rect and after.visible_rect.near(expected, 4), (after, expected)
        undo = engine.run(SwapAction('u', 'Undo', 'undo'), displays, service)
        assert undo.moved == len(handles) and not undo.errors, undo
        assert all(unchanged(w, service.snapshot(w.hwnd, layout)) for w in before)
    finally:
        for hwnd in handles:
            if win32gui.IsWindow(hwnd):
                win32gui.DestroyWindow(hwnd)
        win32gui.UnregisterClass(atom, 0)
        service.restore_focus(focus)
        service.close()


@pytest.mark.interactive
@pytest.mark.parametrize('blocking', [False, True])
def test_real_qt_three_window_layout_across_dpi(blocking):
    import os
    import subprocess
    from pathlib import Path
    env = os.environ.copy()
    env.pop('QT_QPA_PLATFORM', None)
    command = [sys.executable, str(Path(__file__).with_name('qt_layout_probe.py'))]
    if blocking:
        command.append('--with-blocking-window')
    result = subprocess.run(command,
                            capture_output=True, text=True, env=env, timeout=20)
    if result.returncode == 77:
        pytest.skip('Mixed-DPI desktop required')
    assert result.returncode == 0, (result.stdout, result.stderr)
