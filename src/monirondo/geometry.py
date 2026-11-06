"""Pure functions. All rectangles are physical pixels, never Qt logical coordinates."""

from monirondo.models import MonitorInfo, Rect


def placement_rect_to_screen(rect: Rect, monitor: MonitorInfo, tool_window: bool = False) -> Rect:
    if tool_window:
        return rect
    return rect.translate(monitor.work.left - monitor.bounds.left, monitor.work.top - monitor.bounds.top)


def screen_rect_to_placement(rect: Rect, monitor: MonitorInfo, tool_window: bool = False) -> Rect:
    if tool_window:
        return rect
    return rect.translate(monitor.bounds.left - monitor.work.left, monitor.bounds.top - monitor.work.top)


def assign_monitor(rect: Rect, monitors: list[MonitorInfo]) -> MonitorInfo:
    if not monitors:
        raise ValueError("No active monitors")
    cx, cy = rect.center
    # Enum order is irrelevant: stable IDs break ties deterministically.
    return min(monitors, key=lambda m: (
        -rect.intersection_area(m.bounds),
        (cx - m.bounds.center[0]) ** 2 + (cy - m.bounds.center[1]) ** 2,
        m.id,
    ))


def transfer_rect(rect: Rect, source: Rect, target: Rect, mode: str = "keep_size_fit_if_needed") -> Rect:
    if min(source.width, source.height, target.width, target.height, rect.width, rect.height) <= 0:
        raise ValueError("Invalid window or monitor geometry")
    cx, cy = rect.center
    x = target.left + (cx - source.left) / source.width * target.width
    y = target.top + (cy - source.top) / source.height * target.height
    w, h = rect.width, rect.height
    if mode == "proportional":
        w = round(w * target.width / source.width)
        h = round(h * target.height / source.height)
    elif mode != "keep_size_fit_if_needed":
        raise ValueError("Unknown geometry mode")
    # Apply the safety margin only when an oversize window actually needs shrinking.
    w = min(max(1, w), max(1, target.width - 24)) if w > target.width else max(1, w)
    h = min(max(1, h), max(1, target.height - 24)) if h > target.height else max(1, h)
    left = min(max(round(x - w / 2), target.left), target.right - w)
    top = min(max(round(y - h / 2), target.top), target.bottom - h)
    return Rect(left, top, left + w, top + h)


def transfer_tile(outer: Rect, visible: Rect, source: Rect, target: Rect,
                  dpi_ratio: float = 1.0) -> tuple[Rect, Rect] | None:
    """Recognize common visible Snap slots; transfer their edges, not the restore RECT.

    Geometric recognition intentionally also covers manually arranged identical
    slots. This preserves the visible layout, not undocumented shell Snap groups.
    Invisible resize borders must extend outside the work area, not be clamped in.
    """
    if min(source.width, source.height, target.width, target.height) <= 0:
        return None
    horizontal = [(0., .5), (.5, 1.), (0., 1 / 3), (1 / 3, 2 / 3), (2 / 3, 1.),
                  (0., 2 / 3), (1 / 3, 1.), (0., 1.)]
    vertical = [(0., 1.), (0., .5), (.5, 1.)]
    for left, right in horizontal:
        for top, bottom in vertical:
            slot = Rect(source.left + round(left * source.width), source.top + round(top * source.height),
                        source.left + round(right * source.width), source.top + round(bottom * source.height))
            if not visible.near(slot, 8):
                continue
            result = Rect(target.left + round(left * target.width), target.top + round(top * target.height),
                          target.left + round(right * target.width), target.top + round(bottom * target.height))
            framed = outer_rect_for_visible(result, outer, visible, dpi_ratio)
            return (framed, result) if framed is not None else None
    return None


def outer_rect_for_visible(target: Rect, outer: Rect, visible: Rect, scale: float = 1.) -> Rect | None:
    """Convert desired visible bounds using measured frame margins, in physical pixels."""
    margins = (visible.left - outer.left, visible.top - outer.top,
               outer.right - visible.right, outer.bottom - visible.bottom)
    if any(n < 0 or n > 64 for n in margins) or not 0.25 <= scale <= 4:
        return None
    a, b, c, d = (round(n * scale) for n in margins)
    return Rect(target.left - a, target.top - b, target.right + c, target.bottom + d)
