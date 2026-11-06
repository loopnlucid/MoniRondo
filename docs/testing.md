# Test record

Environment of the recorded runs: Windows 11 Build 26200, Python 3.12.10 x64, Qt/PySide6 6.12.0. The automated pytest suite moves only its own test windows. Separate, explicitly approved diagnostic runs with the user's applications are listed separately below.

## Multilingual UI and open-source release 1.2.0

Date: 2026-11-06.

- Regular build check run: **154 passed, 9 native move tests deliberately skipped**, exit code 0. Ruff and mypy without findings (21 source files). The window move logic was not changed; only user-visible texts now come from the translation catalogs.
- Pure core without PySide6 (as in the Linux CI job): **134 passed, 5 skipped**.
- Translation catalogs: identical keys and placeholders in all four languages, no accidental Qt mnemonics, English fallback, unknown languages rejected. Hotkey labels checked per language.
- Configuration: new profiles start in English; a profile without a stored language (all releases before 1.2.0) keeps German; an unsupported language is treated as a damaged file and backed up.
- Live switch with the real controller (private profile, no hotkeys, read-only native capture): English → German → French → English rebuilds the settings window, keeps the selected tab and translates the tray menu.
- All settings tabs and the action editor were rendered in every language with `scripts/preview_ui.py` and checked visually for cut-off text. A `&` in "Actions & hotkeys" turned into a Qt mnemonic and was replaced.
- Finished `MoniRondo.exe` 1.2.0: isolated startup, native capture, tray, hotkey message path and shutdown passed. The bundle contains the four JSON catalogs and Qt's `qtbase_de/es/fr` translations.

## New icon 1.1.1

- The provided `MoniRondo_Minimal_Teal.svg` was copied byte for byte to `assets/icon.svg` and into the runtime resources.
- The actual ICO was checked visually on light and dark taskbars and in the settings window as a Qt preview. All nine sizes (16/20/24/32/40/48/64/128/256 pixels) are included. The nine icon images embedded in the EXE and the shipped runtime ICO match the generated ICO byte for byte; the shipped SVG matches the original.
- Regular build check run: **136 passed, 9 native move tests deliberately skipped**, exit code 0. Ruff and mypy without findings (20 source files).
- Finished `MoniRondo.exe` with version resource 1.1.1: isolated startup, native capture, tray, hotkey message path and shutdown passed. No window move action was triggered.

## Rename 1.1.0 – MoniRondo

- Regular build check run: **136 passed, 9 native move tests deliberately skipped**, exit code 0. Ruff and mypy without findings (20 source files). The window move logic was not changed for the rename.
- Regression test with an existing MonitorSwap profile: a custom key combination, a changed cycle direction, the size mode, the minimized setting and stored monitor identities are read back directly under MoniRondo. No second profile folder is created. The instance lock and the autostart ID stay compatible.
- The new SVG/ICO icon was checked visually at the actual image sizes on light and dark taskbars, including 16 and 20 pixels. The ICO contains 16/20/24/32/40/48/64/128/256 pixels. The settings including the new name and logo were checked as a Qt preview.
- Finished `MoniRondo.exe`: isolated startup, native capture, tray, hotkey message path and shutdown passed. Product name, original file name and version resource 1.1.0 checked. All nine embedded Windows icon images match the new ICO byte for byte; the shipped runtime icon matches as well. The embedded Python code contains the new brand and the retained profile ID.

## Fixes 1.0.4

- Full suite including native moves: **144 passed**, exit code 0, 19.14 seconds. Ruff and mypy without findings (20 source files).
- Before the change, the time-budget defect was reproduced deterministically: a window that was checked first and refused permanently used up 800 ms; two quarter windows queued later received no correction and stayed too large. The same regression test passes with shared verification rounds. Every window gets its limited correction attempts within the same 800 ms.
- Real Qt regression with four own windows: the three-way split plus a window processed first with a minimum height of 1000 logical pixels. On the 125 % monitor this minimum height cannot be met. The three tiled windows still reach their target rectangles; only the unachievable free geometry is reported as a deviation. Both DPI directions, Undo and another round trip pass.
- Deterministic checks also cover a size change that only happens after 85 ms, a target DPI that is only reached after 250 ms, and the isolation of a capture error to its own window.
- Separate real diagnostics with the seven existing user windows, including Vivaldi and two PuTTY windows: direct swap to the small monitor and a swap via the other large monitor, two seconds of observation each and a complete Undo without reported errors. The two PuTTY windows reached (960, 0) / (960, 510), each 960×510 visible pixels. These diagnostics use the current program code in a separate process; they do not instrument the running older EXE.
- The measured DPI-related enlargement and the proven time-budget defect are separate findings. The two real diagnostic runs did not reproduce a permanently wrong final state. From this version on, the regular hotkey execution therefore logs planned/actual rectangles, the number of corrections and the final status in order to attribute a remaining user case.
- Regular build check run: **135 passed, 9 native move tests deliberately skipped**, exit code 0. The finished EXE passed the isolated startup/hotkey smoke test. Version resource 1.0.4, x64 GUI subsystem and DPI manifest were checked; the embedded Python code objects actually contain the shared result check including its calls for swap and Undo.

