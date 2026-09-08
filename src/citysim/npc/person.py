"""Person —— NPC 大脑/状态的门面(字段私有, 仅方法对外)。

目标(架构决策): npc 目录对外只有 Person; brain/memory 是其内部实现。
- 字段全部 _private, 外界读写只走方法/property。
- 生理信号读写合成"一个方法 + 类型参数"(set_signal/add_signal), 不逐信号造 getter。
- 记忆 = MemBase(memory); 决策 = brain.decide(mem + 自身状态), 决策只看记忆+自身, 不看环境。

对外门面分四类:
  大脑   : perceive(现场→记忆) / decide(→Intent)
  状态写 : set_signal/add_signal / move_to / arrive / set_activity / pay / set_signals…
  状态读 : 少量稳定 @property + snapshot()(观测一份)
  装配   : Person(…) 构造 + set_signals/set_personality 等设初值

铁律: 本模块(npc 层)不得 import citysim.world。percept/cfg 作为方法参数由外部注入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Mapping

from citysim.core.config import SIGNALS
from citysim.core.types import PerceptionRecord, intent_kind
from citysim.npc import brain
from citysim.npc.memory import MemBase, MemItem

if TYPE_CHECKING:  # pragma: no cover
    from citysim.core.config import SimConfig
    from citysim.core.types import Intent, Percept


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


# ----------------------------------------------------------------------
# 身份(几乎不变)
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
# 视图/消耗纯函数(模块级, 供外部工具与测试用; 非 Person 私有)
# ----------------------------------------------------------------------
def signals_as_percent(signals: Mapping[str, float]) -> dict[str, int]:
    """显示视图: 0..1 float → 0..100 int(永不进入存储路径)。"""
    return {k: round(_clamp(float(v)) * 100) for k, v in signals.items()}


def full_signals(value: float = 1.0) -> dict[str, float]:
    """构造含 SIGNALS 全集、初值为 value 的信号字典。"""
    return {s: _clamp(value) for s in SIGNALS}


def apply_metabolism(
    signals: dict[str, float],
    deltas: Mapping[str, float],
    personality_mul: Mapping[str, float] | None = None,
    activity_mul: Mapping[str, float] | None = None,
) -> None:
    """原位应用一 tick 基础消耗, clamp 0..1。deltas 来自 SimConfig.metabolism。"""
    pers = personality_mul or {}
    act = activity_mul or {}
    for s, d in deltas.items():
        if d == 0.0 or s not in signals:
            continue
        mul = float(pers.get(s, 1.0)) * float(act.get(s, 1.0))
        signals[s] = _clamp(signals[s] + d * mul)


class Person:
    """NPC 大脑/状态门面。字段私有, 读写走方法。"""

    def __init__(
        self,
        identity: Identity | None = None,
        *,
        signals: Mapping[str, float] | None = None,
        personality: Mapping[str, float] | None = None,
        position: tuple[float, float] = (0.0, 0.0),
        current_activity: str = "idle",
        location_id: str = "",
        home: str = "",
        tell_bias: float = 1.0,
        money: float = 100.0,
    ) -> None:
        self._identity: Identity = identity or Identity(person_id="anon", name="匿名")
        self._signals: dict[str, float] = full_signals()
        self._personality: dict[str, float] = dict(personality or {})
        self._position: tuple[float, float] = tuple(position)
        self._current_activity: str = current_activity
        self._location_id: str = location_id
        self._home: str = home
        self._tell_bias: float = tell_bias
        self._money: float = money
        self._bladder_pending: float = 0.0
        self._last_intent: "Intent | None" = None
        self._last_percept: "PerceptionRecord | None" = None
        self._mem = MemBase()
        if signals:
            self.set_signals(**dict(signals))

    # ------------------------------------------------------------------
    # 只读 property(少量极稳, 供观测/世界读)
    # ------------------------------------------------------------------
    @property
    def person_id(self) -> str:
        return self._identity.person_id

    @property
    def name(self) -> str:
        return self._identity.name

    @property
    def identity(self) -> Identity:
        return self._identity

    @property
    def location_id(self) -> str:
        return self._location_id

    @property
    def home(self) -> str:
        return self._home

    @property
    def money(self) -> float:
        return self._money

    @property
    def position(self) -> tuple[float, float]:
        return self._position

    @property
    def current_activity(self) -> str:
        return self._current_activity

    @property
    def last_intent(self) -> "Intent | None":
        return self._last_intent

    @property
    def bladder_pending(self) -> float:
        return self._bladder_pending

    @property
    def signals(self) -> Mapping[str, float]:
        """只读视图(调用方要按名读信号用 signal() 更省)。"""
        return dict(self._signals)

    @property
    def personality(self) -> Mapping[str, float]:
        return dict(self._personality)

    def signal(self, name: str) -> float:
        return self._signals.get(name, 1.0)

    def is_alive(self) -> bool:
        return self._signals.get("hp", 1.0) > 0.0

    # ------------------------------------------------------------------
    # 状态写 —— 信号(一个方法 + 类型参数)
    # ------------------------------------------------------------------
    def set_signals(self, **kw: float) -> None:
        """装配/init: 覆盖若干信号(clamp 0..1)。"""
        for k, v in kw.items():
            if k in SIGNALS:
                self._signals[k] = _clamp(float(v))

    def set_signal(self, signal: str, value: float) -> None:
        """绝对设某信号(clamp)。"""
        if signal in SIGNALS:
            self._signals[signal] = _clamp(value)

    def add_signal(self, signal: str, delta: float) -> None:
        """相对累加某信号(clamp)。交互/效果/代谢都用它。"""
        if signal in SIGNALS:
            self._signals[signal] = _clamp(self._signals.get(signal, 1.0) + delta)

    def set_personality(self, mapping: Mapping[str, float]) -> None:
        self._personality = dict(mapping)

    def apply_metabolism(self, deltas: Mapping[str, float],
                         activity_mul: Mapping[str, float] | None = None) -> None:
        """一 tick 基础消耗(内部走模块 apply_metabolism + 自身 personality)。"""
        apply_metabolism(self._signals, deltas,
                         personality_mul=self._personality,
                         activity_mul=activity_mul)

    def heartbeat(self, now_tick: int, cfg: "SimConfig", *,
                  sleep: bool = False, busy: bool = False) -> None:
        """身体每 tick 演化(世界广播心跳, Person 内部自己做, 上帝不改 signals):

        顺序 = 代谢(睡眠冻结 energy / 忙碌冻结 fun) → hp(饿渴死/恢复) → 排泄(pending→膀胱)。
        若 hp 归零则不再往下(死亡由世界在心跳后按 is_alive 回收)。
        """
        amul: dict[str, float] = {}
        if sleep:
            amul["energy"] = 0.0
        if busy:
            amul["fun"] = 0.0
        apply_metabolism(self._signals, cfg.metabolism,
                         personality_mul=self._personality,
                         activity_mul=amul or None)
        # hp: 饥饿/饥渴任一为 0 → 降; 都满足 → 越大回升越快
        hunger = self._signals.get("hunger", 1.0)
        thirst = self._signals.get("thirst", 1.0)
        hp = self._signals.get("hp", 1.0)
        if hunger <= 0.0 or thirst <= 0.0:
            self._signals["hp"] = max(0.0, hp - cfg.hp_decay)
        else:
            rate = (hunger + thirst) / 2.0
            self._signals["hp"] = min(1.0, hp + cfg.hp_regen * rate)
        if self._signals.get("hp", 1.0) <= 0.0:
            return
        # 排泄: pending → 膀胱
        if self._bladder_pending > 0.0:
            step = min(cfg.bladder_convert, self._bladder_pending)
            self._bladder_pending -= step
            self._signals["bladder"] = _clamp(
                self._signals.get("bladder", 1.0) - step)

    # ------------------------------------------------------------------
    # 状态写 —— 位置 / 活动 / 膀胱 / 钱
    # ------------------------------------------------------------------
    def move_to(self, position: tuple[float, float]) -> None:
        self._position = tuple(position)

    def arrive(self, location_id: str,
               position: tuple[float, float] | None = None) -> None:
        """到达: 落 region(可带精确落点)。"""
        self._location_id = location_id
        if position is not None:
            self._position = tuple(position)

    def set_activity(self, activity: str) -> None:
        self._current_activity = activity

    def set_bladder_pending(self, v: float) -> None:
        self._bladder_pending = max(0.0, float(v))

    def add_bladder_pending(self, delta: float) -> None:
        self._bladder_pending = max(0.0, self._bladder_pending + float(delta))

    def pay(self, amount: float) -> bool:
        """扣钱(只减不增); 钱不够返回 False。"""
        if self._money < amount:
            return False
        self._money -= amount
        return True

    def set_money(self, money: float) -> None:
        self._money = max(0.0, float(money))

    def set_home(self, home: str) -> None:
        self._home = home

    def set_tell_bias(self, v: float) -> None:
        self._tell_bias = v

    # ------------------------------------------------------------------
    # 大脑 —— 感知写入记忆 + 决策(只看记忆+自身, 不看环境)
    # ------------------------------------------------------------------
    def note(self, item_id: str, tick: int = 0, *, located: str | None = None,
             owner: str | None = None, afford: str | None = None,
             value: float | None = None, price: float | None = None,
             stock: int | None = None, believe: float | None = None) -> None:
        """往记忆 upsert 一行(增/改; 部分字段可省略)。供成交/事件等记记忆用。"""
        row = self._mem.get(item_id)
        if row is None:
            row = MemItem(item_id=item_id)
            self._mem.set(row)
        fields: dict = {}
        if located is not None:
            fields["located"] = located
        if owner is not None:
            fields["owner"] = owner
        if afford is not None:
            fields["afford"] = afford
        if value is not None:
            fields["value"] = float(value)
        if price is not None:
            fields["price"] = float(price)
        if stock is not None:
            fields["stock"] = int(stock)
        if believe is not None:
            fields["believe"] = float(believe)
        fields.setdefault("remember", 1.0)
        fields.setdefault("last_seen", tick)
        self._mem.update(item_id, **fields)

    def memory_dicts(self) -> list:
        """观测: 记忆库只读快照(不对外暴露可写对象)。"""
        return self._mem.to_dicts()

    def perceive(self, percept: "Percept", tick: int) -> None:
        """现场 → 记忆(写入)。非纯函数。"""
        brain.perceive_into(self._mem, percept, tick)
        self._last_percept = PerceptionRecord(
            tick=tick, npc_id=self.person_id,
            location_id=percept.location_id, position=self._position,
            observed_entity_ids=tuple(sorted(v.entity_id
                                             for v in percept.visible)))

    def decide(self, cfg: "SimConfig") -> "Intent":
        """决策: 只读 记忆+自身状态 → Intent。铁律: 不看环境。"""
        intent = brain.decide(
            self._signals, self._personality, self._mem,
            self._location_id, cfg, self._money)
        self._last_intent = intent
        return intent

    def decay_memory(self, cfg: "SimConfig", now_tick: int) -> int:
        """遗忘(remember 衰减删行)。每游戏日由主循环调; 返回遗忘条数。"""
        return brain.forget(self._mem, now_tick, cfg.half_life_ticks)

    # ------------------------------------------------------------------
    # 观测快照(外部一份只读 dict, 避免拆着读字段)
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "id": self.person_id, "name": self.name,
            "loc": self._location_id, "home": self._home,
            "position": list(self._position),
            "activity": self._current_activity,
            "money": round(self._money, 2),
            "signals": {k: round(v, 4) for k, v in self._signals.items()},
            "personality": dict(self._personality),
            "bladder_pending": round(self._bladder_pending, 4),
            "tell_bias": self._tell_bias,
            "last_intent": None if self._last_intent is None
            else intent_kind(self._last_intent),
            "mem": len(self._mem),
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"Person({self.person_id})"
