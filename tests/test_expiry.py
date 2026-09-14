"""食物保质期(简单 MVP)。

    货有保质期 → 到点变质(stock 归 0)
    → 目标存量由【保质期】推导(不再是“每种囤几个”的魔法数字)

设计见 docs/20260914/plan.md §6。加保质期的目的不是“限制买多少”,
而是让“买多少”变成真决策 —— 且给店主开了“新鲜度 / 临期促销”这条玩法线。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.npc import brain
from citysim.sim.loop import run_tick
from citysim.world.engine import _deliver  # noqa: PLC2701  (测试专用: 直接验送货)
from citysim.world.itemdefs import load_item_defs

from helpers import add_entity, add_npc, make_runtime

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


# ---------------------------------------------------------------------------
# 数据 → 实体
# ---------------------------------------------------------------------------
def test_item_defs_declare_shelf_life() -> None:
    defs = load_item_defs()
    assert defs["meal_simple"].shelf_life_ticks == 1440        # 1 天
    assert defs["food_apple"].shelf_life_ticks == 4320         # 3 天
    assert defs["bed_basic"].shelf_life_ticks == 0             # 床不会坏


def test_deliver_stamps_expiry() -> None:
    w, s, _ = make_runtime(CFG)
    shop = add_entity(w, "market_1", location="market",
                      affordances={"hunger": 0.5}, stock=50)
    shop.item_type = "meal_simple"
    shop.shelf_life_ticks = 1440
    npc = add_npc(w, s, "npc", location="home")
    npc.set_home("home")
    w.clock_tick = 1000
    c = _deliver(w, "npc", npc, shop, 2, "home")
    assert c is not None
    assert c.stock == 2
    assert c.expires_tick == 1000 + 1440        # 打戳 = 现在 + 保质期
    assert c.shelf_life_ticks == 1440


def test_merge_takes_earliest_expiry() -> None:
    """合并库存取【最早到期】: 一格只要有一份旧了, 整格算旧(方案 A)。"""
    w, s, _ = make_runtime(CFG)
    shop = add_entity(w, "market_1", location="market",
                      affordances={"hunger": 0.5}, stock=50)
    shop.item_type = "meal_simple"
    shop.shelf_life_ticks = 1440
    npc = add_npc(w, s, "npc", location="home")
    npc.set_home("home")
    w.clock_tick = 0
    c1 = _deliver(w, "npc", npc, shop, 1, "home")
    assert c1.expires_tick == 1440
    w.clock_tick = 600                          # 半路又买一份(它更新)
    c2 = _deliver(w, "npc", npc, shop, 1, "home")
    assert c2 is c1 and c2.stock == 2
    assert c2.expires_tick == 1440              # 不因为“有新货”而延后


# ---------------------------------------------------------------------------
# 变质
# ---------------------------------------------------------------------------
def test_food_spoils_and_emits_once() -> None:
    w, s, rng = make_runtime(CFG, log=True)
    shop = add_entity(w, "market_1", location="market",
                      affordances={"hunger": 0.5}, stock=50)
    shop.item_type = "meal_simple"
    shop.shelf_life_ticks = 10                  # 让它很快坏
    add_entity(w, "bed", location="home", tags=("sleepable",),
               affordances={"energy": 0.7}, duration_ticks=100)
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng)
    npc.set_home("home")
    c = _deliver(w, "npc", npc, shop, 3, "home")
    assert c.stock == 3

    for _ in range(11):
        run_tick(w, s, CFG, rng)
    assert c.stock == 0, "到点没变质"
    evs = [e for e in s.ui_events if e.get("kind") == "spoiled"]
    assert len(evs) == 1, evs                  # 只报一次, 不每 tick 刷

    for _ in range(5):
        run_tick(w, s, CFG, rng)
    assert len([e for e in s.ui_events if e.get("kind") == "spoiled"]) == 1


def test_non_perishable_never_spoils() -> None:
    w, s, rng = make_runtime(CFG, log=True)
    bed = add_entity(w, "bed", location="home", tags=("sleepable",),
                     affordances={"energy": 0.7}, duration_ticks=10)
    assert bed.expires_tick == 0
    add_npc(w, s, "npc", location="home", rng_pool=rng)
    for _ in range(50):
        run_tick(w, s, CFG, rng)
    assert bed.stock == 1


# ---------------------------------------------------------------------------
# 进决策: 目标存量由保质期推导
# ---------------------------------------------------------------------------
def test_target_stock_derived_from_shelf_life() -> None:
    """同样家里还剩 1 份: 短保的(1 天)不再补, 长保的(3 天)还想补。

    —— 这就是“把保质期加进购买决策”: 不是限制买多少,
       而是“在它坏掉之前我吃得完多少”。
    """
    # 简餐: value 0.5, 保质期 1 天 → 目标 ≈ 0.67 份/天 × 1 天 × 0.8 = 0.53
    short = brain._future_need(CFG, 1.0, "hunger", 0.5, 1440, 1.0)
    # 苹果: value 0.35, 保质期 3 天 → 目标 ≈ 0.95 × 3 × 0.8 = 2.29
    long_ = brain._future_need(CFG, 1.0, "hunger", 0.35, 4320, 1.0)
    assert short == 0.0, short          # 已经够了(再囤就要坏)
    assert long_ > 0.4, long_           # 明显还缺口

    # 家里空的 → 两者都要补
    assert brain._future_need(CFG, 0.0, "hunger", 0.5, 1440, 1.0) == 1.0
    assert brain._future_need(CFG, 0.0, "hunger", 0.35, 4320, 1.0) == 1.0


def test_thrift_scales_target() -> None:
    """抠门(爱囤)的人同样的货还想多囤一点。"""
    n = brain._future_need(CFG, 0.8, "hunger", 0.35, 4320, 1.0)
    t = brain._future_need(CFG, 0.8, "hunger", 0.35, 4320, 2.0)
    assert t > n


def test_no_shelf_life_falls_back_to_default_days() -> None:
    """不会坏的东西按 default_days 算(否则会想囤到无穷)。"""
    v = brain._future_need(CFG, 0.0, "hunger", 0.5, 0, 1.0)
    assert v == 1.0
