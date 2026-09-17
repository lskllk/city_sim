"""world/econ/economy —— 钱的去向: 成交/过户/进货/发货

_execute_buy 是【唯一的成交处】: 钱从买家 → 店铺所属公司(双分录),
_deliver 把货送到手里/家里(带保质期戳), _restock_if_open 在开门前
把货架补到 restock_to。没有登记公司的店不许卖(用户定的开零售前提)。
"""
from __future__ import annotations

from citysim.core.config import SimConfig
from citysim.core.types import Buy, InteractionDone, InteractionFailed
from citysim.world.model.itemdefs import load_item_defs
from citysim.world.world import entity_from_def




def _is_registered_shop(world, shop) -> bool:
    """这家店登记过公司吗? 没登记 → 不许卖(用户定的开零售前提)。"""
    cid = str((world.locations.get(str(shop.location_id)) or {}).get("company", ""))
    return bool(cid) and cid in world.companies



def _company_of_shop(world, shop):
    """这家店归哪个公司? 先看实体, 再看它所在的建筑(含楼层单元的父建筑)。"""
    cid = str(getattr(shop, "owner", "")) or ""
    loc = str(getattr(shop, "location_id", ""))
    for lid in (loc, (world.locations.get(loc) or {}).get("part_of", "")):
        if not lid:
            continue
        c = str((world.locations.get(str(lid)) or {}).get("company", ""))
        if c:
            cid = c
            break
    return world.companies.get(cid) if cid else None



def _credit_shop(world, shop, amount: float):
    """把一笔货款记到店铺所属公司的账上。返回 Company 或 None。"""
    comp = _company_of_shop(world, shop)
    if comp is None or amount <= 0:
        return None
    comp.cash += float(amount)
    return comp



def _expiry(world, shelf_life: int) -> int:
    """新货的到期刻。0 = 不会坏。"""
    return (world.clock_tick + int(shelf_life)) if shelf_life > 0 else 0



def _deliver(world, pid: str, npc, shop, qty: int, home: str):
    """把 qty 件送进家中的同类容器(合并到 stock); 无则新建一个。

    "商店一种货物不要重叠" → 同类只保留一个实体, 数量记在 stock 上。

    保质期取【最早到期】(方案 A): 一格只要有一份旧了, 整格算旧。
    代价是略微低估保质期; 好处是不用给每份建档(实体数不膨胀)。
    """
    shelf = int(getattr(shop, "shelf_life_ticks", 0))
    for e in sorted(world.entities.values(), key=lambda x: x.entity_id):
        if (e.item_type == shop.item_type and e.location_id == home
                and e.owner == pid and e.stock != -1):
            e.stock += qty
            exp = _expiry(world, shelf)
            if exp and (e.expires_tick == 0 or exp < e.expires_tick):
                e.expires_tick = exp          # 合并取最早到期
            world.layout_location(home)
            return e
    d = load_item_defs().get(shop.item_type)
    if d is None:
        return None
    e = entity_from_def(d, home)
    e.owner = pid
    e.stock = qty
    # 不设 persist_empty: 食物是消耗品 —— 吃光/坏掉就该销毁
    # (货架那种“空着也要留着”的才在 itemdef 里写 persist_empty=true)
    # 以【实际卖出那件货】的保质期为准(shop 的 shelf_life 本就是从 itemdef 带入的),
    # 这样两分支口径一致; 也让测试/场景可以改单件货的保质期。
    e.shelf_life_ticks = shelf
    e.expires_tick = _expiry(world, shelf)
    world.spawn_entity(e)
    world.layout_location(home)
    return e



def _execute_buy(world, systems, cfg: SimConfig, pid: str, npc,
                 intent: Buy, from_counter: bool = False) -> None:
    """成交: 扣钱 + 减店铺库存 + 送货到家容器(合并库存, 不另生成多个实体)。

    from_counter=True 表示这是【柜台服务出来的那 1 份】(由 _serve_shops 调)。
    普通路径(_apply)现在【不再直接成交】→ 先排队, 见 enqueue_buy。
    """
    shop = world.entities.get(intent.item_id)
    qty = max(1, int(getattr(intent, "qty", 1)))
    home = npc.home or world.loc_of(pid)
    why = ""
    if shop is None:
        why = "目标不存在"
    elif shop.location_id != world.loc_of(pid):
        why = "目标不在此地"
    elif shop.owner and str(shop.owner) not in world.companies:
        # 只拦“别人的个人物品”; 归【公司】的货是可以卖的(顾客买 = 零售)。
        why = "已被他人拥有"
    elif shop.price <= 0:
        why = "非卖品"
    elif not _is_registered_shop(world, shop):
        # 用户拍板: 【没有注册公司的店不能卖】。店铺建筑没挂公司 →
        # 它的货架不生效(既不合规, 也给编辑器一个能看见的错误)。
        why = "这家店没有登记公司"
    elif shop.stock != -1 and shop.stock < qty:
        why = "库存不足"
    elif npc.money < shop.price * qty:
        # 理论上到不了: brain 已经按钱跳过了买不起的候选(这里只是兵库)。
        why = "钱不够"
    if why:
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid,
            {"target": intent.item_id, "why": why}))
        npc.notify(InteractionFailed(intent.item_id, why, world.clock_tick))
        return
    # ★ 定死三条规则: 免费自用的东西(住所授权 / 公共无主 / 本公司店员)
    #   一律不扣钱 —— 即使有人写了 Buy 意图, 引擎也不收钱。
    free = world.free_use(shop, pid)
    cost = 0.0 if free else shop.price * qty
    if cost:
        npc.pay(cost)
    # ★ 双分录: 买家付的钱进【店铺所属公司】的账。
    #   以前这钱凭空消失 → 城里只有支出没有收入, 所有人慢慢破产饿死。
    #   没登记公司的店 → 仍然"钱消失"(旧行为; 让店主=公司是下一步的事)。
    comp = _credit_shop(world, shop, cost) if cost else None
    if shop.stock != -1:
        shop.stock -= qty
    container = _deliver(world, pid, npc, shop, qty, home)
    # 送货信息随 `bought` 事件交回 NPC —— 由 NPC 自己写记忆,
    # world 不再反写 NPC。(afford/value 必须带上: 否则他不知道家里这堆能吃。)
    cafford, cvalue = (next(iter(container.affordances.items()), ("", 0.0))
                       if container is not None else ("", 0.0))
    world.bus.publish(world.bus.make(
        world.clock_tick, "bought", pid,
        {"item": shop.entity_id, "qty": qty, "price": cost,
         "home": home, "money": round(npc.money, 2),
         "company": comp.company_id if comp else "",
         "container": container.entity_id if container else "",
         "afford": cafford, "value": float(cvalue),
         "stock": int(container.stock) if container is not None else 0,
         "item_type": container.item_type if container is not None else "",
         "tags": list(container.tags) if container is not None else [],
         "shelf_life_ticks": int(container.shelf_life_ticks) if container else 0,
         "expires_tick": int(container.expires_tick) if container else 0}))
    npc.notify(InteractionDone(intent.item_id, world.clock_tick))



def _restock_if_open(world, systems, cfg: SimConfig) -> None:
    """每天开门那一刻, 各公司补一次货(只补货架, 不动任何 NPC)。"""
    from citysim.world.econ.market import restock_all
    minute = world.clock_tick % max(1, cfg.ticks_per_day)
    day = world.clock_tick // max(1, cfg.ticks_per_day)
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        if int(comp.open_minute) != minute:
            continue
        if systems.last_restock_day == day:
            continue                       # 同一开门时刻只补一次
        systems.last_restock_day = day
        restock_all(world)
