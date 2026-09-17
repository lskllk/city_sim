"""hp: 只有【饥饿】参与 —— 连续 hunger==0 满宽限(3 天)才开始渐降。

    · 归零不立刻掉血: 连续 hunger==0 满 starve_grace_days 天才开始掉
    · 中途吃了饭(hunger>0) → 计数清零, 下次归零重新计
    · 睡眠/精力【不参与 hp】(旧三态: 衰减/回升/中间带 已删)
    · hp < hp_override → 日程失去拉力(命比钱大): 计划不执行

注: 文件名沿用作历史; 现在没有“三态”了。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Idle, Interact, Plan
from citysim.npc.schedule import PlanEntry

from helpers import add_entity, add_npc, make_runtime

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


# ---------------------------------------------------------------------------
# 饥饿 → hp
# ---------------------------------------------------------------------------
def test_hunger_zero_does_not_drop_hp_immediately() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=0.0, energy=1.0, hp=0.8)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") == 0.8


def test_hp_drops_after_grace() -> None:
    """连续 hunger==0 满 starve_grace_days 天 → hp 才开始掉(渐降)。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=0.0, energy=1.0, hp=0.8)
    grace = int(CFG.hp_starve_grace_ticks)
    for _ in range(grace - 1):
        npc.heartbeat(0, CFG)
    assert npc.signal("hp") == 0.8            # 还差一 tick, 不掉
    npc.heartbeat(0, CFG)                      # 满宽限 → 开始掉
    assert npc.signal("hp") < 0.8


def test_eating_resets_the_counter() -> None:
    """中途吃了饭 → 计数清零; 下次归零重新计。"""
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
    assert npc.signal("hp") >= hp_after        # 重新计时, 还没到宽限


def test_energy_never_affects_hp() -> None:
    """睡眠/精力【不参与】: energy 一直 0 也不掉血。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=1.0, energy=0.0, hp=0.8)
    for _ in range(int(CFG.hp_starve_grace_ticks) + 10):
        npc.heartbeat(0, CFG)
        npc.set_signal("energy", 0.0)          # 一直熬夜
        npc.set_signal("hunger", 1.0)          # 但不饿
    assert npc.signal("hp") == 0.8


def test_no_regen_eating_does_not_heal() -> None:
    """没有回血: 吃饱也不涨 hp(旧三态的“回升”已删)。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=1.0, energy=1.0, hp=0.5)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") == 0.5


def test_bladder_not_involved() -> None:
    """膀胱归零不影响 hp(憋不住不致命)。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", hunger=1.0, energy=1.0, bladder=0.0, hp=0.9)
    npc.heartbeat(0, CFG)
    assert npc.signal("hp") == 0.9


# ---------------------------------------------------------------------------
# hp_override: 日程失去拉力
# ---------------------------------------------------------------------------
def _plan_bench(w, s, hp: float):
    add_entity(w, "bench", tags=("work",), affordances={})
    npc = add_npc(w, s, "n", hp=hp, energy=1.0, hunger=0.7)   # 无需求在阈上
    npc.assign(Plan([PlanEntry("e0", 1, Interact("bench"))]))
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
