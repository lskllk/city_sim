"""world/econ/market —— 批发市场。**它是一个建筑(地点), 不是配置文件。**

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
    from citysim.world.model.itemdefs import load_item_defs
    d = load_item_defs().get(item_type)
    return float(d.price) if d is not None else None


def is_fixture(item_type: str) -> bool:
    """装修件(马桶/销售前台/工位…): 一次买断、摆进店里, 不是可零售的货。

    靠物品定义上的 tag "fixture" 判定 —— 不写死类型清单(加了新装修件
    只要在 config/items 里打这个 tag, 市场和面板都自动认得)。
    """
    from citysim.world.model.itemdefs import load_item_defs
    d = load_item_defs().get(item_type)
    return d is not None and "fixture" in d.tags


def fixture_catalog() -> list:
    """所有可装修件: [{type, name, price}]。前端【装修管理】页读它。"""
    from citysim.world.model.itemdefs import load_item_defs
    out = []
    for t, d in sorted(load_item_defs().items()):
        if "fixture" in d.tags:
            out.append({"type": t, "name": d.name,
                        "price": float(d.build_cost)})
    return out


def market_catalog() -> list:
    """批发市场能进什么货: [{type, name, price}]。价格 = 物品定义的基准价。

    前端【货物管理】页按它列“向市场进货”的清单(装修件不算)。
    """
    from citysim.world.model.itemdefs import load_item_defs
    out = []
    for t, d in sorted(load_item_defs().items()):
        if "fixture" in d.tags:
            continue
        if float(getattr(d, "price", 0.0)) > 0.0:
            out.append({"type": t, "name": d.name, "price": float(d.price)})
    return out


def purchase(world, company, shop_id: str, item_type: str, qty: int) -> dict:
    """公司向市场进货 qty 份, 上架到自己的某家店。

    返回 {"ok": bool, "why": str, "cost": float, "stock": int}
    钱不够 → 能买多少买多少(不借钱、不欠款); 一份都买不起 → ok=False。
    """
    from citysim.world.model.itemdefs import load_item_defs
    from citysim.world.world import entity_from_def

    if is_fixture(item_type):
        return {"ok": False, "why": "这是装修件, 去装修管理里放",
                "cost": 0.0, "stock": 0}
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
        if (e.item_type == item_type and e.location_id == shop_id
                and e.price > 0 and e.owner in ("", company.company_id)):
            shelf = e
            break
    if shelf is None:
        d = load_item_defs().get(item_type)
        if d is None:
            return {"ok": False, "why": "没有这种货的定义", "cost": 0.0, "stock": 0}
        shelf = entity_from_def(d, shop_id)
        shelf.persist_empty = True                    # 货架: 卖空了也留着, 等下次进货
        world.spawn_entity(shelf)
    # ★ 商品固定归属这家公司(不再靠“地点公司”推断): 顾客要买, 店员免费。
    shelf.owner = company.company_id
    if shelf.stock == -1:
        return {"ok": False, "why": "货架是无限货(不需要进货)", "cost": 0.0,
                "stock": shelf.stock}
    cost = unit * qty
    company.cash -= cost
    shelf.stock += qty
    world.layout_location(shop_id)
    return {"ok": True, "why": "", "cost": cost, "stock": int(shelf.stock),
            "shelf": shelf.entity_id}


def decorate(world, company, shop_id: str, item_type: str,
             public: bool = False) -> dict:
    """公司给自己的店【装修】: 摆一件装修件(马桶/销售前台/工位…), 从公司账出钱。

    public=True → 这件家具是【公共】的(owner="", 任何人都能用, 如门口马桶);
    public=False(默认) → 归公司(owner=cid, 只有本公司店员免费使用)。
    返回 {"ok": bool, "why": str, "cost": float, "entity": str}。
    装修件与"货"分开: 它不进货架、不零售, 一次买断地钉在店里(persist_empty)。
    """
    from citysim.world.model.itemdefs import load_item_defs
    from citysim.world.world import entity_from_def

    if shop_id not in company.shops or shop_id not in world.locations:
        return {"ok": False, "why": "这家店不是它的", "cost": 0.0, "entity": ""}
    if not is_fixture(item_type):
        return {"ok": False, "why": "这不是装修件", "cost": 0.0, "entity": ""}
    d = load_item_defs().get(item_type)
    if d is None:
        return {"ok": False, "why": "没有这种装修件", "cost": 0.0, "entity": ""}
    price = float(getattr(d, "build_cost", 0.0))
    if price > 0 and company.cash < price:
        return {"ok": False, "why": "公司现钱不够", "cost": 0.0, "entity": ""}
    e = entity_from_def(d, shop_id)
    e.persist_empty = True                 # 装修件不因空库存被回收
    e.owner = "" if public else company.company_id   # ★ 家具权限: 公共 / 公司
    world.spawn_entity(e)
    if price > 0:
        company.cash -= price
    world.layout_location(shop_id)
    return {"ok": True, "why": "", "cost": price,
            "entity": e.entity_id, "item_type": item_type}


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
                     if e.location_id == shop_id and e.price > 0
                     and e.stock != -1 and not is_fixture(e.item_type)}
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
