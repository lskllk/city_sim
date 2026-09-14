"""world/engine —— 世界执行器(推进一个 tick 的世界演化 + 决策编排)。

按 World↔Person 契约: 上帝(World 侧)执行"世界进程"并广播心跳, 只发事件不写 Person。
systems 为执行环境(duck: interaction/travel/pulses/日志), 由上层构造传入,
本模块不 import sim(避免 world→sim 反向依赖)。
"""
from __future__ import annotations

import zlib

from typing import Any

from citysim.core.config import SimConfig
from citysim.core.types import (
    Buy,
    Idle,
    Interact,
    MoveTo,
    intent_kind,
    intent_target,
)
from citysim.world.drive import due_npcs
from citysim.world.itemdefs import load_item_defs
from citysim.world.pulses import apply as apply_pulses
from citysim.world.perception import build_percept
from citysim.world.travel import Travel
from citysim.world.world import Entity, entity_from_def


def _travel_cost(systems, cfg: SimConfig, a: str, b: str) -> int:
    """跨地点移动耗时: 优先 travel_costs 矩阵, 缺省回落 cfg.move_ticks。"""
    if systems.travel_costs:
        c = systems.travel_costs.get(f"{a}|{b}") or \
            systems.travel_costs.get(f"{b}|{a}")
        if c is not None:
            return c
    return cfg.move_ticks


def _route_between(world, systems, a: str, b: str):
    """有路网且两端都接得上 → 沿路最短路径; 否则 None(上层降级)。"""
    roads = getattr(systems, "roads", None)
    if roads is None or not roads.ok:
        return None
    pa, pb = world.door_point(a), world.door_point(b)
    if pa is None or pb is None:
        return None
    return roads.route(pa, pb)


def _sleeping(world, systems, pid: str) -> bool:
    act = systems.interaction.active.get(pid)
    if act is None:
        return False
    ent = world.entities.get(act.entity_id)
    return ent is not None and ent.is_sleepable


def _busy(world, systems, pid: str) -> bool:
    """忙碌 = 有进行中交互 或 正在跨地点移动。"""
    return (systems.interaction.active.get(pid) is not None
            or pid in systems.travel)


def _kill(world, systems, pid: str) -> None:
    """NPC 死亡: 清残留 → 从世界销毁 → 发布死亡事件。"""
    npc = world.npcs.get(pid)
    if npc is None:
        return
    systems.interaction.release_active(world, pid)   # 清 claim
    systems.travel.pop(pid, None)                    # 清旅行
    world.npcs.pop(pid, None)                        # 从世界销毁
    world.bus.publish(world.bus.make(
        world.clock_tick, "npc_died", pid,
        {"name": npc.name, "loc": world.loc_of(pid)}))


# --- 传播(传闻) -----------------------------------------------------------
#
# 规则(docs/20260914/mvp.md):
#   - 信任只有两档: 同址(同一个 home) 0.9~1.0; 否则 0.4~0.7
#   - 按 (a,b) **确定性派生** —— 每对人一个固定值, 零存储、可回放
#   - 传出去的 believe = 说话人自己信的程度 × 对听者的信任
#   - “对方已知就不说” → 消息播完自己就停, 不会全城皆知
#
# 注意: 这里**不做** trust 的演化(mind.md 的 verify) —— 那是后续插件。

BELIEF_FLOOR = 0.3      # 低于此就不值得再传了
TRUST_SAME_HOME = (0.9, 1.0)
TRUST_OTHER = (0.4, 0.7)


def _unit_hash(key: str) -> float:
    """把字符串稳定地映到 [0,1)。**不用内置 hash()** —— 它每进程随机化, 回放会飘。"""
    return (zlib.crc32(key.encode("utf-8")) % 10_000) / 10_000.0


def trust_between(a, b) -> float:
    """a 有多信 b 说的话(0..1)。同址(同一个 home) → 高信任档。"""
    same = bool(a.home) and a.home == b.home
    lo, hi = TRUST_SAME_HOME if same else TRUST_OTHER
    k = a.person_id if a.person_id < b.person_id else b.person_id
    j = b.person_id if a.person_id < b.person_id else a.person_id
    return lo + (hi - lo) * _unit_hash("%s|%s" % (k, j))


