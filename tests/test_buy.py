"""Buy 意图执行: 成交扣钱(只减不增) + owner 归自己 + 移回家 + KB 刷新位置。

单元集成: 市场在售电视 → NPC 有钱买 → 电视进屋; 场景集成: elm_lane 里
npc_wang 有钱且 fun 低 → 去市场买 tv_1 搬回家, 市场少一件、家多一件,
之后 NPC 回家。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.gateway.scenarios import build_scenario
from citysim.npc.knowledge import Source
from citysim.sim.loop import run_tick

from helpers import add_entity, add_npc, make_runtime, seed_reviews

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _run(world, systems, rng_pool, ticks: int) -> None:
    for _ in range(ticks):
        run_tick(world, systems, CFG, rng_pool)


def test_buy_moves_item_home_deducts_money_updates_kb() -> None:
    world, systems, rng_pool = make_runtime(CFG, log=True)
    tv = add_entity(world, "tv_1", location="market",
                    tags=("entertain",), affordances={"fun": 0.4},
                    duration_ticks=40, stock=1)
    tv.price = 60.0
    tv.owner = ""
    npc = add_npc(world, systems, "npc", location="market",
                  rng_pool=rng_pool, seed=1, fun=0.2)
    npc.home = "home"
    npc.money = 100.0
    npc.kb.learn(subject="tv_1", relation="affords", obj="fun", value=0.4,
                 confidence=1.0, source=Source(kind="INJECTED"), tick=0)
    npc.kb.learn(subject="tv_1", relation="located_at", obj="market",
                 confidence=1.0, source=Source(kind="INJECTED"), tick=0)
    seed_reviews(world, systems)

    _run(world, systems, rng_pool, 3)

    assert tv.owner == "npc"
    assert tv.location_id == "home"
    assert npc.money == 40.0
    locs = {f.obj for f in npc.kb.query(subject="tv_1",
                                        relation="located_at")}
    assert locs == {"home"}
    assert any("\tbought\t" in l and "item=tv_1" in l
               for l in systems.log_lines)


def test_scene_npc_buys_tv_brings_home_then_goes_home() -> None:
    w, s, rng = build_scenario("elm_lane", seed=3)
    npc = w.npcs["npc_wang"]
    npc.money = 100.0
    # 压低 fun、拉高其它需求, 聚焦"买电视"
    npc.signals["fun"] = 0.2
    npc.signals["hunger"] = 0.9
    npc.signals["thirst"] = 0.9
    npc.signals["energy"] = 0.9

    # 跑到买到 tv_1(上限防死循环)
    for _ in range(2000):
        run_tick(w, s, CFG, rng)
        if w.entities["tv_1"].owner == "npc_wang":
            break

    assert w.entities["tv_1"].owner == "npc_wang"
    assert w.entities["tv_1"].location_id == "apt_101"
    assert npc.money < 100.0

    market_tvs = [e for e in w.entities.values()
                  if e.location_id == "market" and "entertain" in e.tags]
    home_tvs = [e for e in w.entities.values()
                if e.location_id == "apt_101" and "entertain" in e.tags]
    assert len(market_tvs) == 1          # 市场只剩 tv_2
    assert len(home_tvs) == 1            # tv_1 进了家

    # 之后 NPC 会回家(用 tv / 吃饭)
    for _ in range(2000):
        run_tick(w, s, CFG, rng)
        if npc.location_id == "apt_101":
            break
    assert npc.location_id == "apt_101"
