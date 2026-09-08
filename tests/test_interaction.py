"""M3 DoD: claim 仲裁 / 消耗品 / 睡眠唤醒 / 不可打断交互(走主循环集成)。"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Interact
from citysim.npc.person import Identity, Person
from citysim.sim.loop import run_tick
from citysim.world.interaction import ActiveInteraction, InteractionSystem
from citysim.world.world import World

from helpers import (add_entity, add_npc, is_asleep, make_runtime,
                     seed_reviews)

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _run(world, systems, rng_pool, ticks: int) -> None:
    for _ in range(ticks):
        run_tick(world, systems, CFG, rng_pool)


def test_claim_conflict() -> None:
    """两个饥饿 NPC、一份食物(stock=1), 同 tick 重评 → 恰一人开吃,
    另一人收到 intent_failed。"""
    world, systems, rng_pool = make_runtime(CFG, log=True)
    add_entity(world, "food_1", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=10, stock=1)
    add_npc(world, systems, "npc_a", rng_pool=rng_pool, seed=5, hunger=0.2)
    add_npc(world, systems, "npc_b", rng_pool=rng_pool, seed=6, hunger=0.2)
    seed_reviews(world, systems)
    _run(world, systems, rng_pool, 60)

    assert "food_1" not in world.entities       # 吃完即回收(空消耗品不滞留)
    done = [l for l in systems.log_lines
            if "\tinteraction_done\t" in l and "entity=food_1" in l]
    assert len(done) == 1                        # 只有一人完成对该食物的交互
    failed = [l for l in systems.log_lines if "\tintent_failed\t" in l]
    assert len(failed) >= 1                      # 另一人收到 intent_failed


def test_consumable_stock() -> None:
    """吃完 stock 减 1; stock=0 后不再出现在可占用(可 claim)。"""
    world, systems, rng_pool = make_runtime(CFG)
    food = add_entity(world, "food_1", tags=("edible", "consumable"),
                      affordances={"hunger": 0.5}, duration_ticks=10, stock=1)
    npc = add_npc(world, systems, "npc", rng_pool=rng_pool, seed=7, hunger=0.2)
    seed_reviews(world, systems)
    _run(world, systems, rng_pool, 40)
    assert food.stock == 0
    assert "food_1" not in world.entities       # 空消耗品已回收
    assert npc.signal("hunger") > 0.5           # 吃了 → 饱了
    # 再多跑一段, 不会再吃同一个已空/已回收食物
    _run(world, systems, rng_pool, 30)
    assert food.stock == 0


def test_sleep_wake() -> None:
    """精力 0.3 上床 → wake_condition(energy>=0.99) 自动醒 → 醒后不再睡着。"""
    world, systems, rng_pool = make_runtime(CFG)
    add_entity(world, "bed_1", tags=("sleepable",),
               affordances={"energy": 0.7}, duration_ticks=480,
               wake_condition="energy>=0.99")
    npc = add_npc(world, systems, "npc", rng_pool=rng_pool, seed=8, energy=0.3)
    seed_reviews(world, systems)
    _run(world, systems, rng_pool, 520)
    assert npc.signal("energy") > 0.9           # 睡饱
    assert not is_asleep(world, systems, "npc")  # 已醒(不在睡眠交互中)
    assert systems.interaction.active.get("npc") is None


def test_interruptible_false_refuses_override() -> None:
    """interruptible=False(床) 进行中 → 拒绝被新意图顶掉, claim 不悬挂。"""
    world = World()
    bed = world.spawn_item_type("bed_basic", "home")
    toilet = world.spawn_item_type("toilet", "home")
    npc = Person(identity=Identity(person_id="p", name="p"))
    world.npcs["p"] = npc
    bed.claimed_by = "p"
    isys = InteractionSystem()
    isys.active["p"] = ActiveInteraction(npc_id="p", entity_id=bed.entity_id,
                                         remaining_ticks=480, total_ticks=480)
    failed: list[str] = []

    def _on(ev):
        if ev.kind == "intent_failed":
            failed.append(ev.kind)

    world.bus.subscribe_log(_on)
    ok = isys.submit(world, npc,
                     Interact(target_id=toilet.entity_id))
    assert ok is False                     # 不可打断 → 拒绝
    assert failed == ["intent_failed"]
    assert bed.claimed_by == "p"           # 未被顶替
    assert isys.active["p"].entity_id == bed.entity_id
