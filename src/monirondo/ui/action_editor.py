import uuid
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from monirondo.hotkeys import validate_hotkey
from monirondo.i18n import tr
from monirondo.models import Hotkey, MonitorInfo, SwapAction

QT_KEYS = {"PAGEDOWN": Qt.Key.Key_PageDown, "PAGEUP": Qt.Key.Key_PageUp,
           "BACKSPACE": Qt.Key.Key_Backspace, "TAB": Qt.Key.Key_Tab, "RETURN": Qt.Key.Key_Return,
           "ESCAPE": Qt.Key.Key_Escape, "SPACE": Qt.Key.Key_Space, "END": Qt.Key.Key_End,
           "HOME": Qt.Key.Key_Home, "LEFT": Qt.Key.Key_Left, "UP": Qt.Key.Key_Up,
           "RIGHT": Qt.Key.Key_Right, "DOWN": Qt.Key.Key_Down, "INSERT": Qt.Key.Key_Insert,
           "DELETE": Qt.Key.Key_Delete,
           **{chr(n): Qt.Key(n) for n in range(65, 91)}, **{str(n): Qt.Key(48 + n) for n in range(10)},
           **{f"F{n}": Qt.Key(int(Qt.Key.Key_F1) + n - 1) for n in range(1, 25)}}
QT_MODS = {"CTRL": Qt.KeyboardModifier.ControlModifier, "ALT": Qt.KeyboardModifier.AltModifier,
           "SHIFT": Qt.KeyboardModifier.ShiftModifier, "WIN": Qt.KeyboardModifier.MetaModifier}


def key_sequence(hotkey: Hotkey | None) -> QKeySequence:
    if not hotkey:
        return QKeySequence()
    mods = Qt.KeyboardModifier.NoModifier
    for m in hotkey.modifiers:
        mods |= QT_MODS.get(m, Qt.KeyboardModifier.NoModifier)
    key = QT_KEYS.get(hotkey.key)
    return QKeySequence(mods | key) if key else QKeySequence()


