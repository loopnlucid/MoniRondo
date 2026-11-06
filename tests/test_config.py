import json
from dataclasses import asdict

import pytest

from monirondo.config import (
    Configuration,
    FutureSchemaError,
    config_path,
    load_config,
    log_dir,
    parse_config,
    save_config,
)
from monirondo.models import Hotkey


def test_defaults_roundtrip_and_no_hwnds(tmp_path):
    path = tmp_path / "app/config.json"
    config, warning = load_config(path)
    assert not warning and not config.app.start_with_windows and len(config.actions) == 3
    save_config(path, config)
    loaded, _ = load_config(path)
    assert loaded == config
    assert "hwnd" not in path.read_text().lower()
    assert list(path.parent.iterdir()) == [path]


def test_corrupt_config_backup(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{bad json', encoding='utf-8')
    config, warning = load_config(path)
    assert warning and config == Configuration()
    backups = list(tmp_path.glob("*.corrupt-*.json"))
    assert len(backups) == 1 and backups[0].read_text() == '{bad json'


def test_migration_and_future_schema(tmp_path):
    assert parse_config({}).schema_version == 1
    path = tmp_path / 'config.json'
    path.write_text('{"schema_version":99}')
    with pytest.raises(FutureSchemaError):
        load_config(path)
    assert path.exists()


def test_atomic_failure_preserves_previous(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    save_config(path, Configuration())
    previous = path.read_bytes()
    def fail(*args):
        raise PermissionError("disk error")
    monkeypatch.setattr('monirondo.config.os.replace', fail)
    with pytest.raises(PermissionError):
        save_config(path, Configuration())
    assert path.read_bytes() == previous
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("change", [{"app": {"include_minimized": "yes"}}, {"actions": [{"id": "a", "name": "A", "type": "bad"}]}, {"excluded_executables": "bad"}])
def test_invalid_semantics_are_backed_up(tmp_path, change):
    data = asdict(Configuration()) | change
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    assert load_config(path)[1]


def test_malformed_hotkey_cannot_crash_startup(tmp_path):
    data = asdict(Configuration())
    data['actions'][0]['hotkey'] = {'modifiers': [{}], 'key': 'A'}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(data))
    assert load_config(path)[1]


def test_reuses_existing_monitorswap_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    legacy = tmp_path / 'MonitorSwap/config.json'
    original = Configuration()
    original.app.geometry_mode = 'proportional'
    original.app.include_minimized = False
    original.actions[0].direction = 'backward'
    original.actions[0].name = 'Meine Bildschirmrunde'
    original.actions[0].hotkey = Hotkey(('CTRL', 'ALT'), 'RIGHT')
    original.actions[0].monitor_ids = ['display:old-a', 'display:old-b']
    original.monitor_history = {'display:existing': {'name': 'Existing display'}}
    save_config(legacy, original)
    assert config_path() == legacy
    assert load_config(config_path()) == (original, '')
    assert log_dir() == tmp_path / 'MonitorSwap/logs'
    assert not (tmp_path / 'MoniRondo').exists()


def test_new_profile_defaults_to_english(tmp_path):
    config, _ = load_config(tmp_path / 'config.json')
    assert config.app.language == 'en'
    assert config.actions[0].name == 'All monitors forward'


def test_profile_without_language_keeps_german(tmp_path):
    # Every release before 1.2.0 was German-only and saved no language.
    data = asdict(Configuration())
    del data['app']['language']
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    config, warning = load_config(path)
    assert not warning and config.app.language == 'de'


def test_language_roundtrip_and_validation(tmp_path):
    path = tmp_path / 'config.json'
    config = Configuration()
    config.app.language = 'fr'
    save_config(path, config)
    assert load_config(path)[0].app.language == 'fr'
    data = asdict(config)
    data['app']['language'] = 'xx'
    path.write_text(json.dumps(data), encoding='utf-8')
    loaded, warning = load_config(path)
    assert warning and loaded == Configuration()
