# Changelog

All notable changes to MoniRondo are documented here. The project follows [Semantic Versioning](https://semver.org/).

## 1.2.0 – 2026-11-06

- First open-source release on GitHub.
- The user interface is now multilingual: **English** (default), **German**, **Spanish** and **French**. The language can be changed under **General → Language** and takes effect immediately, including the tray menu, hotkey key names and Qt's standard dialogs.
- Existing profiles from earlier, German-only releases keep German; new profiles start in English. Settings, hotkeys and monitor assignments are reused unchanged.
- Translations are plain JSON catalogs in `src/monirondo/locales/`; tests ensure every language has the same keys and placeholders as English.
- The diagnostic report is always English so that it can be attached to bug reports.
- The Python package was renamed from `monitorswap` to `monirondo`. The `monitorswap` launcher alias still works; profile path, autostart value and instance lock keep the former technical name.
- All documentation, code comments and developer tooling are now in English. Added contribution guidelines, a security policy, a code of conduct and issue/PR templates.
- `scripts/preview_ui.py` renders every settings tab in every language for visual checks.

## 1.1.1 – 2026-10-22

- Adopted the provided `MoniRondo_Minimal_Teal.svg` as the new program and tray icon: a white monitor with circular arrows on a teal background, transparent rounded corners.
- Regenerated the Windows ICO with nine sizes from 16 to 256 pixels for the EXE, tray and settings.

## 1.1.0 – 2026-10-22

- Renamed the app to **MoniRondo**: windows, tray, notifications, diagnostics, EXE, version resources and release archives carry the new name.
- New icon with a monitor, teal-violet circular arrows and a dark background. The ICO contains nine sizes from 16 to 256 pixels, including 20 pixels for the 125 % taskbar. The icon also appears in the settings header.
- Kept the existing user profile, autostart ID and shared instance lock. Existing hotkeys, geometry mode and monitor assignments are preserved. A regression test checks that an existing profile with a custom key combination is reused.
- The Python package and the previous launcher alias stay compatible; the launcher alias `monirondo` was added.

## 1.0.4 – 2026-10-22

- Observe and correct all moved windows in shared verification rounds, also for Undo. A refusing application can no longer use up the correction budget of all later windows.
- On a DPI change, take the reported window DPI of per-monitor-aware applications and a longer stable phase into account. Rectangles that match briefly before the application rescales are no longer treated as final too early. Temporarily contradictory DWM frames do not consume correction attempts.
- Report remaining size/position deviations for free normal windows too. Log planned/actual rectangles and the number of corrections so that deviations in actual hotkey runs can be traced.
- Proved the time-budget defect with a failing regression test before the fix; additionally test the three-way split with a real Qt window whose minimum height cannot be met on the small monitor.
- Added targeted diagnostics with an independent reference calculation, the actual Win32 requests, continuous geometry observation and a subsequent Undo.

## 1.0.3 – 2026-10-22

- Wait for later size changes caused by the DPI change and correct the target tiling using the window frames actually measured on the target. In particular, the three-way layout "left half, two quarters on the right" is now preserved when swapping from 100 % to 125 %.
- Limit the correction to at most two attempts within the shared waiting budget. Report unachievable tiles, e.g. because of an application minimum size, as a deviation and record the actual position for Undo.
- Added a real Qt regression scenario with three own windows, both DPI directions, Undo and another round trip; additionally test delayed DPI resizing, changed frames, minimum sizes and HWND identity changes deterministically.

## 1.0.2 – 2026-10-22

- Move normal and snapped windows based on their current window rectangle. The differing restore position is only used for minimized and maximized windows.
- Transfer detected screen halves, quarters and thirds to the target work area based on the visible DWM bounds, accounting for invisible frames and different DPI, also in "keep size where possible" mode.
- For normal windows, Undo restores the arrangement that was actually visible before and no longer mistakes changed Snap restore metadata for a manual position change.
- Regression tests for restore sizes that differ from before snapping, repeated cycles and native half-screen geometry with Undo. Windows-internal Snap groups are not reconstructed.

## 1.0.1 – 2026-10-22

- Receive global hotkeys through a dedicated, persistent Win32 message window and forward them to the action as a Qt signal. A receive counter and technical log entries extend the diagnostics.
- Run an action triggered during a re-detection after the detection; parallel swaps are still prevented.
- Submit all moves before checking results. Swap and Undo share one waiting budget instead of waiting up to 800 ms per window in sequence.
- The isolated EXE startup test also checks the hotkey message path without triggering a window action. Test IPC and startup check run independently of an already running user instance.
- The release lives in its own version folder; settings are reused.

## 1.0.0 – 2026-10-22

- German PySide6 tray app with monitor overview, action management and diagnostics.
- Arbitrary monitor pairs, dynamic and fixed cycles, safe single-step Undo.
- Global hotkeys with conflict handling, per-user autostart and single instance.
- Native display identities, window states, workspace coordinates and virtual desktops.
- Automated tests, Windows build and release ZIP with licenses.
