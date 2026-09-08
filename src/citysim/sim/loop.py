"""sim/loop —— 引擎装配与薄 tick 入口。

世界执行(每个 tick 的演化/编排)已下沉到 world/engine.tick。本模块只负责:
  Systems(执行环境容器) + make_systems + attach_replay(观测/回放) + run_tick(薄转发)。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from citysim.core.config import SimConfig
from citysim.world.events import Event
from citysim.world.interaction import InteractionSystem
from citysim.world.scheduler import TimingWheel
from citysim.world.travel import Travel
from citysim.world.world import World


@dataclass
class Systems:
    """执行环境(世界侧容器; 由 engine.tick duck 消费)。"""
    scheduler: TimingWheel
    interaction: InteractionSystem
    travel: dict[str, Travel] = field(default_factory=dict)  # npc_id -> Travel
    log_lines: list[str] | None = None   # 录制/回放(非 None 即开启)
    ui_events: list = field(default_factory=list)  # 结构化事件(UI/网关消费)
    tell_p: float = 0.0                  # (预留)通知概率, 待 _notify_due 用
    log_attached: bool = False           # attach_replay 幂等标记
    travel_costs: dict[str, int] | None = None
    pulses: list = field(default_factory=list)


def make_systems(*, log: bool = False, tell_p: float = 0.0) -> Systems:
    sch = TimingWheel()
    return Systems(scheduler=sch,
                   interaction=InteractionSystem(scheduler=sch),
                   log_lines=[] if log else None, tell_p=tell_p)


def attach_replay(world: World, systems: Systems) -> None:
    """挂事件日志订阅 + 结构化事件流(幂等, 单一事件源)。"""
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


def run_tick(world: World, systems: Systems, cfg: SimConfig,
             rng_pool=None) -> None:
    """推进一个 tick(薄转发到 world/engine.tick; rng_pool 保留兼容, 暂未用)。"""
    from citysim.world.engine import tick as _engine_tick
    _engine_tick(world, systems, cfg)
