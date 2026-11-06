"""Catalog completeness and lookup rules; pure Python, no Qt."""
import string

import pytest

from monirondo.i18n import DEFAULT_LANGUAGE, SUPPORTED, catalog, current, set_language, tr


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.mark.parametrize("language", sorted(set(SUPPORTED) - {DEFAULT_LANGUAGE}))
def test_catalog_matches_english_keys_and_placeholders(language):
    english, other = catalog(DEFAULT_LANGUAGE), catalog(language)
    assert set(other) == set(english), (sorted(set(english) - set(other)), sorted(set(other) - set(english)))
    for key, text in english.items():
        assert placeholders(other[key]) == placeholders(text), key
        assert other[key].strip(), key


def test_catalog_texts_format_without_errors():
    for language in SUPPORTED:
        for key, text in catalog(language).items():
            assert text.format(**{name: "x" for name in placeholders(text)}), (language, key)


def test_switch_and_lookup():
    assert current() == DEFAULT_LANGUAGE
    assert tr("tab.general") == "General"
    set_language("de")
    assert current() == "de"
    assert tr("tab.general") == "Allgemein"
    assert tr("window.quit", app="MoniRondo") == "MoniRondo beenden"


def test_missing_key_falls_back(monkeypatch):
    set_language("fr")
    monkeypatch.delitem(catalog("fr"), "tab.general")  # Simulate an untranslated key.
    assert tr("tab.general") == "General"
    assert tr("no.such.key") == "no.such.key"


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError):
        set_language("xx")
    assert current() == DEFAULT_LANGUAGE


def test_no_accidental_qt_mnemonics():
    # Qt turns "&x" in tab titles, buttons and check boxes into an underlined shortcut.
    for language in SUPPORTED:
        for key, text in catalog(language).items():
            assert "&" not in text.replace("&amp;", ""), (language, key)