def _pick_tell(speaker, other) -> object | None:
    """挑一条“对方不知道、也不是他说的、且我比较信”的记忆。

    确定性: 按 item_id 排序后取 believe 最大的那条。
    """
    best = None
    for row in sorted(speaker.memory_dicts(), key=lambda r: r["item_id"]):
        if row.get("source") == other.person_id:
            continue                      # 别把他刚告诉我的再告诉他
        if float(row.get("believe", 0.0)) < BELIEF_FLOOR:
            continue
        if other.remembers(row["item_id"]):
            continue                      # 对方已经知道了 → 不说
        if other.home and row.get("located") == other.home:
            continue                      # “告诉他他自己家里有什么”是噪声
        if best is None or float(row["believe"]) > float(best["believe"]):
            best = row
    return best


def _notify_due(world, systems, npc) -> None:
    """空闲时: 跟同地的某人说一件他不知道的事(带信任折扣 + 溯源)。"""
    tell_p = float(getattr(systems, "tell_p", 0.0))
    if tell_p <= 0.0:
        return
    rng = getattr(systems, "rng", None)
    if rng is None:
        return
    loc = world.loc_of(npc.person_id)
    for other_id in sorted(world.npcs):
        if other_id == npc.person_id or world.loc_of(other_id) != loc:
            continue
        other = world.npcs[other_id]
        if rng.random() >= tell_p * npc.tell_bias:
            continue                      # 说不说, 随机
        row = _pick_tell(npc, other)
        if row is None:
            continue
        trust = trust_between(npc, other)
        other.note(row["item_id"], tick=world.clock_tick,
                   located=row.get("located", ""),
                   afford=row.get("afford", ""), value=row.get("value", 0.0),
                   price=row.get("price", 0.0), item_type=row.get("item_type", ""),
                   believe=float(row["believe"]) * trust,
                   source=npc.person_id)
        # 气泡挂在【听者】头上 —— 内容是“他刚学到的事实”(支柱 B 的出口)
        ent = world.entities.get(row["item_id"])
        nm = ent.name if ent is not None else str(row["item_id"])
        price = float(row.get("price", 0.0))
        text = ("听说%s %g 块" % (nm, price) if price > 0
                else "听说有%s" % nm)
        ttl = int(getattr(systems, "bubble_ttl", 40) or 40)
        other.set_bubble(text, world.clock_tick + ttl, "told")
        world.bus.publish(world.bus.make(
            world.clock_tick, "told", npc.person_id,
            {"audience": [other_id], "item_id": row["item_id"],
             "from": npc.person_id, "believe": round(trust, 3)}))


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
                 intent: Buy) -> None:
    """成交: 扣钱 + 减店铺库存 + 送货到家容器(合并库存, 不另生成多个实体)。"""
    shop = world.entities.get(intent.item_id)
    qty = max(1, int(getattr(intent, "qty", 1)))
    home = npc.home or world.loc_of(pid)
    why = ""
    if shop is None:
        why = "目标不存在"
    elif shop.location_id != world.loc_of(pid):
        why = "目标不在此地"
    elif shop.owner != "":
        why = "已被他人拥有"
    elif shop.price <= 0:
        why = "非卖品"
    elif shop.stock != -1 and shop.stock < qty:
        why = "库存不足"
    elif npc.money < shop.price * qty:
        # 理论上到不了: brain 已经按钱跳过了买不起的候选(这里只是兵库)。
        why = "钱不够"
    if why:
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid,
            {"target": intent.item_id, "why": why}))
        npc.on_failure(intent.item_id, why, world.clock_tick)
        return
    cost = shop.price * qty
    npc.pay(cost)
    if shop.stock != -1:
        shop.stock -= qty
    container = _deliver(world, pid, npc, shop, qty, home)
    world.bus.publish(world.bus.make(
        world.clock_tick, "bought", pid,
        {"item": shop.entity_id, "qty": qty, "price": cost,
         "home": home, "money": round(npc.money, 2),
         "container": container.entity_id if container else ""}))
    if container is not None:
        # 送货进家: 写记忆时**必须带 afford/value** —— 否则他不知道家里
        # 这堆东西能吃, 就永远不会回家吃(买了也饿死)。
        cafford, cvalue = next(iter(container.affordances.items()), ("", 0.0))
        npc.note(container.entity_id, tick=world.clock_tick,
                 located=home, owner=pid, stock=container.stock,
                 afford=cafford, value=float(cvalue),
                 item_type=container.item_type, source="",
                 shelf_life_ticks=int(container.shelf_life_ticks),
                 expires_tick=int(container.expires_tick))
    npc.on_interaction_done(intent.item_id, world.clock_tick)



