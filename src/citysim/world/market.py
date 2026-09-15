"""world/market —— 批发市场。**它是一个建筑(地点), 不是配置文件。**

用户定的规矩:
    · 市场是一栋楼(编辑器决定放哪), 自带【无限库存】
    · **只有公司能采购**(个人买不到批发价; 个人买的是店铺货架上的零售)
    · 价格 = 物品定义里的【基准价】(config/items/*.json 的 price);
      店铺想卖多少自己定(场景里覆盖实体 price) → 差价就是公司的利润

为什么要有它: 店铺卖出去的货总得从哪来。以前货架上的货是场景写死的 1000 份,
卖完就没了 —— 有了市场, "进货 → 上架 → 零售"才成为一个可循环的生意。
后续: NPC 老板可以自己走到市场去进货(现在先由面板/上帝视角按一下)。
"""
from __future__ import annotations

import logging

log = logging.getLogger("citysim.market")

MARKET_KIND = "market"          # 建筑类型库里的 kind


def market_places(world) -> list:
    """所有【市场建筑】的地点 id(可能有多个市场)。"""
    return sorted(lid for lid, loc in world.locations.items()
                  if isinstance(loc, dict) and str(loc.get("kind", "")) == MARKET_KIND
                  and not loc.get("part_of"))


def wholesale_price(world, item_type: str) -> float | None:
    """批发价 = 物品定义里的基准价(市场"正常定价")。"""
    from citysim.world.itemdefs import load_item_defs
    d = load_item_defs().get(item_type)
    return float(d.price) if d is not None else None


def market_items(world) -> list:
    """市场里有卖什么: 所有可买的物品类型(数据驱动, 不用手写清单)。"""
    from citysim.world.itemdefs import load_item_defs
    return sorted(t for t, d in load_item_defs().items()
                  if float(getattr(d, "price", 0.0)) > 0.0)


def purchase(world, company, shop_id: str, item_type: str, qty: int) -> dict:
    """公司向市场进货 qty 份, 上架到自己的某家店。

    返回 {"ok": bool, "why": str, "cost": float, "stock": int}
    钱不够 → 能买多少买多少(不借钱、不欠款); 一份都买不起 → ok=False。
    """
    from citysim.world.itemdefs import load_item_defs
    from citysim.world.world import entity_from_def

    if not market_places(world):
        return {"ok": False, "why": "城里还没有市场", "cost": 0.0, "stock": 0}
    if shop_id not in company.shops or shop_id not in world.locations:
        return {"ok": False, "why": "这家店不是它的", "cost": 0.0, "stock": 0}
    unit = wholesale_price(world, item_type)
    if unit is None:
        return {"ok": False, "why": "市场没有这种货", "cost": 0.0, "stock": 0}
    qty = max(0, int(qty))
    if qty <= 0:
        return {"ok": False, "why": "没说要几份", "cost": 0.0, "stock": 0}
    if unit > 0:
        qty = min(qty, int(company.cash // unit))     # 钱够几份就进几份
    if qty <= 0:
        return {"ok": False, "why": "公司现钱不够", "cost": 0.0, "stock": 0}

    # 上架: 店里已经有同类货架就加库存, 没有就开一个新的(空货架要留着 → persist_empty)
    shelf = None
    for e in sorted(world.entities.values(), key=lambda x: x.entity_id):
        if e.item_type == item_type and e.location_id == shop_id and e.price > 0:
            shelf = e
            break
    if shelf is None:
        d = load_item_defs().get(item_type)
        if d is None:
            return {"ok": False, "why": "没有这种货的定义", "cost": 0.0, "stock": 0}
        shelf = entity_from_def(d, shop_id)
        shelf.persist_empty = True                    # 货架: 卖空了也留着, 等下次进货
        world.spawn_entity(shelf)
    if shelf.stock == -1:
        return {"ok": False, "why": "货架是无限货(不需要进货)", "cost": 0.0,
                "stock": shelf.stock}
    cost = unit * qty
    company.cash -= cost
    shelf.stock += qty
    world.layout_location(shop_id)
    return {"ok": True, "why": "", "cost": cost, "stock": int(shelf.stock),
            "shelf": shelf.entity_id}


def restock_all(world) -> list[dict]:
    """简单经营规则: 开门前把旗下货架补到 restock_to 份(用公司的钱)。

    没有这一步, 货架卖空就永远空着。以后"补多少/什么时候补"应该由经营策略
    (面板 / NPC 老板去市场) 决定 —— 现在先给个能跑通的规则。
    """
    out: list[dict] = []
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        for shop_id in comp.shops:
            if shop_id not in world.locations:
                continue
            types = {e.item_type for e in world.entities.values()
                     if e.location_id == shop_id and e.price > 0 and e.stock != -1}
            for itype in sorted(types):
                have = sum(e.stock for e in world.entities.values()
                           if e.location_id == shop_id and e.item_type == itype
                           and e.price > 0 and e.stock != -1)
                need = int(getattr(comp, "restock_to", 60)) - int(have)
                if need <= 0:
                    continue
                res = purchase(world, comp, shop_id, itype, need)
                res.update({"company": cid, "shop": shop_id, "item_type": itype})
                out.append(res)
                if res["ok"]:
                    world.bus.publish(world.bus.make(
                        world.clock_tick, "restocked", "",
                        {"audience": [], "company": cid, "shop": shop_id,
                         "item_type": itype, "cost": round(res["cost"], 2),
                         "stock": res["stock"], "cash": round(comp.cash, 2)}))
    return out
