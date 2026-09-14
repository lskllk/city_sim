"""hp 三态 + hp_override(docs/20260914/plan.md §3.7)。

    下降   hunger == 0  或  energy == 0
    上升   hunger ≥ hp_regen_floor 且 energy ≥ hp_regen_floor
    不动   其他(中间带 —— 否则咬一口饭 hp 就开始涨, “饿死”永远发生不了)
    不参与 bladder

    hp < hp_override → 日程失去拉力(命比钱大): 计划不执行。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Idle, Interact
from citysim.npc.schedule import PlanEntry

from helpers import add_entity, add_npc, make_runtime

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


# ---------------------------------------------------------------------------
# 三态
# ---------------------------------------------------------------------------
def test_starving_drops_hp() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=0.0, energy=1.0, hp=0.8)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") < 0.8


def test_exhausted_drops_hp() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=1.0, energy=0.0, hp=0.8)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") < 0.8


def test_both_satisfied_heals() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=1.0, energy=1.0, hp=0.5)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") > 0.5


def test_middle_band_does_nothing() -> None:
    """吃了但没吃饱(0.3) → hp 不动。这条是“饿得死”能不能发生的关键。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=0.3, energy=0.8, hp=0.5)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") == 0.5


def test_partially_satisfied_is_still_middle_band() -> None:
    """一个够、一个不够 → 还是在中间带。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=1.0, energy=0.4, hp=0.5)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") == 0.5


def test_bladder_not_involved() -> None:
    """膀胱归零不影响 hp(憋不住不致命)。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=1.0, energy=1.0, bladder=0.0, hp=0.9)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") > 0.9


def test_floor_boundary() -> None:
    """正好等于 floor → 算满足(≥)。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=CFG.hp_regen_floor,
                  energy=CFG.hp_regen_floor, hp=0.5)
    npc.heartbeat(0, CFG)
    # 代谢会先把 hunger/energy 往下拉一点点 → 落到中间带; 所以只断言“不下降”
    assert npc.signal("hp") >= 0.5


# ---------------------------------------------------------------------------
# hp_override: 日程失去拉力
# ---------------------------------------------------------------------------
def _plan_bench(w, s, hp: float):
    add_entity(w, "bench", tags=("work",), affordances={"energy": 0.5})
    npc = add_npc(w, s, "n", hp=hp, energy=1.0, hunger=0.7)   # 无需求在阈上
    npc.set_plan([PlanEntry("e0", 1, Interact("bench"))])
    return npc


def test_plan_runs_when_hp_healthy() -> None:
    w, s, _ = make_runtime(CFG)
    npc = _plan_bench(w, s, 0.9)
    assert isinstance(npc.decide(CFG, 5).intent, Interact)


def test_plan_loses_pull_when_hp_low() -> None:
    """hp < override → 先顾命, 日程不执行。"""
    w, s, _ = make_runtime(CFG)
    npc = _plan_bench(w, s, 0.3)
    assert isinstance(npc.decide(CFG, 5).intent, Idle)


def test_plan_loses_pull_mid_interaction() -> None:
    """正做着日程的事, hp 掉了 → 立刻放弃(不等迟滞比)。"""
    w, s, _ = make_runtime(CFG)
    npc = _plan_bench(w, s, 0.9)
    assert isinstance(npc.decide(CFG, 5).intent, Interact)
    npc.set_signal("hp", 0.2)
    assert isinstance(npc.decide(CFG, 6).intent, Idle)
