"""Transactional registration independent of the native message transport."""
from collections.abc import Callable

from monirondo.i18n import tr
from monirondo.models import Hotkey

KEYS = {"BACKSPACE": 8, "TAB": 9, "RETURN": 13, "ESCAPE": 27, "SPACE": 32,
        "PAGEUP": 33, "PAGEDOWN": 34, "END": 35, "HOME": 36, "LEFT": 37, "UP": 38,
        "RIGHT": 39, "DOWN": 40, "INSERT": 45, "DELETE": 46,
        **{chr(n): n for n in range(65, 91)}, **{str(n): 48 + n for n in range(10)},
        **{f"F{n}": 111 + n for n in range(1, 25) if n != 12}}
MODIFIERS = {"ALT": 1, "CTRL": 2, "SHIFT": 4, "WIN": 8}
# Keys with a localized display name ("key.<NAME>" in the catalogs); letters, digits and F-keys are shown as-is.
LABELED_KEYS = frozenset({*MODIFIERS, "PAGEUP", "PAGEDOWN", "BACKSPACE", "DELETE", "INSERT", "HOME", "END",
                          "SPACE", "RETURN", "ESCAPE", "TAB", "LEFT", "RIGHT", "UP", "DOWN"})


def validate_hotkey(key: Hotkey) -> tuple[int, int]:
    if not key.modifiers or any(m not in MODIFIERS for m in key.modifiers) or key.key not in KEYS:
        raise ValueError(tr("hotkey.error.unsupported"))
    if len(set(key.modifiers)) != len(key.modifiers):
        raise ValueError(tr("hotkey.error.duplicate_modifier"))
    if "WIN" in key.modifiers or (key.key == "DELETE" and {"CTRL", "ALT"} <= set(key.modifiers)):
        raise ValueError(tr("hotkey.error.reserved"))
    return sum(MODIFIERS[m] for m in key.modifiers) | 0x4000, KEYS[key.key]


def hotkey_label(key: Hotkey | None) -> str:
    if not key:
        return tr("hotkey.none")
    return " + ".join(tr(f"key.{k}") if k in LABELED_KEYS else k for k in (*key.modifiers, key.key))


class HotkeyRegistry:
    def __init__(self, register: Callable[[int, int, int], bool], unregister: Callable[[int], None]) -> None:
        self.register = register
        self.unregister = unregister
        self.active: dict[str, tuple[int, Hotkey]] = {}
        self.next_id = 1

    def replace(self, action_id: str, key: Hotkey | None) -> None:
        old = self.active.get(action_id)
        if key is not None:
            mods, vk = validate_hotkey(key)
            if old and old[1].canonical == key.canonical:
                return
            if any(a != action_id and k.canonical == key.canonical for a, (_, k) in self.active.items()):
                raise ValueError(tr("hotkey.error.in_use"))
            used = {i for i, _ in self.active.values()}
            for _ in range(0xBFFF):
                identifier = self.next_id
                self.next_id = self.next_id % 0xBFFF + 1
                if identifier not in used:
                    break
            else:
                raise ValueError(tr("hotkey.error.too_many"))
            if not self.register(identifier, mods, vk):
                raise ValueError(tr("hotkey.error.register_failed"))
            self.active[action_id] = (identifier, key)
        else:
            self.active.pop(action_id, None)
        if old:
            self.unregister(old[0])

    def action_for(self, identifier: int) -> str | None:
        return next((a for a, (i, _) in self.active.items() if i == identifier), None)

    def close(self) -> None:
        for i, _ in self.active.values():
            self.unregister(i)
        self.active.clear()
