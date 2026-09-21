"""demo_scene —— 供观察器与 soak 测试共用的可复现 demo 世界。

一座房子(home): 餐台/散落食物(直接吃) + 床(睡眠) + 饮水机(补水) +
马桶(清膀胱)。NPC 同 location, 靠 claim 仲裁竞争。
"""
from __future__ import annotations

import random
from pathlib import Path

from citysim import api

ROOT = Path(__file__).resolve().parents[1]
CFG = api.load_config(ROOT / "config" / "sim.toml")
DEFAULT_NAMES = ["王二", "李四", "张三", "赵五", "钱六",
                 "孙七", "周八", "吴九", "郑十", "陈一"]


def _entity(world: api.World, eid: str, name: str, tags, affordances,
            duration_ticks: int, stock: int = 1,
            attrs=None) -> api.Entity:
    e = api.Entity(
        entity_id=eid, name=name, tags=set(tags),
        affordances=dict(affordances), duration_ticks=duration_ticks,
        location_id="home", stock=stock,
        attrs=dict(attrs or {}),
    )
    world.entities[eid] = e
    return e


def build_demo(n_npc: int = 6, seed: int = 7, log: bool = False,
               names: list[str] | None = None,
               noise: float = 0.0):
    """搭一座可复现的 demo 房子。返回 (world, systems, rng_pool, cfg)。

    NPC 出生空白知识(单层, 靠观察落知识)。noise: 初始信号扰动幅度(破同相位)。
    """
    world = api.World()
    systems = api.make_systems(log=log)
    if log:
        api.attach_replay(world, systems)
    rng_pool: dict[str, random.Random] = {}

    # ---- 家具/资源 ------------------------------------------------
    # 常备餐台(无限 loose edible): 少量多餐(~8h 一次), 保证任意 24h 吃 2~4 次
    for i in range(max(2, n_npc // 2)):
        _entity(world, f"plate_{i}", "餐台", {"edible", "consumable"},
                {"hunger": 0.35}, duration_ticks=15, stock=10000)
    for i in range(max(2, n_npc)):
        _entity(world, f"bed_{i}", "床", {"sleepable"},
                {"energy": 0.7}, duration_ticks=480)
    _entity(world, "toilet_1", "马桶", {"toilet"},
            {"bladder": 0.6}, duration_ticks=5)

    # ---- NPC(初始状态由 seed 扰动, 避免同相位) ---------------------
    names = names or DEFAULT_NAMES
    for i in range(n_npc):
        pid = f"npc_{i:02d}"
        r = random.Random(seed * 100 + i)
        p = api.Person(identity=api.Identity(person_id=pid,
                                     name=names[i % len(names)]),
                   home="home")
        base = {"energy": r.uniform(0.4, 0.9), "hunger": r.uniform(0.3, 0.9),
                "bladder": 1.0, "hp": 1.0}
        if noise:
            base = {s: max(0.0, min(1.0, v + r.uniform(-noise, noise)))
                    for s, v in base.items()}
        p.set_signals(**base)
        world.npcs[pid] = p
        world.place_npc(pid, "home")
        rng_pool[pid] = random.Random(seed + i)

    return world, systems, rng_pool, CFG


def build_scarce(n_npc: int = 4, seed: int = 1, log: bool = False,
                 names: list[str] | None = None):
    """稀缺场景: 4 NPC 抢 1 厕所 + 1 餐盘(stock=2, 有限)。

    床按人数足额(避免无关卡点), 把竞争集中在 厕所/餐盘 —— 让 claim 冲突与
    失败重选路径被真实压到。NPC 同初始状态 → 需求同步 → 高并发争抢。
    """
    world = api.World()
    systems = api.make_systems(log=log)
    if log:
        api.attach_replay(world, systems)
    rng_pool: dict[str, random.Random] = {}

    # 稀缺食物: 散落餐盘(stock=2, 有限) —— 直接吃, 竞争焦点之一
    _entity(world, "food_1", "餐盘", {"edible", "consumable"},
            {"hunger": 0.35}, duration_ticks=15, stock=2)
    _entity(world, "toilet_1", "马桶", {"toilet"},
            {"bladder": 0.6}, duration_ticks=5)
    for i in range(n_npc):
        _entity(world, f"bed_{i}", "床", {"sleepable"},
                {"energy": 0.7}, duration_ticks=480)

    names = names or DEFAULT_NAMES
    for i in range(n_npc):
        pid = f"npc_{i:02d}"
        p = api.Person(identity=api.Identity(person_id=pid,
                                     name=names[i % len(names)]),
                   home="home")
        p.set_signals(energy=0.6, hunger=0.25, bladder=0.9, hp=1.0)
        world.npcs[pid] = p
        world.place_npc(pid, "home")
        rng_pool[pid] = random.Random(seed + i)
    return world, systems, rng_pool, CFG
