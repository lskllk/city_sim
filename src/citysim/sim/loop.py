"""sim/loop —— 主循环(唯一 tick 入口)。推进顺序定死(design M3 3.5)。

1 代谢 → 2 排泄转化 → 3 交互推进 → 4 睡眠唤醒(在 interaction 内以
wake_condition 完成) → 5 到点重评(decide + submit + 排下次)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from citysim.core.config import SimConfig
from citysim.npc.brain import arousal, decide, review_interval_ticks
from citysim.npc.person import apply_metabolism
from citysim.world.events import Event
from citysim.world.interaction import InteractionSystem
from citysim.world.perception import build_percept, consolidate_observations
from citysim.world.scheduler import TimingWheel
from citysim.world.world import World

# M5: 跨 location 移动耗时(tick)。TODO(config): 入 sim.toml 由日程/距离驱动。
MOVE_TICKS = 30


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _step_elimination(npc, cfg: SimConfig) -> None:
    """pending → 膀胱压力(事件驱动, 非线性基线)。"""
    if npc.bladder_pending <= 0:
        return
    step = min(cfg.bladder_convert, npc.bladder_pending)
    npc.bladder_pending -= step
    npc.signals["bladder"] = _clamp(npc.signals.get("bladder", 1.0) - step)


@dataclass
class Systems:
    scheduler: TimingWheel
    interaction: InteractionSystem
    travel: dict[str, str] = field(default_factory=dict)  # npc_id -> 目的地
    log_lines: list[str] | None = None   # 录制/回放(非 None 即开启)


def make_systems(*, log: bool = False) -> Systems:
    sch = TimingWheel()
    return Systems(scheduler=sch, interaction=InteractionSystem(scheduler=sch),
                   log_lines=[] if log else None)


def attach_replay(world: World, systems: Systems) -> None:
    """挂事件日志订阅(与 decide 日志一起构成回放流)。"""
    if systems.log_lines is None:
        return

    def _on_event(ev: Event) -> None:
        payload = ";".join(f"{k}={v}" for k, v in ev.payload.items())
        systems.log_lines.append(  # type: ignore[union-attr]
            f"E\t{ev.tick}\t{ev.kind}\t{ev.subject_id}\t{payload}")

    world.bus.subscribe_log(_on_event)


def _sleeping(world: World, systems: Systems, pid: str) -> bool:
    """当前是否在睡眠交互中(active 实体 tags 含 sleepable)。"""
    act = systems.interaction.active.get(pid)
    if act is None:
        return False
    ent = world.entities.get(act.entity_id)
    return ent is not None and ent.is_sleepable


def run_tick(world: World, systems: Systems, cfg: SimConfig,
             rng_pool: dict[str, Any]) -> None:
    """推进一个 tick(唯一入口)。"""
    world.clock_tick += 1
    hour = world.hour_f()

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
    # 5. 到点重评
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
            npc.location_id = systems.travel.pop(npc_id)
        percept = build_percept(world, npc)
        kb = getattr(npc, "kb", None)
        if kb is not None:
            consolidate_observations(npc, percept, kb)   # 感知 → 知识
        intent = decide(percept, npc.signals, npc.personality, kb=kb,
                        cfg=cfg, rng=rng_pool[npc_id])
        npc.last_intent = intent
        if systems.log_lines is not None:
            plan = ",".join(intent.trace.plan)
            systems.log_lines.append(
                f"D\t{world.clock_tick}\t{npc_id}\t{intent.kind}\t"
                f"{intent.target_id or ''}\t{plan}")
        decisions.append((npc_id, npc, intent))
    for npc_id, npc, intent in decisions:
        if intent.kind == "move_to":
            # 旅行由主循环管理(不走 InteractionSystem)
            systems.travel[npc_id] = intent.target_id or npc.location_id
            systems.scheduler.schedule(npc_id, MOVE_TICKS)
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
