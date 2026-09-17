"""sim/loop —— 引擎装配与薄 tick 入口。

世界执行(每个 tick 的演化/编排)已下沉到 world/run/engine.tick。本模块只负责:
  Systems(执行环境容器) + make_systems + attach_replay(观测/回放) + run_tick(薄转发)。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from citysim.core.config import SimConfig
from citysim.core.ring import RingBuffer
from citysim.world.mechanism.events import Event
from citysim.world.mechanism.interaction import InteractionSystem
from citysim.world.run.travel import Travel
from citysim.world.world import World


@dataclass
class Systems:
    """执行环境(世界侧容器; 由 engine.tick duck 消费)。"""
    interaction: InteractionSystem
    travel: dict[str, Travel] = field(default_factory=dict)  # npc_id -> Travel
    activity_log: dict = field(default_factory=dict)  # pid -> 当天行为段(时间线 viz)
    log_lines: list[str] | None = None   # 录制/回放(非 None 即开启)
    ui_events: RingBuffer = field(default_factory=RingBuffer)  # 事件环形缓冲(定长)
    tell_p: float = 0.0                  # 我这一轮想开口的概率(乘 tell_bias)
    listen_p: float = 1.0                # 被搭话的人愿意听的概率
    tell_same_home: float = 1.0          # 跟【同屋的人】搭话的权重
    tell_stranger: float = 0.15          # 跟【路人】搭话的权重
    # 一轮传播是【一对一】的: 说的人和听的人各用掉本轮名额, 说过的这轮不再听、
    # 听过的这轮不再说(见 engine._notify_due)。talked_tick 用来按 tick 清空。
    talked: set[str] = field(default_factory=set)
    talked_tick: int = -1
    last_wage_tick: int = -1     # 上次发工资的 tick(每天只发一次)
    last_restock_day: int = -1   # 上次开市补货的日子(每天只补一次)
    last_collect_day: int = -1   # 上次批发市场收货的日子(每天只收一次)
    production: dict = field(default_factory=dict)  # npc_id → 已攒工时(件)
    last_collect_day: int = -1   # 上次批发市场收货的日子(每天只收一次)
    last_hire_tick: int = -1     # 上次招聘匹配的 tick(每天一次)
    # —— 店铺排队(用户定: 一个前台同时只能服务 1 人, 多的排队) ——
    #   shop_id -> [pid...]   谁在排(先进先出, 两条前台就是两条线)
    #   pid -> shop_id        反查; 排队中的人这轮不决策(他在等)
    #   pid -> (item_id, 还想买几份)  成交 1 份就减 1
    shop_queue: dict[str, list] = field(default_factory=dict)
    queued: dict[str, str] = field(default_factory=dict)
    buy_left: dict[str, tuple] = field(default_factory=dict)
    queued_since: dict[str, int] = field(default_factory=dict)   # pid -> 开始排队的 tick
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    #     ↑ 传播用的随机源。【必须来自 systems】: 用全局 random 会让回放飘。
    bubble_ttl: int = 40                 # 气泡存活 tick(冒一下就走)
    # 只在【我关注的人/地方】冒泡, 其余屏蔽(满城同时冒泡等于没信息)。
    # None = 不限(无头工具/测试用); 空集合 = 一个都不冒。
    bubble_watch: set[str] | None = None
    log_attached: bool = False           # attach_replay 幂等标记
    travel_costs: dict[str, int] | None = None
    # 场景顶层 travel.default: 矩阵缺项时的兜底
    # (以前这个字段【没人读】—— 编辑器每次导出都白写一行, 调它也没有任何反应)
    travel_default: int = 0
    planner: object | None = None        # 日计划器: 有 `plan_for_person(person,
                                         # day_start_tick) -> list[PlanEntry]` 就算;
                                         # None = 纯 utility 驱动(不写时刻表)
                                         # 缺省 None = 纯 utility 驱动)
    roads: object | None = None          # world.roads.RoadGraph; 有则 MoveTo 走最短路
    last_decision: dict = field(default_factory=dict)  # 观测去重: npc_id -> 上次决策签名


def make_systems(*, log: bool = False, tell_p: float = 0.0,
                 listen_p: float = 1.0,
                 tell_same_home: float = 1.0, tell_stranger: float = 0.15,
                 roads: object | None = None,
                 seed: int = 0) -> Systems:
    return Systems(interaction=InteractionSystem(),
                   log_lines=[] if log else None, tell_p=tell_p,
                   listen_p=listen_p,
                   tell_same_home=tell_same_home,
                   tell_stranger=tell_stranger,
                   roads=roads, rng=random.Random(seed))


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
    """推进一个 tick(薄转发到 world/run/engine.tick; rng_pool 保留兼容, 暂未用)。"""
    from citysim.world.run.engine import tick as _engine_tick
    _engine_tick(world, systems, cfg)
