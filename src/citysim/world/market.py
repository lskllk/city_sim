"""world/market —— 批发市场: 公司进货的地方。

规矩(用户拍板):
    · 固定商品清单 + **数量无限** —— 世界不需要模拟上游, 只提供"按价拿货"这一手
    · **只有公司能采购**(个人买不到批发价; 个人的零售买走的是店铺货架)
    · 价格是**进货价**, 低于店铺零售价 → 差价就是公司的利润(或亏损)

为什么要有它: 店铺卖出去的货总得从哪来。以前货架上的货是场景写死的 1000 份,
卖完就没了 —— 有了市场, "进货 → 上架 → 零售"才成为一个可循环的生意。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("citysim.market")


@dataclass(frozen=True)
class Market:
    """批发价表: item_type -> 进货单价。"""

    prices: dict[str, float]

    def price_of(self, item_type: str) -> float | None:
        return self.prices.get(item_type)

    def items(self) -> tuple[str, ...]:
        return tuple(sorted(self.prices))


def load_market(path: str | Path) -> Market:
    """读 config/market.json。文件不存在 → 空市场(什么都进不到货)。"""
    p = Path(path)
    if not p.is_file():
        return Market(prices={})
    raw = json.loads(p.read_text(encoding="utf-8"))
    items = raw.get("items", raw) if isinstance(raw, dict) else raw
    prices: dict[str, float] = {}
    for rec in items or []:
        if isinstance(rec, dict) and str(rec.get("item_type", "")):
            prices[str(rec["item_type"])] = float(rec.get("price", 0.0))
    return Market(prices=prices)


def purchase(world, company, shop_id: str, item_type: str, qty: int) -> dict:
    """公司向市场进货 qty 份, 上架到自己的某家店。

    返回 {"ok": bool, "why": str, "cost": float, "stock": int}
    钱不够 → 能买多少买多少(不借钱、不欠款); 一份都买不起 → ok=False。
    """
    from citysim.world.itemdefs import load_item_defs
    from citysim.world.world import entity_from_def

    if world.market is None:
        return {"ok": False, "why": "没有市场", "cost": 0.0, "stock": 0}
    if shop_id not in company.shops or shop_id not in world.locations:
        return {"ok": False, "why": "这家店不是它的", "cost": 0.0, "stock": 0}
    unit = world.market.price_of(item_type)
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

    没有这一步, 货架卖空就永远空着(空货架=空货架, 没人会去补)。
    以后"补多少/什么时候补"应该由经营策略(玩家/面板)决定 —— 现在先给个能跑通的规则。
    """
    out: list[dict] = []
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        for shop_id in comp.shops:
            if shop_id not in world.locations:
                continue
            # 这家店在卖哪些品类 → 每种都补到目标
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
