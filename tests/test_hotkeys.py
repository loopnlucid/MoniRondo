import pytest

from monirondo.hotkeys import HotkeyRegistry, hotkey_label, validate_hotkey
from monirondo.i18n import set_language
from monirondo.models import Hotkey


def test_registration_failure_preserves_old_and_no_leak():
    registrations = {}
    def register(i, mods, vk):
        if vk == ord('B'):
            return False
        registrations[i] = (mods, vk)
        return True
    registry = HotkeyRegistry(register, lambda i: registrations.pop(i))
    a, b = Hotkey(("CTRL", "ALT"), "A"), Hotkey(("CTRL", "ALT"), "B")
    registry.replace("action", a)
    for _ in range(500):
        with pytest.raises(ValueError):
            registry.replace("action", b)
    assert registry.active["action"][1] == a and len(registrations) == 1
    registry.replace("action", Hotkey(("CTRL", "ALT"), "C"))
    assert len(registrations) == 1
    registry.close()
    assert not registrations


def test_duplicates_and_norepeat():
    registry = HotkeyRegistry(lambda i, m, k: True, lambda i: None)
    registry.replace('a', Hotkey(("CTRL", "ALT"), "A"))
    with pytest.raises(ValueError):
        registry.replace('b', Hotkey(("ALT", "CTRL"), "A"))
    assert validate_hotkey(Hotkey(("CTRL",), "F8"))[0] & 0x4000


@pytest.mark.parametrize("key", [Hotkey((), "A"), Hotkey(("CTRL",), "F12"), Hotkey(("WIN",), "A"), Hotkey(("CTRL", "ALT"), "DELETE"), Hotkey(("BAD",), "A")])
def test_invalid_and_reserved_combinations(key):
    with pytest.raises(ValueError):
        validate_hotkey(key)


@pytest.mark.parametrize(("language", "label"), [
    ("en", "Ctrl + Alt + Page Down"), ("de", "Strg + Alt + Bild ab"),
    ("es", "Ctrl + Alt + Av Pág"), ("fr", "Ctrl + Alt + Pg Suiv"),
])
def test_labels_follow_ui_language(language, label):
    set_language(language)
    assert hotkey_label(Hotkey(("CTRL", "ALT"), "PAGEDOWN")) == label
    assert hotkey_label(Hotkey(("SHIFT",), "F7")).endswith(" + F7")


def test_label_without_hotkey():
    assert hotkey_label(None) == "No hotkey"
