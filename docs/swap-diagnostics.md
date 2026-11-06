# Measuring a window swap

`scripts/trace_swap.py` records a targeted diagnostic run. It uses the same planner, the same engine and the same Win32 adapters as the current source tree. The measurement runs as its own process; it does not instrument an already running EXE. No window titles, document names or full program paths are read. The recording names program base names such as `putty.exe`.

The diagnostics capture:

- Current outer and visible window bounds, Windows snap state and window DPI.
- Monitor resolution and usable work area in physical pixels.
- An independent proportional reference based on the work-area edges, plus the production plan that was actually computed.
- Every `SetWindowPos` request sent to Windows with position, size and flags; additionally `SetWindowPlacement` requests.
- Actual geometry changes during an observation interval of two seconds. The observer polls the windows roughly every 10 ms; very short intermediate states can fall between two polls.
- The start of the result check per window and the waiting budget still available at that point.
- The result and safe Undo attempts. Windows that appear during the run or are replaced by other identities are excluded from the diagnostic run.

## Checking the calculation only

In the project folder with an existing Python environment:

```powershell
.\.venv\Scripts\python.exe scripts/trace_swap.py --action cycle-forward --output artifacts/swap-plan
```

Without `--execute`, no windows are moved. The action ID must exist and be enabled in the current configuration. Its name and direction may have been changed by the user, so do not infer the spatial direction from the ID.

## Measuring an actual swap

```powershell
.\.venv\Scripts\python.exe scripts/trace_swap.py --action cycle-forward --execute --output artifacts/swap-trace
```

This runs the configured action once with the currently eligible windows, observes the results for two seconds and then attempts Undo. Leave windows and monitors unchanged during the measurement. Undo skips windows that were changed or closed in the meantime; a complete revert is confirmed in the report or listed as a deviation.

Optionally, another action can prepare the starting position. Both steps are then reverted via Undo:

```powershell
.\.venv\Scripts\python.exe scripts/trace_swap.py --action cycle-backward --prepare-action cycle-backward --execute --output artifacts/swap-trace-via-other-monitor
```

## Reading the report

The output folder contains `report.md` and `trace.json`. The Markdown report contains a planned-vs-actual table and a timeline per window. The JSON additionally contains all raw data and the actual API parameters. With asynchronous delivery, a successful return value of `SetWindowPos` only confirms that the request was accepted; what matters are the rectangles measured later.

## Measurements on 2026-10-22 with version 1.0.3

With an explicit diagnostic run, the applications actually present were examined: Vivaldi on the left and two PuTTY windows on the right, plus the other eligible windows. Tested were the direct route from the 2560×1440 monitor to the 1920×1080 monitor and the route via the 1920×1200 monitor. The small monitor uses 125 % scaling, the two large ones 100 %; its usable work area is 1920×1020 pixels.

- The independent reference and the production plan both yielded 960×510 visible pixels for the two right-hand windows; target positions (960, 0) and (960, 510).
- In reality, both PuTTY windows were first enlarged to 1195×621 visible pixels and shifted during the DPI change. In the direct run they were temporarily at (843, -55) and (843, 455), i.e. 111 pixels of vertical overlap. Windows still reported both as snapped.
- In these two runs, the existing follow-up correction took effect. After two seconds both PuTTY windows were exactly 960×510 pixels and at the intended position. All seven windows were restored in each Undo step without reported errors.
- The permanently wrong state previously observed by the user was therefore not yet reproduced. These measurements do not prove a complete fix. For a difference between this diagnostic run and a normal hotkey run, the specific hotkey run has to be observed separately.

Reports of this session: `artifacts/swap-diagnosis-real` and `artifacts/swap-diagnosis-via-other-monitor` (local, not part of the repository). The diagnostics change neither the configuration nor the installed EXE.

## Fix and re-check with version 1.0.4

A separate regression test revealed a sequencing defect in the previous result check: the window processed first could use up the entire time budget and thus prevent later corrections. Shared verification rounds fix this defect; a real Qt window with an unachievable minimum height guards the other three tiled windows against it.

The real diagnostics were repeated with the changed code for both monitor routes. Both PuTTY windows again reached exactly 960×510 visible pixels at the intended positions. All seven windows were restored in each Undo step without reported errors. Reports: `artifacts/swap-diagnosis-1.0.4-direct` and `artifacts/swap-diagnosis-1.0.4-via-other-monitor`.

Since version 1.0.4, the regular EXE also logs `geometry_corrected` and `geometry_checked` with HWND, planned/actual rectangles, number of corrections and final status. This makes it possible to investigate a deviation of an actual hotkey run from its own log. Window titles are still neither read nor stored.
