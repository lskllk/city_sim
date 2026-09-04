"""scenarios —— 场景注册表(display_m5_ui G0)。

复用 tools/demo_scene 的 demo/scarce; stale_kb/gossip 为 M5 剧本封装。
每个 builder 返回 (world, systems, rng_pool), systems.log 开启(log_lines)。
"""
from __future__ import annotations

import random

from citysim.core.config import load_config
from citysim.npc.knowledge import ArchetypeKB, Fact, KnowledgeBase, Source
from citysim.npc.person import Identity, Person
from citysim.sim.loop import make_systems
from citysim.world.world import Entity, World

from tools.demo_scene import build_demo, build_scarce

CFG = load_config()

_SCENARIO_DEFAULTS = {"scenario": "demo", "seed": 3, "n_npc": 5,
                      "kb_mode": "off", "tell_p": 0.0}


def _fact(seq, subj, rel, obj, conf=1.0, kind="INJECTED"):
    return Fact(fact_id=f"g{seq}", subject=subj, relation=rel, obj=obj,
                confidence=conf, source=Source(kind=kind, ref=("scn",)))


def _add(world: World, eid: str, name: str, loc: str, tags, afford=None,
         dur: int = 30, stock: int = 1, wake: str | None = None) -> Entity:
    e = Entity(entity_id=eid, name=name, tags=set(tags),
               affordances=dict(afford or {}), duration_ticks=dur,
               location_id=loc, stock=stock, wake_condition=wake,
               on_start=[], on_complete=[])
    world.entities[eid] = e
    return e


def _fac(world: World, loc: str, n: int) -> None:
    for i in range(n):
        _add(world, f"bed_{loc}_{i}", "床", loc, {"sleepable"},
             {"energy": 0.7}, dur=480, wake="energy>=0.99")
        _add(world, f"water_{loc}_{i}", "饮水机", loc,
             {"drink", "consumable"}, {"thirst": 0.6}, dur=10, stock=5000)
    toilet = _add(world, f"toilet_{loc}", "马桶", loc, {"toilet"},
                  {"bladder": 0.6, "comfort": 0.05}, dur=5)
    toilet.on_complete = [
        {"op": "set_signal", "signal": "bladder", "value": 1.0},
        {"op": "clear_pending", "field": "bladder_pending"}]


def _food(world: World, eid: str, name: str, loc: str, stock: int) -> None:
    _add(world, eid, name, loc, {"container"},
         {"provides:edible": 1.0}, dur=2, stock=stock)


def _person(world: World, systems, pid: str, name: str, loc: str,
            seed: int, hunger: float = 0.3) -> None:
    p = Person(identity=Identity(person_id=pid, name=name), location_id=loc)
    p.set_state(energy=0.7, hunger=hunger, thirst=0.6, bladder=0.9,
                health=1.0, temperature=1.0, fun=0.6, social=0.6,
                comfort=0.8, hp=1.0)
    world.npcs[pid] = p
    systems.scheduler.schedule(pid, 1, now=world.clock_tick)


def _demo(seed=3, n_npc=5, kb_mode="off", tell_p=0.0):
    world, systems, rng_pool, _ = build_demo(n_npc=n_npc, seed=seed,
                                             log=True, kb_mode=kb_mode)
    systems.tell_p = tell_p
    return world, systems, rng_pool


def _scarce(seed=3, n_npc=4, kb_mode="off", tell_p=0.0):
    world, systems, rng_pool, _ = build_scarce(n_npc=n_npc, seed=seed,
                                               log=True)
    systems.tell_p = tell_p
    return world, systems, rng_pool


def _stale_kb(seed=3, n_npc=2, kb_mode="full", tell_p=0.0):
    """剧本 S2 精简: 旧知识冰箱有食(原型)但厨房冰箱已空 → 扑空 → tombstone →
    改道超市; 两小人 home→kitchen→market 移动肉眼可见。"""
    world = World()
    systems = make_systems(log=True, tell_p=tell_p)
    from citysim.sim.loop import attach_replay
    attach_replay(world, systems)
    _fac(world, "home", n_npc)
    _fac(world, "market", n_npc)
    _food(world, "fridge_1", "冰箱", "kitchen", 0)      # 真空
    _food(world, "market_1", "超市", "market", 200)     # 真食源
    arch = ArchetypeKB([
        _fact(1, "fridge_1", "contains", "edible", 0.9),
        _fact(2, "fridge_1", "located_at", "kitchen", 1.0),
        _fact(3, "market_1", "sells", "meal_simple", 1.0),
        _fact(4, "market_1", "located_at", "market", 1.0),
        _fact(5, "meal_simple", "is_a", "edible", 1.0)])
    rng_pool = {}
    names = ["王二", "李四"]
    for i in range(n_npc):
        pid = f"npc_{i:02d}"
        _person(world, systems, pid, names[i % 2], "home", seed + i,
                hunger=0.25)
        world.npcs[pid].kb = KnowledgeBase(arch)
        rng_pool[pid] = random.Random(seed * 10 + i)
    return world, systems, rng_pool


def _gossip(seed=3, n_npc=10, kb_mode="full", tell_p=0.1):
    """剧本 S3 精简: 广场 10 人闲聊, p0 目击"咖啡馆有乐子" → told 扩散。"""
    world = World()
    systems = make_systems(log=True, tell_p=tell_p)
    from citysim.sim.loop import attach_replay
    attach_replay(world, systems)
    _fac(world, "plaza", n_npc)          # 床水马桶(非容器, 不产生观察事实)
    rng_pool = {}
    names = ["王二", "李四", "张三", "赵五", "钱六", "孙七",
             "周八", "吴九", "郑十", "陈一"]
    for i in range(n_npc):
        pid = f"npc_{i:02d}"
        p = Person(identity=Identity(person_id=pid, name=names[i]),
                   location_id="plaza")
        p.set_state(energy=0.9, hunger=1.0, thirst=1.0, bladder=0.9,
                    health=1.0, temperature=1.0, fun=0.6, social=0.6,
                    comfort=0.8, hp=1.0)
        p.kb = KnowledgeBase()
        world.npcs[pid] = p
        rng_pool[pid] = random.Random(seed * 10 + i)
        systems.scheduler.schedule(pid, 1, now=0)
    world.npcs["npc_00"].kb.learn(
        subject="cafe_7", relation="affords", obj="fun", confidence=1.0,
        source=Source(kind="OBSERVED"))
    return world, systems, rng_pool


SCENARIOS = {"demo": _demo, "scarce": _scarce,
             "stale_kb": _stale_kb, "gossip": _gossip}


def build_scenario(scenario="demo", seed=3, n_npc=5, kb_mode="off",
                   tell_p=0.0):
    fn = SCENARIOS.get(scenario, _demo)
    return fn(seed=seed, n_npc=n_npc, kb_mode=kb_mode, tell_p=tell_p)
