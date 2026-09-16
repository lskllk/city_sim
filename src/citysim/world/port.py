"""world/port —— WorldPortImpl: NPC 主动拉的 world 侧实现。

权限 / 仲裁都在这里, 一步做全(校验 → 改账 → 发事件, 原子)。
NPC 只拿到返回值(`Grant` / `Deny` / `Ack` / `Percept`), **永远拿不到 world / Entity**。

本模块是 `engine._apply` 各分支的归属地: WP-02 搬 `MoveTo`, WP-03 搬 `Interact`,
WP-04 搬 `Buy`; WP-06 之后 engine 只做 dispatch(端口由 tick 建一次)。
"""
from __future__ import annotations

from typing import Any

from citysim.core.config import SimConfig
from citysim.core.ports import Ack, Deny, Grant
from citysim.core.types import Buy, Interact, Percept
from citysim.world.perception import build_percept
from citysim.world.travel import Travel


# ---------------------------------------------------------------------------
# 共享 helper(原 engine 里的私有函数; 搬到这里避免 engine ⇄ port 循环 import)
# ---------------------------------------------------------------------------
def travel_cost(systems, cfg: SimConfig, a: str, b: str) -> int:
    """跨地点移动耗时: 优先 travel_costs 矩阵, 缺省回落 cfg.move_ticks。"""
    if systems.travel_costs:
        c = systems.travel_costs.get(f"{a}|{b}") or \
            systems.travel_costs.get(f"{b}|{a}")
        if c is not None:
            return c
    if int(getattr(systems, "travel_default", 0) or 0) > 0:
        return int(systems.travel_default)
    return cfg.move_ticks


def route_between(world, systems, a: str, b: str):
    """有路网且两端都接得上 → 沿路最短路径; 否则 None(上层降级)。"""
    roads = getattr(systems, "roads", None)
    if roads is None or not roads.ok:
        return None
    pa, pb = world.door_point(a), world.door_point(b)
    if pa is None or pb is None:
        return None
    return roads.route(pa, pb)


def can_preempt(world, systems, pid: str) -> bool:
    """能不能中止当前交互: 只有可打断的才行(睡觉不可打断)。"""
    act = systems.interaction.active.get(pid)
    if act is None:
        return True
    ent = world.entities.get(act.entity_id)
    return bool(ent is not None and ent.interruptible)


def preempt(world, systems, pid: str) -> None:
    """中止当前交互(唯一能打断的是 PLAN: 上班)。"""
    systems.interaction.abort(world, pid)


