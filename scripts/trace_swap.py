"""Record one real swap: independent geometry reference, native requests and results.

Without --execute this only writes the plan. With --execute it runs exactly one
configured action, observes all windows for two seconds, then requests safe Undo.
No titles, document names, full process paths, keystrokes or screenshots are read.
"""
from __future__ import annotations

import argparse
import ctypes as C
import json
import logging
import threading
import time
from ctypes import wintypes as W
from datetime import datetime
from pathlib import Path, PureWindowsPath

import win32gui
import win32process

from monirondo import __version__
from monirondo.config import config_path, load_config
from monirondo.engine import SwapEngine
from monirondo.models import Rect, SwapAction
from monirondo.planner import plan_moves
from monirondo.windows import window_service
from monirondo.windows.monitors import MonitorService
from monirondo.windows.native import NativePlacement, bind, get_attribute, initialize_dpi, is_zoomed, user32
from monirondo.windows.window_service import WindowService, process_info


def rect_data(rect):
    if rect is None:
        return None
    return {'x': rect.left, 'y': rect.top, 'width': rect.width, 'height': rect.height}


def proportional_reference(visible, source, target):
    """Independent edge calculation; deliberately does not call our planner/geometry helpers."""
    left = target.work.left + round((visible.left - source.work.left) / source.work.width * target.work.width)
    right = target.work.left + round((visible.right - source.work.left) / source.work.width * target.work.width)
    top = target.work.top + round((visible.top - source.work.top) / source.work.height * target.work.height)
    bottom = target.work.top + round((visible.bottom - source.work.top) / source.work.height * target.work.height)
    return Rect(left, top, right, bottom)


class Trace:
    def __init__(self, layout, windows):
        self.layout = layout
        self.labels = {w.hwnd: f'F{i + 1}' for i, w in enumerate(windows)}
        self.identities = {w.hwnd: w.identity for w in windows}
        self.started = time.monotonic()
        self.events = []
        self.phase = 'plan'
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.reader = None
        try:
            self.arranged = bind(user32, 'IsWindowArranged', W.BOOL, W.HWND)
        except AttributeError:
            self.arranged = None
        self.dpi = bind(user32, 'GetDpiForWindow', W.UINT, W.HWND)
        self.original_pos = window_service.set_window_pos
        self.original_placement = window_service.set_placement

    def event(self, event, hwnd=None, **data):
        with self.lock:
            self.events.append({'ms': round((time.monotonic() - self.started) * 1000, 2),
                                'phase': self.phase, 'event': event,
                                'window': self.labels.get(hwnd), **data})

    def raw(self, hwnd):
        if not win32gui.IsWindow(hwnd):
            return None
        thread, pid = win32process.GetWindowThreadProcessId(hwnd)
        outer = Rect(*win32gui.GetWindowRect(hwnd))
        frame = W.RECT()
        visible = None
        if get_attribute(hwnd, 9, C.byref(frame), C.sizeof(frame)) == 0:
            visible = rect_data(Rect(frame.left, frame.top, frame.right, frame.bottom))
        return {'outer': rect_data(outer), 'visible': visible, 'dpi': self.dpi(hwnd),
                'snapped': bool(self.arranged(hwnd)) if self.arranged else None,
                'minimized': bool(win32gui.IsIconic(hwnd)), 'maximized': bool(is_zoomed(hwnd)),
                'pid': pid, 'thread': thread}

    def observe(self):
        previous = {}
        while not self.stop.is_set():
            for hwnd in self.labels:
                try:
                    current = self.raw(hwnd)
                    if hwnd not in previous or previous[hwnd] != current:
                        self.event('observed_change', hwnd, actual=current)
                        previous[hwnd] = current
                except Exception as exc:
                    self.event('observation_failed', hwnd, error=type(exc).__name__)
            self.stop.wait(.01)

    def position(self, hwnd, after, x, y, width, height, flags):
        self.event('SetWindowPos', hwnd, requested={'x': x, 'y': y, 'width': width, 'height': height},
                   flags=f'0x{flags:04x}')
        ok = self.original_pos(hwnd, after, x, y, width, height, flags)
        self.event('SetWindowPos_return', hwnd, request_accepted=bool(ok))
        return ok

    def placement(self, hwnd, pointer):
        p = C.cast(pointer, C.POINTER(NativePlacement)).contents
        self.event('SetWindowPlacement', hwnd, normal=rect_data(Rect(p.normal.left, p.normal.top,
                                                                   p.normal.right, p.normal.bottom)),
                   show_cmd=p.showCmd, flags=p.flags)
        return self.original_placement(hwnd, pointer)

    def __enter__(self):
        window_service.set_window_pos, window_service.set_placement = self.position, self.placement
        self.reader = threading.Thread(target=self.observe, name='geometry-observer', daemon=True)
        self.reader.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        if self.reader:
            self.reader.join(timeout=2)
        window_service.set_window_pos, window_service.set_placement = self.original_pos, self.original_placement


