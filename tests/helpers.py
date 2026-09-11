"""M3 测试共享辅助：搭 scene(世界+系统+rng)。"""
from __future__ import annotations

import random

from citysim.core.config import SimConfig
from citysim.npc.person import Identity, Person
from citysim.sim.loop import attach_replay, make_systems
from citysim.world.world import Entity, World


def make_runtime(cfg: SimConfig, *, log: bool = False):
    """新开 world + systems(+可选回放日志) + rng_pool。"""
    world = World()
    systems = make_systems(log=log)
    rng_pool: dict[str, random.Random] = {}
    if log:
        attach_replay(world, systems)
    return world, systems, rng_pool


def add_npc(world: World, systems, person_id: str, *, location: str = "loc",
            rng_pool: dict | None = None, seed: int = 1, **kw) -> Person:
    p = Person(identity=Identity(person_id=person_id, name=person_id))
    if kw:
        p.set_signals(**kw)
    world.npcs[person_id] = p
    world.place_npc(person_id, location)
    if rng_pool is not None:
        rng_pool[person_id] = random.Random(seed)
    return p


def add_entity(world: World, entity_id: str, *, location: str = "loc",
               name: str | None = None, tags=(), affordances=None,
               duration_ticks: int = 30, stock: int = 1,
               attrs=None, on_complete: list | None = None) -> Entity:
    e = Entity(
        entity_id=entity_id, name=name or entity_id, tags=set(tags),
        affordances=dict(affordances or {}), duration_ticks=duration_ticks,
        location_id=location, stock=stock,
        attrs=dict(attrs or {}),
        on_complete=list(on_complete or []),
    )
    world.entities[entity_id] = e
    return e


def seed_reviews(world: World, systems, delay: int = 1) -> None:
    """兼容占位: 旧"给所有 NPC 排首评"已删除(驱动改为每 tick 扫描空闲 NPC)。"""
    return None


def is_asleep(world: World, systems, person_id: str) -> bool:
    act = systems.interaction.active.get(person_id)
    if act is None:
        return False
    ent = world.entities.get(act.entity_id)
    return ent is not None and ent.is_sleepable
