"""world/econ/factory —— 制造公司(加工厂)的两件事: 生产 与 交货。

用户定的规矩:
    · 制造公司注册时定类型; 它**没有进货/上架** —— 只有【工人站工位产出原料】。
    · 产出的东西**不能给员工吃**(原料没有 affordance → 谁都吃不了, 天然成立)。
    · 批发市场(= 城外)每天 collect_minute 来收一次, 按【物品定义里的价】
      把厂里未上架的产出**全部**收走 → 钱从城外进来(这就是城市的经济来源)。

产量按【时间】算:
    一份产出 = produce_base_ticks / 熟练度 个在岗 tick
    熟练度 = skill_min(新员工) → skill_max(老手), 按本公司累计在岗时间线性涨。
    参照饥饿定 base: 简餐补 0.5 饥饿, 满饥饿 720t 消耗完 → 一份 = 360t。
"""
from __future__ import annotations

import logging

from citysim.core.config import SimConfig

log = logging.getLogger("citysim.factory")

WORKBENCH_ITEM = "station_workbench"   # 工位: 站着就是干活
MACHINE_ITEM = "industry_machine"     # 工业机器(家具): 给一个工位提产量


def machines_of(world, company) -> int:
    """这家厂里摆了几台【工业机器】(家具, 从公司账买)。"""
    return sum(1 for e in world.entities.values()
               if e.item_type == MACHINE_ITEM and e.location_id in company.shops)


def faster_benches(world, company, benches: list) -> set:
    """哪几个工位被机器带快了 —— 一台机器配一个工位(按 id 排序, 先到先得)。

    "每个工位的产量提高三倍": 有机器就 ×3; 机器比工位少时, 只有前几台工位吃到。
    想再提就【再加机器 + 再加工位】—— 资本和岗位一起投, 单投哪一边都不划算。
    """
    n = machines_of(world, company)
    if n <= 0:
        return set()
    return {b.entity_id for b in benches[:n]}


def _workbenches(world, company) -> list:
    """这家公司旗下的工位(实体) —— 摆在它旗下任何建筑里。"""
    return [e for e in sorted(world.entities.values(), key=lambda x: x.entity_id)
            if e.item_type == WORKBENCH_ITEM and e.location_id in company.shops]


def _on_bench(world, systems, bench_id: str, npc) -> bool:
    """这个人此刻【守着自己该守的工位】吗? (和销售台同一把闸门)"""
    return (npc is not None
            and str(npc.work.get("station", "")) == bench_id
            and systems.interaction.active.get(npc.person_id) is not None
            and systems.interaction.active[npc.person_id].entity_id == bench_id)


def skill_of(skill_ticks: float, cfg: SimConfig) -> float:
    """熟练度: 新员工 skill_min → 干满 skill_full_ticks 到 skill_max(线性)。

    输入是【累计在岗 tick】—— 由 Person 自己记(见 person/work.py: worked/skill_ticks),
    世界只读不写。
    """
    span = max(0.0, cfg.produce_skill_max - cfg.produce_skill_min)
    full = max(1.0, cfg.produce_skill_full_ticks)
    return cfg.produce_skill_min + span * min(1.0, max(0.0, skill_ticks) / full)


def produce(world, systems, cfg: SimConfig) -> list[dict]:
    """[每个 tick] 制造公司里站在工位上的员工, 按时间攒出一件件产出。

    进度与熟练度都记在【员工自己】身上(npc.work 里) —— "根据自己的时间产出":
    人走了活儿就没接着攒, 换个人从头来。
    """
    out: list[dict] = []
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        if comp.kind != "manufacture" or not comp.produces_item:
            continue
        benches = _workbenches(world, comp)
        fast = faster_benches(world, comp, benches)     # 有机器带的工位 ×3
        for bench in benches:
            pid = ""
            for cand, act in sorted(systems.interaction.active.items()):
                if act is not None and act.entity_id == bench.entity_id:
                    pid = cand
                    break
            npc = world.npcs.get(pid) if pid else None
            if not _on_bench(world, systems, bench.entity_id, npc):
                continue
            # 熟练度是【他自己】的(只读); 进度是【世界的账】(谁干到哪了)。
            skill = skill_of(npc.skill_ticks, cfg)
            per_unit = max(1.0, cfg.produce_base_ticks / skill)
            # ★ 工业机器: 这个工位有机器 → 产出速度 ×bonus(默认 3)
            if bench.entity_id in fast:
                per_unit = max(1.0, per_unit / float(cfg.produce_machine_bonus))
            prog = float(systems.production.get(npc.person_id, 0.0)) + 1.0
            if prog < per_unit:
                systems.production[npc.person_id] = prog
                continue
            systems.production[npc.person_id] = prog - per_unit
            made = _make_one(world, comp, npc)
            if made is not None:
                out.append(made)
                world.bus.publish(world.bus.make(
                    world.clock_tick, "produced", npc.person_id,
                    {"company": cid, "item_type": comp.produces_item,
                     "loc": world.loc_of(npc.person_id), "skill": round(skill, 2)}))
    return out


def _make_one(world, company, npc):
    """产出 1 件: 就地并进同类那堆(没有就开一堆), 归属公司。"""
    from citysim.world.model.itemdefs import load_item_defs
    from citysim.world.world import entity_from_def

    itype = company.produces_item
    here = world.loc_of(npc.person_id)
    pile = None
    for e in sorted(world.entities.values(), key=lambda x: x.entity_id):
        if (e.item_type == itype and e.location_id == here
                and e.owner == company.company_id):
            pile = e
            break
    if pile is None:
        d = load_item_defs().get(itype)
        if d is None:
            return None                                # 货物定义不在 → 静静地不产
        pile = entity_from_def(d, here)
        pile.owner = company.company_id                # ★ 商品: 员工也不能白拿
        pile.stock = 0
        world.spawn_entity(pile)
    pile.stock += 1
    return {"company": company.company_id, "item_type": itype,
            "loc": here, "stock": int(pile.stock)}


def collect(world, cfg: SimConfig) -> list[dict]:
    """[每天 collect_minute] 批发市场来收货 —— 城外的买家, 钱从这里进城。

    收的是【本公司所有】该类型产出(制造公司没有店铺, 所以不存在"已上架"要留);
    按物品定义里的价(原料价)全部结清, 实体销毁。
    """
    from citysim.core.types import ItemGone
    from citysim.world.econ.market import wholesale_price

    out: list[dict] = []
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        if comp.kind != "manufacture" or not comp.produces_item:
            continue
        picked = [e for e in sorted(world.entities.values(), key=lambda x: x.entity_id)
                  if e.owner == cid and e.item_type == comp.produces_item]
        total = sum(int(e.stock) for e in picked if int(e.stock) > 0)
        if total <= 0:
            continue
        unit = wholesale_price(world, comp.produces_item) or 0.0
        gain = unit * total
        comp.cash += gain
        for e in picked:
            world.entities.pop(e.entity_id, None)
            for other in world.npcs.values():          # 别人脑子里的那行也清掉
                other.notify(ItemGone(e.entity_id))
        rec = {"company": cid, "item_type": comp.produces_item,
               "qty": total, "unit": unit, "gain": round(gain, 2),
               "cash": round(comp.cash, 2)}
        out.append(rec)
        world.bus.publish(world.bus.make(
            world.clock_tick, "collected", "",
            {"company": cid, "item_type": comp.produces_item, "qty": total,
             "gain": round(gain, 2), "cash": round(comp.cash, 2)}))
        log.info("factory: %s 交货 %d 件 %s → +%.2f", cid, total,
                 comp.produces_item, gain)
    return out
