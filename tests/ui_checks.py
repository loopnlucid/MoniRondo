"""Subprocess assertions used by test_ui.py. No pytest or native movement here."""
import sys
from pathlib import Path

from helpers import monitors

from monirondo.config import Configuration

kind = sys.argv[1]
if kind == 'import':
    from monirondo.app import main
    assert callable(main)
elif kind == 'queue':
    from types import SimpleNamespace

    from PySide6.QtCore import QCoreApplication

    from monirondo.app import Controller
    app = QCoreApplication([])
    action = Configuration().actions[0]
    started = []
    owner = SimpleNamespace(
        quitting=False, job=SimpleNamespace(action=None, deleteLater=lambda: None),
        pending_action=None, refresh_pending=False,
        config=SimpleNamespace(actions=[action]), action_issue=lambda a: '',
        start_job=started.append, rebuild_views=lambda: None, update_diagnostics=lambda: None,
        window=SimpleNamespace(tabs=SimpleNamespace(setEnabled=lambda value: None)),
    )
    owner.execute = lambda aid: Controller.execute(owner, aid)
    owner.execute(action.id)
    assert not started and owner.pending_action == action.id
    Controller.job_finished(owner)
    app.processEvents()
    assert started == [action] and owner.pending_action is None
elif kind == 'switch':
    # Real controller with a private profile and no hotkeys; native capture is read-only.
    import os

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    os.environ['APPDATA'] = os.environ['LOCALAPPDATA'] = sys.argv[2]
    from monirondo.app import Controller, install_qt_translator
    from monirondo.i18n import current
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    config = Configuration()
    for action in config.actions:
        action.hotkey = None
    controller = Controller(app, config)
    controller.window.tabs.setCurrentIndex(2)
    seen = []

    def switch():
        try:
            for language, settings in (('de', 'Einstellungen'), ('fr', 'Paramètres'), ('en', 'Settings')):
                old = controller.window
                config.app.language = language
                controller.apply_language(language)
                assert current() == language and controller.window is not old
                assert controller.window.tabs.currentIndex() == 2
                assert controller.window.language.currentData() == language
                assert [a.text() for a in controller.menu.actions()][-2] == settings
                seen.append(language)
            assert install_qt_translator(app, 'en', None) is None
        finally:
            controller.quit()

    QTimer.singleShot(200, switch)
    app.exec()
    assert seen == ['de', 'fr', 'en'], seen
elif kind == 'ipc':
    import uuid

    from PySide6.QtCore import QCoreApplication

    from monirondo.windows.single_instance import SingleInstance
    app = QCoreApplication([])
    namespace = 'MonitorSwap-Test-' + uuid.uuid4().hex
    first = SingleInstance(namespace)
    assert first.primary, 'Another test instance is already running'
    requests = []
    first.show_requested.connect(lambda: requests.append(True))
    second = SingleInstance(namespace)
    try:
        assert not second.primary
        assert second.notify()
        for _ in range(5):
            app.processEvents()
        assert requests == [True]
    finally:
        second.close()
        first.close()
else:
    import traceback

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from monirondo.ui.action_editor import ActionEditor
    from monirondo.ui.main_window import STYLE, MainWindow
    app = QApplication([])
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    failed = []

    def check_gui():
        try:
            if kind == 'editor':
                for action in Configuration().actions:
                    dialog = ActionEditor(monitors(8), action)
                    result = dialog.value()
                    assert result.hotkey == action.hotkey
                    assert result.direction == action.direction
                    dialog.close()
                    dialog.deleteLater()
            elif kind == 'window':
                window = MainWindow(Configuration())
                window.diagram.monitors = monitors(8)
                window.show()
                app.processEvents()
                assert window.grab().save(str(Path(sys.argv[2]) / 'main.png'))
                window.close()
                assert not window.isVisible()
                window.allow_close = True
                window.close()
                window.deleteLater()
            elif kind == 'languages':
                from monirondo.i18n import SUPPORTED, set_language
                expected = {'en': 'Monitors', 'de': 'Monitore', 'es': 'Monitores', 'fr': 'Écrans'}
                for language in SUPPORTED:
                    set_language(language)
                    config = Configuration()
                    config.app.language = language
                    window = MainWindow(config)
                    assert window.tabs.tabText(0) == expected[language], window.tabs.tabText(0)
                    assert window.language.currentData() == language
                    dialog = ActionEditor(monitors(2), None, window)
                    assert dialog.windowTitle() != 'editor.title.add'
                    dialog.deleteLater()
                    window.allow_close = True
                    window.close()
                    window.deleteLater()
            else:
                raise ValueError(kind)
        except Exception:
            traceback.print_exc()
            failed.append(True)
        # Deferred QObject deletion needs a live Qt event loop, just as in the real app.
        QTimer.singleShot(80, app.quit)

    QTimer.singleShot(0, check_gui)
    app.exec()
    if failed:
        raise SystemExit(1)
print('OK', kind)
