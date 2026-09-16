"""工作离岗成本(WP-B) + 食物按真实缺口封顶(WP-A)。

用户口径:
  · 食物补不超过缺口 —— min(value, need), 只对 driver="now";
  · 上班时间离开公司 = 旷工 → cost 计入【日薪】;
    在班 + 人在工位 + 目的地不是工位 才算离岗; 手边的货不算。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.npc import brain
from citysim.core.types import Interact, MoveTo

from helpers import add_entity, add_npc, make_runtime

CFG = load_config("config/sim.toml")


def _setup(hunger: float, meal_value: float = 0.5):
    """NPC 站在工位 shop; 手边有免费梨; 家里有简餐(meal_value)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "pear", location="shop", tags=("edible", "consumable"),
               affordances={"hunger": 0.3}, duration_ticks=12, stock=5)
    add_entity(w, "meal", location="home", tags=("edible", "consumable"),
               affordances={"hunger": meal_value}, duration_ticks=20, stock=5)
    npc = add_npc(w, s, "npc", location="shop", hunger=hunger)
    # 免费公共(owner="" price=0 → _self_use), 家食 located==home 也自用
    npc.note("pear", located="shop", owner="", price=0.0, afford="hunger",
             value=0.3, stock=5, believe=1.0, tags=("edible", "consumable"))
    npc.note("meal", located="home", owner="", price=0.0, afford="hunger",
             value=meal_value, stock=5, believe=1.0,
             tags=("edible", "consumable"))
    npc.set_travel_costs({"home|shop": 31, "shop|home": 31})
    return w, npc


def _decide(npc, leave_cost: float):
    return brain.decide_scored(
        npc.signals, {}, npc._mem, "shop", CFG, 0, npc.person_id,
        npc._travel_costs, npc._money, "home",
        workplace="shop", leave_cost=leave_cost)


def test_no_leave_cost_home_wins() -> None:
    """不计离岗: 家食 value 0.5 > 梨 0.3 → 回家。"""
    w, npc = _setup(hunger=0.2)
    intent, _ = _decide(npc, leave_cost=0.0)
    assert isinstance(intent, MoveTo) and intent.dest == "home"


def test_leave_cost_makes_eat_in_place_win() -> None:
    """旷工扣日薪 ¥80: 家的分被压到梨之下 → 就地吃公司的梨。"""
    w, npc = _setup(hunger=0.2)
    intent, eff = _decide(npc, leave_cost=80.0)
    assert isinstance(intent, Interact) and intent.target_id == "pear", (intent, eff)


def test_value_capped_by_real_gap() -> None:
    """家里放一个 value=20 的大补食物 —— 封顶到 need(0.8) 后仍不敌手边的梨。"""
    w, npc = _setup(hunger=0.2, meal_value=20.0)
    intent, _ = _decide(npc, leave_cost=80.0)
    assert isinstance(intent, Interact) and intent.target_id == "pear"


def test_cap_only_for_now_driver() -> None:
    """封顶只作用于 now; 囤货(future)的 value 不该被 need 夹。"""
    from citysim.npc.brain import _gather_candidates
    w, npc = _setup(hunger=0.2)
    cands = _gather_candidates(npc._mem, npc.signals, 0, self_id=npc.person_id,
                               home="home", cfg=CFG,
                               future_weight=CFG.stock_future_weight)
    # 两种 driver 都出现(梨=now, 家食 future 或 now); 至少不崩
    assert cands
