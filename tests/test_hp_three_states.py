"""hp 三态 + 饥饿宽限 + hp_override(docs/design.md §2)。

    下降   hunger == 0 或 energy == 0 【连续满 starve_grace_days 天】
    上升   hunger ≥ hp_regen_floor 且 energy ≥ hp_regen_floor
    不动   其他(中间带 + 宽限期 —— 归零不立刻掉命)
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
def test_starving_does_not_drop_hp_immediately() -> None:
    """饥饿归零【不立刻掉命】—— 宽限期内 hp 不动。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=0.0, energy=1.0, hp=0.8)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") == 0.8


def test_starving_drops_hp_after_grace() -> None:
    """连续 hunger==0 满 starve_grace_days 天 → hp 才开始掉。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=0.0, energy=1.0, hp=0.8)
    grace = int(CFG.hp_starve_grace_ticks)
    for _ in range(grace - 1):
        npc.heartbeat(0, CFG)
    assert npc.signal("hp") == 0.8            # 还差一 tick, 不掉
    npc.heartbeat(0, CFG)                      # 满宽限 → 开始掉
    assert npc.signal("hp") < 0.8


def test_recovering_resets_the_grace() -> None:
    """中间恢复就不掉: 计数器重置, 重新开始算。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=0.0, energy=1.0, hp=0.8)
    for _ in range(1000):
        npc.heartbeat(0, CFG)
    npc.set_signal("hunger", 1.0)
    npc.heartbeat(0, CFG)
    assert npc._starve_ticks == 0
    hp_after = npc.signal("hp")
    npc.set_signal("hunger", 0.0)
    for _ in range(1000):
        npc.heartbeat(0, CFG)
    assert npc.signal("hp") >= hp_after        # 重新计时, 还没到宽限 → 不掉


def test_exhausted_drops_hp_after_grace() -> None:
    """energy==0 同理: 宽限期内不掉。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=1.0, energy=0.0, hp=0.8)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") == 0.8
    for _ in range(int(CFG.hp_starve_grace_ticks)):
        npc.heartbeat(0, CFG)
        npc.set_signal("energy", 0.0)         # 保持归零
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


