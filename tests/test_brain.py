"""M2 DoD: 契约层 + decide() 纯函数。

覆盖: 纯函数性 / 饿挑 edible / 满足即 idle / GOAP 容器取食 / 平局确定性。
"""
from __future__ import annotations

import copy
import random
from pathlib import Path

import pytest

from citysim.core.config import load_config
from citysim.core.types import EntityView, Intent, Percept
from citysim.npc.brain import decide
from citysim.npc.person import full_signals

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _ev(entity_id: str, tags=(), affordances=None, claimable=True,
        duration_ticks: int = 30, distance: float = 0.0) -> EntityView:
    return EntityView(
        entity_id=entity_id,
        name=entity_id,
        tags=frozenset(tags),
        affordances=dict(affordances or {}),
        duration_ticks=duration_ticks,
        distance=distance,
        claimable=claimable,
        location_id="loc",
    )


def _percept(*visible) -> Percept:
    return Percept(tick=0, hour_f=12.0, location_id="loc", visible=tuple(visible))


def _signals(**kw) -> dict[str, float]:
    s = full_signals(1.0)
    s.update(kw)
    return s


# --- 纯函数性 ---------------------------------------------------------
def test_pure_same_input_same_output_no_mutation() -> None:
    sig = _signals(hunger=0.2)
    perc = _percept(_ev("fridge", tags=("container",),
                        affordances={"provides:edible": 1.0}))
    sig_before = copy.deepcopy(sig)
    i1 = decide(perc, sig, {}, None, CFG, random.Random(3))
    i2 = decide(perc, sig, {}, None, CFG, random.Random(3))
    assert i1 == i2
    assert sig == sig_before  # 入参未被修改


# --- 行为 -------------------------------------------------------------
def test_hungry_picks_edible() -> None:
    edible = _ev("rice_1", tags=("edible", "consumable"),
                 affordances={"hunger": 0.4, "thirst": 0.1})
    intent = decide(_percept(edible), _signals(hunger=0.2), {},
                    None, CFG, random.Random(0))
    assert intent.kind == "interact"
    assert intent.target_id == "rice_1"


def test_idle_when_satisfied() -> None:
    edible = _ev("tv_1", tags=("fun",), affordances={"fun": 0.3})
    intent = decide(_percept(edible), _signals(), {}, None, CFG, random.Random(0))
    assert intent.kind == "idle"
    assert intent.target_id is None


def test_goap_container() -> None:
    """无散落 edible、有 container(affordances 声明 provides:edible) → 取→吃计划。"""
    fridge = _ev("fridge_1", tags=("container",),
                 affordances={"provides:edible": 1.0})
    intent = decide(_percept(fridge), _signals(hunger=0.2), {},
                    None, CFG, random.Random(0))
    assert intent.kind == "interact"
    assert intent.target_id == "fridge_1"
    # M4: GOAP 动作库 JSON 化后动作名为 take_from_container/eat(原 take_food/eat)
    assert intent.trace.plan == ("take_from_container", "eat")


def test_loose_edible_beats_container_goap() -> None:
    """有散落 edible 时不再走容器取食计划(直接吃)。"""
    rice = _ev("rice_1", tags=("edible",), affordances={"hunger": 0.4})
    fridge = _ev("fridge_1", tags=("container",),
                 affordances={"provides:edible": 1.0})
    intent = decide(_percept(rice, fridge), _signals(hunger=0.2), {},
                    None, CFG, random.Random(0))
    assert intent.kind == "interact"
    assert intent.target_id == "rice_1"
    assert intent.trace.plan == ()


# --- 确定性 -----------------------------------------------------------
def test_tie_break_deterministic() -> None:
    a = _ev("a_1", tags=("x",), affordances={"hunger": 0.4})
    b = _ev("b_1", tags=("x",), affordances={"hunger": 0.4})
    picks = []
    for _ in range(2):
        rng = random.Random(42)
        intent = decide(_percept(a, b), _signals(hunger=0.2), {},
                        None, CFG, rng)
        picks.append(intent.target_id)
    assert picks[0] == picks[1]
    assert picks[0] in ("a_1", "b_1")


def test_not_claimable_is_ignored() -> None:
    occupied = _ev("bed_1", tags=("sleepable",), claimable=False,
                   affordances={"energy": 0.7})
    intent = decide(_percept(occupied), _signals(energy=0.1), {},
                    None, CFG, random.Random(0))
    assert intent.kind == "idle"
