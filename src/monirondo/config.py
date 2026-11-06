import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from monirondo import APP_NAME, COMPAT_ID
from monirondo.i18n import DEFAULT_LANGUAGE, SUPPORTED, tr
from monirondo.models import Hotkey, SwapAction

# Builds before 1.2.0 were German-only and did not store a language.
LEGACY_LANGUAGE = "de"


def config_path() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home() / ".config"))) / COMPAT_ID / "config.json"


def log_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache"))) / COMPAT_ID / "logs"


def default_actions() -> list[SwapAction]:
    return [
        SwapAction("cycle-forward", tr("default_action.cycle_forward"), "cycle", hotkey=Hotkey(("CTRL", "ALT"), "PAGEDOWN")),
        SwapAction("cycle-backward", tr("default_action.cycle_backward"), "cycle", hotkey=Hotkey(("CTRL", "ALT"), "PAGEUP"), direction="backward"),
        SwapAction("undo", tr("default_action.undo"), "undo", hotkey=Hotkey(("CTRL", "ALT"), "BACKSPACE")),
    ]


@dataclass
class AppSettings:
    start_with_windows: bool = False
    close_to_tray: bool = True
    notify_on_success: bool = False
    include_minimized: bool = True
    geometry_mode: str = "keep_size_fit_if_needed"
    tray_hint: bool = True
    language: str = DEFAULT_LANGUAGE


@dataclass
class Configuration:
    schema_version: int = 1
    app: AppSettings = field(default_factory=AppSettings)
    actions: list[SwapAction] = field(default_factory=default_actions)
    excluded_executables: list[str] = field(default_factory=list)
    monitor_history: dict[str, dict[str, Any]] = field(default_factory=dict)


class FutureSchemaError(ValueError):
    pass


def parse_config(data: dict[str, Any]) -> Configuration:
    version = data.get("schema_version", 0)
    if type(version) is not int or version < 0:
        raise ValueError("Invalid schema version")
    if version > 1:
        raise FutureSchemaError(tr("config.future_schema", app=APP_NAME))
    # Version 0 used the same action schema; migrate missing defaults to v1.
    values = data.get("app", {})
    if not isinstance(values, dict):
        raise ValueError("Invalid general settings")
    settings = AppSettings(**{k: values[k] for k in AppSettings.__dataclass_fields__ if k in values})
    if "language" not in values:
        settings.language = LEGACY_LANGUAGE
    for key in ("start_with_windows", "close_to_tray", "notify_on_success", "include_minimized", "tray_hint"):
        if type(getattr(settings, key)) is not bool:
            raise ValueError("Invalid general setting")
    if settings.geometry_mode not in ("keep_size_fit_if_needed", "proportional"):
        raise ValueError("Invalid geometry mode")
    if settings.language not in SUPPORTED:
        raise ValueError("Unsupported language")
    actions = []
    for raw in data.get("actions", [asdict(a) for a in default_actions()]):
        if not isinstance(raw, dict):
            raise ValueError("Invalid action")
        args = {k: v for k, v in raw.items() if k in SwapAction.__dataclass_fields__}
        hotkey = args.get("hotkey")
        if hotkey and (not isinstance(hotkey, dict) or not isinstance(hotkey.get("modifiers"), (list, tuple))
                       or not all(isinstance(m, str) for m in hotkey["modifiers"])
                       or not isinstance(hotkey.get("key"), str)):
            raise ValueError("Invalid hotkey data")
        args["hotkey"] = Hotkey(tuple(hotkey["modifiers"]), hotkey["key"]) if hotkey else None
        a = SwapAction(**args)
        if not isinstance(a.id, str) or not a.id or not isinstance(a.name, str) or not a.name.strip():
            raise ValueError("Invalid action ID or name")
        if a.type not in ("pair", "cycle", "undo") or type(a.enabled) is not bool:
            raise ValueError("Invalid action")
        if a.direction not in ("forward", "backward") or a.monitor_order not in ("dynamic_spatial", "fixed"):
            raise ValueError("Invalid cycle")
        if not isinstance(a.monitor_ids, list) or not all(isinstance(i, str) for i in a.monitor_ids):
            raise ValueError("Invalid monitor list")
        if not isinstance(a.monitor_a_id, str) or not isinstance(a.monitor_b_id, str):
            raise ValueError("Invalid monitor identity")
        actions.append(a)
    if len({a.id for a in actions}) != len(actions):
        raise ValueError("Duplicate action ID")
    excluded = data.get("excluded_executables", [])
    history = data.get("monitor_history", {})
    if not isinstance(excluded, list) or not all(isinstance(s, str) for s in excluded) or not isinstance(history, dict):
        raise ValueError("Invalid exclusion list or monitor data")
    return Configuration(1, settings, actions, excluded, history)


def load_config(path: Path) -> tuple[Configuration, str]:
    if not path.exists():
        return Configuration(), ""
    try:
        return parse_config(json.loads(path.read_text(encoding="utf-8"))), ""
    except FutureSchemaError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        backup = path.with_suffix(f".corrupt-{datetime.now():%Y%m%d-%H%M%S-%f}.json")
        path.replace(backup)
        return Configuration(), tr("config.corrupt_backup", name=backup.name)


def save_config(path: Path, config: Configuration) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(asdict(config), indent=2, ensure_ascii=False) + "\n"
    temp: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            temp = f.name
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp and Path(temp).exists():
            Path(temp).unlink()
