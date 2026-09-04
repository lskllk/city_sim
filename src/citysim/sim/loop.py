"""sim/loop —— 主循环(唯一 tick 入口)。推进顺序定死(design M3 3.5)。

1 代谢 → 2 排泄转化 → 3 交互推进 → 4 睡眠唤醒(在 interaction 内以
wake_condition 完成) → 5 到点重评(decide + submit + 排下次)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from citysim.core.config import SimConfig
from citysim.npc.brain import arousal, decide, review_interval_ticks
from citysim.npc.goap import default_actions
from citysim.npc.knowledge import CONF_UNKNOWN, Source
from citysim.npc.person import apply_metabolism
from citysim.sim.pulses import apply as apply_pulses
from citysim.world.events import Event
from citysim.world.interaction import InteractionSystem
from citysim.world.perception import build_percept, consolidate_observations
from citysim.world.scheduler import TimingWheel
from citysim.world.world import World

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
    """跨地点移动(display_m5_ui G0): 记录出发/到达地点与 tick, 供前端插值。"""
    from_loc: str
    to_loc: str
    depart_tick: int
    arrive_tick: int


@dataclass
class Systems:
    scheduler: TimingWheel
    interaction: InteractionSystem
    travel: dict[str, Travel] = field(default_factory=dict)  # npc_id -> Travel
    log_lines: list[str] | None = None   # 录制/回放(非 None 即开启)
    ui_events: list = field(default_factory=list)  # 结构化事件(UI/网关消费)
    tell_p: float = 0.0                  # 传闻概率(M5; 0=关闭)
    actions: tuple | None = None         # GOAP 动作库(装配期注入, m5-rectify 14)
    log_attached: bool = False           # attach_replay 幂等标记
    # elm_lane: 距离矩阵(key "a|b"->ticks) 与 归一化场景脉冲(见 sim/pulses)
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


def make_systems(*, log: bool = False, tell_p: float = 0.0,
                 actions: tuple | None = None) -> Systems:
    sch = TimingWheel()
    if actions is None:
        actions, _ = default_actions()   # 装配期加载一次(测试可注入临时动作库)
    return Systems(scheduler=sch,
                   interaction=InteractionSystem(scheduler=sch, actions=actions),
                   log_lines=[] if log else None, tell_p=tell_p,
                   actions=actions)


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
            "tick": ev.tick, "kind": ev.kind, "subject": ev.subject_id,
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
    if p <= 0.0 or speaker_npc.kb is None:
        return
    rng = rng_pool[speaker_id]
    if rng.random() >= p:
        return
    # 先找同地可接收的听众(是否"已知"交给选样判定)
    ids = [pid for pid, npc in world.npcs.items()
           if pid != speaker_id and npc.kb is not None and npc.is_alive()
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
    _REL_ZH = {"contains": "里有", "sells": "在卖", "located_at": "在",
               "price_of": "定价为", "is_a": "是", "affords": "可提供"}

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


def run_tick(world: World, systems: Systems, cfg: SimConfig,
             rng_pool: dict[str, Any]) -> None:
    """推进一个 tick(唯一入口)。"""
    world.clock_tick += 1
    hour = world.hour_f()

    # 0. 场景脉冲(世界侧定时, elm_lane): 在 NPC 感知前改库存/停业
    if systems.pulses:
        apply_pulses(world, systems.pulses, world.clock_tick,
                     cfg.ticks_per_day)

    # 1. 代谢(全体活着的 NPC; 睡眠中冻结精力消耗, 否则永远睡不饱)
    for pid, npc in world.npcs.items():
        npc.hour_f = hour
        if npc.is_alive():
            amul = {"energy": 0.0} if _sleeping(world, systems, pid) else None
            apply_metabolism(npc.signals, cfg.metabolism,
                             personality_mul=npc.personality,
                             activity_mul=amul)
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
            npc.location_id = systems.travel.pop(npc_id).to_loc
        percept = build_percept(world, npc)
        kb = getattr(npc, "kb", None)
        if kb is not None:
            consolidate_observations(npc, percept, kb,
                                     tick=world.clock_tick)  # 感知 → 知识
        intent = decide(percept, npc.signals, npc.personality, kb=kb,
                        cfg=cfg, rng=rng_pool[npc_id], actions=systems.actions)
        npc.last_intent = intent
        # M5 传闻: 仅本次到点且算成 idle 者才可能开口(m5-rectify 05, O(due))
        if intent.kind == "idle":
            _gossip_due(world, systems, rng_pool, npc_id, npc)
        if systems.log_lines is not None:
            plan = ",".join(intent.trace.plan)
            systems.log_lines.append(
                f"D\t{world.clock_tick}\t{npc_id}\t{intent.kind}\t"
                f"{intent.target_id or ''}\t{plan}")
            systems.ui_events.append({
                "tick": world.clock_tick, "kind": "decision",
                "subject": npc_id, "intent": intent.kind,
                "target": intent.target_id or "", "plan": plan,
                "payload": {},
            })
        decisions.append((npc_id, npc, intent))
    for npc_id, npc, intent in decisions:
        if intent.kind == "move_to":
            # 旅行由主循环管理(不走 InteractionSystem); 出发前清残留 claim
            systems.interaction.release_active(world, npc_id)
            dest = intent.target_id or npc.location_id
            cost = _travel_cost(systems, cfg, npc.location_id, dest)
            systems.travel[npc_id] = Travel(
                from_loc=npc.location_id, to_loc=dest,
                depart_tick=world.clock_tick,
                arrive_tick=world.clock_tick + cost)
            systems.scheduler.schedule(npc_id, cost)
            continue
        ok = systems.interaction.submit(world, npc, intent)
        if intent.kind == "interact" and ok:
            ent = world.entities.get(intent.target_id)
            delay = ent.duration_ticks if ent else cfg.review_max_ticks
            systems.scheduler.schedule(npc_id, max(1, delay))
        else:
            # idle 或提交失败: 按清醒度节律排下次
            a = arousal(npc.hour_f, npc.signals.get("energy", 0.5),
                        npc.signals.get("hunger", 0.5))
            systems.scheduler.schedule(npc_id, review_interval_ticks(a, cfg))
    # 5.5 M5 遗忘: 每游戏日 0 点对带 KB 的 NPC 批量 decay(design 553;
    #    kb=None 不触发 → M4 golden 平价保持)。
    if world.clock_tick % cfg.ticks_per_day == 0:
        for npc in world.npcs.values():
            kb = getattr(npc, "kb", None)
            if kb is not None:
                kb.decay(now_tick=world.clock_tick,
                         half_life_ticks=cfg.half_life_ticks)
