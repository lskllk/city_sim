"""testm4 D 组 —— 黄金标准: 新增物品零 Python 改动即可用。

test_new_item_zero_python: 动态写 coffee_machine JSON -> 加载 -> spawn ->
低 energy NPC 500 tick 内使用它(事件可见 + energy 上升 + bladder_pending>0),
全程未 import 新模块。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from citysim.core.config import load_config
from citysim.npc.person import Identity, Person
from citysim.sim.loop import attach_replay, make_systems, run_tick
from citysim.world.itemdefs import clear_cache
from citysim.world.world import World

ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = ROOT / "config" / "items"
CFG = load_config(ROOT / "config" / "sim.toml")

COFFEE = {
    "item_type": "coffee_machine",
    "name": "咖啡机",
    "tags": ["drinkable_source"],
    "affordances": {"energy": 0.15, "thirst": 0.2},
    "duration_ticks": 5,
    "on_start": [{"op": "add_pending", "field": "bladder_pending",
                   "amount": 0.2}],
    "attrs": {},
    "stock": 1,
}


@pytest.fixture
def coffee_json():
    p = ITEMS_DIR / "zz_coffee_machine.json"
    p.write_text(json.dumps(COFFEE, ensure_ascii=False), encoding="utf-8")
    clear_cache()
    yield p
    p.unlink(missing_ok=True)
    clear_cache()


def _scene():
    world = World()
    npc = Person(identity=Identity(person_id="p", name="p"), location_id="home")
    world.npcs["p"] = npc
    systems = make_systems(log=True)
    attach_replay(world, systems)
    systems.scheduler.schedule("p", 1, now=0)
    return world, systems, npc


def test_new_item_zero_python(coffee_json) -> None:
    world, systems, npc = _scene()
    machine = world.spawn_item_type("coffee_machine", "home")
    assert machine is not None
    used: list[bool] = []

    def _on(ev):
        if ev.kind == "interaction_done" \
                and ev.payload.get("entity") == machine.entity_id:
            used.append(True)

    world.bus.subscribe_log(_on)
    npc.set_state(energy=0.15, thirst=0.4)
    pend_ever = False
    rng_pool = {"p": random.Random(3)}
    for _ in range(500):
        run_tick(world, systems, CFG, rng_pool)
        pend_ever = pend_ever or npc.bladder_pending > 0
    assert used, "咖啡机从未被使用"
    assert npc.signals["energy"] > 0.16          # energy 从 0.15 回升
    assert pend_ever                              # bladder_pending 曾 >0(膀胱负荷生效)
