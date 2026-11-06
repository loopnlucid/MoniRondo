# Contributing to MoniRondo

Thanks for your interest in improving MoniRondo! Bug reports, translations, documentation fixes and code contributions are all welcome.

## Reporting bugs and requesting features

- Search the [existing issues](https://github.com/loopnlucid/MoniRondo/issues) first.
- For bugs, use the bug report template and attach the **diagnostic report** (Settings → *Diagnostics / About* → *Copy diagnostic report*). It contains versions, monitor counts and hotkey conflicts, but no window titles.
- Describe your monitor setup (resolutions, scaling, arrangement) and the applications involved. If a specific application misbehaves, say which one.
- Security issues: please follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Development setup

Windows 10/11 x64 and Python 3.12 x64 are required for the full app; the pure logic (planner, geometry, engine, config, i18n) also runs on other systems.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m monirondo
```

Before opening a pull request, run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
```

Tests that move real windows only move their own short-lived test windows and are opt-in with `--run-native-moves`. Please never add tests that move, close or read the titles of the user's own windows.

See [docs/architecture.md](docs/architecture.md) and [docs/decisions.md](docs/decisions.md) for how the pieces fit together.

## Coding guidelines

- Code, comments, docstrings, commit messages and documentation are written in English.
- Keep the pure core (`models`, `geometry`, `planner`, `engine`, `config`, `hotkeys`, `i18n`) free of Qt and Win32 imports so it stays testable everywhere.
- Every user-visible text goes through `monirondo.i18n.tr("some.key")`. Add the key to **all** catalogs in `src/monirondo/locales/` (see below). Log messages stay short English event identifiers such as `swap_finished`.
- Keep changes focused. Add or update tests for behavior changes and note user-visible changes in [CHANGELOG.md](CHANGELOG.md).
- Privacy is a feature: no telemetry, no network access, no window titles in logs.

## Translations

UI texts live in `src/monirondo/locales/<language>.json`. `en.json` is the reference; every other catalog must contain exactly the same keys.

- Keep placeholders such as `{app}`, `{count}` or `{error}` unchanged; they are filled in by the program.
- Do not use `&` in texts (Qt would turn it into a keyboard shortcut marker).
- Keep texts about as long as the English ones where possible; the settings window has limited room.
- Hotkey key names (`key.*`) should match the labels printed on keyboards in that language.

**Improving a translation:** edit the JSON file and open a pull request. Native speakers reviewing the existing German, Spanish and French texts are very welcome.

**Adding a new language:**

1. Copy `en.json` to `<code>.json` (ISO 639-1 code, e.g. `it.json`) and translate the values.
2. Add the code and the language's native name to `SUPPORTED` in `src/monirondo/i18n.py`.
3. Run `.\.venv\Scripts\python.exe -m pytest -q tests/test_i18n.py tests/test_ui.py` – it checks keys and placeholders and builds the UI in every language.
4. Run `.\.venv\Scripts\python.exe scripts/preview_ui.py <code>` and look at the screenshots in `artifacts/preview/<code>/` for cut-off texts.
5. Mention the new language in the README and the changelog.

Qt's own standard dialogs use the `qtbase_<code>` translations that ship with PySide6.

## Pull requests

- Fork the repository and create a branch from `main`.
- Make sure the checks above pass; GitHub Actions runs them on Windows and Linux as well.
- Fill in the pull request template and link related issues.

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE). Please follow our [Code of Conduct](CODE_OF_CONDUCT.md).
