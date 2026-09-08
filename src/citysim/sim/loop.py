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
from citysim.npc.brain import arousal, decide, review_interval_ticks
from citysim.npc.knowledge import CONF_UNKNOWN, Source
from citysim.npc.person import apply_metabolism
from citysim.sim.pulses import apply as apply_pulses
from citysim.world.events import Event
from citysim.world.interaction import InteractionSystem
from citysim.world.perception import build_percept, consolidate_observations
from citysim.world.scheduler import TimingWheel
from citysim.world.world import World, lerp

# M5: 跨 location 移动耗时已入 config [motion] move_ticks(m5-rectify 13)。


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _step_elimination(npc, cfg: SimConfig) -> None:
    """pending → 膀胱压力(事件驱动, 非线性基线)。"""
    if npc.bladder_pending <= 0:
        return
    step = min(cfg.bladder_convert, npc.bladder_pending)
    npc.bladder_pending -= step
    npc.signals["bladder"] = _clamp(npc.signals.get("bladder", 1.0) - step)


@dataclass(frozen=True, slots=True)
class Travel:
    """跨地点移动(display_m5_ui G0): 记录出发/到达地点与 tick, 供前端插值。

    TASK001: start/target_position 让 NPC 在 travel 期间拥有连续 2D position
    (每 tick 由主循环线性推进)。
    """
    from_loc: str
    to_loc: str
    depart_tick: int
    arrive_tick: int
    start_position: tuple[float, float] | None = None
    target_position: tuple[float, float] | None = None


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


def _advance_travel_positions(world: World, systems: Systems) -> None:
    """每 tick 把旅行中 NPC 的连续 position 沿 start→target 线性推进。

    t=depart → start; t=arrive → target(与到达时 location 落点一致)。
    无几何/无坐标的世界不移动(position 保持), 不改变旧行为。
    """
    for pid, trv in list(systems.travel.items()):
        npc = world.npcs.get(pid)
        if npc is None or trv.start_position is None \
                or trv.target_position is None:
            continue
        span = trv.arrive_tick - trv.depart_tick
        if span <= 0:
            continue
        t = (world.clock_tick - trv.depart_tick) / span
        npc.position = lerp(trv.start_position, trv.target_position, t)


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


def _apply_hp(npc, cfg: SimConfig) -> None:
    """生命: 饥饿/饥渴任一为 0 → hp 下降; 两者都满足 → 越大越快回升。"""
    hunger = npc.signals.get("hunger", 1.0)
    thirst = npc.signals.get("thirst", 1.0)
    hp = npc.signals.get("hp", 1.0)
    if hunger <= 0.0 or thirst <= 0.0:
        npc.signals["hp"] = max(0.0, hp - cfg.hp_decay)
    else:
        rate = (hunger + thirst) / 2.0          # 两者越大回升越快
        npc.signals["hp"] = min(1.0, hp + cfg.hp_regen * rate)


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


def _pick_tell_fact(kb, rng, interesting=None):
    """传闻选样: overlay 非注入事实按 confidence 加权随机(m5-rectify 05)。

    避免恒取最高置信(陈旧 OBSERVED 1.0 永远压过新近 TOLD 0.8 → 假消息
    无法二次传播)。interesting(f)->bool 可选: 只从"对听众有信息量"的事实选,
    排除人人可见的设施常识(如"床能睡"), 否则会稀释真消息。
    """
    cands = [f for f in kb.overlay.values()
             if f.source.kind != "INJECTED" and f.confidence >= CONF_UNKNOWN]
    if interesting is not None:
        cands = [f for f in cands if interesting(f)]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    weights = [c.confidence for c in cands]
    return rng.choices(cands, weights=weights)[0]


def _gossip_due(world: World, systems: Systems, rng_pool: dict[str, Any],
                speaker_id: str, speaker_npc) -> None:
    """讲话者本次重评(idle)时按 tell_p 向一位同地 idle 听众分享一条事实。

    m5-rectify 05: 挂 due 重评(成本 O(due))而非每 tick 每对; 选样置信加权。
    m5-rectify 06: 接收方 TOLD 来源携带起源 fact 引用 (speaker, f:origin)。
    """
    p = systems.tell_p * getattr(speaker_npc, "tell_bias", 1.0)
    if p <= 0.0:
        return
    rng = rng_pool[speaker_id]
    if rng.random() >= p:
        return
    # 先找同地可接收的听众(是否"已知"交给选样判定)
    ids = [pid for pid, npc in world.npcs.items()
           if pid != speaker_id and npc.is_alive()
           and npc.location_id == speaker_npc.location_id
           and pid not in systems.interaction.active
           and pid not in systems.travel]
    if not ids:
        return
    # 只传播"至少有听众不知道"的事实(排除人人可见的设施常识)
    fact = _pick_tell_fact(
        speaker_npc.kb, rng,
        interesting=lambda f: any(
            not world.npcs[pid].kb.knows(f.subject, f.relation, f.obj)
            for pid in ids))
    if fact is None:
        return
    receivers = [pid for pid in ids
                 if not world.npcs[pid].kb.knows(
                     fact.subject, fact.relation, fact.obj)]
    receiver = rng.choice(receivers)
    r_kb = world.npcs[receiver].kb
    f2 = r_kb.learn(subject=fact.subject, relation=fact.relation,
                    obj=fact.obj, confidence=fact.confidence * 0.8,
                    source=Source(kind="TOLD",
                                  ref=(speaker_id, f"f:{fact.fact_id}")),
                    tick=world.clock_tick)
    _REL_ZH = {"located_at": "在", "affords": "可提供"}

    def _term(x: str) -> str:      # 服务端生成人话(canvasrecode 9: short)
        e = world.entities.get(x)
        return e.name if (e is not None and e.name) else str(x)
    short = f"{_term(fact.subject)} {_REL_ZH.get(fact.relation, fact.relation)} " \
            f"{_term(fact.obj)}"
    world.bus.publish(world.bus.make(
        world.clock_tick, "told", speaker_id,
        {"audience": [receiver], "from": speaker_id,
         "subject": fact.subject, "relation": fact.relation,
         "obj": fact.obj, "conf": round(fact.confidence * 0.8, 3),
         "origin": fact.fact_id, "fact_id": f2.fact_id, "short": short}))