class WorldPortImpl:
    """`core.ports.WorldPort` 的实现体(duck typing, 不需要显式继承)。

    `world` / `systems` / `cfg` 都是引用, 构造极廉价 —— engine 每 tick 建一次即可。
    """

    def __init__(self, world, systems, cfg: SimConfig) -> None:
        self.world = world
        self.systems = systems
        self.cfg = cfg

    # --- 观察 ---------------------------------------------------------
    def observe(self, pid: str) -> Percept:
        return build_percept(self.world, self.world.npcs[pid])

    # --- 移动 ---------------------------------------------------------
    def try_move(self, pid: str, dest: str) -> Ack:
        """搬自 engine._apply 的 MoveTo 分支(行为不变, 失败处理暂留 world 侧)。"""
        world, systems = self.world, self.systems
        npc = world.npcs.get(pid)
        if npc is None:
            return Ack(ok=False, reason="人不存在")
        dest = dest or world.loc_of(pid)
        trv = systems.travel.get(pid)
        if trv is not None and trv.to_loc == dest:
            return Ack()                             # 已在去往该地途中
        active = systems.interaction.active.get(pid)
        if active is not None:
            if not can_preempt(world, systems, pid):
                return Ack(ok=False, reason="当前交互不可打断")
            preempt(world, systems, pid)
        here = world.loc_of(pid)
        if dest == here:
            return Ack()                             # 已在原地
        ok, why = world.entry_check(dest, pid)
        if not ok:                                   # 无权/已满: 不出发(事件在此, 记忆归 NPC)
            world.bus.publish(world.bus.make(
                world.clock_tick, "intent_failed", pid,
                {"target": dest, "why": why}))
            return Ack(ok=False, reason=why)
        route = route_between(world, systems, here, dest)
        if route is None:                            # 无路网 → 直线/固定耗时降级
            cost = travel_cost(systems, self.cfg, here, dest)
            wps: tuple[tuple[float, float], ...] = ()
        else:
            cost = route.ticks
            wps = route.waypoints
        systems.travel[pid] = Travel(
            from_loc=here, to_loc=dest,
            depart_tick=world.clock_tick,
            arrive_tick=world.clock_tick + cost,
            waypoints=wps)
        return Ack()

    # --- 免费使用(吃/睡/上厕所/自家物品) -------------------------
    def try_take(self, pid: str, entity_id: str) -> "Grant | Deny":
        """搬自 engine._apply 的 Interact 分支。

        本票只搬【校验 + claim】, 返回 Grant(handle=entity_id, 数据从 affordances 取,
        pending/on_done 留空)。信号仍由 InteractionSystem.step 应用(WP-08 才搬)。
        """
        world, systems = self.world, self.systems
        npc = world.npcs.get(pid)
        if npc is None:
            return Deny("人不存在")
        ent = world.entities.get(entity_id)
        # 防御: 在售商品不能拿 Interact “白拿”(例外: 住所授权/公共无主/本公司店员)
        if (ent is not None and ent.price > 0 and ent.owner != pid
                and not world.free_use(ent, pid)):
            why = "在售商品·需购买"
            world.bus.publish(world.bus.make(
                world.clock_tick, "intent_failed", pid,
                {"target": entity_id, "why": why}))
            return Deny(why)
        active = systems.interaction.active.get(pid)
        if active is not None and active.entity_id != entity_id:
            if not can_preempt(world, systems, pid):
                return Deny("当前交互不可打断")
            preempt(world, systems, pid)
        ok = systems.interaction.submit(world, npc, Interact(target_id=entity_id))
        if not ok:
            # submit 内部已发 intent_failed; 原因由 last_fail 交回 NPC 自己处理
            why, retry = systems.interaction.last_fail
            return Deny(why or "提交失败", retry_ticks=retry)
        signal, value = (next(iter(ent.affordances.items()), ("", 0.0))
                         if ent is not None else ("", 0.0))
        return Grant(
            handle=entity_id, entity_id=entity_id,
            signal=str(signal), value=float(value),
            duration_ticks=max(1, int(getattr(ent, "duration_ticks", 1) or 1)),
            tags=tuple(getattr(ent, "tags", ()) or ()))

    # --- 购买(排队, 异步) -----------------------------------------
    def try_buy(self, pid: str, item_id: str, qty: int) -> Ack:
        """搬自 engine._apply 的 Buy 分支。★ 异步: ok=True 只表示【已入队】。"""
        world, systems = self.world, self.systems
        npc = world.npcs.get(pid)
        if npc is None:
            return Ack(ok=False, reason="人不存在")
        # 延迟 import: 买卖/排队的 world 侧实现暂在 engine(避免 engine ⇄ port 顶层环)。
        # TODO(WP-16): shop/queue 逻辑抽到 world/shop.py 后改为顶层 import。
        from citysim.world.engine import _execute_buy, _set_bubble, enqueue_buy
        qty = max(1, int(qty))
        shop = world.entities.get(item_id)
        if shop is None or shop.location_id != world.loc_of(pid):
            # 兜底: 不在店里的异常情形 → 直接走成交(可能失败并记入 on_failure)
            _execute_buy(world, systems, self.cfg, pid, npc,
                         Buy(item_id=item_id, qty=qty))
            return Ack(ok=False, reason="不在店里·走兜底成交")
        if systems.interaction.active.get(pid) is not None:
            preempt(world, systems, pid)
        enqueue_buy(world, systems, pid, shop.location_id, item_id, qty)
        _set_bubble(systems, npc, "老板, 来 %d 份" % qty, "queue", world.clock_tick)
        return Ack(ok=True, reason="queued")
