"""demo_scene —— 供观察器与 soak 测试共用的可复现 demo 世界。

一座房子(home): 冰箱(无限产餐, GOAP 取→吃链) + 床(睡眠) + 饮水机(补水) +
马桶(清膀胱)。NPC 同 location, 靠 claim 仲裁竞争。
"""
from __future__ import annotations

import random
from pathlib import Path

from citysim.core.config import load_config
from citysim.npc.person import Identity, Person, full_signals
from citysim.sim.loop import attach_replay, make_systems
from citysim.world.world import Entity, World

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")

DEFAULT_NAMES = ["王二", "李四", "张三", "赵五", "钱六",
                 "孙七", "周八", "吴九", "郑十", "陈一"]


def _entity(world: World, eid: str, name: str, tags, affordances,
            duration_ticks: int, stock: int = 1,
            wake_condition: str | None = None, attrs=None) -> Entity:
    e = Entity(
        entity_id=eid, name=name, tags=set(tags),
        affordances=dict(affordances), duration_ticks=duration_ticks,
        location_id="home", stock=stock,
        attrs=dict(attrs or {}), wake_condition=wake_condition,
    )
    world.entities[eid] = e
    return e


def build_demo(n_npc: int = 6, seed: int = 7, log: bool = False,
               names: list[str] | None = None):
    """搭一座可复现的 demo 房子。返回 (world, systems, rng_pool, cfg)。"""
    world = World()
    systems = make_systems(log=log)
    if log:
        attach_replay(world, systems)
    rng_pool: dict[str, random.Random] = {}

    # ---- 家具/资源 ------------------------------------------------
    _entity(world, "fridge_1", "冰箱", {"container"},
            {"provides:edible": 1.0}, duration_ticks=2, stock=-1)
    # 常备餐台(无限 loose edible): 少量多餐(~8h 一次), 保证任意 24h 吃 2~4 次
    for i in range(max(2, n_npc // 2)):
        _entity(world, f"plate_{i}", "餐台", {"edible", "consumable"},
                {"hunger": 0.35}, duration_ticks=15, stock=10000,
                attrs={"bladder_load": 0.3})
    for i in range(max(2, n_npc)):
        _entity(world, f"bed_{i}", "床", {"sleepable"},
                {"energy": 0.7}, duration_ticks=480,
                wake_condition="energy>=0.99")
    for i in range(max(4, n_npc)):
        _entity(world, f"water_{i}", "饮水机", {"drink", "consumable"},
                {"thirst": 0.6}, duration_ticks=10, stock=5000,
                attrs={"bladder_load": 0.15})
    _entity(world, "toilet_1", "马桶", {"toilet"},
            {"bladder": 0.6, "comfort": 0.05}, duration_ticks=5)

    # ---- NPC(初始状态由 seed 扰动, 避免同相位) ---------------------
    names = names or DEFAULT_NAMES
    for i in range(n_npc):
        pid = f"npc_{i:02d}"
        r = random.Random(seed * 100 + i)
        p = Person(identity=Identity(person_id=pid,
                                     name=names[i % len(names)]),
                   location_id="home")
        p.hour_f = r.uniform(0.0, 24.0)
        p.set_state(
            energy=r.uniform(0.4, 0.9), hunger=r.uniform(0.3, 0.9),
            thirst=r.uniform(0.3, 0.9), bladder=1.0,
            health=1.0, temperature=1.0, fun=0.6, social=0.6,
            comfort=0.8, hp=1.0,
        )
        p.personality = {}   # 中性性格; 可后续注入差异
        world.npcs[pid] = p
        rng_pool[pid] = random.Random(seed + i)
        systems.scheduler.schedule(pid, 1, now=0)

    return world, systems, rng_pool, CFG


def build_scarce(n_npc: int = 4, seed: int = 1, log: bool = False,
                 names: list[str] | None = None):
    """稀缺场景(testM0~M3 疑点 2): 4 NPC 抢 1 厕所 + 1 冰箱(stock=2, 有限)。

    床/水按人数足额(避免无关卡点), 把竞争集中在 厕所/冰箱 —— 让 claim 冲突与
    失败重选路径被真实压到。NPC 同初始状态 → 需求同步 → 高并发争抢。
    """
    world = World()
    systems = make_systems(log=log)
    if log:
        attach_replay(world, systems)
    rng_pool: dict[str, random.Random] = {}

    _entity(world, "fridge_1", "冰箱", {"container"},
            {"provides:edible": 1.0}, duration_ticks=2, stock=2)
    _entity(world, "toilet_1", "马桶", {"toilet"},
            {"bladder": 0.6, "comfort": 0.05}, duration_ticks=5)
    _entity(world, "water_0", "饮水机", {"drink", "consumable"},
            {"thirst": 0.6}, duration_ticks=10, stock=1000,
            attrs={"bladder_load": 0.15})
    for i in range(n_npc):
        _entity(world, f"bed_{i}", "床", {"sleepable"},
                {"energy": 0.7}, duration_ticks=480,
                wake_condition="energy>=0.99")

    names = names or DEFAULT_NAMES
    for i in range(n_npc):
        pid = f"npc_{i:02d}"
        p = Person(identity=Identity(person_id=pid,
                                     name=names[i % len(names)]),
                   location_id="home")
        p.hour_f = 8.0                       # 同步相位 → 同步需求
        p.set_state(energy=0.6, hunger=0.25, thirst=0.6, bladder=0.9,
                    health=1.0, temperature=1.0, fun=0.5, social=0.5,
                    comfort=0.8, hp=1.0)
        world.npcs[pid] = p
        rng_pool[pid] = random.Random(seed + i)
        systems.scheduler.schedule(pid, 1, now=0)
    return world, systems, rng_pool, CFG
