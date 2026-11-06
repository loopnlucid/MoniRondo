"""Read-only capture timings, without window titles or movements."""
from statistics import median
from time import perf_counter

from monirondo.windows.monitors import MonitorService
from monirondo.windows.native import initialize_dpi
from monirondo.windows.window_service import WindowService

initialize_dpi()
displays = MonitorService()
windows = WindowService(include_minimized=False)
try:
    layout_times, capture_times = [], []
    for _ in range(10):
        start = perf_counter()
        layout = displays.enumerate()
        layout_times.append((perf_counter() - start) * 1000)
        start = perf_counter()
        captured = windows.enumerate(layout)
        capture_times.append((perf_counter() - start) * 1000)
    print(f'Monitors: {len(layout)}, eligible windows: {len(captured)}')
    print(f'Full monitor query median: {median(layout_times):.2f} ms')
    print(f'Window snapshot median: {median(capture_times):.2f} ms')
finally:
    windows.close()