def _execute_buy(world: World, systems: Systems, cfg: SimConfig,
                 pid: str, npc, intent: Buy) -> None:
    """成交购买: 扣钱(资金只减不增) + 归自己 + 移到家 + KB 刷新商品位置。

    买入后实体从商店搬到 npc.home, 并把 KB 里该商品的 located_at 改到新家、
    证伪旧位置。"""
    ent = world.entities.get(intent.item_id)
    if (ent is None or ent.price <= 0 or ent.owner != ""
            or npc.money < ent.price or ent.stock == 0):
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid,
            {"target": intent.item_id,
             "why": "购买失败(无货/已售/钱不够)"}))
    else:
        npc.money = max(0.0, npc.money - ent.price)
        ent.owner = pid
        ent.location_id = npc.home or npc.location_id
        # TASK001 空间: 归家后实体锚点随 region 重排(旧几何不再适用)
        ent.position = None
        world.layout_location(ent.location_id)
        # KB 刷新商品位置: 学新家位置 + 证伪其余旧位置
        npc.kb.learn(subject=ent.entity_id, relation="located_at",
                     obj=ent.location_id, confidence=1.0,
                     source=Source(kind="OBSERVED"), tick=world.clock_tick)
        for f in npc.kb.query(subject=ent.entity_id, relation="located_at"):
            if f.obj != ent.location_id:
                npc.kb.refute(f.fact_id)
        world.bus.publish(world.bus.make(
            world.clock_tick, "bought", pid,
            {"item": ent.entity_id, "price": ent.price,
             "home": ent.location_id, "money": round(npc.money, 2)}))
    # 买完/失败都尽快重评(回家/换目标)
    a = arousal(world.hour_f(), npc.signals.get("energy", 0.5),
                npc.signals.get("hunger", 0.5))
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
    _advance_travel_positions(world, systems)

    # 1. 代谢(全体活着的 NPC; 睡眠冻结精力, 忙碌冻结娱乐——无聊才降 fun)
    died: list[str] = []
    for pid, npc in world.npcs.items():
        if npc.is_alive():
            amul: dict[str, float] = {}
            if _sleeping(world, systems, pid):
                amul["energy"] = 0.0
            if _busy(world, systems, pid):
                amul["fun"] = 0.0
            apply_metabolism(npc.signals, cfg.metabolism,
                             personality_mul=npc.personality,
                             activity_mul=amul or None)
            _apply_hp(npc, cfg)
            if not npc.is_alive():
                died.append(pid)
    for pid in died:
        _kill(world, systems, pid)             # 死亡销毁 + 日志
    # 2. 排泄转化
    for npc in world.npcs.values():
        _step_elimination(npc, cfg)
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
            npc.location_id = trv.to_loc
            if trv.target_position is not None:
                npc.position = trv.target_position   # 位置与 region 落点一致
        prev_ids = npc.kb.overlay_fact_ids()
        percept = build_percept(world, npc)
        # TASK002: perceived 事件(观察用; audience=[] 只进日志/UI 流)
        world.bus.publish(world.bus.make(
            world.clock_tick, "perceived", npc_id,
            {"audience": [],
             "observed_entity_ids": sorted(
                 v.entity_id for v in percept.visible),
             "location_id": npc.location_id,
             "position": [npc.position[0], npc.position[1]]}))
        consolidate_observations(npc, percept, npc.kb,
                                 tick=world.clock_tick)  # 感知 → 知识
        # TASK001/002 观察: 本 tick 新学到的 overlay 事实 → learned 事件(调用侧发,
        # audience=[] 只进日志/UI 流, 不塞回 NPC 信箱)
        for fid in sorted(npc.kb.overlay_fact_ids() - prev_ids):
            f = npc.kb.overlay.get(fid)
            if f is None:
                continue
            world.bus.publish(world.bus.make(
                world.clock_tick, "learned", npc_id,
                {"audience": [], "fact_id": fid, "subject": f.subject,
                 "relation": f.relation, "obj": f.obj,
                 "source_kind": f.source.kind,
                 "confidence": round(f.confidence, 3)}))
        intent = decide(percept, npc.signals, npc.personality, kb=npc.kb,
                        cfg=cfg, rng=rng_pool[npc_id], money=npc.money)
        npc.last_intent = intent
        kind = intent_kind(intent)
        target = intent_target(intent)
        # M5 传闻: 仅本次到点且算成 idle 者才可能开口(m5-rectify 05, O(due))
        if isinstance(intent, Idle):
            _gossip_due(world, systems, rng_pool, npc_id, npc)
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
                        npc.signals.get("hunger", 0.5))
            systems.scheduler.schedule(npc_id, review_interval_ticks(a, cfg))
    # 5.5 M5 遗忘: 每游戏日 0 点对全部 NPC 批量 decay。
    if world.clock_tick % cfg.ticks_per_day == 0:
        for npc in world.npcs.values():
            npc.kb.decay(now_tick=world.clock_tick,
                         half_life_ticks=cfg.half_life_ticks)
