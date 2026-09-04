"""数据契约层：NPC <-> 世界 通信数据结构(全部 frozen + slots, 0.2 铁律)。

M2 定死: Percept / Intent / DecisionTrace / EntityView / EventView。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

SourceKind = Literal["INJECTED", "OBSERVED", "TOLD", "INFERRED"]


@dataclass(frozen=True, slots=True)
class EntityView:
    """NPC 视野里的一个可交互实体(世界侧不可变快照)。"""
    entity_id: str
    name: str
    tags: frozenset[str]                  # {"edible","sleepable","toilet","container",...}
    affordances: Mapping[str, float]      # 完成后信号效果 {"hunger": +0.4}
    duration_ticks: int
    distance: float = 0.0                 # 到 NPC 的距离(M2 先全 0.0)
    claimable: bool = True                # True=当前无人占用
    stock_zero: bool = False              # True=stock==0(真空), 区别于被占用
    location_id: str = ""


@dataclass(frozen=True, slots=True)
class EventView:
    event_id: str
    tick: int
    kind: str                             # "intent_failed" | "interaction_done" | "told" | ...
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Percept:
    tick: int
    hour_f: float
    location_id: str
    visible: tuple[EntityView, ...] = ()
    events: tuple[EventView, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    ranked: tuple[tuple[str, float], ...] = ()   # (entity_id, utility分) 降序
    reason: str = ""
    used_fact_ids: tuple[str, ...] = ()          # M5 前恒为 ()
    plan: tuple[str, ...] = ()                   # GOAP 动作名序列, 无计划=()
    features: Mapping[str, float] = field(default_factory=dict)  # M8 前为 {}


@dataclass(frozen=True, slots=True)
class Intent:
    kind: Literal["interact", "move_to", "idle"]
    target_id: str | None = None
    trace: DecisionTrace = field(default_factory=DecisionTrace)