def traced_service(trace, **kwargs):
    class TracedWindows(WindowService):
        def enumerate(self, monitors):
            return [w for w in super().enumerate(monitors) if w.identity == trace.identities.get(w.hwnd)]

        def move(self, move, exact=None):
            trace.event('move', move.before.hwnd, target_outer=rect_data(move.normal_screen),
                        target_visible=rect_data(move.target_visible), exact=exact is not None)
            return super().move(move, exact)

        def wait_after(self, move, monitors, timeout=.8):
            trace.event('wait_begin', move.before.hwnd, budget_ms=round(timeout * 1000, 2))
            result = super().wait_after(move, monitors, timeout)
            trace.event('wait_end', move.before.hwnd, actual=trace.raw(move.before.hwnd) if result else None)
            return result

        def wait_all(self, moves, monitors, timeout=.8):
            for move in moves:
                trace.event('wait_begin', move.before.hwnd, budget_ms=round(timeout * 1000, 2))
            results = super().wait_all(moves, monitors, timeout)
            for move, result in zip(moves, results, strict=True):
                trace.event('wait_end', move.before.hwnd,
                            actual=trace.raw(move.before.hwnd) if result is not None and not isinstance(result, Exception) else None)
            return results

    return TracedWindows(**kwargs)


def format_rect(data):
    return f"({data['x']}, {data['y']}) {data['width']} × {data['height']}" if data else '–'


def describe_plan(plan, trace, layout):
    items = []
    for move in plan.moves:
        w = move.before
        source = next(m for m in layout if m.id == w.monitor_id)
        info = process_info(w.pid)
        items.append({'window': trace.labels[w.hwnd],
                      'program': PureWindowsPath(info[1]).name if info else 'unknown',
                      'before': trace.raw(w.hwnd), 'target_outer': rect_data(move.normal_screen),
                      'target_visible': rect_data(move.target_visible),
                      'reference_visible': rect_data(proportional_reference(w.visible_rect, source, move.target))
                      if w.visible_rect else None})
    return items


