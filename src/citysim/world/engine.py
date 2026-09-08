"""world/engine —— 世界执行器(推进一个 tick 的世界演化 + 决策编排)。

按 World↔Person 契约: 上帝(World 侧)执行"世界进程"并广播心跳, 只发事件不写 Person。
systems 为执行环境(duck: interaction/scheduler/travel/pulses/日志), 由上层构造传入,
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
from citysim.world.pulses import apply as apply_pulses
from citysim.world.perception import build_percept
from citysim.world.travel import Travel


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


def _execute_buy(world, systems, cfg: SimConfig, pid: str, npc,
                 intent: Buy) -> None:
    """成交购买: 扣钱(只减不增) + 归自己 + 移到家 + 记忆刷新商品位置。"""
    ent = world.entities.get(intent.item_id)
    home = npc.home or world.loc_of(pid)
    if (ent is None or ent.price <= 0 or ent.owner != "" or ent.stock == 0
            or not npc.pay(ent.price)):
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid,
            {"target": intent.item_id,
             "why": "购买失败(无货/已售/钱不够)"}))
    else:
        ent.owner = pid
        ent.location_id = home
        ent.position = None                     # 归家后锚点重排
        world.layout_location(home)
        npc.note(ent.entity_id, tick=world.clock_tick,
                 located=home, owner="me", price=ent.price)   # 记忆: 在家归我
        world.bus.publish(world.bus.make(
            world.clock_tick, "bought", pid,
            {"item": ent.entity_id, "price": ent.price,
             "home": home, "money": round(npc.money, 2)}))
    systems.scheduler.schedule(pid, npc.next_review(cfg, world.hour_f()))


def tick(world, systems, cfg: SimConfig) -> None:
    """推进一个 tick 的世界演化(唯一执行入口)。世界进程在此, loop 只薄转发。"""
    world.clock_tick += 1
    hour = world.hour_f()

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

    # 5. 到点重评: 先对全部到点者算 Intent(同一世界快照), 再统一仲裁提交
    due = systems.scheduler.pop_due(world.clock_tick)
    decisions: list[tuple[str, Any, Any]] = []
    for npc_id in due:
        npc = world.npcs.get(npc_id)
        if npc is None:
            continue
        # 抵达: 旅行到期 → 落到目标 location 再重评
        if npc_id in systems.travel:
            trv = systems.travel.pop(npc_id)
            world.place_npc(npc_id, trv.to_loc)
        percept = build_percept(world, npc)
        world.bus.publish(world.bus.make(
            world.clock_tick, "perceived", npc_id,
            {"audience": [],
             "observed_entity_ids": sorted(
                 v.entity_id for v in percept.visible),
             "location_id": world.loc_of(npc_id)}))
        intent = npc.process(percept, cfg)        # 窄协议: 感知+决策一体(只看记忆+自身)
        kind = intent_kind(intent)
        target = intent_target(intent)
        if isinstance(intent, Idle):
            _notify_due(world, systems, npc)      # TODO(notify) 通用通知骨架
        if systems.log_lines is not None:
            systems.log_lines.append(
                f"D\t{world.clock_tick}\t{npc_id}\t{kind}\t{target or ''}")
            systems.ui_events.append({
                "event_id": f"dec:{world.clock_tick}:{npc_id}",
                "tick": world.clock_tick, "kind": "decision",
                "subject": npc_id, "intent": kind,
                "target": target or "",
                "payload": {},
            })
        decisions.append((npc_id, npc, intent))

    for npc_id, npc, intent in decisions:
        if isinstance(intent, MoveTo):
            systems.interaction.release_active(world, npc_id)   # 出发前清残留
            here = world.loc_of(npc_id)
            dest = intent.dest or here
            cost = _travel_cost(systems, cfg, here, dest)
            systems.travel[npc_id] = Travel(
                from_loc=here, to_loc=dest,
                depart_tick=world.clock_tick,
                arrive_tick=world.clock_tick + cost)
            systems.scheduler.schedule(npc_id, cost)
            continue
        if isinstance(intent, Buy):
            _execute_buy(world, systems, cfg, npc_id, npc, intent)
            continue
        ok = systems.interaction.submit(world, npc, intent)
        if isinstance(intent, Interact) and ok:
            ent = world.entities.get(intent.target_id)
            delay = ent.duration_ticks if ent else cfg.review_max_ticks
            systems.scheduler.schedule(npc_id, max(1, delay))
        else:
            # idle 或提交失败: 按清醒度节律排下次
            systems.scheduler.schedule(npc_id, npc.next_review(cfg, hour))

    # 5.5 遗忘: 每游戏日 0 点批量 decay(收进 Person)
    if world.clock_tick % cfg.ticks_per_day == 0:
        for npc in world.npcs.values():
            npc.on_day(cfg, world.clock_tick)
