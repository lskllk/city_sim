"""背包 DoD: take/place 瞬时、按实例/占位、@self 记忆、上限、随身可交互。"""
from __future__ import annotations

from dataclasses import replace

from citysim.core.config import SimConfig, load_config
from citysim.core.types import BACKPACK, Interact, Place, Take
from citysim.npc import brain
from citysim.world.engine import _execute_place, _execute_take
from citysim.world.interaction import InteractionSystem
from citysim.world.world import World

from helpers import add_entity, add_npc, make_runtime

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _carryable(world, eid: str, item_type: str, *, location: str = "home",
               afford: str = "hunger", value: float = 0.5,
               stock: int = 1):
    e = add_entity(world, eid, location=location, tags=("edible", "consumable"),
                   affordances={afford: value}, duration_ticks=10, stock=stock)
    e.carryable = True
    e.item_type = item_type
    return e


def test_take_moves_whole_stack_into_one_slot() -> None:
    world, systems, rng = make_runtime(CFG)
    npc = add_npc(world, systems, "npc_a", location="home", rng_pool=rng)
    _carryable(world, "apple_1", "food_apple", stock=1)
    _execute_take(world, systems, CFG, "npc_a", npc, Take("apple_1"))

    held = world.entities_held_by("npc_a")
    assert len(held) == 1 and held[0].item_type == "food_apple"
    assert "apple_1" not in world.entities          # stock=1 消耗品被搬空
    assert world.entities_at("home") == []          # 世界地面不再有它
    row = npc._mem.get(held[0].entity_id)
    assert row is not None and row.located == BACKPACK and row.owner == "npc_a"


def test_take_merges_same_type_and_counts_slots() -> None:
    world, systems, rng = make_runtime(CFG)
    npc = add_npc(world, systems, "npc_a", location="home", rng_pool=rng)
    _carryable(world, "apple_1", "food_apple", stock=100)
    _execute_take(world, systems, CFG, "npc_a", npc, Take("apple_1", qty=3))
    _execute_take(world, systems, CFG, "npc_a", npc, Take("apple_1", qty=4))
    held = world.entities_held_by("npc_a")
    assert len(held) == 1 and held[0].stock == 7    # x100 也只占 1 格
    assert world.entities["apple_1"].stock == 93


def test_inventory_limit_blocks_new_type() -> None:
    cfg = replace(CFG, inventory_limit=1)
    world, systems, rng = make_runtime(cfg)
    npc = add_npc(world, systems, "npc_a", location="home", rng_pool=rng)
    _carryable(world, "apple_1", "food_apple")
    _carryable(world, "pear_1", "food_pear")
    _execute_take(world, systems, cfg, "npc_a", npc, Take("apple_1"))
    _execute_take(world, systems, cfg, "npc_a", npc, Take("pear_1"))
    types = {e.item_type for e in world.entities_held_by("npc_a")}
    assert types == {"food_apple"}                  # 第二类被"背包已满"拒绝
    assert "pear_1" in world.entities               # 世界上的没动


def test_place_puts_back_to_region() -> None:
    world, systems, rng = make_runtime(CFG)
    npc = add_npc(world, systems, "npc_a", location="home", rng_pool=rng)
    world.locations["work"] = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
    _carryable(world, "apple_1", "food_apple", stock=2)
    _execute_take(world, systems, CFG, "npc_a", npc, Take("apple_1", qty=2))
    held = world.entities_held_by("npc_a")[0]
    _execute_place(world, systems, CFG, "npc_a", npc,
                   Place(held.entity_id, "work", qty=2))
    assert world.entities_held_by("npc_a") == []
    placed = world.entities_at("work")
    assert len(placed) == 1 and placed[0].item_type == "food_apple" \
        and placed[0].stock == 2


def test_brain_takes_carryable_then_interacts_held() -> None:
    world, systems, rng = make_runtime(CFG)
    npc = add_npc(world, systems, "npc_a", location="home", rng_pool=rng,
                  hunger=0.05)
    npc._perceived_loc = "home"
    _carryable(world, "apple_1", "food_apple")
    npc.note("apple_1", tick=0, located="home", owner="",
             afford="hunger", value=0.5, carryable=True,
             item_type="food_apple", believe=1.0)
    intent = brain.decide(npc._signals, npc._personality, npc._mem,
                          "home", CFG, 0, self_id="npc_a")
    assert isinstance(intent, Take)                 # 同地可携带 → 先 take

    # 拿起后再决策 → 直接交互随身物品
    _execute_take(world, systems, CFG, "npc_a", npc, intent)
    held = world.entities_held_by("npc_a")[0]
    intent2 = brain.decide(npc._signals, npc._personality, npc._mem,
                           "home", CFG, 0, self_id="npc_a")
    assert isinstance(intent2, Interact) and intent2.target_id == held.entity_id


def test_interact_held_anywhere() -> None:
    world, systems, rng = make_runtime(CFG)
    npc = add_npc(world, systems, "npc_a", location="home", rng_pool=rng,
                  hunger=0.05)
    _carryable(world, "apple_1", "food_apple")
    _execute_take(world, systems, CFG, "npc_a", npc, Take("apple_1"))
    held = world.entities_held_by("npc_a")[0]
    world.place_npc("npc_a", "elsewhere")           # 人走了, 东西还在背包
    inter = InteractionSystem()
    assert inter.submit(world, npc, Interact(target_id=held.entity_id)) is True