def write_report(output, payload):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'trace.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Window swap: planned vs. actual', '', f"Version: {payload['version']}; mode: {payload['mode']}; "
             f"action: {payload['action']}; executed: {payload['executed']}", '',
             'All positions and sizes are physical pixels. Positions are global screen coordinates.', '',
             '| Window | Program | Snapped before | Visible before | Proportional reference | Planned visible target | Measured after 2 s |',
             '|---|---|---|---|---|---|---|']
    for item in payload['windows']:
        before = item['before'] or {}
        lines.append(f"| {item['window']} | {item['program']} | {before.get('snapped')} | "
                     f"{format_rect(before.get('visible'))} | {format_rect(item['reference_visible'])} | "
                     f"{format_rect(item['target_visible'])} | {format_rect(item.get('after', {}).get('visible'))} |")
    lines += ['', 'The proportional reference is computed directly from the relative work-area edges, independently '
              'of the production planner. Free windows may deviate from it in keep-size mode. '
              'The planned outer rectangles and every actual SetWindowPos request are listed in trace.json.', '']
    for item in payload['windows']:
        label = item['window']
        lines += [f'## {label}', '']
        for event in payload['events']:
            if event['window'] != label:
                continue
            prefix = f"- {event['ms']} ms ({event['phase']}): "
            if event['event'] == 'SetWindowPos':
                lines.append(prefix + f"requested {format_rect(event['requested'])}, flags {event['flags']}")
            elif event['event'] == 'observed_change':
                actual = event['actual']
                lines.append(prefix + (f"visible {format_rect(actual['visible'])}, DPI {actual['dpi']}, snapped {actual['snapped']}"
                                       if actual else 'window no longer exists'))
            elif event['event'] == 'wait_begin':
                lines.append(prefix + f"result check begins, remaining budget {event['budget_ms']} ms")
        lines.append('')
    for key in ('prepare_result', 'result', 'undo', 'error'):
        if key in payload:
            lines += [f'{key}: {payload[key]}', '']
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', required=True, help='ID of an existing pair or cycle action')
    parser.add_argument('--prepare-action', help='optionally swap once to the other large monitor first; also reverted')
    parser.add_argument('--execute', action='store_true', help='execute once, measure for 2 seconds, then attempt Undo')
    parser.add_argument('--output', type=Path, default=Path('artifacts') / f'swap-trace-{datetime.now():%Y%m%d-%H%M%S}')
    args = parser.parse_args()
    if args.prepare_action and not args.execute:
        parser.error('--prepare-action requires --execute')
    initialize_dpi()
    config, warning = load_config(config_path())
    if warning:
        raise RuntimeError(warning)
    action = next(a for a in config.actions if a.id == args.action and a.enabled and a.type in ('pair', 'cycle'))
    displays = MonitorService()
    layout = displays.enumerate()
    # Emulate the running application's exclusion of its own windows.
    options = {'include_minimized': config.app.include_minimized,
               'excluded': [*config.excluded_executables, 'MonitorSwap.exe', 'MoniRondo.exe']}
    base = WindowService(**options)
    try:
        windows = base.enumerate(layout)
    finally:
        base.close()
    plan = plan_moves(action, layout, windows, mode=config.app.geometry_mode)
    trace = Trace(layout, windows)
    payload = {'version': __version__, 'mode': config.app.geometry_mode, 'action': action.id,
               'executed': args.execute, 'monitors': [dict(index=i, device=m.device, dpi=m.dpi,
               bounds=rect_data(m.bounds), work=rect_data(m.work)) for i, m in enumerate(layout)], 'windows': []}
    payload['windows'] = describe_plan(plan, trace, layout)
    if args.execute:
        engine = SwapEngine()
        service = traced_service(trace, **options)
        history = []
        try:
            with trace:
                try:
                    if args.prepare_action:
                        prepare = next(a for a in config.actions if a.id == args.prepare_action and a.enabled
                                       and a.type in ('pair', 'cycle'))
                        trace.phase = 'prepare'
                        started = time.monotonic()
                        prepared = engine.run(prepare, displays, service, config.app.geometry_mode)
                        if prepared.entries:
                            history.append((prepared.entries.copy(), engine.undo_layout.copy()))
                        payload['prepare_result'] = {'moved': prepared.moved, 'skipped': prepared.skipped,
                                                     'errors': prepared.errors}
                        time.sleep(max(0, 2 - (time.monotonic() - started)))
                        plan = plan_moves(action, layout, service.enumerate(layout), mode=config.app.geometry_mode)
                        payload['windows'] = describe_plan(plan, trace, layout)
                    trace.phase = 'swap'
                    started = time.monotonic()
                    result = engine.run(action, displays, service, config.app.geometry_mode)
                    if result.entries:
                        history.append((result.entries.copy(), engine.undo_layout.copy()))
                    payload['result'] = {'moved': result.moved, 'skipped': result.skipped, 'errors': result.errors}
                    time.sleep(max(0, 2 - (time.monotonic() - started)))
                    for move, item in zip(plan.moves, payload['windows'], strict=True):
                        item['after'] = trace.raw(move.before.hwnd) or {}
                finally:
                    payload['undo'] = []
                    while history:
                        trace.phase = f'undo-{len(history)}'
                        engine.undo_entries, engine.undo_layout = history.pop()
                        undo = engine.run(SwapAction('trace-undo', 'Revert diagnostics', 'undo'), displays, service)
                        payload['undo'].append({'moved': undo.moved, 'skipped': undo.skipped, 'errors': undo.errors})
                        time.sleep(.2)
        except Exception as exc:
            payload['error'] = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            service.close()
            payload['events'] = sorted(trace.events, key=lambda e: e['ms'])
            write_report(args.output, payload)
    else:
        payload['events'] = []
        write_report(args.output, payload)
    print(args.output.resolve() / 'report.md')
    print(json.dumps({key: payload[key] for key in ('result', 'undo') if key in payload}, ensure_ascii=False))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
