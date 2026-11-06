from collections.abc import Callable
from importlib.resources import files

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QCloseEvent, QColor, QFont, QIcon, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from monirondo import APP_NAME
from monirondo.config import Configuration
from monirondo.i18n import SUPPORTED, tr
from monirondo.models import MonitorInfo, SwapAction
from monirondo.ui.action_editor import ActionEditor

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #172b42; }
QMainWindow, QDialog { background: #f3f6fa; }
QLabel#brand { color: #10263e; font-size: 25pt; font-weight: 700; }
QLabel#subtitle { color: #50647c; }
QLabel#status { color: #205d58; background: #e2f1ed; border-radius: 7px; padding: 10px; }
QPushButton { background: white; border: 1px solid #cbd6e1; padding: 8px 15px; border-radius: 6px; }
QPushButton:hover { background: #e6eef7; border-color: #8aa8bc; }
QPushButton:disabled { color: #95a3b1; background: #eef1f5; }
QPushButton#primary { background: #17685f; border-color: #17685f; color: white; }
QPushButton#primary:hover { background: #12564e; }
QTabWidget::pane { border: 1px solid #d7e0e9; background: white; border-radius: 6px; }
QTabBar::tab { background: #e8eef5; padding: 11px 22px; margin-right: 3px; }
QTabBar::tab:selected { background: white; border-top: 3px solid #1c8073; }
QTableWidget { background: white; border: 1px solid #dce4ed; gridline-color: #e9eef5; selection-background-color: #dceee9; selection-color: #173f39; }
QHeaderView::section { background: #edf2f7; border: 0; padding: 9px; font-weight: 600; }
QLineEdit, QComboBox, QKeySequenceEdit, QPlainTextEdit, QListWidget { background: white; border: 1px solid #cbd6e1; border-radius: 4px; padding: 6px; }
QGroupBox { margin-top: 12px; padding: 14px; border: 1px solid #d1dce7; border-radius: 6px; }
"""


class MonitorDiagram(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.monitors: list[MonitorInfo] = []
        self.setMinimumHeight(190)
        self.setAccessibleName(tr("diagram.accessible_name"))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.monitors:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("diagram.empty"))
            return
        left, top = min(m.bounds.left for m in self.monitors), min(m.bounds.top for m in self.monitors)
        right, bottom = max(m.bounds.right for m in self.monitors), max(m.bounds.bottom for m in self.monitors)
        scale = min((self.width() - 32) / max(1, right - left), (self.height() - 32) / max(1, bottom - top))
        ox, oy = (self.width() - (right - left) * scale) / 2, (self.height() - (bottom - top) * scale) / 2
        for i, m in enumerate(self.monitors, 1):
            r = QRectF(ox + (m.bounds.left - left) * scale + 3, oy + (m.bounds.top - top) * scale + 3,
                       max(12, m.bounds.width * scale - 6), max(12, m.bounds.height * scale - 6))
            painter.setBrush(QColor("#e0f1eb" if m.primary else "#e7eef7"))
            painter.setPen(QPen(QColor("#1f8174" if m.primary else "#90aac3"), 2))
            painter.drawRoundedRect(r, 7, 7)
            painter.setPen(QColor("#123c39"))
            painter.setFont(QFont("Segoe UI", max(9, min(22, int(r.height() / 4))), QFont.Weight.DemiBold))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, str(i) + (" ★" if m.primary else ""))
        painter.end()


class MainWindow(QMainWindow):
    refresh_requested = Signal()
    run_requested = Signal(str)
    delete_requested = Signal(str)
    general_requested = Signal()
    quit_requested = Signal()
    hidden_to_tray = Signal()

    def __init__(self, config: Configuration) -> None:
        super().__init__()
        self.config = config
        self.monitors: list[MonitorInfo] = []
        self.statuses: dict[str, str] = {}
        self.allow_close = False
        self.setWindowTitle(tr("window.title", app=APP_NAME))
        icon = QIcon(str(files("monirondo").joinpath("resources/icon.ico")))
        self.setWindowIcon(icon)
        self.resize(1000, 760)
        self.setMinimumSize(760, 560)
        base = QWidget()
        layout = QVBoxLayout(base)
        layout.setContentsMargins(26, 22, 26, 18)
        header = QHBoxLayout()
        header.setSpacing(14)
        mark = QLabel()
        mark.setPixmap(icon.pixmap(48, 48))
        mark.setFixedSize(48, 48)
        header.addWidget(mark)
        title = QLabel(APP_NAME)
        title.setObjectName("brand")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)
        subtitle = QLabel(tr("window.tagline"))
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._monitors_tab()
        self._actions_tab()
        self._general_tab()
        self._diagnostics_tab()
        self.status = QLabel(tr("window.ready"))
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        footer = QHBoxLayout()
        hint = QLabel(tr("window.close_hint", app=APP_NAME))
        footer.addWidget(hint)
        footer.addStretch()
        quit_button = QPushButton(tr("window.quit", app=APP_NAME))
        quit_button.clicked.connect(self.quit_requested)
        footer.addWidget(quit_button)
        layout.addLayout(footer)
        self.setCentralWidget(base)

    def _page(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        self.tabs.addTab(page, title)
        return page, layout

    def _monitors_tab(self) -> None:
        _, layout = self._page(tr("tab.monitors"))
        intro = QLabel(tr("monitors.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.diagram = MonitorDiagram()
        layout.addWidget(self.diagram, 1)
        self.monitor_table = QTableWidget(0, 5)
        self.monitor_table.setHorizontalHeaderLabels([tr(f"monitors.column.{c}") for c in ("display", "name", "resolution", "scaling", "identity")])
        self._table(self.monitor_table)
        layout.addWidget(self.monitor_table, 1)
        refresh = QPushButton(tr("monitors.refresh"))
        refresh.clicked.connect(self.refresh_requested)
        layout.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignLeft)
        note = QLabel(tr("monitors.note"))
        note.setWordWrap(True)
        layout.addWidget(note)

    @staticmethod
    def _table(table: QTableWidget) -> None:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().hide()
        table.setAlternatingRowColors(True)

    def _actions_tab(self) -> None:
        _, layout = self._page(tr("tab.actions"))
        intro = QLabel(tr("actions.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.action_table = QTableWidget(0, 5)
        self.action_table.setHorizontalHeaderLabels([tr(f"actions.column.{c}") for c in ("action", "type", "assignment", "hotkey", "status")])
        self._table(self.action_table)
        self.action_table.cellDoubleClicked.connect(lambda *_: self.edit_action())
        layout.addWidget(self.action_table, 1)
        buttons = QHBoxLayout()
        for label, callback in [(tr("actions.add"), lambda: self.edit_action(new=True)), (tr("actions.edit"), self.edit_action),
                                (tr("actions.delete"), self.delete_selected), (tr("actions.test"), self.test_selected)]:
            b = QPushButton(label)
            b.clicked.connect(callback)
            buttons.addWidget(b)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.save_action: Callable[[SwapAction], None] | None = None

    def _general_tab(self) -> None:
        _, layout = self._page(tr("tab.general"))
        self.autostart = QCheckBox(tr("general.autostart"))
        self.close_tray = QCheckBox(tr("general.close_to_tray"))
        self.notifications = QCheckBox(tr("general.notify_success"))
        self.minimized = QCheckBox(tr("general.include_minimized"))
        self.tray_hint = QCheckBox(tr("general.tray_hint"))
        for widget in (self.autostart, self.close_tray, self.notifications, self.minimized, self.tray_hint):
            layout.addWidget(widget)
        self.mode = QComboBox()
        self.mode.addItem(tr("general.mode.keep_size"), "keep_size_fit_if_needed")
        self.mode.addItem(tr("general.mode.proportional"), "proportional")
        self.language = QComboBox()
        for code, name in SUPPORTED.items():
            self.language.addItem(name, code)
        form = QFormLayout()
        form.addRow(tr("general.geometry_mode"), self.mode)
        form.addRow(tr("general.language"), self.language)
        layout.addLayout(form)
        note = QLabel(tr("general.snap_note"))
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(QLabel(tr("general.exclusions")))
        self.exclusions = QPlainTextEdit()
        self.exclusions.setPlaceholderText(tr("general.exclusions_placeholder"))
        layout.addWidget(self.exclusions, 1)
        save = QPushButton(tr("general.save"))
        save.setObjectName("primary")
        save.clicked.connect(self.general_requested)
        layout.addWidget(save, alignment=Qt.AlignmentFlag.AlignLeft)
        self.reload_general()

    def reload_general(self) -> None:
        app = self.config.app
        for widget, value in [(self.autostart, app.start_with_windows), (self.close_tray, app.close_to_tray),
                              (self.notifications, app.notify_on_success), (self.minimized, app.include_minimized),
                              (self.tray_hint, app.tray_hint)]:
            widget.setChecked(value)
        self.mode.setCurrentIndex(self.mode.findData(app.geometry_mode))
        self.language.setCurrentIndex(max(0, self.language.findData(app.language)))
        self.exclusions.setPlainText("\n".join(self.config.excluded_executables))

    def _diagnostics_tab(self) -> None:
        _, layout = self._page(tr("tab.diagnostics"))
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        layout.addWidget(self.diagnostics, 1)
        buttons = QHBoxLayout()
        copy = QPushButton(tr("diagnostics.copy"))
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.diagnostics.toPlainText()))
        buttons.addWidget(copy)
        self.open_logs = QPushButton(tr("diagnostics.open_logs"))
        buttons.addWidget(self.open_logs)
        layout.addLayout(buttons)
        license_label = QLabel(tr("diagnostics.about", app=APP_NAME))
        license_label.setOpenExternalLinks(True)
        license_label.setWordWrap(True)
        layout.addWidget(license_label)

    def selected_action(self) -> SwapAction | None:
        row = self.action_table.currentRow()
        return self.config.actions[row] if 0 <= row < len(self.config.actions) else None

    def edit_action(self, checked: bool = False, new: bool = False) -> None:
        action = None if new else self.selected_action()
        if not new and not action:
            return
        dialog = ActionEditor(self.monitors, action, self)

        def save() -> None:
            try:
                value = dialog.value()
                if self.save_action:
                    self.save_action(value)
                dialog.accept()
            except (ValueError, OSError) as exc:
                dialog.show_error(exc)

        dialog.buttons.accepted.connect(save)
        dialog.exec()

    def delete_selected(self) -> None:
        action = self.selected_action()
        if action:
            self.delete_requested.emit(action.id)

    def test_selected(self) -> None:
        action = self.selected_action()
        if action:
            self.run_requested.emit(action.id)

    def show_settings(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.allow_close:
            event.accept()
        elif self.config.app.close_to_tray:
            event.ignore()
            self.hide()
            self.hidden_to_tray.emit()
        else:
            event.ignore()
            self.quit_requested.emit()