## Fixes 1.0.3

- Full suite including native moves: **139 passed**, exit code 0, 16.45 seconds. Ruff without findings; mypy without findings in 20 source files.
- The reported three-way layout was reproduced with three real Qt windows: left 50 % width/100 % height, top right and bottom right one quarter each. When swapping from the large 100 % monitor to the small 125 % monitor, Qt changed the size again after the first native move; the previous result check reported no error despite the oversized visible bounds. With the fix, the DWM visible bounds on the target match to within 4 physical pixels.
- The Qt test swaps to the small monitor, undoes to the large monitor and performs another complete round trip. Each phase checks three moved windows without errors and checks the actual visible bounds again after another 150 ms. The Qt event loop and the move worker run separately, as in the program. No simulated DPI handling and no moves of user windows.
- Deterministic tests cover a geometry that matches initially and is later enlarged by DPI handling, actually changed frames, at most two correction attempts with a minimum size, and no correction when the window identity changed. Remaining layout deviations are reported; Undo uses the actual after state.
- The previous native checks for normal, maximized and both minimized states as well as half-screen tiles and Undo still pass. Shell Snap group membership remains outside these tests.
- The regular build check run passed with **132 tests and 7 deliberately skipped native move tests**, exit code 0. The finished EXE passed the isolated startup test including native capture, hotkey message path, tray and shutdown; no move action was triggered.

## Fixes 1.0.2

- Full suite: **133 passed**, exit code 0, 10.20 seconds. Ruff and mypy without findings (20 source files).
- Regression case: a normal/snapped window with visible half-screen geometry but a different large restore position. Planning uses the current geometry; the differing latent Snap metadata does not block normal Undo.
- Pure tests cover half, quarter and third tiles, both size modes, negative coordinates, different DPI and invisible frames. Repeated cycles keep the tiling without drift.
- Native tests on the three existing monitors: two own half-screen windows each are cycled and restored, in keep-size and proportional mode. DWM visible bounds are checked on the target. The differing pre-snap restore position is simulated in the adapter; the HWND/DWM/SetWindowPos geometry is real. Newly created test windows wait for their asynchronous DWM/desktop assignment.
- No keyboard/mouse simulation and no private Snap APIs. Actual shell Snap group membership is neither reconstructed nor reported as tested.

## Fixes 1.0.1

- Full suite: **102 passed**, exit code 0, 12.32 seconds, including native swaps on the three existing monitors. Ruff and mypy without findings (20 source files).
- New dedicated Win32 hotkey window checked with an active Qt native event filter, hidden settings and queued Qt delivery. The test delivers a WM_HOTKEY message to its own registered window; it generates no keyboard input and moves no user windows. The actual physical key combination while a foreign application has focus remains a manual check.
- A hotkey pressed during a re-detection stays queued and runs exactly once afterwards. A running swap still never starts a second one in parallel.
- Swap and Undo send all move requests before the first waiting phase. A deterministic test with ten delayed windows limits the total waiting budget to 0.8 seconds instead of 0.8 seconds per window; window capture and native API time come on top.
- Read-only profiling in that session: three monitors, nine eligible windows; full monitor query median 0.57 ms, window snapshot 7.91 ms (ten measurements each). The measurement moved no windows.
- The isolated background start also checks the hotkey message path with a probe ID that has no window action assigned. The check therefore stays independent and harmless even next to a running older user instance.

## Original test state 1.0.0

