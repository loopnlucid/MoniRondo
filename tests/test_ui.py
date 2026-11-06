"""Run Qt in isolated processes; native Win32 tests must not share its GUI lifecycle."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec('PySide6') is None, reason='PySide6 not installed')


@pytest.mark.parametrize('check', ['editor', 'window', 'languages', 'import', 'queue'])
def test_ui_in_isolated_process(check, tmp_path):
    run_check(check, tmp_path)


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != 'win32', reason='Windows only')
def test_single_instance_ipc_in_isolated_process(tmp_path):
    run_check('ipc', tmp_path)


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != 'win32', reason='Windows only')
def test_live_language_switch_rebuilds_window_and_tray(tmp_path):
    run_check('switch', tmp_path)


def run_check(check, tmp_path):
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('ui_checks.py')), check, str(tmp_path)],
                            env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, (result.stdout, result.stderr)
