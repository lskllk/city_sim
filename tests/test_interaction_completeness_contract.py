"""交互完成时序契约(M5 前置记账 附注, 显式锁死)。

契约: 消耗品完成 ->
  1. interaction_done 事件发布时 entity 仍在 world.entities(观察者可解析)
  2. 该 tick 结束(entity 回收)后 entity 已不在 world
任何打乱顺序的重构(golden 之外)先在这里红。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.sim.loop import run_tick

from helpers import add_entity, add_npc, make_runtime, seed_reviews

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def test_consume_self_event_sequence() -> None:
    world, systems, rng_pool = make_runtime(CFG)
    food = add_entity(world, "food_1", tags=("edible", "consumable"),
                      affordances={"hunger": 0.5}, duration_ticks=3, stock=1)
    at_event_present: list[bool] = []

    def _on(ev):
        if ev.kind == "interaction_done" \
                and ev.payload.get("entity") == "food_1":
            at_event_present.append(food.entity_id in world.entities)

    world.bus.subscribe_log(_on)
    add_npc(world, systems, "npc", rng_pool=rng_pool, seed=1, hunger=0.2)
    seed_reviews(world, systems)

    done_tick = None
    for t in range(1, 40):
        run_tick(world, systems, CFG, rng_pool)
        if at_event_present:                    # 本 tick 内事件已发布
            done_tick = t
            break

    assert done_tick is not None, "未见 interaction_done(food_1)"
    assert at_event_present and at_event_present[-1], \
        "事件回调时 entity 已被回收(时序破坏)"
    # 事件发布所在 tick 结束后, entity 已从 world 移除
    assert "food_1" not in world.entities
