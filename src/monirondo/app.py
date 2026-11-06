from __future__ import annotations

import argparse
import ctypes as C
import logging
import platform
import sys
from copy import deepcopy
from ctypes import wintypes as W
from importlib.resources import files
from logging.handlers import RotatingFileHandler
from typing import Any

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QByteArray,
    QLibraryInfo,
    QObject,
    Qt,
    QThread,
    QTimer,
    QTranslator,
    QUrl,
    Signal,
)
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from monirondo import APP_NAME, COMPAT_ID, __version__
from monirondo.config import AppSettings, Configuration, config_path, load_config, log_dir, save_config
from monirondo.engine import SwapEngine
from monirondo.hotkeys import hotkey_label
from monirondo.i18n import current, set_language, tr
from monirondo.models import Hotkey, MonitorInfo, SwapAction, SwapResult
from monirondo.planner import monitor_mapping
from monirondo.ui.main_window import STYLE, MainWindow

log = logging.getLogger(__name__)


def install_qt_translator(app: QApplication, language: str, previous: QTranslator | None) -> QTranslator | None:
    """Swap Qt's own translations (standard dialogs, key names) to match the UI language."""
    if previous is not None:
        app.removeTranslator(previous)
        previous.deleteLater()
    if language == "en":
        return None
    translator = QTranslator(app)
    if translator.load(f"qtbase_{language}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
        return translator
    translator.deleteLater()
    return None


class NativeEvents(QAbstractNativeEventFilter):
    def __init__(self, owner: Controller) -> None:
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type: QByteArray | bytes | bytearray | memoryview[int], message: int) -> tuple[bool, int]:
        try:
            msg = W.MSG.from_address(int(message))
            if msg.message in (0x007E, 0x001A, 0x0219, 0x0218, 0x02B1):
                self.owner.refresh_timer.start()
        except Exception:
            log.exception("native_event_failed")
        return False, 0


class NativeJob(QThread):
    completed = Signal(object, object, str, int)

    def __init__(self, engine: SwapEngine, config: Configuration, action: SwapAction | None,
                 parent: QObject) -> None:
        super().__init__(parent)
        self.engine, self.config, self.action = engine, deepcopy(config), deepcopy(action)

    def run(self) -> None:
        from monirondo.windows.monitors import MonitorService
        from monirondo.windows.window_service import WindowService
        service = None
        try:
            monitors = MonitorService()
            service = WindowService(self.config.app.include_minimized, self.config.excluded_executables)
            result = self.engine.run(self.action, monitors, service, self.config.app.geometry_mode) if self.action else None
            layout = monitors.enumerate()
            count = len(service.enumerate(layout))
            self.completed.emit(result, layout, "", count)
        except Exception as exc:
            log.exception("native_job_failed")
            self.completed.emit(None, [], tr("status.native_failed", error=type(exc).__name__), 0)
        finally:
            if service:
                service.close()


