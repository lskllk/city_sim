"""TASK006: 计划里的购买(Buy) —— 扣钱 + 减店库存 + 合并进家容器。"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Buy
from citysim.npc.schedule import PlanEntry
from citysim.sim.loop import run_tick

from helpers import register_company, add_entity, add_npc, make_runtime

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _run(w, s, rng, ticks: int) -> None:
    for _ in range(ticks):
        run_tick(w, s, CFG, rng)


def test_plan_buy_deducts_money_and_merges_stock() -> None:
    w, s, rng = make_runtime(CFG, log=True)
    shop = add_entity(w, "market_1", location="market",
                      tags=("edible", "consumable"),
                      affordances={"hunger": 0.5}, duration_ticks=10, stock=50)
    shop.price = 3.0
    shop.item_type = "meal_simple"
    shop.persist_empty = True
    pantry = add_entity(w, "food", location="home",
                        tags=("edible", "consumable"),
                        affordances={"hunger": 0.5}, duration_ticks=10, stock=1)
    pantry.item_type = "meal_simple"
    pantry.owner = "npc"
    pantry.persist_empty = True
    register_company(w, "market")

    npc = add_npc(w, s, "npc", location="home", rng_pool=rng)   # money=100
    npc.set_home("home")
    npc.note("market_1", located="market", believe=1.0)         # 知道店在哪
    npc.set_plan([PlanEntry("e0", 1, Buy("market_1", qty=3))])
    _run(w, s, rng, 80)

    # 注(2026-09-14): 现在一次买【缺口】(不是固定 3 件) → 不锁死具体金额,
    # 只验不变量: 钱少了 / 店里少了 / 合并进了家里的同一个容器。
    assert npc.money < 100.0
    assert shop.stock < 50
    assert pantry.stock > 1
    assert w.loc_of("npc") == "market"       # 自动走位到店


def test_plan_buy_insufficient_money_fails_and_skips() -> None:
    w, s, rng = make_runtime(CFG, log=True)
    shop = add_entity(w, "market_1", location="market",
                      tags=("edible", "consumable"),
                      affordances={"hunger": 0.5}, duration_ticks=10, stock=50)
    shop.price = 999.0
    shop.item_type = "meal_simple"
    register_company(w, "market")            # 没登记公司的店现在不能卖
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng)
    npc.set_home("home")
    npc.note("market_1", located="market", believe=1.0)
    npc.set_plan([PlanEntry("e0", 1, Buy("market_1", qty=3))])
    _run(w, s, rng, 80)
    assert npc.money == 100.0                # 没扣钱
    assert any("钱不够" == f["why"] for f in npc.failure_log())
