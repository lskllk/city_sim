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
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from citysim.core.config import SIGNALS
from citysim.core.types import (
    Buy,
    Decision,
    Idle,
    Interact,
    MoveTo,
    PerceptionRecord,
    intent_kind,
    intent_target,
)
from citysim.npc import brain
from citysim.npc.memory import MemBase, MemItem
from citysim.npc.schedule import PlanEntry, Schedule

if TYPE_CHECKING:  # pragma: no cover
    from citysim.core.config import SimConfig
    from citysim.core.types import Intent, Percept


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


_GAME_EPOCH = date(2026, 1, 1)   # 游戏第 0 天对应的日期(用于年龄)


def _age_on(birthday: date, current: date) -> int:
    """整岁: 未过生日则减一。"""
    return (current.year - birthday.year
            - ((current.month, current.day) < (birthday.month, birthday.day)))


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


@dataclass
class _Goal:
    """正在执行的一个目标(计划的当前条目 / 一个 reflex)。

    phase: to_dest=还没到目标地(异地), doing=已在目标地/正在交互。
    """
    source: str                               # "plan" | "reflex"
    intent: "Intent"
    phase: str = "to_dest"


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
        current_activity: str = "idle",
        home: str = "",
        tell_bias: float = 1.0,
        money: float = 100.0,
    ) -> None:
        self._identity: Identity = identity or Identity(person_id="anon", name="匿名")
        self._signals: dict[str, float] = full_signals()
        self._personality: dict[str, float] = dict(personality or {})
        self._current_activity: str = current_activity
        self._home: str = home
        self._tell_bias: float = tell_bias
        self._money: float = money
        self._age: int | None = self._age_from_birthday(0)   # 每天 on_day 重算
        self._bladder_pending: float = 0.0
        self._last_intent: "Intent | None" = None
        self._last_percept: "PerceptionRecord | None" = None
        self._mem = MemBase()
        self._perceived_loc: str = ""   # 最近一次感知到自己在哪(自身认知, 不长期维护坐标)
        self._schedule = Schedule()     # 当天计划表(空 = 纯 reflex 模式)
        self._plan_goal: "_Goal | None" = None
        self._reflex_goal: "_Goal | None" = None
        self._failures: list[dict] = []  # 失败日志(0:00 交 LLM)
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
    def home(self) -> str:
        return self._home

    @property
    def money(self) -> float:
        return self._money

    @property
    def age(self) -> int | None:
        """整岁(每天 on_day 更新); 生日缺失时 None。"""
        return self._age

    @property
    def role(self) -> str:
        """角色码(如 "worker"/"student"), 由场景写入 Identity.traits。"""
        return str(self._identity.traits.get("role", ""))

    @property
    def gender(self) -> str:
        """性别码("male"/"female"/""), 来自场景人设。"""
        return self._identity.gender

    @property
    def perceived_loc(self) -> str:
        """最近一次感知到自己在哪(决策用; 真实位置归 World, 本层不长期维护坐标)。"""
        return self._perceived_loc

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
                  sleep: bool = False, busy: bool = False) -> bool:
        """身体每 tick 演化(世界广播心跳, Person 内部自己做, 上帝不改 signals)。

        顺序 = 代谢(睡眠冻结 energy / 忙碌冻结 fun) → hp(饿渴死/恢复) → 排泄(pending→膀胱)。
        返回是否仍存活(死则不再往下)。
        """
        amul: dict[str, float] = {}
        if sleep:
            amul["energy"] = 0.0
        if busy:
            amul["fun"] = 0.0
        apply_metabolism(self._signals, cfg.metabolism,
                         personality_mul=self._personality,
                         activity_mul=amul or None)
        # hp: 饥饿/口渴/精力任一为 0 → 降; 三者都满足 → 越大回升越快
        hunger = self._signals.get("hunger", 1.0)
        thirst = self._signals.get("thirst", 1.0)
        energy = self._signals.get("energy", 1.0)
        hp = self._signals.get("hp", 1.0)
        if hunger <= 0.0 or thirst <= 0.0 or energy <= 0.0:
            self._signals["hp"] = max(0.0, hp - cfg.hp_decay)
        else:
            rate = (hunger + thirst + energy) / 3.0
            self._signals["hp"] = min(1.0, hp + cfg.hp_regen * rate)
        if self._signals.get("hp", 1.0) <= 0.0:
            return False
        # 排泄: pending → 膀胱
        if self._bladder_pending > 0.0:
            step = min(cfg.bladder_convert, self._bladder_pending)
            self._bladder_pending -= step
            self._signals["bladder"] = _clamp(
                self._signals.get("bladder", 1.0) - step)
        return True

    # ------------------------------------------------------------------
    # 状态写 —— 位置 / 活动 / 膀胱 / 钱
    # ------------------------------------------------------------------
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
             stock: int | None = None, believe: float | None = None,
             carryable: bool | None = None,
             item_type: str | None = None) -> None:
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
        if carryable is not None:
            fields["carryable"] = bool(carryable)
        if item_type is not None:
            fields["item_type"] = str(item_type)
        fields.setdefault("remember", 1.0)
        fields.setdefault("last_seen", tick)
        self._mem.update(item_id, **fields)

    def memory_dicts(self) -> list:
        """观测: 记忆库只读快照(不对外暴露可写对象)。"""
        return self._mem.to_dicts()

    def forget_item(self, item_id: str) -> None:
        """删除一条记忆(物品已不存在/已交出/已消耗)。"""
        self._mem.delete(item_id)

    def plan_snapshot(self) -> list[dict]:
        """观测: 当天计划表只读快照(供前端时间线渲染)。"""
        return [{
            "id": e.entry_id, "at_tick": e.at_tick, "status": e.status,
            "intent": intent_kind(e.intent),
            "target": intent_target(e.intent) or "",
        } for e in self._schedule.entries()]

    def perceive(self, percept: "Percept", tick: int) -> None:
        """现场 → 记忆(写入)。非纯函数。感知即知道自己当前在哪。"""
        self._perceived_loc = percept.location_id
        brain.perceive_into(self._mem, percept, tick)
        self._last_percept = PerceptionRecord(
            tick=tick, npc_id=self.person_id,
            location_id=percept.location_id,
            observed_entity_ids=tuple(sorted(v.entity_id
                                             for v in percept.visible)))

    def set_plan(self, entries: "Sequence[PlanEntry]") -> None:
        """装配: 灌入当天计划(LLM 产物)。覆盖旧计划与执行指针。"""
        self._schedule = Schedule(entries)
        self._plan_goal = None

    def _reflex_intent(self, cfg: "SimConfig", now_tick: int) -> "Intent | None":
        """兜底决策(高危需求): 复用 brain.decide; Idle → None。"""
        intent = brain.decide(
            self._signals, self._personality, self._mem,
            self._perceived_loc, cfg, now_tick, self.person_id)
        return None if isinstance(intent, Idle) else intent

    def decide(self, cfg: "SimConfig", now_tick: int,
               can_preempt: bool = True) -> Decision:
        """决策仲裁: 致命 reflex > 计划 > idle。只读记忆+自身, 不看环境。

        can_preempt: 世界告知"当前交互能否被计划抢占"(不可打断的睡觉等);
                     reflex(致命)不受此限, 始终可抢占。
        """
        while True:
            # 1. reflex 执行中 → 继续
            if self._reflex_goal is not None:
                d = self._advance(self._reflex_goal)
                if d is not None:
                    return self._record(d)
                continue
            # 2. 启动 reflex(在途不打断: 先到站)
            traveling = (self._plan_goal is not None
                         and self._plan_goal.phase == "to_dest")
            if not traveling:
                r = self._reflex_intent(cfg, now_tick)
                if r is not None:
                    self._reflex_goal = _Goal("reflex", r)
                    continue
            # 3. 计划执行中 → 截止/推进
            if self._plan_goal is not None:
                dl = self._schedule.deadline()
                if dl is not None and now_tick >= dl and can_preempt:
                    self._schedule.drop()          # 硬中止当前条目
                    self._plan_goal = None
                    continue
                d = self._advance(self._plan_goal)
                if d is not None:
                    return self._record(d)
                continue
            # 4. 取下一计划条目
            e = self._schedule.current()
            if e is None or now_tick < e.at_tick:
                return self._record(Decision(Idle(), "idle"))
            self._schedule.commit()
            self._plan_goal = _Goal("plan", e.intent)
            continue

    def _advance(self, goal: "_Goal") -> "Decision | None":
        """推进一个 goal: 异地先 MoveTo; 到达/无需移动后返回实际 Intent。"""
        if goal.phase == "to_dest":
            dest = self._dest_for(goal.intent)
            if dest and self._perceived_loc != dest:
                return Decision(MoveTo(dest=dest), goal.source)
            if isinstance(goal.intent, MoveTo):
                self._finish_goal(goal)            # 纯移动: 到达即完成
                return None
            goal.phase = "doing"
        return Decision(goal.intent, goal.source)

    def _dest_for(self, intent: "Intent") -> str:
        if isinstance(intent, MoveTo):
            return intent.dest
        if isinstance(intent, Interact):
            row = self._mem.get(intent.target_id)
            return row.located if row is not None else ""
        if isinstance(intent, Buy):
            row = self._mem.get(intent.item_id)
            return row.located if row is not None else ""
        return ""

    def _finish_goal(self, goal: "_Goal") -> None:
        if goal.source == "plan":
            self._schedule.complete()
            if self._plan_goal is goal:
                self._plan_goal = None
        elif self._reflex_goal is goal:
            self._reflex_goal = None

    def _record(self, decision: Decision) -> Decision:
        self._last_intent = decision.intent
        return decision

    def on_interaction_done(self, entity_id: str, tick: int = 0) -> None:
        """窄协议: 世界告知某交互自然完成 → 结束对应 goal(计划推进下一条)。"""
        for g in (self._reflex_goal, self._plan_goal):
            if g is not None and intent_target(g.intent) == entity_id:
                self._finish_goal(g)
                return

    def failure_log(self) -> list[dict]:
        """观测: 失败日志只读快照(0:00 交 LLM 用)。"""
        return list(self._failures)

    def drain_failures(self) -> list[dict]:
        """取走并清空失败日志(夜间计划器消费)。"""
        out = self._failures
        self._failures = []
        return out

    def on_failure(self, target_id: str, why: str, now_tick: int,
                   retry_ticks: int | None = None) -> None:
        """窄协议: 交互失败 → 证伪/冷却记忆 + 记失败日志 + 跳过对应计划条。

        - 目标不存在 / 已空(stock=0) → 删掉该 item 记忆。
        - 已被占用 / 不可打断 / 购买失败等 → 冷却(cool_until=now+retry), 到时再看。
        - 失败日志留待 0:00 交 LLM(底层不推理)。
        """
        self._failures.append(
            {"tick": now_tick, "target": target_id, "why": why})
        row = self._mem.get(target_id)
        if row is not None:
            if "目标不存在" in why or why.startswith("已空"):
                self._mem.delete(target_id)
            else:
                until = now_tick + (retry_ticks
                                    if retry_ticks is not None else 120)
                self._mem.update(target_id, cool_until=until)
        # 该目标失败 → 清 reflex / skip 计划条
        if self._reflex_goal is not None \
                and intent_target(self._reflex_goal.intent) == target_id:
            self._reflex_goal = None
        elif self._plan_goal is not None \
                and intent_target(self._plan_goal.intent) == target_id:
            self._schedule.drop()
            self._plan_goal = None

    def process(self, percept: "Percept", cfg: "SimConfig",
                can_preempt: bool = True) -> Decision:
        """窄协议: 感知+决策一体(engine 只调这个)。

        内部 = perceive(现场→记忆, 记自身认知) + decide(仲裁, 当前 tick)。
        """
        self.perceive(percept, percept.tick)
        return self.decide(cfg, percept.tick, can_preempt)

    def on_day(self, cfg: "SimConfig", now_tick: int) -> int:
        """窄协议: 每游戏日 ① 重算年龄 ② 遗忘。返回遗忘条数。"""
        self._age = self._age_from_birthday(now_tick // max(1, cfg.ticks_per_day))
        return self.decay_memory(cfg, now_tick)

    def _age_from_birthday(self, day_index: int) -> int | None:
        try:
            b = self._identity.birthday_date()
        except (ValueError, AttributeError):
            return None
        return _age_on(b, _GAME_EPOCH + timedelta(days=day_index))

    def decay_memory(self, cfg: "SimConfig", now_tick: int) -> int:
        """遗忘(remember 衰减删行)。每游戏日调; 返回遗忘条数。"""
        return brain.forget(self._mem, now_tick, cfg.half_life_ticks)

    # ------------------------------------------------------------------
    # 观测快照(外部一份只读 dict, 避免拆着读字段)
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "id": self.person_id, "name": self.name,
            "home": self._home,
            "activity": self._current_activity,
            "money": round(self._money, 2),
            "age": self._age,
            "role": self.role,
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
