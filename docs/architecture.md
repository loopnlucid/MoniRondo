# Architecture

`models`, `geometry`, `planner`, `engine`, `config`, `hotkeys` and `i18n` contain platform-independent data models and logic. `windows` implements the Win32 adapters, `ui` the presentation. `app` wires these layers together.

## Data flow

1. The tray, the UI or `WM_HOTKEY` passes an action ID to the controller.
2. Exactly one Qt worker creates its own COM/Windows adapters. The UI stays responsive; further triggers are discarded meanwhile. The engine additionally holds a non-blocking lock.
3. The worker reads the active display paths and takes a complete window snapshot before the first move. The pure planner builds a bijective monitor mapping and at most one move per HWND.
4. Display layout and window state are checked again before every move. Native changes use no Z-order requests and no input simulation. All moves are submitted first; then all results are checked in shared verification rounds with a budget of 800 ms plus API/capture overhead. A difficult window therefore delays neither the other move requests nor their follow-up corrections.
5. The actual before/after states form the Undo set. Results reach the UI only through Qt signals. All COM pointers are released on the thread that created them.

## Interfaces and units

`MonitorInfo` holds the identity, the temporary GDI name, physical monitor and work areas, and the available DPI. `WindowSnapshot` holds identity attributes, window state, placement, topmost flag, owner and Z index. `MovePlan` is immutable. `SwapResult` holds counts, user-facing errors and the Undo entries that were actually observed.

`Displays` and `Windows` are protocols for native or fake adapters. Pure functions use only `Rect` in physical pixels. Workspace conversion is explicit; Qt geometry is used for drawing only. For normal windows the current outer Win32 rectangle determines the move. The separately captured restore geometry is used for minimized/maximized windows. Optionally captured DWM visible bounds are used to detect halves, quarters and thirds. Their edges are transferred proportionally to the target work area and then extended by the DPI-adjusted invisible frame. SetWindowPos always receives the outer screen rectangle.

After a DPI change, the first matching geometry is not yet the final result: Qt and other applications may then process `WM_DPICHANGED` and set a different size. The result check therefore waits at least 150 ms after the move and for 60 ms of unchanged geometry. For per-monitor-aware windows the target DPI must also have been observed for at least 50 ms. If the result deviates, at most two corrections are made per window; detected tiles use the DWM frame actually measured on the target. Contradictory frames during a DWM update do not consume an attempt. All steps stay within the shared waiting budget. Windows that already match are kept under observation for the rest of the check so that late changes are noticed. The engine reports remaining deviations of normal windows and still stores the actually observed position for Undo.

## Internationalization

`i18n.py` loads JSON catalogs from `src/monirondo/locales/<code>.json` (`en`, `de`, `es`, `fr`). Keys are stable message IDs; values use `str.format` placeholders such as `{app}`. English is the source of truth and the fallback for missing keys. The module has no Qt dependency, so the pure core (planner and engine errors, hotkey labels, default action names) can be translated and tested without PySide6. The active language is stored as `app.language` in the configuration. Profiles from releases before 1.2.0, which were German-only, keep German; new profiles start in English.

When the language is saved in the General settings, the controller swaps Qt's own `qtbase_<code>` translator and rebuilds the settings window and tray menu immediately. Action names that the user stored are not translated. The diagnostic report is always English so that it can be pasted into bug reports.

## Lifecycle

A manual start shows the settings; `--background` starts in the tray. A mutex bound to the user and session selects the first instance. A local named pipe (`QLocalServer`) that only the user can access asks the existing instance to show its settings. `APP_NAME` defines the visible brand MoniRondo; `COMPAT_ID` keeps the profile, autostart value and IPC at the former technical name MonitorSwap. Old and new versions therefore do not compete for hotkeys and share the same settings. A dedicated invisible Win32 window with its own WndProc receives hotkeys and forwards them to the controller through an explicitly queued Qt signal. The Qt native event filter only handles display and session events. Actions triggered during a re-detection run afterwards.

Display, device, resume and session signals trigger a debounced re-capture. QSystemTrayIcon re-registers after an Explorer restart. Quitting waits for a running worker, unregisters hotkeys and saves atomically. When the Windows session ends normally, Qt handles the native session protocol; the configuration is already written on every user change.

## Build

PyInstaller creates an `onedir`/`windowed` build with `asInvoker`, PerMonitorV2 and version resources. The icon files are generated from SVG with Qt; the ICO contains nine resolutions (16/20/24/32/40/48/64/128/256). `preview_brand.py` shows the actual ICO images on light and dark taskbars, `preview_ui.py` renders every settings tab in every UI language. Libraries and license texts stay replaceable in the release folder. GitHub Actions checks Windows and the platform-independent core on Linux; the CI runner does not replace interactive hardware tests.
