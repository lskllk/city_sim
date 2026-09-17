"""测试共享辅助: 搭最小 scene(世界 + 系统 + rng)。"""
from __future__ import annotations

import random

from citysim.core.config import SimConfig
from citysim.core.types import Work
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
            rng_pool: dict | None = None, seed: int = 1, home: str = "",
            **kw) -> Person:
    p = Person(identity=Identity(person_id=person_id, name=person_id), home=home)
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
    return ent is not None and "sleepable" in ent.tags


def register_company(world: World, shop_ids, cash: float = 1000.0,
                     name: str = "测试公司"):
    """给店铺挂一个公司 —— 现在【没登记公司的店不能卖】(用户定的开零售前提)。

    测试里凡是要真的成交, 都得先注册。返回 Company。
    """
    from citysim.world.model.companies import Company
    cid = "org_test"
    ids = tuple(shop_ids) if not isinstance(shop_ids, str) else (shop_ids,)
    # 测试里默认【全天营业】—— 不然跑几十 tick 还在清晨, 店没开门什么都不会发生
    comp = Company(cid, name, cash=cash, shops=ids,
                   open_minute=0, close_minute=1440)
    world.companies = {**getattr(world, "companies", {}), cid: comp}
    for bid in ids:
        world.locations.setdefault(bid, {})       # 测试夹具可能没登记地点
        world.locations[bid]["company"] = cid
    return comp


def add_counter(world: World, shop_id: str, n: int = 1) -> list:
    """给店铺摆 n 个销售前台(每个 = 1 个销售位: 每 tick 最多成交 1 份)。

    现在交易是【柜台一份一份卖】: 没有前台 → 服务不了 → 顾客排队然后放弃。
    """
    from citysim.world.model.itemdefs import load_item_defs
    from citysim.world.world import entity_from_def
    d = load_item_defs()["station_counter"]
    out = []
    for _ in range(n):
        e = entity_from_def(d, shop_id)
        world.spawn_entity(e)
        out.append(e)
    return out


def staff_counter(world: World, systems, npc_id: str, shop_id: str,
                  counter_id: str, company_id: str = "org_test") -> None:
    """把一个员工【安排到台前】(测试用): 绑定工位 + 放进店里。

    对应世界里的真实路径: 被雇佣 → 班次闸门把他钉在工位上。
    测试里直接落状态, 省掉走路与排队(全天班: 0..1440)。
    """
    npc = world.npcs[npc_id]
    npc.assign(Work(company_id, shop_id, counter_id, role="worker"))
    world.place_npc(npc_id, shop_id)
