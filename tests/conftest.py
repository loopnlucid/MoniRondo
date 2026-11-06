import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def pytest_addoption(parser):
    parser.addoption("--run-native-moves", action="store_true", help="Move exclusively our own generated test windows")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-native-moves"):
        import pytest
        for item in items:
            if "interactive" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Use --run-native-moves to create/move isolated test windows"))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def english_ui():
    """Every test starts and ends with the default UI language; i18n keeps it as module state."""
    from monirondo.i18n import DEFAULT_LANGUAGE, set_language
    set_language(DEFAULT_LANGUAGE)
    yield
    set_language(DEFAULT_LANGUAGE)
