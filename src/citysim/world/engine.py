"""world/engine —— 世界执行器(推进一个 tick 的世界演化 + 决策编排)。

按 World↔Person 契约: 上帝(World 侧)执行"世界进程"并广播心跳, 只发事件不写 Person。
systems 为执行环境(duck: interaction/travel/pulses/日志), 由上层构造传入,
本模块不 import sim(避免 world→sim 反向依赖)。
"""
from __future__ import annotations

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
from citysim.world.world import entity_from_def


def _travel_cost(systems, cfg: SimConfig, a: str, b: str) -> int:
    """跨地点移动耗时: 优先 travel_costs 矩阵, 缺省回落 cfg.move_ticks。"""
    if systems.travel_costs:
        c = systems.travel_costs.get(f"{a}|{b}") or \
            systems.travel_costs.get(f"{b}|{a}")
        if c is not None:
            return c
    return cfg.move_ticks


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


def _notify_due(world, systems, npc) -> None:
    """通用事件/社交通知骨架 —— 原 gossip(传闻)已删, 暂不实现。

    TODO(notify): 通用事件通知 —— 谁在 idle 时可广播一条信息给同地他人; 具体
    (选样 / 置信(TOLD) / 受众判"是否已知" / 溯源)等 mem 模型语义定稳后再实现。
    """
    pass  # TODO(notify): 待实现, 见上


def _deliver(world, pid: str, npc, shop, qty: int, home: str):
    """把 qty 件送进家中的同类容器(合并到 stock); 无则新建一个。

    "商店一种货物不要重叠" → 同类只保留一个实体, 数量记在 stock 上。
    """
    for e in sorted(world.entities.values(), key=lambda x: x.entity_id):
        if (e.item_type == shop.item_type and e.location_id == home
                and e.owner == pid and e.stock != -1):
            e.stock += qty
            world.layout_location(home)
            return e
    d = load_item_defs().get(shop.item_type)
    if d is None:
        return None
    e = entity_from_def(d, home)
    e.owner = pid
    e.stock = qty
    e.persist_empty = True
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
        npc.note(container.entity_id, tick=world.clock_tick,
                 located=home, owner=pid, stock=container.stock)
    npc.on_interaction_done(intent.item_id, world.clock_tick)


def _can_preempt(world, systems, pid, source) -> bool:
    """计划只能硬中止可打断的交互; reflex(致命)始终可。"""
    if source == "reflex":
        return True
    act = systems.interaction.active.get(pid)
    if act is None:
        return True
    ent = world.entities.get(act.entity_id)
    return bool(ent is not None and ent.interruptible)


def _preempt(world, systems, pid, source) -> None:
    """抢占当前交互: reflex=软挂起(可恢复), plan=硬中止(触发 on_complete)。"""
    if source == "reflex":
        systems.interaction.suspend(world, pid)
    else:
        systems.interaction.abort(world, pid)


def _apply(world, systems, cfg, pid, npc, decision) -> None:
    """执行一条 Decision: 继续(同目标)/挂起/中止/提交。见 docs/task006.md。"""
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
        cost = _travel_cost(systems, cfg, here, dest)
        systems.travel[pid] = Travel(
            from_loc=here, to_loc=dest,
            depart_tick=world.clock_tick,
            arrive_tick=world.clock_tick + cost)
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
            world.place_npc(pid, trv.to_loc)

    # 5b. 决策: 先对全部该决策者算 Decision(同一世界快照), 再统一仲裁执行
    #     仲裁 = 继续/挂起/中止/提交; 见 docs/task006.md。
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