class Controller(QObject):
    def __init__(self, app: QApplication, config: Configuration, warning: str = "",
                 qt_translator: QTranslator | None = None) -> None:
        super().__init__()
        from monirondo.windows.hotkey_window import HotkeyWindow
        self.app, self.config = app, config
        self.qt_translator = qt_translator
        self.engine = SwapEngine()
        self.job: NativeJob | None = None
        self.layout: list[MonitorInfo] = []
        self.hotkey_errors: dict[str, str] = {}
        self.refresh_pending = False
        self.pending_action: str | None = None
        self.quitting = False
        self.window_count = 0
        self.had_error = False
        self.icon = QIcon(str(files("monirondo").joinpath("resources/icon.ico")))
        app.setWindowIcon(self.icon)
        self._create_window()
        self.helper = QWidget()
        self.helper.setWindowTitle(f"{APP_NAME} native events")
        self.hwnd = int(self.helper.winId())
        self.hotkey_source = HotkeyWindow(self)
        self.hotkeys = self.hotkey_source.registry
        self.hotkey_source.triggered.connect(self.execute, Qt.ConnectionType.QueuedConnection)
        self.events = NativeEvents(self)
        app.installNativeEventFilter(self.events)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(350)
        self.refresh_timer.timeout.connect(self.refresh)
        self.tray = QSystemTrayIcon(self.icon, self)
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        self.register_initial()
        for screen in app.screens():
            screen.geometryChanged.connect(self.queue_refresh)
            screen.availableGeometryChanged.connect(self.queue_refresh)
        app.screenAdded.connect(self.screen_added)
        app.screenRemoved.connect(self.queue_refresh)
        # Resume/unlock and RDP session changes are delivered to the hidden native helper.
        try:
            from monirondo.windows.native import bind
            bind(C.WinDLL("wtsapi32"), "WTSRegisterSessionNotification", W.BOOL, W.HWND, W.DWORD)(self.hwnd, 0)
        except OSError:
            log.warning("session_notifications_unavailable")
        from monirondo.windows.autostart import command, current
        autostart_warning = ""
        if config.app.start_with_windows and current() != command():
            autostart_warning = tr("status.autostart_stale")
        self.start_warning = "\n".join(s for s in [warning, autostart_warning] if s)
        self.rebuild_views()
        QTimer.singleShot(0, self.refresh)

    def _create_window(self) -> None:
        """(Re)build the settings window; called again after a language change."""
        self.window = MainWindow(self.config)
        self.window.setWindowIcon(self.icon)
        self.window.refresh_requested.connect(self.refresh)
        self.window.run_requested.connect(self.execute)
        self.window.delete_requested.connect(self.delete_action)
        self.window.general_requested.connect(self.save_general)
        self.window.quit_requested.connect(self.quit)
        self.window.hidden_to_tray.connect(self.tray_hint)
        self.window.save_action = self.save_action
        self.window.open_logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir()))))

    def show_settings(self) -> None:
        self.window.show_settings()

    def apply_language(self, language: str) -> None:
        set_language(language)
        self.qt_translator = install_qt_translator(self.app, language, self.qt_translator)
        old = self.window
        visible, tab, geometry = old.isVisible(), old.tabs.currentIndex(), old.saveGeometry()
        old.allow_close = True
        old.hide()
        old.deleteLater()
        self._create_window()
        self.window.restoreGeometry(geometry)
        self.window.tabs.setCurrentIndex(tab)
        self.window.tabs.setEnabled(self.job is None)
        if visible:
            self.window.show_settings()
        self.rebuild_views()

    def screen_added(self, screen: Any) -> None:
        screen.geometryChanged.connect(self.queue_refresh)
        screen.availableGeometryChanged.connect(self.queue_refresh)
        self.queue_refresh()

    def queue_refresh(self, *args: Any) -> None:
        self.refresh_timer.start()

    def tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_settings()

    def register_initial(self) -> None:
        for action in self.config.actions:
            if action.enabled and action.hotkey:
                try:
                    self.hotkeys.replace(action.id, action.hotkey)
                except ValueError as exc:
                    self.hotkey_errors[action.id] = str(exc)

    def action_issue(self, action: SwapAction) -> str:
        if not action.enabled:
            return tr("actions.status.disabled")
        if action.type == "undo":
            return "" if self.engine.undo_entries else tr("actions.status.nothing_to_undo")
        try:
            monitor_mapping(action, self.layout)
        except ValueError as exc:
            return str(exc)
        return ""

    def rebuild_views(self) -> None:
        window = self.window
        self.tray.setToolTip(tr("tray.tooltip", app=APP_NAME))
        window.monitors = self.layout
        window.diagram.monitors = self.layout
        window.diagram.update()
        window.monitor_table.setRowCount(len(self.layout))
        from PySide6.QtWidgets import QTableWidgetItem
        for row, m in enumerate(self.layout):
            values = [f"{row + 1}" + (f" · {tr('monitors.primary')}" if m.primary else ""), m.name,
                      f"{m.bounds.width} × {m.bounds.height}",
                      f"{round(m.dpi / 96 * 100)} %" if m.dpi else tr("monitors.unknown"),
                      tr("monitors.stable") if m.stable else tr("monitors.session_only")]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(m.device if col == 0 else value)
                window.monitor_table.setItem(row, col, item)
        row = window.action_table.currentRow()
        window.action_table.setRowCount(len(self.config.actions))
        self.menu.clear()
        # Cycles first, then named pairs, then Undo.
        menu_actions = sorted(self.config.actions, key=lambda a: {"cycle": 0, "pair": 1, "undo": 2}[a.type])
        for i, action in enumerate(self.config.actions):
            issue = self.action_issue(action)
            status = issue or self.hotkey_errors.get(action.id, tr("actions.status.ready"))
            if action.type == "pair":
                nums = {m.id: str(n) for n, m in enumerate(self.layout, 1)}
                assignment = f"{nums.get(action.monitor_a_id, '?')} ↔ {nums.get(action.monitor_b_id, '?')}"
            elif action.type == "cycle":
                order = (tr("actions.assignment.spatial") if action.monitor_order == "dynamic_spatial"
                         else tr("actions.assignment.fixed", count=len(action.monitor_ids)))
                assignment = order + (" →" if action.direction == "forward" else " ←")
            else:
                assignment = tr("actions.assignment.last_swap")
            for col, value in enumerate([action.name, tr(f"actions.type.{action.type}"),
                                         assignment, hotkey_label(action.hotkey), status]):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                window.action_table.setItem(i, col, item)
        if row >= 0:
            window.action_table.selectRow(min(row, len(self.config.actions) - 1))
        for action in menu_actions:
            label = action.name + ("\t" + hotkey_label(action.hotkey) if action.hotkey else "")
            entry = QAction(label, self.menu)
            issue = self.action_issue(action)
            entry.setEnabled(not issue and self.job is None and not self.quitting)
            entry.setToolTip(issue or self.hotkey_errors.get(action.id, ""))
            entry.triggered.connect(lambda checked=False, aid=action.id: self.execute(aid))
            self.menu.addAction(entry)
        self.menu.addSeparator()
        self.menu.addAction(tr("tray.settings"), self.show_settings)
        self.menu.addAction(tr("tray.quit"), self.quit)
        self.menu.setToolTipsVisible(True)
        self.update_diagnostics()

    def update_diagnostics(self) -> None:
        # Deliberately English in every UI language: the report is meant to be pasted into bug reports.
        text = (f"{APP_NAME} {__version__}\nPython {platform.python_version()} ({platform.architecture()[0]})\n"
                f"Windows {platform.version()}\nUI language: {current()}\nActive monitors: {len(self.layout)}\n"
                f"Eligible windows: {self.window_count}\nActive global hotkeys: {len(self.hotkeys.active)}\n"
                f"Hotkey conflicts: {len(self.hotkey_errors)}\nUndo windows: {len(self.engine.undo_entries)}\n\n"
                f"Hotkey triggers received: {self.hotkey_source.received_count}\n\n"
                "No telemetry. No window titles in the log.\n"
                "Elevated apps, full screen, Snap groups and self-positioning apps may have limitations.\n"
                "MIT License and full third-party texts: LICENSE and LICENSES in the release folder.\n")
        if self.hotkey_errors:
            text += "\nHotkeys:\n" + "\n".join(f"{a.name}: {self.hotkey_errors[a.id]}" for a in self.config.actions if a.id in self.hotkey_errors)
        self.window.diagnostics.setPlainText(text)

    def refresh(self) -> None:
        if self.quitting:
            return
        if self.job:
            self.refresh_pending = True
            return
        self.start_job(None)

    def execute(self, action_id: str) -> None:
        if self.quitting:
            return
        self.update_diagnostics()
        if self.job:
            if self.job.action is None:
                self.pending_action = action_id
                log.info("action_queued_during_refresh action=%s", action_id)
            else:
                log.info("action_ignored_busy action=%s", action_id)
            return
        action = next((a for a in self.config.actions if a.id == action_id), None)
        if not action:
            return
        issue = self.action_issue(action)
        if issue:
            self.report(issue, error=True)
            return
        self.start_job(action)

    def start_job(self, action: SwapAction | None) -> None:
        self.window.tabs.setEnabled(False)
        self.window.status.setText(tr("status.swapping") if action else tr("status.detecting"))
        self.job = NativeJob(self.engine, self.config, action, self)
        self.job.completed.connect(self.job_completed)
        self.job.finished.connect(self.job_finished)
        self.job.start()
        self.rebuild_views()

    def job_completed(self, result: SwapResult | None, monitors: list[MonitorInfo], error: str, count: int) -> None:
        self.layout = monitors
        self.window_count = count
        log.info("native_capture monitors=%d windows=%d", len(monitors), count)
        for m in monitors:
            self.config.monitor_history[m.id] = {"device": m.device, "name": m.name,
                                                  "bounds": m.bounds.tuple(), "stable": m.stable}
        if error:
            self.had_error = True
            self.report(error, True)
        elif result:
            text = tr("status.result", moved=result.moved, skipped=result.skipped)
            if result.errors:
                text += " " + " ".join(dict.fromkeys(result.errors))
            self.report(text, bool(result.errors))
        else:
            self.window.status.setText(tr("status.summary", monitors=len(monitors), windows=count))
        if self.start_warning:
            self.report(self.start_warning, True)
            self.start_warning = ""
        self.rebuild_views()

    def job_finished(self) -> None:
        if self.job:
            self.job.deleteLater()
        self.job = None
        self.window.tabs.setEnabled(True)
        self.rebuild_views()
        if self.quitting:
            self.finish_quit()
        elif self.pending_action:
            action_id, self.pending_action = self.pending_action, None
            QTimer.singleShot(0, lambda: self.execute(action_id))
        elif self.refresh_pending:
            self.refresh_pending = False
            QTimer.singleShot(0, self.refresh)

    def report(self, text: str, error: bool = False) -> None:
        self.window.status.setText(text)
        if error or self.config.app.notify_on_success:
            self.tray.showMessage(APP_NAME, text, QSystemTrayIcon.MessageIcon.Warning if error else QSystemTrayIcon.MessageIcon.Information, 6000)

    def save_action(self, action: SwapAction) -> None:
        for other in self.config.actions:
            if other.id != action.id and action.hotkey and other.hotkey and action.hotkey.canonical == other.hotkey.canonical:
                raise ValueError(tr("hotkey.error.in_use"))
        old = next((a for a in self.config.actions if a.id == action.id), None)
        old_registration = self.hotkeys.active.get(action.id)
        self.hotkeys.replace(action.id, action.hotkey if action.enabled else None)
        previous = self.config.actions.copy()
        if old:
            self.config.actions[self.config.actions.index(old)] = action
        else:
            self.config.actions.append(action)
        try:
            save_config(config_path(), self.config)
        except OSError:
            self.config.actions = previous
            self.hotkeys.replace(action.id, old_registration[1] if old_registration else None)
            raise
        self.hotkey_errors.pop(action.id, None)
        self.rebuild_views()

    def delete_action(self, action_id: str) -> None:
        previous = self.config.actions.copy()
        self.config.actions = [a for a in previous if a.id != action_id]
        try:
            save_config(config_path(), self.config)
        except OSError as exc:
            self.config.actions = previous
            self.report(tr("status.delete_failed", error=exc), True)
            return
        self.hotkeys.replace(action_id, None)
        self.hotkey_errors.pop(action_id, None)
        self.rebuild_views()

    def save_general(self) -> None:
        from monirondo.windows.autostart import set_enabled
        old = deepcopy(self.config)
        w = self.window
        self.config.app = AppSettings(
            start_with_windows=w.autostart.isChecked(), close_to_tray=w.close_tray.isChecked(),
            notify_on_success=w.notifications.isChecked(), include_minimized=w.minimized.isChecked(),
            geometry_mode=w.mode.currentData(), tray_hint=w.tray_hint.isChecked(), language=w.language.currentData())
        self.config.excluded_executables = [s.strip() for s in w.exclusions.toPlainText().splitlines() if s.strip()]
        try:
            # Persist first: a disk error must not silently alter autostart.
            save_config(config_path(), self.config)
            set_enabled(self.config.app.start_with_windows)
        except OSError as exc:
            self.config.app, self.config.excluded_executables = old.app, old.excluded_executables
            try:
                save_config(config_path(), self.config)
            except OSError:
                log.exception("settings_rollback_failed")
            self.window.reload_general()
            self.report(tr("general.save_failed", error=exc), True)
            return
        if self.config.app.language != current():
            self.apply_language(self.config.app.language)
        self.report(tr("general.saved"))
        self.refresh()

    def tray_hint(self) -> None:
        if self.config.app.tray_hint:
            self.tray.showMessage(tr("tray.hint_title", app=APP_NAME), tr("tray.hint_body", app=APP_NAME))
            self.config.app.tray_hint = False
            self.window.tray_hint.setChecked(False)
            try:
                save_config(config_path(), self.config)
            except OSError:
                log.exception("tray_hint_save_failed")

    def quit(self) -> None:
        self.quitting = True
        self.engine.stop_requested.set()
        self.hotkeys.close()
        self.pending_action = None
        if self.job:
            self.window.status.setText(tr("status.quitting"))
        else:
            self.finish_quit()

    def finish_quit(self) -> None:
        try:
            save_config(config_path(), self.config)
        except OSError:
            log.exception("shutdown_save_failed")
        self.tray.hide()
        self.app.removeNativeEventFilter(self.events)
        self.window.allow_close = True
        self.window.close()
        self.helper.close()
        self.app.quit()

    def session_cleanup(self) -> None:
        self.engine.stop_requested.set()
        self.hotkey_source.close()
        if self.job and self.job.isRunning():
            self.job.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} – swap windows between monitors")
    parser.add_argument("--background", action="store_true", help="start in the notification area only")
    parser.add_argument("--smoke-test", action="store_true", help="check startup and quit automatically; moves no windows")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()
    if sys.platform != "win32":
        print(f"{APP_NAME} requires Windows 10/11 (64-bit).", file=sys.stderr)
        return 1
    from monirondo.windows.native import initialize_dpi
    initialize_dpi()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    import os

    from monirondo.windows.single_instance import SingleInstance
    instance = SingleInstance(f"{APP_NAME}-Smoke-{os.getpid()}" if args.smoke_test else COMPAT_ID)
    if not instance.primary:
        ok = instance.notify()
        instance.close()
        return 0 if ok else 2
    try:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / "monirondo.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logging.basicConfig(level=logging.INFO, handlers=[handler])
        config, warning = load_config(config_path())
        set_language(config.app.language)
        qt_translator = install_qt_translator(app, config.app.language, None)
        controller = Controller(app, config, warning, qt_translator)
        app.aboutToQuit.connect(controller.session_cleanup)
        instance.show_requested.connect(controller.show_settings)
        if not args.background and not args.smoke_test:
            controller.show_settings()
        if args.smoke_test:
            # Exercise the packaged native HWND -> queued Qt callback too. The probe
            # ID is deliberately absent from config.actions, so it cannot move windows.
            from monirondo.windows.native import bind, user32
            for number in range(24, 17, -1):
                try:
                    controller.hotkeys.replace("__smoke_probe__", Hotkey(("CTRL", "ALT", "SHIFT"), f"F{number}"))
                    break
                except ValueError:
                    continue
            else:
                raise RuntimeError("No free hotkey for the isolated startup test")
            identifier, key = controller.hotkeys.active["__smoke_probe__"]
            post = bind(user32, "PostMessageW", W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
            QTimer.singleShot(100, lambda: post(controller.hotkey_source.hwnd, 0x0312, identifier, 0))
            QTimer.singleShot(2500, controller.quit)
        result = app.exec()
        return 1 if args.smoke_test and (controller.had_error or controller.hotkey_source.received_count != 1) else result
    except Exception as exc:
        log.exception("startup_failed")
        if not args.smoke_test:
            QMessageBox.critical(None, tr("status.startup_failed", app=APP_NAME), str(exc))
        return 1
    finally:
        instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
