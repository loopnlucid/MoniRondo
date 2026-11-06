from dataclasses import replace

import pytest

from monirondo.geometry import (
    assign_monitor,
    placement_rect_to_screen,
    screen_rect_to_placement,
    transfer_rect,
)
from monirondo.models import MonitorInfo, Rect


@pytest.mark.parametrize("origin", [(-1920, -1080), (0, 0), (1920, 1440)])
@pytest.mark.parametrize("offset", [(0, 0), (0, 48), (72, 0), (72, 48)])
@pytest.mark.parametrize("tool", [False, True])
def test_workspace_roundtrip_no_drift(origin, offset, tool):
    x, y = origin
    dx, dy = offset
    m = MonitorInfo("a", "a", "a", Rect(x, y, x + 1920, y + 1080), Rect(x + dx, y + dy, x + 1920, y + 1040))
    r = Rect(x + 120, y + 100, x + 620, y + 500)
    for _ in range(300):
        assert screen_rect_to_placement(placement_rect_to_screen(r, m, tool), m, tool) == r


@pytest.mark.parametrize("work", [Rect(-1920, 0, 0, 1040), Rect(0, -2160, 3840, 0), Rect(0, 0, 1080, 1880)])
@pytest.mark.parametrize("mode", ["keep_size_fit_if_needed", "proportional"])
def test_transfer_mixed_sizes(work, mode):
    source = Rect(0, 40, 2560, 1440)
    original = Rect(500, 400, 1100, 800)
    moved = transfer_rect(original, source, work, mode)
    assert moved.width <= work.width and moved.height <= work.height
    assert moved.left >= work.left and moved.top >= work.top
    restored = transfer_rect(moved, work, source, mode)
    assert original.near(restored, 2)


def test_oversize_fits_and_title_visible():
    target = Rect(-1080, -1000, 0, 800)
    result = transfer_rect(Rect(0, 0, 5000, 4000), Rect(0, 0, 1920, 1080), target)
    assert result.width == target.width - 24
    assert result.height == target.height - 24
    assert result.top >= target.top and result.right <= target.right


def test_largest_intersection_and_nearest():
    a = MonitorInfo("a", "a", "Same Model", Rect(-1920, 0, 0, 1080), Rect(-1920, 0, 0, 1080))
    b = replace(a, id="b", bounds=Rect(0, 0, 1920, 1080))
    assert assign_monitor(Rect(-100, 40, 500, 400), [a, b]) == b
    assert assign_monitor(Rect(-6000, 0, -5000, 900), [b, a]) == a


def test_invalid_rects_rejected():
    with pytest.raises(ValueError):
        transfer_rect(Rect(0, 0, 0, 20), Rect(0, 0, 10, 10), Rect(0, 0, 10, 10))