def _can_preempt(world, systems, pid, source) -> bool:
    """计划只能硬中止可打断的交互; 需求轨(need)始终可。"""
    if source == "need":
        return True
    act = systems.interaction.active.get(pid)
    if act is None:
        return True
    ent = world.entities.get(act.entity_id)
    return bool(ent is not None and ent.interruptible)


def _preempt(world, systems, pid, source) -> None:
    """抢占当前交互: need=软挂起(可恢复), plan=硬中止(触发 on_complete)。"""
    if source == "need":
        systems.interaction.suspend(world, pid)
    else:
        systems.interaction.abort(world, pid)


def _apply(world, systems, cfg, pid, npc, decision) -> None:
    """执行一条 Decision: 继续(同目标)/挂起/中止/提交。"""
    intent = decision.intent
    active = systems.interaction.active.get(pid)

    if isinstance(intent, MoveTo):
        dest = intent.dest or world.loc_of(pid)
        trv = systems.travel.get(pid)
        if trv is not None and trv.to_loc == dest:
            return                                   # 已在去往该地途中
        if active is not None:
            if not _can_preempt(world, systems, pid, decision.source):
                return
            _preempt(world, systems, pid, decision.source)
        here = world.loc_of(pid)
        if dest == here:
            return
        ok, why = world.entry_check(dest, pid)
        if not ok:                               # 无权/已满: 不出发, 记一次失败
            world.bus.publish(world.bus.make(
                world.clock_tick, "intent_failed", pid,
                {"target": dest, "why": why}))
            npc.on_failure(dest, why, world.clock_tick)
            return
        route = _route_between(world, systems, here, dest)
        if route is None:                        # 无路网 → 直线/固定耗时降级
            cost = _travel_cost(systems, cfg, here, dest)
            wps: tuple[tuple[float, float], ...] = ()
        else:
            cost = route.ticks
            wps = route.waypoints
        systems.travel[pid] = Travel(
            from_loc=here, to_loc=dest,
            depart_tick=world.clock_tick,
            arrive_tick=world.clock_tick + cost,
            waypoints=wps)
        return
    if isinstance(intent, Buy):
        if active is not None:
            if not _can_preempt(world, systems, pid, decision.source):
                return
            _preempt(world, systems, pid, decision.source)
        _execute_buy(world, systems, cfg, pid, npc, intent)
        return

    if isinstance(intent, Interact):
        tid = intent.target_id
        # 防御: 在售商品不能拿 Interact “白拿” —— 得走 Buy 付钱。
        # (模板计划器已不再挑它们; 但 ScriptedPlanner / LLM 计划可能写错。)
        ent = world.entities.get(tid)
        if ent is not None and ent.price > 0 and ent.owner != pid:
            why = "在售商品·需购买"
            world.bus.publish(world.bus.make(
                world.clock_tick, "intent_failed", pid,
                {"target": tid, "why": why}))
            npc.on_failure(tid, why, world.clock_tick)
            return
        if active is not None and active.entity_id == tid:
            return                                   # 继续当前交互
        if active is not None:
            if not _can_preempt(world, systems, pid, decision.source):
                return
            _preempt(world, systems, pid, decision.source)
        if systems.interaction.resume(world, npc, tid):
            return                                   # 恢复挂起进度
        systems.interaction.submit(world, npc, intent)
        return

    # Idle: 不主动释放(由 Person 决定何时结束); 仅空转


