"""纯数据 Person（M1: 信号单一真源）。

0..1 float signals 是唯一存储; 不再有 Body(0..100 int) 双写、无第二份生理
副本。Identity(身份, 几乎不变) / Life(人生轨迹, 缓慢变) 保留为独立小对象;
状态层 = signals + 少量活动字段(position/activity/hour_f/bladder_pending)。

本模块不得 import citysim.world(0.2 铁律, CI 检查)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Mapping

from citysim.core.config import SIGNALS

if TYPE_CHECKING:  # pragma: no cover
    from citysim.core.types import Intent


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


# ----------------------------------------------------------------------
# 不变层: 身份 (const, 几乎不变)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Identity:
    person_id: str
    name: str
    gender: str = ""
    birthday: str = ""                       # YYYY-MM-DD
    traits: Mapping[str, Any] = field(default_factory=dict)

    def birthday_date(self) -> date:
        y, m, d = self.birthday.split("-")
        return date(int(y), int(m), int(d))


# ----------------------------------------------------------------------
# 慢变层: 人生轨迹 (long term, 按天/年变)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Life:
    age: int = 0
    family_id: str = ""
    home: str = ""
    role: str = "retired"                    # worker | shopper | student | retired
    skills: Mapping[str, int] = field(default_factory=dict)
    kinship: Mapping[str, str] = field(default_factory=dict)


# ----------------------------------------------------------------------
# 视图: 0..1 float -> 0..100 int (仅展示/日志; 永不进入存储路径)
# ----------------------------------------------------------------------
def signals_as_percent(signals: Mapping[str, float]) -> dict[str, int]:
    """显示视图。存储一律 0..1 float; 需要百分比展示时才调本函数。"""
    return {k: round(_clamp(float(v)) * 100) for k, v in signals.items()}


def full_signals(value: float = 1.0) -> dict[str, float]:
    """构造含 SIGNALS 全集、初值为 value 的信号字典。"""
    return {s: _clamp(value) for s in SIGNALS}


# ----------------------------------------------------------------------
# 基础消耗纯函数 (替代旧 BasalMetabolism 类, 为 M7 SoA 化铺路)
# ----------------------------------------------------------------------
def apply_metabolism(
    signals: dict[str, float],
    deltas: Mapping[str, float],
    personality_mul: Mapping[str, float] | None = None,
    activity_mul: Mapping[str, float] | None = None,
) -> None:
    """原位应用一 tick 基础消耗, clamp 0..1。deltas 来自 SimConfig.metabolism。

    personality_mul / activity_mul: {信号: 倍率}(缺省 1)。
    """
    pers = personality_mul or {}
    act = activity_mul or {}
    for s, d in deltas.items():
        if d == 0.0 or s not in signals:
            continue
        mul = float(pers.get(s, 1.0)) * float(act.get(s, 1.0))
        signals[s] = _clamp(signals[s] + d * mul)


# ----------------------------------------------------------------------
# Person —— 纯数据(瘦身后); 决策/交互方法 M2/M3 在 brain/world 侧
# ----------------------------------------------------------------------
@dataclass
class Person:
    identity: Identity = field(
        default_factory=lambda: Identity(person_id="anon", name="匿名"))
    signals: dict[str, float] = field(default_factory=full_signals)
    personality: dict[str, float] = field(default_factory=dict)   # {信号: 代谢倍率}
    activity_mul: dict[str, float] = field(default_factory=dict)  # {信号: 活动倍率}

    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    current_activity: str = "idle"
    hour_f: float = 8.0                        # 当日时刻(供清醒度)
    bladder_pending: float = 0.0               # 待转化排泄负荷
    location_id: str = ""                     # 所在 location(M3 世界侧登记)
    active_interaction_id: str | None = None  # 正在交互的实体 id(观测/仲裁)
    last_intent: "Intent | None" = None       # 最近一次决策(观测)

    def __post_init__(self) -> None:
        # 初始化必须含 SIGNALS 全集; 缺失补 1.0(充足)
        for s in SIGNALS:
            self.signals[s] = _clamp(self.signals.get(s, 1.0))

    # --- 便捷代理 -----------------------------------------------------
    @property
    def person_id(self) -> str:
        return self.identity.person_id

    @property
    def name(self) -> str:
        return self.identity.name

    def is_alive(self) -> bool:
        return self.signals.get("hp", 1.0) > 0.0

    def set_state(self, **kw: float) -> None:
        """clamp 到 [0,1] 后直接写 signals(唯一真源, 无 body 同步)。"""
        for k, v in kw.items():
            if k in SIGNALS:
                self.signals[k] = _clamp(float(v))

