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
    tags: frozenset[str]                  # {"edible","sleepable","toilet",...}
    affordances: Mapping[str, float]      # 完成后信号效果 {"hunger": +0.4}
    duration_ticks: int
    distance: float = 0.0                 # 到 NPC 的距离(M2 先全 0.0)
    claimable: bool = True                # True=当前无人占用
    stock_zero: bool = False              # True=stock==0(真空), 区别于被占用
    location_id: str = ""
    price: float = 0.0                    # 价格(0=免费)
    owner: str = ""                       # 归属(""=无主/商店)


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
    features: Mapping[str, float] = field(default_factory=dict)  # M8 前为 {}
    # TASK001: 结构化 trace —— 相关信号及其缺口(need=1-signal, 降序)
    relevant_signals: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class PerceptionRecord:
    """一次可观察的感知记录(重评构建 percept 时落一份到 Person.last_percept)。

    只读观察用; 不参与决策。observed = 同 region 全部 + 跨 region 距离内可见。
    """
    tick: int
    npc_id: str
    location_id: str
    position: tuple[float, float] = (0.0, 0.0)
    observed_entity_ids: tuple[str, ...] = ()


# --- 意图(多态): 每种意图自持字段, 取代单一 kind+target_id ---
@dataclass(frozen=True, slots=True)
class Idle:
    trace: DecisionTrace = field(default_factory=DecisionTrace)


@dataclass(frozen=True, slots=True)
class MoveTo:
    dest: str
    trace: DecisionTrace = field(default_factory=DecisionTrace)


@dataclass(frozen=True, slots=True)
class Interact:
    target_id: str
    trace: DecisionTrace = field(default_factory=DecisionTrace)


@dataclass(frozen=True, slots=True)
class Buy:
    item_id: str
    trace: DecisionTrace = field(default_factory=DecisionTrace)


Intent = Idle | MoveTo | Interact | Buy


def intent_kind(intent: Intent) -> str:
    """意图 → 旧式 kind 字符串(日志/快照/前端兼容)。"""
    if isinstance(intent, Idle):
        return "idle"
    if isinstance(intent, MoveTo):
        return "move_to"
    if isinstance(intent, Interact):
        return "interact"
    if isinstance(intent, Buy):
        return "buy"
    raise TypeError(f"unknown intent {intent!r}")


def intent_target(intent: Intent) -> str | None:
    """意图 → 目标 id(旧式 target_id; idle 为 None)。"""
    if isinstance(intent, MoveTo):
        return intent.dest
    if isinstance(intent, Interact):
        return intent.target_id
    if isinstance(intent, Buy):
        return intent.item_id
    return None