class ActionEditor(QDialog):
    def __init__(self, monitors: list[MonitorInfo], action: SwapAction | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.original = action or SwapAction(uuid.uuid4().hex, tr("editor.default_name"), "pair")
        self.setWindowTitle(tr("editor.title.edit") if action else tr("editor.title.add"))
        self.setMinimumWidth(510)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(self.original.name)
        self.kind = QComboBox()
        for label, value in [(tr("editor.kind.pair"), "pair"), (tr("editor.kind.cycle"), "cycle"), (tr("editor.kind.undo"), "undo")]:
            self.kind.addItem(label, value)
        self.kind.setCurrentIndex(self.kind.findData(self.original.type))
        self.enabled = QCheckBox(tr("editor.enabled"))
        self.enabled.setChecked(self.original.enabled)
        form.addRow(tr("editor.name"), self.name)
        form.addRow(tr("editor.type"), self.kind)
        form.addRow("", self.enabled)
        layout.addLayout(form)
        self.pair_box = QGroupBox(tr("editor.pair"))
        pair_form = QFormLayout(self.pair_box)
        self.a, self.b = QComboBox(), QComboBox()
        for box, selected in [(self.a, self.original.monitor_a_id), (self.b, self.original.monitor_b_id)]:
            box.addItem(tr("editor.select_monitor"), "")
            for i, m in enumerate(monitors, 1):
                box.addItem(f"{i} · {m.name} ({m.device})", m.id)
            if selected and box.findData(selected) < 0:
                box.addItem(tr("editor.disconnected_assignment"), selected)
            box.setCurrentIndex(max(0, box.findData(selected)))
        pair_form.addRow(tr("editor.monitor_a"), self.a)
        pair_form.addRow(tr("editor.monitor_b"), self.b)
        layout.addWidget(self.pair_box)
        self.cycle_box = QGroupBox(tr("editor.cycle"))
        cycle_form = QVBoxLayout(self.cycle_box)
        self.direction = QComboBox()
        self.direction.addItem(tr("editor.forward"), "forward")
        self.direction.addItem(tr("editor.backward"), "backward")
        self.direction.setCurrentIndex(self.direction.findData(self.original.direction))
        self.fixed = QCheckBox(tr("editor.fixed_order"))
        self.fixed.setChecked(self.original.monitor_order == "fixed")
        self.order = QListWidget()
        self.order.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        ids = self.original.monitor_ids or [m.id for m in monitors]
        # Include connected monitors in the editor, unchecked if outside a saved subset.
        for mid in dict.fromkeys([*ids, *(m.id for m in monitors)]):
            found = next((m for m in monitors if m.id == mid), None)
            item = QListWidgetItem(found.name if found else tr("editor.disconnected_monitor"))
            item.setData(Qt.ItemDataRole.UserRole, mid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if mid in ids else Qt.CheckState.Unchecked)
            self.order.addItem(item)
        buttons = QHBoxLayout()
        for label, delta in [(tr("editor.move_up"), -1), (tr("editor.move_down"), 1)]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, d=delta: self.shift(d))
            buttons.addWidget(button)
        cycle_form.addWidget(self.direction)
        cycle_form.addWidget(self.fixed)
        cycle_form.addWidget(self.order)
        cycle_form.addLayout(buttons)
        self.order.setEnabled(self.fixed.isChecked())
        self.fixed.toggled.connect(self.order.setEnabled)
        layout.addWidget(self.cycle_box)
        key_form = QFormLayout()
        self.key = QKeySequenceEdit(key_sequence(self.original.hotkey))
        self.key.setMaximumSequenceLength(1)
        self.key.setClearButtonEnabled(True)
        line = self.key.findChild(QLineEdit)
        if line:
            line.setPlaceholderText(tr("editor.hotkey_placeholder"))
        self.key.setToolTip(tr("editor.hotkey_tooltip"))
        key_form.addRow(tr("editor.hotkey"), self.key)
        layout.addLayout(key_form)
        note = QLabel(tr("editor.hotkey_note"))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("editor.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("editor.cancel"))
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.kind.currentIndexChanged.connect(self.update_visibility)
        self.update_visibility()

    def update_visibility(self) -> None:
        self.pair_box.setVisible(self.kind.currentData() == "pair")
        self.cycle_box.setVisible(self.kind.currentData() == "cycle")

    def shift(self, delta: int) -> None:
        row = self.order.currentRow()
        if row >= 0 and 0 <= row + delta < self.order.count():
            item = self.order.takeItem(row)
            self.order.insertItem(row + delta, item)
            self.order.setCurrentRow(row + delta)

    def value(self) -> SwapAction:
        if not self.name.text().strip():
            raise ValueError(tr("editor.error.name_required"))
        seq = self.key.keySequence()
        hotkey = None
        if not seq.isEmpty():
            combo = seq[0]  # type: ignore[index]  # PySide supports indexing; its 6.12 stub omits it.
            key = next((name for name, code in QT_KEYS.items() if code == combo.key()), "")
            mods = tuple(name for name, flag in QT_MODS.items() if combo.keyboardModifiers() & flag)
            hotkey = Hotkey(mods, key)
            validate_hotkey(hotkey)
        action = replace(self.original, name=self.name.text().strip(), type=self.kind.currentData(),
                         enabled=self.enabled.isChecked(), hotkey=hotkey,
                         monitor_a_id=self.a.currentData(), monitor_b_id=self.b.currentData(),
                         direction=self.direction.currentData(),
                         monitor_order="fixed" if self.fixed.isChecked() else "dynamic_spatial",
                         monitor_ids=[self.order.item(i).data(Qt.ItemDataRole.UserRole)
                                      for i in range(self.order.count())
                                      if self.order.item(i).checkState() == Qt.CheckState.Checked])
        if action.type == "pair" and (not action.monitor_a_id or not action.monitor_b_id or action.monitor_a_id == action.monitor_b_id):
            raise ValueError(tr("editor.error.two_monitors"))
        if action.type == "cycle" and action.monitor_order == "fixed" and len(action.monitor_ids) < 2:
            raise ValueError(tr("editor.error.fixed_cycle"))
        return action

    def show_error(self, error: Exception) -> None:
        QMessageBox.warning(self, tr("editor.not_saved"), str(error))
