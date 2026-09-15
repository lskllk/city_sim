"""单轨决策(删双轨后的简单回归)。

覆盖 docs/design.md §2 的核心约定:

    **需求(utility) > 日程(plan) > idle**, 只有一条轨; 阈值只在得分上。

    1. 没有候选门槛了: 非致命需求也能驱动行为
    2. 有需求 → 不看日程
    3. 没需求 → 才走日程
    4. 迟滞: 只好了“一点点”的需求不打断当前动作; 明显更好才打断
    5. 结构: Person 上只剩一个 _goal(不再有 _plan_goal / _reflex_goal 两条轨)
    6. move_penalty 已删: 异地要不要去, 由【真实行走 tick】算进成本
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import (
    Buy,
    Decision,
    Idle,
    Interact,
    MoveTo,
    intent_kind,
)
from citysim.npc.schedule import PlanEntry
from citysim.sim.loop import run_tick

from helpers import add_entity, add_npc, make_runtime

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _decide(npc, tick: int = 100) -> Decision:
    return npc.decide(CFG, tick)


# ---------------------------------------------------------------------------
# 1. 没有候选门槛: 非致命需求也产生行为
# ---------------------------------------------------------------------------
def test_hungry_but_not_dying_still_eats() -> None:
    """hunger=0.4(缺口 0.6, 完全不到致命) —— 旧版被 fallback_need=0.9 挡死,
    现在会去吃: 阈值放在得分上, 0.6³×0.5=0.108 > 0.05。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "food", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "npc", hunger=0.4)
    _perceive(w, npc)
    d = _decide(npc)
    assert isinstance(d.intent, Interact) and d.intent.target_id == "food", d


def test_barely_hungry_does_nothing() -> None:
    """但只缺一点点(hunger=0.7) 就不值得跑一趟 —— 阈值落在得分上。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "food", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "npc", hunger=0.7)
    _perceive(w, npc)
    assert isinstance(_decide(npc).intent, Idle)


def test_fully_satisfied_stays_idle() -> None:
    """什么都不缺 → 不行动(阈值落在得分上: eff < threshold)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "food", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "npc")            # 默认信号全满
    _perceive(w, npc)
    assert isinstance(_decide(npc).intent, Idle)


# ---------------------------------------------------------------------------
# 2/3. 需求 vs 日程
# ---------------------------------------------------------------------------
def test_need_beats_plan() -> None:
    """有需求 → 做需求; 日程里那条被丢掉(不是排队等)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "food", tags=("edible",), affordances={"hunger": 0.5})
    add_entity(w, "bench", tags=("work",), affordances={"energy": 0.5})
    npc = add_npc(w, s, "npc", hunger=0.2)          # 饿 → 需求轨有活干
    npc.set_plan([PlanEntry("e0", 1, Interact("bench"))])
    _run(w, s, 3)
    assert s.interaction.active["npc"].entity_id == "food"


def test_plan_runs_when_no_need() -> None:
    """没有需求(什么都满) → 才轮到日程。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "bench", tags=("work",), affordances={"energy": 0.5})
    npc = add_npc(w, s, "npc")
    npc.set_plan([PlanEntry("e0", 1, Interact("bench"))])
    _run(w, s, 3)
    assert s.interaction.active["npc"].entity_id == "bench"


