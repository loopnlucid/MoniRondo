import subprocess
import sys
import winreg

from monirondo import COMPAT_ID

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = COMPAT_ID


def command() -> str:
    if getattr(sys, "frozen", False):
        args = [sys.executable, "--background"]
    else:
        from pathlib import Path
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        args = [str(pythonw if pythonw.exists() else Path(sys.executable)), "-m", "monirondo", "--background"]
    return subprocess.list2cmdline(args)


def current() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return str(winreg.QueryValueEx(key, VALUE_NAME)[0])
    except FileNotFoundError:
        return None


def set_enabled(enabled: bool) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
