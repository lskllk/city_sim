"""sim/loop —— 主循环(唯一 tick 入口)。推进顺序定死(design M3 3.5)。

1 代谢 → 2 排泄转化 → 3 交互推进 → 4 睡眠唤醒(在 interaction 内以
wake_condition 完成) → 5 到点重评(decide + submit + 排下次)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
from citysim.npc.brain import arousal, review_interval_ticks
from citysim.world.pulses import apply as apply_pulses
from citysim.world.events import Event
from citysim.world.interaction import InteractionSystem
from citysim.world.perception import build_percept
from citysim.world.scheduler import TimingWheel
from citysim.world.travel import Travel, advance as advance_travel
from citysim.world.world import World

# M5: 跨 location 移动耗时已入 config [motion] move_ticks(m5-rectify 13)。

def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))

@dataclass
class Systems:
    scheduler: TimingWheel
    interaction: InteractionSystem
    travel: dict[str, Travel] = field(default_factory=dict)  # npc_id -> Travel
    log_lines: list[str] | None = None   # 录制/回放(非 None 即开启)
    ui_events: list = field(default_factory=list)  # 结构化事件(UI/网关消费)
    tell_p: float = 0.0                  # 传闻概率(M5; 0=关闭)
    log_attached: bool = False           # attach_replay 幂等标记
    travel_costs: dict[str, int] | None = None
    pulses: list = field(default_factory=list)

def _travel_cost(systems: "Systems", cfg: SimConfig, a: str, b: str) -> int:
    """跨地点移动耗时: 优先 travel_costs 矩阵, 缺省回落到 cfg.move_ticks。"""
    if systems.travel_costs:
        c = systems.travel_costs.get(f"{a}|{b}") or \
            systems.travel_costs.get(f"{b}|{a}")
        if c is not None:
            return c
    return cfg.move_ticks

def make_systems(*, log: bool = False, tell_p: float = 0.0) -> Systems:
    sch = TimingWheel()
    return Systems(scheduler=sch,
                   interaction=InteractionSystem(scheduler=sch),
                   log_lines=[] if log else None, tell_p=tell_p)

def attach_replay(world: World, systems: Systems) -> None:
    """挂事件日志订阅 + 结构化事件流(g5-life 01: 幂等, 单一事件源)。

    log_lines(文本, 供回放测试) 与 ui_events(结构化 dict, 供 UI/网关) 同时写;
    重复调用不重复订阅。
    """
    if systems.log_lines is None:
        return
    if systems.log_attached:
        return
    systems.log_attached = True

    def _on_event(ev: Event) -> None:
        payload = ";".join(f"{k}={v}" for k, v in ev.payload.items())
        systems.log_lines.append(  # type: ignore[union-attr]
            f"E\t{ev.tick}\t{ev.kind}\t{ev.subject_id}\t{payload}")
        systems.ui_events.append({
            "event_id": ev.event_id, "tick": ev.tick,
            "kind": ev.kind, "subject": ev.subject_id,
            "payload": dict(ev.payload),
        })

    world.bus.subscribe_log(_on_event)

def _sleeping(world: World, systems: Systems, pid: str) -> bool:
    """当前是否在睡眠交互中(active 实体 tags 含 sleepable)。"""
    act = systems.interaction.active.get(pid)
    if act is None:
        return False
    ent = world.entities.get(act.entity_id)
    return ent is not None and ent.is_sleepable

def _busy(world: World, systems: Systems, pid: str) -> bool:
    """当前是否忙碌(有进行中交互或正在跨地点移动)。"""
    return (systems.interaction.active.get(pid) is not None
            or pid in systems.travel)

def _kill(world: World, systems: Systems, pid: str) -> None:
    """NPC 死亡: 清残留 → 从世界销毁 → 发布死亡事件(日志记录)。"""
    npc = world.npcs.get(pid)
    if npc is None:
        return
    systems.interaction.release_active(world, pid)   # 清 claim
    systems.travel.pop(pid, None)                    # 清旅行
    world.npcs.pop(pid, None)                        # 从世界销毁
    world.bus.publish(world.bus.make(
        world.clock_tick, "npc_died", pid,
        {"name": npc.name, "loc": npc.location_id}))

def _notify_due(world: World, systems: Systems, npc) -> None:
    """通用事件/社交通知骨架 —— 原 gossip(传闻)已删, 暂不实现。

    未来这里做"NPC 想把自己知道/看到的某条信息, 主动通知他人"。
    TODO(notify): 通用事件通知 —— 谁在 idle 时可广播一条信息给同地他人; 具体
    (选样 / 置信(TOLD) / 受众判"是否已知" / 溯源)等 mem 模型语义定稳后再实现。
    """
    pass  # TODO(notify): 待实现, 见上
def _execute_buy(world: World, systems: Systems, cfg: SimConfig,
                 pid: str, npc, intent: Buy) -> None:
    """成交购买: 扣钱(资金只减不增) + 归自己 + 移到家 + KB 刷新商品位置。

    买入后实体从商店搬到 npc.home, 并把 KB 里该商品的 located_at 改到新家、
    证伪旧位置。"""
    ent = world.entities.get(intent.item_id)
    home = npc.home or npc.location_id
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
    # 买完/失败都尽快重评(回家/换目标)
    a = arousal(world.hour_f(), npc.signals.get("energy", 0.5),
                npc.signals.get("hunger", 0.5), cfg)
    systems.scheduler.schedule(pid, review_interval_ticks(a, cfg))

def run_tick(world: World, systems: Systems, cfg: SimConfig,
             rng_pool: dict[str, Any]) -> None:
    """推进一个 tick(唯一入口)。"""
    world.clock_tick += 1
    hour = world.hour_f()

    # 0. 场景脉冲(世界侧定时, elm_lane): 在 NPC 感知前改库存/停业
    if systems.pulses:
        apply_pulses(world, systems.pulses, world.clock_tick,
                     cfg.ticks_per_day)

    # 0.5 旅行 NPC 连续 position 推进(每 tick; 到达由 to-location 重评落定)
    advance_travel(world, systems.travel)

    # 1. 心跳(身体演化收进 Person; 世界只广播, 不改 signals): 代谢+hp+排泄
    died: list[str] = []
    for pid, npc in world.npcs.items():
        if npc.is_alive():
            npc.heartbeat(world.clock_tick, cfg,
                          sleep=_sleeping(world, systems, pid),
                          busy=_busy(world, systems, pid))
            if not npc.is_alive():
                died.append(pid)
    for pid in died:
        _kill(world, systems, pid)             # 死亡销毁 + 日志
    # 3. 交互推进(含睡眠唤醒提前完成 / plan 链)
    systems.interaction.step(world, cfg)
    # 5. 到点重评: 先对全部到点者算 Intent(同一世界快照, 反映 claim 竞争),
    #    再统一仲裁提交(先手 claim 成功, 后手收到 intent_failed)
    due = systems.scheduler.pop_due(world.clock_tick)
    decisions: list[tuple[str, Any, Any]] = []
    for npc_id in due:
        npc = world.npcs.get(npc_id)
        if npc is None or not npc.is_alive():
            continue
        # 抵达: 旅行到期 → 落到目标 location 再重评
        if npc_id in systems.travel:
            trv = systems.travel.pop(npc_id)
            npc.arrive(trv.to_loc, trv.target_position)
        percept = build_percept(world, npc)
        # TASK002: perceived 事件(观察用; audience=[] 只进日志/UI 流)
        world.bus.publish(world.bus.make(
            world.clock_tick, "perceived", npc_id,
            {"audience": [],
             "observed_entity_ids": sorted(
                 v.entity_id for v in percept.visible),
             "location_id": npc.location_id,
             "position": list(npc.position)}))
        npc.perceive(percept, world.clock_tick)   # 感知 → 记忆(写 mem)
        intent = npc.decide(cfg)                  # 决策(只看记忆+自身)
        kind = intent_kind(intent)
        target = intent_target(intent)
        # TODO(notify): 通用事件通知骨架 —— 原 gossip(传闻)已删, 待 mem 传播语义定稳后实现
        if isinstance(intent, Idle):
            _notify_due(world, systems, npc)
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
            # 旅行由主循环管理(不走 InteractionSystem); 出发前清残留 claim
            systems.interaction.release_active(world, npc_id)
            dest = intent.dest or npc.location_id
            cost = _travel_cost(systems, cfg, npc.location_id, dest)
            target_pos = world.region_center(dest) or npc.position
            systems.travel[npc_id] = Travel(
                from_loc=npc.location_id, to_loc=dest,
                depart_tick=world.clock_tick,
                arrive_tick=world.clock_tick + cost,
                start_position=npc.position,
                target_position=target_pos)
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
            a = arousal(hour, npc.signals.get("energy", 0.5),
                        npc.signals.get("hunger", 0.5), cfg)
            systems.scheduler.schedule(npc_id, review_interval_ticks(a, cfg))
    # 5.5 M5 遗忘: 每游戏日 0 点对全部 NPC 批量 decay。
    if world.clock_tick % cfg.ticks_per_day == 0:
        for npc in world.npcs.values():
            npc.decay_memory(cfg, world.clock_tick)