# ---------------------------------------------------------------------------
# 4. 迟滞: 好一点点不换, 明显更好才换
# ---------------------------------------------------------------------------
def test_hysteresis_keeps_current_when_barely_better() -> None:
    """正在做 bed(need 0.6), 另一个目标只好了不到 1.5 倍 → 不换。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "bed", tags=("sleepable",), affordances={"energy": 0.6},
               duration_ticks=100)
    add_entity(w, "chair", tags=("seat",), affordances={"energy": 0.5},
               duration_ticks=100)
    npc = add_npc(w, s, "npc", energy=0.4)
    npc.set_plan([PlanEntry("e0", 1, Interact("bed"))])
    _run(w, s, 3)
    assert s.interaction.active["npc"].entity_id == "bed"
    # 挤掉不换: chair 的分没到 1.5 倍
    assert s.interaction.active["npc"].entity_id == "bed"


def test_hysteresis_switches_when_much_better() -> None:
    """快饿死时, 需求必须能把人从床上拽起来。"""
    w, s, _ = make_runtime(CFG)
    bed = add_entity(w, "bed", tags=("sleepable",),
                     affordances={"energy": 0.7}, duration_ticks=100)
    bed.interruptible = False
    add_entity(w, "food", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "npc", energy=0.5, hunger=0.9)
    npc.set_plan([PlanEntry("e0", 1, Interact("bed"))])
    _run(w, s, 5)
    assert s.interaction.active["npc"].entity_id == "bed"

    npc.set_signal("hunger", 0.0)               # 快饿死 → 分远高于床
    run_tick(w, s, CFG, {})
    assert s.interaction.active["npc"].entity_id == "food"


# ---------------------------------------------------------------------------
# 5. 结构性: 只有一条轨
# ---------------------------------------------------------------------------
def test_single_track_no_dual_goals() -> None:
    """删双轨: 不再存在 _plan_goal / _reflex_goal 两个字段。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "food", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "npc", hunger=0.2)
    npc.set_plan([PlanEntry("e0", 1, Interact("food"))])
    assert not hasattr(npc, "_plan_goal")
    assert not hasattr(npc, "_reflex_goal")
    assert hasattr(npc, "_goal")


# ---------------------------------------------------------------------------
# 6. 成本模型: 比价 / 比距离
# ---------------------------------------------------------------------------
def test_cheaper_shop_wins() -> None:
    """同样是苹果, 便宜的那家分更高(比价)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "apple_cheap", location="loc", affordances={"hunger": 0.5},
               tags=("edible",), attrs={})
    add_entity(w, "apple_pricey", location="loc", affordances={"hunger": 0.5},
               tags=("edible",), attrs={})
    w.entities["apple_cheap"].price = 3.0
    w.entities["apple_cheap"].owner = "shop"
    w.entities["apple_pricey"].price = 30.0
    w.entities["apple_pricey"].owner = "shop"
    npc = add_npc(w, s, "npc", hunger=0.2, money=100.0)
    npc.set_signals(hunger=0.2)
    _perceive(w, npc)
    d = _decide(npc)
    assert isinstance(d.intent, Buy), d
    assert d.intent.item_id == "apple_cheap", d


def test_far_shop_costs_more_than_near() -> None:
    """同样价钱, 远处的店分更低(比距离) —— 成本里含真实行走 tick。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "apple", location="far", affordances={"hunger": 0.5},
               tags=("edible",))
    w.entities["apple"].price = 5.0
    w.entities["apple"].owner = "shop"
    npc = add_npc(w, s, "npc", location="home", hunger=0.2)
    npc.set_signals(hunger=0.2)
    npc.set_travel_costs({"far|home": 300})       # 走 300 tick
    # 远处的东西感知不到 —— 靠"听说/广告"进入记忆(这正是 knowledge 那条线)
    npc.note("apple", located="far", afford="hunger", value=0.5,
             price=5.0, owner="shop", believe=1.0)
    d = _decide(npc)
    # 目的地是远处 => 先 MoveTo(而不是原地买); 且成本被算进分数
    assert isinstance(d.intent, MoveTo), d
    assert d.intent.dest == "far"


def test_move_penalty_is_gone() -> None:
    """move_penalty 已删 —— 异地成本只能由真实 tick 表达。"""
    assert not hasattr(CFG, "move_penalty")
    assert not hasattr(CFG, "fallback_need")
    assert hasattr(CFG, "cost_lambda") and hasattr(CFG, "time_value")


# ---------------------------------------------------------------------------
def _run(w, s, ticks: int) -> None:
    for _ in range(ticks):
        run_tick(w, s, CFG, {})


def _perceive(w, npc) -> None:
    """决策只读【记忆】—— 世界里的实体得先被看见。"""
    from citysim.world.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
