"""数据契约层：NPC <-> 世界 通信数据结构(全部 frozen + slots, 0.2 铁律)。

M2 定死: Percept / Intent / DecisionTrace / EntityView / EventView。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

@dataclass(frozen=True, slots=True)
class EntityView:
    """NPC 视野里的一个可交互实体(世界侧不可变快照)。"""
    entity_id: str
    name: str
    tags: frozenset[str]                  # {"edible","sleepable","toilet",...}
    affordances: Mapping[str, float]      # 完成后信号效果 {"hunger": +0.4}
    duration_ticks: int
    stock: int = -1                       # 存量(-1=无限); 囤货要靠它算“家里还剩几个”
    shelf_life_ticks: int = 0             # 保质期(0=不坏) —— 目标存量由它推导
    expires_tick: int = 0                 # 到点变质(0=不过期)
    location_id: str = ""
    price: float = 0.0                    # 价格(0=免费)
    owner: str = ""                       # 归属(""=无主/商店) —— 已把所在地主人折进来
    household: bool = False               # ★ 定死: 这件东西放在某住所(kind=home),
                                          #   而我是该住所的授权人(owner/open_to/公共)
                                          #   → 自家财产, 免费使用, 不看 price
    free_use: bool = False                # ★ 定死三条规则的综合结论: 我能【免费直接
                                          #   用】它(住所授权 / 公共无主 / 本公司店员)。
                                          #   False + price>0 → 才要买(Buy)。
    item_type: str = ""                   # 物品类型 id(去重/合并用)


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
    features: Mapping[str, float] = field(default_factory=dict)  # M8 前为 {}
    # TASK001: 结构化 trace —— 相关信号及其缺口(need=1-signal, 降序)
    relevant_signals: tuple[tuple[str, float], ...] = ()


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
    qty: int = 1
    trace: DecisionTrace = field(default_factory=DecisionTrace)


Intent = Idle | MoveTo | Interact | Buy


# ---------------------------------------------------------------------------
# 语义层契约(docs/design.md §2.7)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SemanticEvent:
    """NPC 要把内部状态说成的一句话(结构化, 还没措辞)。

    铁律: 这里全是【真值】。谁说的 / 什么行为 / 什么强度 / 涉及谁 —— 一个都不许编。
    随机只发生在【渲染措辞】那一步(见 npc/semantic.render)。
    """
    event_id: str                     # sem<N>
    tick: int
    speaker: str                      # npc_id
    act: str                          # STATE/INTENT/SURPRISE/DOUBT/REPORT
    topic: str                        # 冷却 / 去重键 ^[a-z][a-z0-9_.]*$
    slots: Mapping[str, Any] = field(default_factory=dict)   # 只放真值
    source: str = ""                  # "" = 自身; 否则 fact_id / 来源 npc_id


@dataclass(frozen=True, slots=True)
class Decision:
    """Person 的一次决策(供 engine 仲裁): intent + 来源。

    source 区分来源:
      "need"   → 需求(utility)驱动; 只在空闲时产生
      "plan"   → 计划/上班; 唯一能中止当前交互的来源
      "idle"   → 无事可做
    """
    intent: Intent
    source: str = "idle"          # "need" | "plan" | "idle"


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