def tick(world, systems, cfg: SimConfig) -> None:
    """推进一个 tick 的世界演化(唯一执行入口)。世界进程在此, loop 只薄转发。"""
    world.clock_tick += 1

    # 0. 场景脉冲(世界脚本): 在 NPC 感知前改库存/停业
    if systems.pulses:
        apply_pulses(world, systems.pulses, world.clock_tick, cfg.ticks_per_day)

    # 0b. 过期变质: 到点的食物 stock 归 0(壳留着 —— 货架/容器可能 persist_empty)。
    #     只在【从有到无】的那一刻发一条事件, 不每 tick 刷。
    for eid in sorted(world.entities):
        e = world.entities[eid]
        if e.expires_tick and e.expires_tick <= world.clock_tick and e.stock != 0:
            e.stock = 0
            world.bus.publish(world.bus.make(
                world.clock_tick, "spoiled", eid,
                {"item_type": e.item_type, "loc": e.location_id}))
            # 【数量为 0 就销毁】: 除非它是货架/容器(persist_empty)
            if not e.persist_empty:
                world.entities.pop(eid, None)
                for other in world.npcs.values():
                    other.forget_item(eid)     # 别人脑子里的那行也清掉


    # 1. 心跳(身体演化收进 Person; 世界只广播, 不改 signals): 代谢+hp+排泄
    died: list[str] = []
    for pid, npc in world.npcs.items():
        alive = npc.heartbeat(world.clock_tick, cfg,
                              sleep=_sleeping(world, systems, pid),
                              busy=_busy(world, systems, pid))
        if not alive:
            died.append(pid)
    for pid in died:
        _kill(world, systems, pid)             # 死亡销毁 + 日志

    # 3. 交互推进(含睡眠唤醒提前完成)
    systems.interaction.step(world, cfg)

    # 5a. 旅行到期: 落到目标 region(世界进程, 先于重评)
    for pid in sorted(systems.travel):
        trv = systems.travel[pid]
        if world.clock_tick >= trv.arrive_tick:
            systems.travel.pop(pid)
            ok, why = world.entry_check(trv.to_loc, pid)   # 到达时再验(可能满)
            if ok:
                world.place_npc(pid, trv.to_loc)
            else:
                world.bus.publish(world.bus.make(
                    world.clock_tick, "entry_denied", pid,
                    {"loc": trv.to_loc, "why": why}))
                npc = world.npcs.get(pid)
                if npc is not None:
                    npc.on_failure(trv.to_loc, why, world.clock_tick)

    # 5b. 决策: 先对全部该决策者算 Decision(同一世界快照), 再统一仲裁执行
    #     仲裁 = 继续/挂起/中止/提交。
    due = due_npcs(world, systems)
    decisions: list[tuple[str, Any, Any]] = []
    for npc_id in due:
        npc = world.npcs.get(npc_id)
        if npc is None:
            continue
        active = systems.interaction.active.get(npc_id)
        can_preempt = True
        if active is not None:
            aent = world.entities.get(active.entity_id)
            can_preempt = bool(aent is not None and aent.interruptible)
        percept = build_percept(world, npc)
        decision = npc.process(percept, cfg, can_preempt)
        intent = decision.intent
        kind = intent_kind(intent)
        target = intent_target(intent)
        if isinstance(intent, Idle):
            _notify_due(world, systems, npc)      # TODO(notify) 通用通知骨架
        # 观测去重: 只在【任务变更】时记一条; 持续同一任务/空闲不刷屏。
        # 签名始终更新(含 idle), 否则"吃→空闲→再吃同一个"会被吞掉。
        sig = f"{decision.source}:{kind}:{target or ''}"
        if sig != systems.last_decision.get(npc_id):
            systems.last_decision[npc_id] = sig
            if kind != "idle" and systems.log_lines is not None:
                systems.log_lines.append(
                    f"D\t{world.clock_tick}\t{npc_id}\t{kind}\t{target or ''}")
                systems.ui_events.append({
                    "event_id": f"dec:{world.clock_tick}:{npc_id}",
                    "tick": world.clock_tick, "kind": "decision",
                    "subject": npc_id, "intent": kind,
                    "target": target or "", "source": decision.source,
                    "payload": {},
                })
        decisions.append((npc_id, npc, decision))

    for npc_id, npc, decision in decisions:
        _apply(world, systems, cfg, npc_id, npc, decision)

    # 5.5 遗忘(0 点) + 夜间计划(LLM/规则模板生成次日计划)
    if world.clock_tick % cfg.ticks_per_day == 0:
        for npc in world.npcs.values():
            npc.on_day(cfg, world.clock_tick)
        planner = getattr(systems, "planner", None)
        if planner is not None:
            for npc in world.npcs.values():
                res = planner.plan_for_person(npc, world.clock_tick)
                npc.set_plan(res.entries)
