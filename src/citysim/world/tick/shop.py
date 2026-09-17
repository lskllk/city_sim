"""world/tick/shop —— 柜台/排队/成交服务

员工站在【销售台】上才能交易: 一个前台每 tick 服务 1 人, 多的排队。
买不起/没人招待/排太久 → 离队 + 好感掉一截(惩罚 = 状态调制产出)。
真正的扣钱/过户在 economy; 这里只管'谁在队里、谁在台上、服务谁'。
"""
from __future__ import annotations

from citysim.core.config import SimConfig
from citysim.core.types import Buy, InteractionFailed

from citysim.world.tick.economy import _execute_buy

COUNTER_ITEM = "station_counter"   # 销售前台: 1 个 = 1 个销售位
QUEUE_GIVEUP = 180                # 排队等超过这么久就放弃(3 小时; 白跑一次要记住)







COUNTER_ITEM = "station_counter"   # 销售前台: 1 个 = 1 个销售位
QUEUE_GIVEUP = 180                # 排队等超过这么久就放弃(3 小时; 白跑一次要记住)


def _counters(world, shop_id: str) -> list:
    """这家店的销售前台(实体) —— 每个前台 = 1 个店员 + 每 tick 最多成交 1 份。"""
    return [e for e in sorted(world.entities.values(), key=lambda x: x.entity_id)
            if e.item_type == COUNTER_ITEM and e.location_id == shop_id]



def _is_open(world, cfg: SimConfig, shop_id: str) -> bool:
    """营业中吗? 找这家店所属公司的营业时间(店铺自己不受 open_to 管)。"""
    cid = str((world.locations.get(shop_id) or {}).get("company", ""))
    comp = world.companies.get(cid)
    if comp is None:
        return True                       # 没公司 → 由"不能卖"那条拦, 不在这里管
    minute = world.clock_tick % max(1, cfg.ticks_per_day)
    return int(comp.open_minute) <= minute < int(comp.close_minute)



def _active_at(world, systems, counter_id: str) -> str:
    """这个前台此刻是谁在守着? 没有 → ""。"""
    for pid, act in systems.interaction.active.items():
        if act is not None and act.entity_id == counter_id:
            return pid
    return ""



def staffed_counters(world, systems, shop_id: str) -> list:
    """【有员工在岗】的前台 —— 这才算产能。

    ★ 用户定的闸门: 员工站在销售台, 交易才能进行。
      半个员工的都没有 → 一台也开不了 → 顾客只能排队(等不住就走, 好感掉)。
    """
    out = []
    for c in _counters(world, shop_id):
        pid = _active_at(world, systems, c.entity_id)
        if not pid:
            continue
        npc = world.npcs.get(pid)
        if npc is None:
            continue
        w = npc.work
        if w.get("station") == c.entity_id:      # 守的是自己该守的台
            out.append((c, pid))
    return out



def _serve_shops(world, systems, cfg: SimConfig) -> None:
    """每 tick 让每个店服务队首: 一个【有人的】前台最多成交 1 份。

    没开门 / 没前台 / 前台没人站着 → 服务不了 → 顾客继续等(等不住就走,
    记一次白跑: 好感掉一截)。这就是"员工在销售台交易才能进行"的落地处。
    """
    # 在岗计时(工资按在岗时间算): 有员工站在台上 → 他这一 tick 算上班
    for shop_id in sorted(world.locations):
        for _c, pid in staffed_counters(world, systems, shop_id):
            npc = world.npcs.get(pid)
            if npc is not None:
                npc.worked(1)
    for shop_id in sorted(systems.shop_queue):
        queue = list(systems.shop_queue.get(shop_id) or [])
        if not queue:
            continue
        seats = len(staffed_counters(world, systems, shop_id))
        open_now = _is_open(world, cfg, shop_id)
        served = 0
        for pid in queue:
            npc = world.npcs.get(pid)
            if npc is None:
                _leave_queue(world, systems, pid)
                continue
            waited = systems.queued_since.get(pid, world.clock_tick)
            if world.clock_tick - waited > QUEUE_GIVEUP:
                # 白跑一趟要记住: 好感掉一截(慢变量, 会慢慢回到中性)。
                # 这是"惩罚 = 状态调制产出"的同一套 —— 不改行为, 只改印象。
                shop_id_q = systems.queued.get(pid, "")
                _leave_queue(world, systems, pid,
                             "没人招待" if (not open_now or seats <= 0) else "排队太久")
                npc.bump_favor(shop_id_q, -cfg.favor_no_service_down, cfg)
                continue
            if not open_now or seats <= 0:
                continue                     # 服务不了: 继续等(等不住会走)
            if served >= seats:
                break                        # 前台用满了 → 后面的人排着
            item_id, left = systems.buy_left.get(pid, ("", 0))
            shop = world.entities.get(item_id)
            if shop is None:
                _leave_queue(world, systems, pid, "目标不存在")
                continue
            seats_ok = _serve_one(world, systems, cfg, pid, npc, shop)
            if seats_ok:
                served += 1
                _, left = systems.buy_left.get(pid, (item_id, 0))
                if left <= 1:
                    _leave_queue(world, systems, pid)
                else:
                    systems.buy_left[pid] = (item_id, left - 1)



def _serve_one(world, systems, cfg: SimConfig, pid: str, npc, shop) -> bool:
    """柜台成交 1 份(钱/货/记忆/好感都走这一处)。"""
    if shop.stock == 0:
        _leave_queue(world, systems, pid, "卖光了")
        return False
    one = Buy(item_id=shop.entity_id, qty=1)
    before = npc.money
    _execute_buy(world, systems, cfg, pid, npc, one, from_counter=True)
    if npc.money < before:                   # 真成交了 → 好感 +一点
        npc.bump_favor(shop.location_id, cfg.favor_trade_up, cfg)
        return True
    return False



def enqueue_buy(world, systems, pid: str, shop_id: str, item_id: str,
                qty: int) -> None:
    """顾客到店 → 排队(不立刻成交)。一个前台只服务队首; 两条前台=两条队。"""
    if systems.queued.get(pid) == shop_id:
        return
    systems.shop_queue.setdefault(shop_id, []).append(pid)
    systems.queued[pid] = shop_id
    systems.buy_left[pid] = (item_id, max(1, int(qty)))
    systems.queued_since[pid] = world.clock_tick



def _leave_queue(world, systems, pid: str, why: str = "") -> None:
    shop_id = systems.queued.pop(pid, "")
    systems.buy_left.pop(pid, None)
    systems.queued_since.pop(pid, None)
    if shop_id:
        q = systems.shop_queue.get(shop_id) or []
        if pid in q:
            q.remove(pid)
        if not q:
            systems.shop_queue.pop(shop_id, None)
    if why:
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid, {"target": shop_id, "why": why}))
        npc = world.npcs.get(pid)
        if npc is not None:
            npc.notify(InteractionFailed(shop_id, why, world.clock_tick))
