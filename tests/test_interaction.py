"""claim 仲裁 / 消耗品 / 睡眠唤醒(走主循环集成)。"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Interact
from citysim.npc.person import Identity, Person
from citysim.sim.loop import run_tick
from citysim.world.mechanism.interaction import ActiveInteraction, InteractionSystem
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
    add_npc(world, systems, "npc_a", rng_pool=rng_pool, seed=5, hunger=0.05)
    add_npc(world, systems, "npc_b", rng_pool=rng_pool, seed=6, hunger=0.05)
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
    npc = add_npc(world, systems, "npc", rng_pool=rng_pool, seed=7, hunger=0.05)
    seed_reviews(world, systems)
    _run(world, systems, rng_pool, 40)
    assert food.stock == 0
    assert "food_1" not in world.entities       # 空消耗品已回收
    # 注: 饥饿现在半天见底(掉得快) → 吃完立刻掉一点点, 不写死 0.5
    assert npc.signal("hunger") > 0.45          # 吃了 → 饱了
    # 再多跑一段, 不会再吃同一个已空/已回收食物
    _run(world, systems, rng_pool, 30)
    assert food.stock == 0


def test_sleep_restores_energy() -> None:
    """精力极低(兜底线以下)上床 → 睡满时长后精力显著回升, 交互结束后已醒。"""
    world, systems, rng_pool = make_runtime(CFG)
    add_entity(world, "bed_1", tags=("sleepable",),
               affordances={"energy": 0.7}, duration_ticks=480)
    npc = add_npc(world, systems, "npc", rng_pool=rng_pool, seed=8, energy=0.05)
    seed_reviews(world, systems)
    _run(world, systems, rng_pool, 520)
    assert npc.signal("energy") > 0.6            # 睡饱(0.05 + 0.7 回升)
    assert not is_asleep(world, systems, "npc")  # 已醒(不在睡眠交互中)
    assert systems.interaction.active.get("npc") is None


def test_new_interaction_replaces_old() -> None:
    """换目标 → 直接顶掉旧交互(不再有“不可打断”这个概念)。"""
    world = World()
    bed = world.spawn_item_type("bed_basic", "home")
    toilet = world.spawn_item_type("toilet_basic", "home")
    npc = Person(identity=Identity(person_id="p", name="p"))
    world.npcs["p"] = npc
    world.place_npc("p", "home")           # 得先在同 region 才能提交
    bed.claimed_by = "p"
    isys = InteractionSystem()
    isys.active["p"] = ActiveInteraction(entity_id=bed.entity_id)
    ok = isys.submit(world, npc, Interact(target_id=toilet.entity_id))
    assert ok is True                       # 新交互顶掉旧的
    assert isys.active["p"].entity_id == toilet.entity_id
    assert bed.claimed_by is None           # 旧的 claim 已释放


def test_sleep_is_interruptible_by_new_action() -> None:
    """睡觉不再是“不可打断”: 上班/换目标能把他从床上叫起来。"""
    from citysim.world.edge.port import WorldPortImpl
    w, s, _ = make_runtime(CFG)
    add_entity(w, "bed", location="home", tags=("sleepable",),
               affordances={}, duration_ticks=1000)
    add_entity(w, "station", location="shop", tags=("work", "station"),
               affordances={}, duration_ticks=600)
    npc = add_npc(w, s, "n", location="home", energy=0.2)
    port = WorldPortImpl(w, s, CFG)
    npc.intake_add(port.try_take("n", "bed"))
    assert "n" in s.interaction.active                # 睡着
    assert port.try_move("n", "shop").ok              # 能起床走了
    assert "n" not in s.interaction.active
    assert s.travel["n"].to_loc == "shop"