- Full suite including native moves: **96 passed**, process exit code 0, 8.00 seconds in the final development run.
- Ruff: successful, no findings. mypy: successful, 19 source files without findings.
- Native moves: three active monitors, a pair between the first and last display, both cycle directions and Undo for each. All four states passed: normal, maximized, minimized, and minimized with restore to maximized. Topmost, the order of the own test windows and the unchanged global focus were checked.
- Physical layouts present: 1920×1200 at (-1920,-1211), 1920×1080 at (0,0), 2560×1440 at (0,-1440). Effective DPI: 96 / 120 / 96 (100 % / 125 % / 100 %). Device identities available for all three displays.
- Real RegisterHotKey collision between two processes: passed, without simulated keystrokes. Mutex and local IPC of a second instance: passed.
- Background start from source with a separate user profile: passed. The first EXE smoke test found a Python 3.12 type annotation evaluated at import time; the error is fixed and covered by its own import test. The fixed EXE smoke test passed startup, native capture, tray and automatic shutdown with exit code 0.
- EXE resources checked: Windows GUI subsystem, `asInvoker` and embedded `PerMonitorV2`. The build contains only Qt Core, Gui, Widgets and Network plus the qwindows/qico plugins; no QtPdf/WebEngine/VirtualKeyboard runtime.
- Final smoke test of the complete release: successful, exit code 0. Native capture reported three monitors and 13 eligible windows; no move action was triggered. ZIP integrity and the presence of the Python runtime, the own source code and the LGPL source archives passed.
- The UI was checked visually from rendered Qt previews. Offscreen Qt checks run in isolated processes so that their GUI lifetime does not mix with the native Win32 tests.
- Regular build check run: **92 passed, 4 native move tests deliberately skipped**, exit code 0. The four move tests are enabled explicitly with `--run-native-moves`. Qt GUI tests use a regular event loop with DeferredDelete; three targeted repetitions of the previously conspicuous test teardown each ended with code 0.

## Automatically covered cases

- Two to eight monitors, pair actions with uninvolved displays, both cycle directions, fixed subsets, a unique move per window.
- Different work-area sizes, negative coordinates, portrait mode and workspace offsets for taskbars at the top/left. Repeated conversion without drift.
- Owner/dialog routes, several windows per process, normal/maximized/minimized states, topmost and focus in the fake adapter.
- Undo with closed, changed and reused windows and missing monitors; 500 swap/Undo pairs with 32 windows.
- Hotkey conflicts, existing binding kept after an error, MOD_NOREPEAT, 500 failed registrations without additional active registrations.
- Configuration migration, corrupt JSON, unknown future schema, atomic write failure, language default and migration.
- Translation catalogs: identical key sets and placeholders in every language, English fallback, hotkey labels per language, the settings window and action editor built in every language.
- Native Win32 structure sizes, active display paths and read-only window capture.
- Qt hotkey editor and rendering for eight displays; tests use an offscreen renderer.

## Manual / hardware-dependent matrix

| Case | Status |
|---|---|
| Own test windows on the three local monitors: pair, both cycles and Undo | Passed |
| Normal / maximized / minimized / minimized with restore-to-maximized | Passed |
| Windows 10, clean VM without Python | Open; no suitable VM available |
| Browser / terminal / Electron in real use | Targeted approved diagnostics with Vivaldi, PuTTY, Notepad, Docker Desktop and Windows Terminal including Undo passed; long-term use and Office open |
| Mixed DPI | 100 % / 125 % with own Win32 and Qt windows passed, including the three-way split and Undo; 150 % / 200 % on hardware open |
| Taskbar at top/left/right | Conversion automated; the real Windows configuration was not changed |
| Hotkey with a foreign focused application and a system-wide conflict | System-wide registration conflict passed; actual keyboard use with a foreign app open |
| Virtual desktop switch | Filter implemented via documented COM; interactive desktop switch open |
| Autostart after a real sign-in | Open; the user registry is not changed for tests |
| Explorer restart, lock/resume, RDP, docking | Open; the running user session is not interrupted |
| Admin app, exclusive full screen, fixed app minimum sizes | Open; limits documented |

## Commands

See README and CONTRIBUTING. A normal pytest run skips native move tests; `--run-native-moves` enables them. Inside restrictive sandboxes, EnumWindows can fail with error 1008. This native check needs access to the current Windows desktop; that is no reason to swallow errors or to report a hardware test as passed.
