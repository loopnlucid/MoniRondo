"""Lightweight translation catalog without a Qt dependency.

Catalogs live in ``monirondo/locales/<code>.json`` and map stable message IDs to
text with ``{name}`` placeholders. English is the source of truth: a key that is
missing from another catalog falls back to the English text, and a key missing
from the English catalog falls back to the key itself.
"""

import json
from functools import cache
from importlib.resources import files

DEFAULT_LANGUAGE = "en"
# Native names, shown as-is in the language selector regardless of the UI language.
SUPPORTED: dict[str, str] = {"en": "English", "de": "Deutsch", "es": "Español", "fr": "Français"}

_current = DEFAULT_LANGUAGE


@cache
def catalog(language: str) -> dict[str, str]:
    if language not in SUPPORTED:
        raise ValueError(f"Unsupported language: {language}")
    text = files("monirondo").joinpath(f"locales/{language}.json").read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError(f"Invalid translation catalog: {language}")
    return data


def set_language(language: str) -> None:
    global _current
    catalog(language)  # Validate before switching.
    _current = language


def current() -> str:
    return _current


def tr(key: str, **values: object) -> str:
    text = catalog(_current).get(key)
    if text is None:
        text = catalog(DEFAULT_LANGUAGE).get(key, key)
    return text.format(**values) if values else text
