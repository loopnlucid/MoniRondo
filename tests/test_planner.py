from dataclasses import replace

import pytest
from helpers import monitors, window

from monirondo.models import SwapAction, WindowState
from monirondo.planner import monitor_mapping, plan_moves


@pytest.mark.parametrize("count", range(2, 9))
@pytest.mark.parametrize("direction", ["forward", "backward"])
def test_cycles_once_and_inverse(count, direction):
    layout = monitors(count)
    windows = [window(n + 1, layout[n % count]) for n in range(25)]
    action = SwapAction("c", "Cycle", "cycle", direction=direction)
    plan = plan_moves(action, layout, windows)
    assert len(plan.moves) == 25 and len({m.before.hwnd for m in plan.moves}) == 25
    mapping = monitor_mapping(action, layout)
    inverse = monitor_mapping(replace(action, direction="backward" if direction == "forward" else "forward"), layout)
    assert all(inverse[mapping[m.id]] == m.id for m in layout)
    assert all(m.target.id == mapping[m.before.monitor_id] for m in plan.moves)


def test_pair_leaves_middle_monitor_untouched():
    layout = monitors()
    windows = [window(i + 1, m) for i, m in enumerate(layout)]
    action = SwapAction("p", "Pair", "pair", monitor_a_id="0", monitor_b_id="2")
    plan = plan_moves(action, layout, windows)
    assert {m.before.hwnd: m.target.id for m in plan.moves} == {1: "2", 3: "0"}


def test_fixed_subset_and_order():
    action = SwapAction("f", "Fixed", "cycle", monitor_order="fixed", monitor_ids=["3", "0", "2"])
    assert monitor_mapping(action, monitors(4)) == {"3": "0", "0": "2", "2": "3"}


@pytest.mark.parametrize("ids", [["0", "missing"], ["0", "0"], []])
def test_invalid_fixed_ids_never_guessed(ids):
    with pytest.raises(ValueError):
        monitor_mapping(SwapAction("f", "Fixed", "cycle", monitor_order="fixed", monitor_ids=ids), monitors())


def test_renumbered_same_models_preserve_identity():
    layout = [replace(m, name="Identical", device="renumbered") for m in monitors()]
    assert monitor_mapping(SwapAction("p", "p", "pair", monitor_a_id="0", monitor_b_id="2"), layout) == {"0": "2", "2": "0"}
    with pytest.raises(ValueError):
        monitor_mapping(SwapAction("p", "p", "pair", monitor_a_id="0", monitor_b_id="9"), layout)
    with pytest.raises(ValueError):
        monitor_mapping(SwapAction("c", "c", "cycle"), [layout[0], layout[0]])


def test_owned_dialog_follows_owner_and_zorder_is_retained():
    layout = monitors()
    owner = window(10, layout[0], z_index=4)
    dialog = window(11, layout[1], owner=10, root_owner=10, z_index=1)
    action = SwapAction("p", "Pair", "pair", monitor_a_id="0", monitor_b_id="2")
    plan = plan_moves(action, layout, [owner, dialog])
    assert [m.before.hwnd for m in plan.moves] == [10, 11]
    assert all(m.target.id == "2" for m in plan.moves)


@pytest.mark.parametrize("state", list(WindowState))
def test_state_is_not_mutated_by_planner(state):
    layout = monitors(2)
    w = window(1, layout[0], state)
    m = plan_moves(SwapAction("c", "C", "cycle"), layout, [w]).moves[0]
    assert m.before is w and m.before.state == state
