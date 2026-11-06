from monirondo.geometry import transfer_rect, transfer_tile
from monirondo.i18n import tr
from monirondo.models import MonitorInfo, Move, MovePlan, SwapAction, WindowSnapshot, WindowState


def monitor_mapping(action: SwapAction, monitors: list[MonitorInfo]) -> dict[str, str]:
    if not action.enabled:
        raise ValueError(tr("planner.disabled"))
    ids = {m.id for m in monitors}
    if len(ids) != len(monitors):
        raise ValueError(tr("planner.ambiguous_identity"))
    if len(monitors) < 2:
        raise ValueError(tr("planner.two_monitors"))
    if action.type == "pair":
        a, b = action.monitor_a_id, action.monitor_b_id
        if a == b or a not in ids or b not in ids:
            raise ValueError(tr("planner.pair_unassigned"))
        return {a: b, b: a}
    if action.type != "cycle":
        raise ValueError(tr("planner.unknown_type"))
    order = [m.id for m in sorted(monitors, key=lambda m: (*m.bounds.center, m.id))]
    if action.monitor_order == "fixed":
        order = action.monitor_ids
        if len(order) < 2 or len(set(order)) != len(order) or not set(order) <= ids:
            raise ValueError(tr("planner.cycle_invalid"))
    if action.direction not in ("forward", "backward"):
        raise ValueError(tr("planner.invalid_direction"))
    step = 1 if action.direction == "forward" else -1
    return {m: order[(i + step) % len(order)] for i, m in enumerate(order)}


def plan_moves(action: SwapAction, monitors: list[MonitorInfo], windows: list[WindowSnapshot],
               foreground: int = 0, mode: str = "keep_size_fit_if_needed") -> MovePlan:
    mapping = monitor_mapping(action, monitors)
    displays = {m.id: m for m in monitors}
    by_hwnd = {w.hwnd: w for w in windows}
    if len(by_hwnd) != len(windows):
        raise ValueError("Duplicate windows in snapshot")
    moves = []
    for w in windows:
        anchor = by_hwnd.get(w.root_owner, w)
        source_id = anchor.monitor_id
        if source_id not in mapping:
            continue
        source, target = displays[source_id], displays[mapping[source_id]]
        rect = transfer_rect(w.movement_rect, source.work, target.work, mode)
        target_visible = None
        if w.state == WindowState.NORMAL and w.visible_rect is not None:
            ratio = target.dpi / source.dpi if source.dpi and target.dpi else 1.0
            tile = transfer_tile(w.rect, w.visible_rect, source.work, target.work, ratio)
            if tile is not None:
                rect, target_visible = tile
        moves.append(Move(w, target, rect, target_visible))
    # Bottom to top helps preserve owner/dialog relationships without changing global Z order.
    moves.sort(key=lambda m: m.before.z_index, reverse=True)
    return MovePlan(tuple(moves), tuple(monitors), foreground)
