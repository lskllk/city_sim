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

import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from citysim.core.config import SIGNALS
from citysim.core.ports import Ack, Deny, Grant
from citysim.core.types import (
    Buy,
    Decision,
    Idle,
    Interact,
    MoveTo,
    Wander,
    intent_kind,
    intent_target,
)
from citysim.npc import brain, semantic
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
    """正在执行的【唯一】目标。

    —— 2026-09-14 删双轨 ——
    以前是 _reflex_goal / _plan_goal 两条轨 + 固定优先级抢占; 现在只有一个。
    source 只用来区分“谁在维持它”:
      "need" —— 需求(utility)驱动的, 做完再决策
      "plan" —— 日程/承诺驱动的, 到点会被下一条硬中止, 也尊重 can_preempt

    phase: to_dest=还没到目标地(异地), doing=已在目标地/正在交互。
    """
    source: str                               # "need" | "plan"
    intent: "Intent"
    phase: str = "to_dest"


@dataclass
class _ActiveGrant:
    """体内正在消化的一份 Grant(WP-08)。

    `total` = max(1, duration_ticks); 每 tick 加 `value/total`, `remaining` 递减到 0
    就算吃完 —— 这就是“吃东西→饥饿下来”的循环, 现在归 NPC 自己。
    """
    grant: "Grant"
    total: int
    remaining: int


# ----------------------------------------------------------------------
# 视图/消耗纯函数(模块级, 供外部工具与测试用; 非 Person 私有)
# ----------------------------------------------------------------------
def signals_as_percent(signals: Mapping[str, float]) -> dict[str, int]:
    """显示视图: 0..1 float → 0..100 int(永不进入存储路径)。供 tools 用。"""
    return {k: round(_clamp(float(v)) * 100) for k, v in signals.items()}


def full_signals(value: float = 1.0) -> dict[str, float]:
    """构造含 SIGNALS 全集、初值为 value 的信号字典。"""
    return {s: _clamp(value) for s in SIGNALS}


def apply_metabolism(
    signals: dict[str, float],
    deltas: Mapping[str, float],
    personality_mul: Mapping[str, float] | None = None,
    activity_mul: Mapping[str, float] | None = None,
    rhythm_mul: Mapping[str, float] | None = None,
) -> None:
    """原位应用一 tick 基础消耗, clamp 0..1。deltas 来自 SimConfig.metabolism。

    总系数 = personality × activity × rhythm
      · personality —— 个体差异(吃得快/累得快)
      · activity    —— 在做什么(睡觉冻结 energy; 干活掉得快)
      · rhythm      —— 昼夜倍率(夜里 energy 掉得快 → 困 → 去睡)
    """
    pers = personality_mul or {}
    act = activity_mul or {}
    rhy = rhythm_mul or {}
    for s, d in deltas.items():
        if d == 0.0 or s not in signals:
            continue
        mul = (float(pers.get(s, 1.0)) * float(act.get(s, 1.0))
               * float(rhy.get(s, 1.0)))
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
        # 位移成本矩阵("a|b" -> tick): 由装配层从场景/路网注入。
        # 纯数据, 不 import world —— 决定“顺路值多少”的就是它。
        self._travel_costs: dict[str, int] = {}
        # “地点热闹度”表 {loc: draw}, 装配注入; 闲逛选址用(纯数据, 不查 world)。
        self._places: list[str] = []   # 可闲逛的公共建筑 id 列表(不含住所; 装配注入)
        self._money: float = money
        self._age: int | None = self._age_from_birthday(0)   # 每天 on_day 重算
        self._bladder_pending: float = 0.0
        self._starve_ticks: int = 0    # 连续 (hunger==0 或 energy==0) 的 tick 数(宽限用)
        self._last_intent: "Intent | None" = None
        # 对【店铺】的好感度(0..2, 中性 1.0)。不记的店 = 中性。
        # 它是慢变量: 交易顺利慢慢涨、被怠慢/买到坏货掉得多、随时间回到中性。
        self._favor: dict[str, float] = {}
        self._work: dict = {}          # {company, shop, station} 被雇佣时绑定
        self._role: str = ""           # 雇佣后写上的角色(现在只做打工人 "worker")
        self._worked_ticks: int = 0    # 本期在岗 tick(工资按在岗时间算)
        self._mem = MemBase()
        self._perceived_loc: str = ""   # 最近一次感知到自己在哪(自身认知, 不长期维护坐标)
        self._schedule = Schedule()     # 当天计划表(空 = 纯需求驱动)
        self._goal: "_Goal | None" = None   # 唯一在执行的标的
        self._intake: list[_ActiveGrant] = []   # 体内正在消化(WP-08)
        self._finished: list[str] = []          # 本 tick 消化完的 handle(取走即清)
        self._bubble: tuple[str, int, str] | None = None   # (文字, 到期的 tick, 类型)
        # —— 语义层(M-S1): 值得说的草稿 + 话题冷却 ——
        self._say_queue: list = []          # [SemanticEvent](未措辞的结构化真值)
        self._said_at: dict[str, int] = {}  # topic -> 上次说的 tick(别复读自己)
        self._name_of = None                # 注入: npc_id -> 名字(渲染“王哥说…”用)
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
    def gender(self) -> str:
        """性别码("male"/"female"/""), 来自场景人设。"""
        return self._identity.gender


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


    def heartbeat(self, now_tick: int, cfg: "SimConfig", *,
                  sleep: bool | None = None, busy: bool = False) -> bool:
        """身体每 tick 演化(世界广播心跳, Person 内部自己做, 上帝不改 signals)。

        顺序 = 代谢(睡眠冻结 energy; busy 暂不对任何信号生效) → hp(饿死/恢复) → 排泄(pending→膀胱) → 消化。
        返回是否仍存活(死则不再往下)。

        sleep=None(默认) 时【自己判】: 体内 intake 里有没有 sleepable 的东西
        (WP-11: 不再由 world 反向告诉 NPC“你在睡”)。
        """
        if sleep is None:
            sleep = any("sleepable" in ag.grant.tags for ag in self._intake)
        # 活动系数: 睡着冻结 energy; 在做事(交互/赶路)掉得更快; 空闲就是基准
        amul: dict[str, float] = {}
        if sleep:
            amul["energy"] = 0.0
        elif busy:
            amul["energy"] = cfg.busy_energy_mul
        # 昼夜系数: 夜里 energy 掉得快 → 困 → 去睡(不是“到点睡觉”)
        hour_f = (now_tick % max(1, cfg.ticks_per_day)) / 60.0
        rmul: dict[str, float] = {"energy": cfg.rhythm_at(hour_f)}
        apply_metabolism(self._signals, cfg.metabolism,
                         personality_mul=self._personality,
                         activity_mul=amul or None,
                         rhythm_mul=rmul)
        # hp: 只有【饥饿】参与 —— 连续 hunger==0 满宽限(默认 3 天)才开始掉血;
        #   中途吃了饭(hunger>0)就清零, 下次归零重新计数。渐降, 不是一下掉光。
        #   ★ 睡眠/精力【不参与 hp】; 旧三态(衰减/回升/中间带)已删。
        hunger = self._signals.get("hunger", 1.0)
        self._starve_ticks = self._starve_ticks + 1 if hunger <= 0.0 else 0
        if self._starve_ticks >= cfg.hp_starve_grace_ticks:
            self._signals["hp"] = max(
                0.0, self._signals.get("hp", 1.0) - cfg.hp_decay)
        if self._signals.get("hp", 1.0) <= 0.0:
            return False
        # 排泄: pending → 膀胱
        if self._bladder_pending > 0.0:
            step = min(cfg.bladder_convert, self._bladder_pending)
            self._bladder_pending -= step
            self._signals["bladder"] = _clamp(
                self._signals.get("bladder", 1.0) - step)
        # fun(娱乐): 上班涨 / 空闲掉; 吃/睡/厕所/赶路/闲逛 → 不变。
        #   判据全来自 NPC 自己的 intake/目标 —— 不新增 world 注入。
        #   (闲逛的 fun 由它自己的 Grant 逐 tick 加, 这里不再加, 避免双算。)
        ftags = {t for ag in self._intake for t in ag.grant.tags}
        if "work" in ftags:
            self._signals["fun"] = _clamp(
                self._signals.get("fun", 1.0) + cfg.fun_work_gain)
        elif "roam" in ftags:
            pass                    # 闲逛的 fun 由 roam Grant 自己涨
        elif not self._intake and not busy:
            # 真·空闲(没事做也不在赶路) → 掉; 吃饭/睡觉/赶路 → 不变
            self._signals["fun"] = _clamp(
                self._signals.get("fun", 1.0) - cfg.fun_idle_drop)
        # 消化(WP-08): 体内 intake 逐 tick 均摊加信号。
        # 放在代谢/排泄【之后】—— 与旧 InteractionSystem.step 的相对顺序一致。
        self._digest(now_tick, cfg)
        return True

    def _digest(self, now_tick: int = 0, cfg: "SimConfig | None" = None) -> None:
        """推进体内 intake: 每 tick 加 value/total。

        结束(通用): ① 目标信号已满(>=1.0) → **满了优先结束**;
                   ② 到 duration_ticks → 到点结束;
                   ③ 工作工位: 一旦【不在班】 → 立刻下班(不再挂着占着台)。
        都走【自然完成】(world 收尾)。
        """
        for ag in list(self._intake):
            g = ag.grant
            tags = tuple(getattr(g, "tags", ()) or ())
            off_duty = ("work" in tags and bool(self._work)
                        and cfg is not None
                        and not self._on_shift(now_tick, cfg))
            if g.signal:
                self.add_signal(g.signal, g.value / ag.total)
            ag.remaining -= 1
            saturated = bool(g.signal) and self.signal(g.signal) >= 1.0
            if ag.remaining <= 0 or saturated or off_duty:
                self._intake.remove(ag)
                self._finished.append(g.handle)

    def _apply_neutral(self, effects) -> None:
        """应用【结构化】NPC 侧效果(无 op 名; 见 world/effects.compile_effects)。

        world 那边把 add_signal/set_signal/add_pending 编译成 {signal, add|set}
        / {field, amount} —— 所以 npc/ 不认识 op 字符串。
        """
        for eff in effects:
            if "signal" in eff:
                s = str(eff["signal"])
                if "set" in eff:
                    self.set_signal(s, float(eff["set"]))
                else:
                    self.add_signal(s, float(eff.get("add", 0.0)))
            elif eff.get("field") == "bladder_pending":
                self.add_bladder_pending(float(eff.get("amount", 0.0)))

    def intake_add(self, grant: "Grant") -> None:
        """把 world 签发的 Grant 收进体内开始消化(+ 应用 on_start 结构化字段)。"""
        if any(ag.grant.handle == grant.handle for ag in self._intake):
            return                                 # 同一份已持有(handle 唯一)
        total = max(1, int(grant.duration_ticks))
        self._apply_neutral(grant.pending)     # on_start(如 bladder_pending)
        self._intake.append(_ActiveGrant(grant=grant, total=total, remaining=total))

    def take_finished(self) -> list[str]:
        """取走本 tick 消化完的 handle(供 world 做收尾: 扣货/回收)。取走即清。"""
        out = self._finished
        self._finished = []
        return out

    def intake_progress(self, entity_id: str = "") -> tuple[int, int]:
        """当前在消化那份的 (剩余, 总时长); 没在消化/不匹配 → (0, 0)。

        WP-08 之后进度归 NPC(体内 _intake); 快照要显示进度条就取这里,
        不要再去看 world 的 ActiveInteraction(那边已不存进度)。
        """
        for ag in self._intake:
            if not entity_id or ag.grant.entity_id == entity_id:
                return ag.remaining, ag.total
        return 0, 0

    # ------------------------------------------------------------------
    # 状态写 —— 位置 / 活动 / 膀胱 / 钱
    # ------------------------------------------------------------------
    def set_activity(self, activity: str) -> None:
        self._current_activity = activity

    def add_bladder_pending(self, delta: float) -> None:
        self._bladder_pending = max(0.0, self._bladder_pending + float(delta))

    def pay(self, amount: float) -> bool:
        """扣钱(只减不增); 钱不够返回 False。"""
        if self._money < amount:
            return False
        self._money -= amount
        return True

    def earn(self, amount: float) -> None:
        """进账(工资/卖货)。与 pay 对称 —— 只动自己的钱, 不做别的。"""
        if amount > 0:
            self._money += float(amount)

    # --- 语义层(M-S1): 攒“值得说的事”, 按优先级取 ---------------------
    def set_name_lookup(self, fn) -> None:
        """装配: 注入 npc_id -> 名字(世界侧提供, 本层只存不查)。"""
        self._name_of = fn

    def said_at(self, topic: str, default: int = -(10 ** 9)) -> int:
        """这个话题上次是什么时候说的(默认很久以前)。"""
        return self._said_at.get(topic, default)

    def mark_said(self, topic: str, now_tick: int) -> None:
        self._said_at[topic] = int(now_tick)

    def _push_speech(self, ev) -> None:
        self._say_queue.append(ev)
        if len(self._say_queue) > 12:        # 只留最近的一小把
            self._say_queue = self._say_queue[-12:]

    def pending_speech(self, now_tick: int, cooldown: int = 600):
        """取一件【值得说】的事(优先级最高 + 不在话题冷却里); 没有则 None。

        优先级(§8): DOUBT > SURPRISE > INTENT > STATE。说完记冷却 ——
        NPC 不会短时间复读自己(上下文决定论 C 的 said_recently)。
        """
        best, best_rank, best_i = None, -1, -1
        for i, ev in enumerate(self._say_queue):
            if now_tick - self._said_at.get(ev.topic, -(10 ** 9)) < cooldown:
                continue                       # 这个话题刚说过
            r = semantic.PRIORITY.get(ev.act, 0)
            if r > best_rank:
                best, best_rank, best_i = ev, r, i
        if best is None:
            # 剩下的都说过/过时了 → 丢掉太旧的, 别让它堆着
            self._say_queue = [e for e in self._say_queue
                               if now_tick - e.tick < cooldown]
            return None
        self._say_queue.pop(best_i)
        self._said_at[best.topic] = now_tick
        return best

    def _spot_surprises(self, percept, tick: int) -> list:
        """【预期 vs 观察】—— 语义层最值钱的两个 act 就长在这儿。

        · 现场与记忆不符 → SURPRISE(单纯意外)
        · 不符的那条记忆本来是【别人说的】→ DOUBT(信念被推翻; 优先级更高)
        第一次见到的东西没有“预期”, 谈不上落差, 不说。
        """
        out = []
        for v in percept.visible:
            row = self._mem.get(v.entity_id)
            if row is None:
                continue
            fact = {"item_id": v.entity_id, "located": v.location_id,
                    "afford": row.afford, "value": row.value,
                    "price": float(v.price), "item_type": v.item_type,
                    "stock": int(v.stock),
                    # 这是【刚亲眼看到】的事实 → 我自己信满(不是旧记忆里那个分)
                    "believe": 1.0, "source": ""}
            if abs(float(v.price) - float(row.price)) > 0.005:
                was = semantic.money_word(row.price)
                now = semantic.money_word(v.price)
                who = row.source
                if who and who != self.person_id and not who.startswith("ad:"):
                    name = ""
                    if self._name_of is not None:
                        name = str(self._name_of(who) or "")
                    if name:
                        out.append(semantic.doubt(
                            tick, self.person_id, v.entity_id, v.name, name,
                            was, now, fact=fact, source=who))
                        continue
                out.append(semantic.surprise(
                    tick, self.person_id, v.entity_id, v.name,
                    was, now, fact=fact))
            elif int(row.stock) > 0 and int(v.stock) == 0:
                out.append(semantic.surprise(
                    tick, self.person_id, v.entity_id, v.name,
                    "还有货", "卖光了", fact=dict(fact, stock=0)))
        return out

    def _queue_intent_speech(self, tick: int, intent) -> None:
        """打算干什么 → 一条 INTENT(只在真的开始新动作时排一次)。"""
        tid = intent_target(intent)
        row = self._mem.get(tid) if tid else None
        if row is None:
            return
        words = semantic.GOAL_WORDS.get(row.afford)
        if words is None:
            return
        # 措辞必须跟【真实驱动】一致: 不饿却去补货时说“家里快没吃的了”,
        # 不许说“有点饿”。driver 由 brain 标注(见 _gather_candidates)。
        goal = words[0]
        trace = getattr(intent, "trace", None)
        feats = getattr(trace, "features", None) or {}
        why = words[2] if feats.get("driver") == "future" else words[1]
        self._push_speech(semantic.intent(
            tick, self.person_id, goal, why,
            topic=f"intent.{row.afford}"))

    # --- 气泡(显示态) --------------------------------------------------
    def set_bubble(self, text: str, until_tick: int, kind: str) -> None:
        """头顶冒一句话(瞬时事件, 不是“当前在做什么”的状态)。

        渲染层只负责画和到点消失; 台词由后端从真实内部状态长出(铁律)。
        """
        self._bubble = (str(text), int(until_tick), str(kind))

    @property
    def bubble(self) -> tuple[str, int, str] | None:
        return self._bubble


    def set_travel_costs(self, costs: dict[str, int]) -> None:
        """装配: 注入位移成本矩阵(engine/场景侧提供, 这里只存不用)。"""
        self._travel_costs = dict(costs or {})

    def set_places(self, places) -> None:
        """装配: 注入【可闲逛的公共建筑】id 列表(不含住所; 纯数据, 不查 world)。"""
        self._places = [str(x) for x in (places or ())]

    @property
    def tell_bias(self) -> float:
        """爱不爱说话(乘在传播概率上): <1 寡言, >1 八卦。"""
        return self._tell_bias


    # ------------------------------------------------------------------
    # 大脑 —— 感知写入记忆 + 决策(只看记忆+自身, 不看环境)
    # ------------------------------------------------------------------
    def note(self, item_id: str, tick: int = 0, *, located: str | None = None,
             owner: str | None = None, afford: str | None = None,
             value: float | None = None, price: float | None = None,
             stock: int | None = None, believe: float | None = None,
             item_type: str | None = None,
             source: str | None = None,
             shelf_life_ticks: int | None = None,
             expires_tick: int | None = None,
             tags: Sequence[str] | None = None) -> None:
        """往记忆 upsert 一行(增/改; 部分字段可省略)。供成交/事件/传闻用。

        source: "" = 亲眼所见; npc_id = 他说的; "ad:<bid>" = 广告招牌。
        """
        row = self._mem.get(item_id)
        if row is None:
            # ★ 新建的行没显式传 believe → 按【亲眼所见】算 1.0。
            # MemItem 的字段默认值是 0.0(空记忆), 而 believe=0 会让这一行
            # 在打分里 base=…×believe=0 → 永远不可能被选中:
            # “买回来的东西记不住/不信”就是这么来的(实测过: 买了简餐,
            # 家里那条 believe 是 0.00, 于是永远不回去吃)。
            row = MemItem(item_id=item_id, believe=1.0, remember=1.0)
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
        if item_type is not None:
            fields["item_type"] = str(item_type)
        if source is not None:
            fields["source"] = str(source)
        if tags is not None:
            fields["tags"] = tuple(sorted(str(x) for x in tags))
        if shelf_life_ticks is not None:
            fields["shelf_life_ticks"] = int(shelf_life_ticks)
        if expires_tick is not None:
            fields["expires_tick"] = int(expires_tick)
        fields.setdefault("remember", 1.0)
        fields.setdefault("last_seen", tick)
        self._mem.update(item_id, **fields)

    # --- 好感度(对店铺的慢变量) ----------------------------------------
    def favor_of(self, shop_id: str, neutral: float = 1.0) -> float:
        """对某家店的好感度; 没记过 = 中性。"""
        if not shop_id:
            return neutral
        return float(self._favor.get(shop_id, neutral))


    def bump_favor(self, shop_id: str, delta: float, cfg) -> float:
        """好感度加减(自动夹在 min..max)。返回新值。"""
        if not shop_id or delta == 0.0:
            return self.favor_of(shop_id, cfg.favor_neutral)
        v = self.favor_of(shop_id, cfg.favor_neutral) + float(delta)
        v = max(cfg.favor_min, min(cfg.favor_max, v))
        self._favor[shop_id] = v
        return v


    def set_work(self, company_id: str, shop_id: str, station_id: str,
                 open_minute: int = 0, close_minute: int = 1440,
                 wage_per_hour: float = 0.0) -> None:
        """被雇佣: 绑定公司/店/工位(销售前台) + 班次时间 + 时薪。

        班次时间/时薪存在这里(而不是每次去问世界), 是因为决策层要自己算
        “离岗要亏多少钱” —— 决策不查世界(铁律)。
        """
        self._work = {"company": company_id, "shop": shop_id,
                      "station": station_id,
                      "open": int(open_minute), "close": int(close_minute),
                      "wage": float(wage_per_hour)}

    @property
    def work(self) -> dict:
        return dict(self._work)

    @property
    def role(self) -> str:
        """角色: 雇佣写上的优先, 否则看人设里的 traits.role。"""
        return self._role or str(self.identity.traits.get("role", ""))

    def set_role(self, role: str) -> None:
        self._role = str(role)

    def clear_work(self) -> None:
        self._work = {}

    def worked(self, ticks: int = 1) -> None:
        """在岗计时(工资按在岗时间算)。"""
        self._worked_ticks += max(0, int(ticks))


    def reset_worked(self) -> int:
        """取走并清零"这一期在岗的 tick 数"(发工资时用)。"""
        n = self._worked_ticks
        self._worked_ticks = 0
        return n


    def remembers(self, item_id: str) -> bool:
        """我记忆里有没有这一条(供“对方已知就不说”这类判断用)。"""
        return self._mem.get(item_id) is not None

    def memory_dicts(self) -> list:
        """观测: 记忆库只读快照(不对外暴露可写对象)。"""
        return self._mem.to_dicts()

    def forget_item(self, item_id: str) -> None:
        """删除一条记忆(物品已不存在/已交出/已消耗)。"""
        self._mem.delete(item_id)

    def plan_snapshot(self, now_tick: int = 0) -> list[dict]:
        """观测: 计划表只读快照(供前端时间线渲染)。

        含两部分:
          · 真实日程表(_schedule, 计划器/脚本写的);
          · 【上班】—— 从 self._work 派生, 不入计划表。
            这样 0:00 计划器 set_plan([]) 冲不掉它(以前就被冲掉 → 时间线空)。
        """
        out = [{
            "id": e.entry_id, "at_tick": e.at_tick, "status": e.status,
            "intent": intent_kind(e.intent),
            "target": intent_target(e.intent) or "",
        } for e in self._schedule.entries()]
        if self._work and self._work.get("station"):
            minute = int(now_tick) % 1440
            day_start = int(now_tick) - minute
            open_m = int(self._work.get("open", 0))
            close_m = int(self._work.get("close", 1440))
            on = open_m <= minute < close_m
            at = day_start + open_m
            out.append({"id": "work_go", "at_tick": at,
                        "status": "done" if on else "pending",
                        "intent": "move_to",
                        "target": str(self._work.get("shop", ""))})
            out.append({"id": "work_stand", "at_tick": at,
                        "status": "active" if on else "pending",
                        "intent": "interact",
                        "target": str(self._work.get("station", ""))})
            # 下班(以前只画了上班, 没有下班节点)
            out.append({"id": "work_off", "at_tick": day_start + close_m,
                        "status": "done" if minute >= close_m else "pending",
                        "intent": "move_to", "target": self._home or ""})
        return out

    def perceive(self, percept: "Percept", tick: int) -> None:
        """现场 → 记忆(写入)。非纯函数。感知即知道自己当前在哪。

        注意顺序: **先拿“预期 vs 观察”**, 再写记忆 —— 写完就没落差了。
        """
        self._perceived_loc = percept.location_id
        for ev in self._spot_surprises(percept, tick):
            self._push_speech(ev)
        self._absorb_events(percept.events, tick)
        brain.perceive_into(self._mem, percept, tick)

    def _absorb_events(self, events, tick: int) -> None:
        """把 world 发来的事件吸收成自己的状态(WP-13: world 不再反写 NPC)。

        目前: `bought` → 把送货进家的容器写进记忆。afford/value 随事件带回,
        所以 NPC 不需要当期看到家里。
        """
        for ev in events:
            if ev.kind != "bought":
                continue
            p = ev.payload
            cid = str(p.get("container", ""))
            if not cid:
                continue
            self.note(
                cid, tick=int(ev.tick),
                located=str(p.get("home", "")), owner=self.person_id,
                stock=int(p.get("stock", 1)),
                afford=str(p.get("afford", "")),
                value=float(p.get("value", 0.0)),
                believe=1.0,                    # 自己买回来的 = 亲眼所见
                item_type=str(p.get("item_type", "")),
                tags=tuple(p.get("tags", ()) or ()), source="",
                shelf_life_ticks=int(p.get("shelf_life_ticks", 0)),
                expires_tick=int(p.get("expires_tick", 0)))

    def set_plan(self, entries: "Sequence[PlanEntry]") -> None:
        """装配: 灌入当天计划(LLM 产物)。覆盖旧计划与执行指针。"""
        self._schedule = Schedule(entries)
        self._goal = None


    def _wander_dest(self, cfg: "SimConfig", now_tick: int) -> str:
        """从【所有非住所的公共建筑】里随机选一个作为闲逛目的地。

        纯数据(不查 world): 只用注入的 `_places`(id 列表)。
        排除“家”和当前所在地(要真的走过去 → 路上算赶路);
        用 person_id + 时间窗的稳定哈希抽一个 → 同人同窗口可复现。
        """
        here = self._perceived_loc
        cands = [loc for loc in self._places
                 if loc and loc != self._home and loc != here]
        if not cands:                                  # 只剩家了 → 就选家外的任意一个
            cands = [loc for loc in self._places if loc and loc != self._home]
        if not cands:
            return ""
        bucket = now_tick // max(1, int(cfg.fun_roam_ticks))
        idx = zlib.crc32(f"{self.person_id}|{bucket}".encode("utf-8")) % len(cands)
        return cands[idx]

    def _idle_or_wander(self, cfg: "SimConfig", now_tick: int) -> Decision:
        """真没事干了: fun 低 → 闲逛(最低优先级); 否则 idle。

        闲逛 = 一个 **committed goal** (source="fun"):
          · 先挑一个【随机建筑】走过去(路上 = 赶路 move);
          · 到了才开逛(闲逛 wander); 逛满 roam_ticks 收工。
        因为占着 _goal, 期间决策冷却(不重算需求)。
        """
        if self._signals.get("fun", 1.0) < cfg.fun_seek_below:
            dest = self._wander_dest(cfg, now_tick)
            if dest:
                self._goal = _Goal("fun", Wander(dest))
                return self._record(Decision(Wander(dest), "fun"))
        return self._record(Decision(Idle(), "idle"))

    def _intent_scored(self, cfg: "SimConfig",
                       now_tick: int) -> "tuple[Intent | None, float]":
        """当前最想做的事 + 它的得分(Idle → (None, 0.0))。

        只在【空闲】时调 —— 手上有事就做完再决策, 不重算。
        """
        # 在班 → 把“工位 + 离岗代价(旷工扣日薪)”交给打分器。
        # 离岗 = 离开公司地点; 手边的货(located==shop)不算。
        workplace, leave_cost = "", 0.0
        if self._work and self._on_shift(now_tick, cfg):
            workplace = str(self._work.get("shop", ""))
            hours = max(0.0, float(self._work.get("close", 0))
                        - float(self._work.get("open", 0))) / 60.0
            leave_cost = hours * float(self._work.get("wage", 0.0))
        intent, eff = brain.decide_scored(
            self._signals, self._personality, self._mem,
            self._perceived_loc, cfg, now_tick, self.person_id,
            self._travel_costs or None, self._money, self._home,
            workplace=workplace, leave_cost=leave_cost)
        return (None if isinstance(intent, Idle) else intent), eff

    def decide(self, cfg: "SimConfig", now_tick: int,
               can_preempt: bool = True) -> Decision:
        """单轨决策: **需求(utility) > 日程(plan) > idle**。只读记忆+自身。

        开头先做一次跨天处理: daily 计划顺延到今天(上班写一次就不必再动)。

        节奏: **手上有事就做完再决策** —— 只有空闲时才每 tick 重算。
        唯一能打断当前动作的是 **PLAN(上班)**; 不再有迟滞/reflex 抢占。

        can_preempt: 世界告知“当前交互能不能被打断”(睡觉等)。
                     只影响【计划条目】的到期推进, 不影响需求目标。
        """
        self._schedule.roll_day(now_tick, cfg.ticks_per_day)
        # ★ 上班只在【上班开始那一刻】硬抢(不管在做什么 → 去上班)。
        #   其余时候守台是一个【committed goal】(时长 = 前台的 duration_ticks),
        #   —— 做完再决策: 需求只在每个 60t 边界被评估, 不会半路把守台打断。
        on_shift = self._on_shift(now_tick, cfg)
        plan = self._plan_intent(now_tick, cfg) if on_shift else None
        minute = now_tick % max(1, cfg.ticks_per_day)
        just_started = (on_shift and bool(self._work)
                        and minute == int(self._work.get("open", -1)))
        if just_started and plan is not None:
            self._goal = _Goal("plan", plan)
            return self._record(Decision(plan, "plan"))
        while True:
            # 1) 手上有事 → 【做完再决策】: 不重算, 不被打断(只有上面的 PLAN 能)。
            #    空闲时才每 tick 决策。
            if self._goal is not None:
                # 日程条目的窗口到期(下一条已到点) → 中止当前条目, 推进计划
                if self._goal.source == "plan" and can_preempt:
                    dl = self._schedule.deadline()
                    if dl is not None and now_tick >= dl:
                        self._schedule.drop()
                        self._goal = None
                        continue
                d = self._advance(self._goal)
                if d is not None:
                    return self._record(d)
                continue

            # 2) 空闲 → 看需求。
            cand, _eff = self._intent_scored(cfg, now_tick)
            # 在班 + 需求不急(都 >= floor) → 不许用需求顶掉工作, 直接去守台
            if cand is not None and not (plan is not None
                                         and not self._need_to_leave_work(cfg)):
                self._goal = _Goal("need", cand)
                self._queue_intent_speech(now_tick, cand)   # 语义层: “我去买点吃的”
                continue

            # 3) 没事可做。
            #    ★ 在班但没需求可做 → 回岗守台(绝不掉 idle)。
            #    起一个 committed goal: 做完这个前台时长(60t) 再决策。
            if plan is not None:
                self._goal = _Goal("plan", plan)
                return self._record(Decision(plan, "plan"))
            #    hp 见底时【不给日程】: 计划暂时挂起(不提交也不丢弃),
            #    等 hp 回来再接着走 —— 否则会“放弃→重新选中→再放弃”转圈。
            if self._hp_low(cfg):
                return self._record(Decision(Idle(), "idle"))
            e = self._schedule.current()
            if e is None or now_tick < e.at_tick:
                return self._idle_or_wander(cfg, now_tick)
            # D3: 这条的窗口已经过去了 → 跳过, 不补做。
            # 窗口边界与 Schedule.deadline() 同一口径: **严格更晚**的下一条才构成截止;
            # 同刻多条是同一组串行任务(如 MoveTo + Interact), 不能互相跳掉。
            nxt = self._schedule.peek_next()
            if (nxt is not None and nxt.at_tick > e.at_tick
                    and nxt.at_tick <= now_tick):
                self._schedule.drop()
                continue
            self._schedule.commit()
            self._goal = _Goal("plan", e.intent)
            continue

    def _on_shift(self, now_tick: int, cfg: "SimConfig") -> bool:
        """现在是我的班次吗? (有工作 且 在 open..close 之间)"""
        if not self._work:
            return False
        minute = now_tick % max(1, cfg.ticks_per_day)
        return int(self._work.get("open", 0)) <= minute < int(self._work.get("close", 1440))

    def _plan_intent(self, now_tick: int, cfg: "SimConfig") -> "Intent | None":
        """班次内该做的那件事: 还没到店里 → 去店里; 到了 → 站上台。

        就地取计划表里那条 daily 的上班条目(应聘时写一次, 之后不动)。
        """
        shop = str(self._work.get("shop", ""))
        station = str(self._work.get("station", ""))
        if not station:
            return None
        if shop and self._perceived_loc != shop:
            return MoveTo(dest=shop)
        return Interact(target_id=station)

    def _need_to_leave_work(self, cfg: "SimConfig") -> bool:
        """强需求掉到线下 → 允许从工作台上下来。

        只认吃饭/上厕所/困到不行这三种 —— 用户原话:
        "如果很想上厕所 或者饿了要吃饭 才从工作下来吃饭"。
        """
        floor = float(getattr(cfg, "work_leave_floor", 0.35))
        return any(float(self._signals.get(s, 1.0)) < floor
                   for s in ("hunger", "energy", "bladder"))

    def _hp_low(self, cfg: "SimConfig") -> bool:
        """命快没了 → 日程失去拉力(先顾命)。"""
        return self._signals.get("hp", 1.0) < cfg.hp_override

    def _abandon(self) -> None:
        """放弃当前目标: 计划来源的把该条标 dropped, 只清目标。"""
        if self._goal is not None and self._goal.source == "plan":
            self._schedule.drop()
        self._goal = None

    def _advance(self, goal: "_Goal") -> "Decision | None":
        """推进一个 goal: 异地先 MoveTo; 到达/无需移动后返回实际 Intent。"""
        if goal.source == "fun":
            # 闲逛两段: 赶路(try_wander 自己会走) → 到建筑里开逛 → 逛完收工
            roaming = any("roam" in ag.grant.tags for ag in self._intake)
            if goal.phase == "to_dest":
                if roaming:
                    goal.phase = "doing"          # 已经在逛了
                return Decision(goal.intent, goal.source)   # 走过去 或 开始逛
            if not roaming:                        # 逛完了
                self._finish_goal(goal)
                return None
            return Decision(goal.intent, goal.source)
        if goal.phase == "to_dest":
            dest = self._dest_for(goal.intent)
            if dest and self._perceived_loc != dest:
                # ★ 把选中时的 trace 一起带上 —— 否则 "去某地" 这一步
                # 在 Inspector/事件日志里【看不到为什么选它】(ranked 是空的),
                # 调参时只能干瞪眼(用户就踩过: 分不清是打分选的还是计划推的)。
                return Decision(MoveTo(dest=dest,
                                       trace=getattr(goal.intent, "trace", None)),
                                goal.source)
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
        if self._goal is goal:
            self._goal = None

    def _record(self, decision: Decision) -> Decision:
        self._last_intent = decision.intent
        return decision

    def on_interaction_done(self, entity_id: str, tick: int = 0) -> None:
        """窄协议: 世界告知某交互自然完成 → 结束对应 goal(计划推进下一条)。"""
        g = self._goal
        if g is not None and intent_target(g.intent) == entity_id:
            self._finish_goal(g)

    def failure_log(self) -> list[dict]:
        """观测: 失败日志只读快照(0:00 交 LLM 用)。"""
        return list(self._failures)


    def on_failure(self, target_id: str, why: str, now_tick: int,
                   retry_ticks: int | None = None) -> None:
        """窄协议: 交互失败 → 证伪/冷却记忆 + 记失败日志 + 跳过对应计划条。

        - 目标不存在 / 已空(stock=0) → 删掉该 item 记忆。
        - 已被占用 / 不可打断 / 购买失败等 → 冷却(cool_until=now+retry), 到时再看。
        - 失败日志留待 0:00 交 LLM(底层不推理)。
        """
        self._failures.append(
            {"tick": now_tick, "target": target_id, "why": why})
        # 失败也要有语义表达 —— “买不起/没货/被人占着”是玩家最该看见的一刻
        self._push_speech(semantic.denied(
            now_tick, self.person_id, semantic.fail_word(why),
            topic="denied.%s" % target_id))
        row = self._mem.get(target_id)
        if row is not None:
            if "目标不存在" in why or why.startswith("已空"):
                self._mem.delete(target_id)
            else:
                until = now_tick + (retry_ticks
                                    if retry_ticks is not None else 120)
                self._mem.update(target_id, cool_until=until)
        # 该目标失败 → 放弃当前目标(计划来源的跳过该条)
        g = self._goal
        if g is not None and intent_target(g.intent) == target_id:
            self._abandon()

    def step(self, port, cfg: "SimConfig",
             can_preempt: bool = True) -> Decision:
        """★ 主动拉(WP-05): 观察 → 感知 → 决策 → 执行。

        与 process 的区别: 不再等 world 把 Percept 推过来; NPC 自己
        `port.observe(...)`, 决策后自己拿意图去 `port.try_*(...)`, 失败自己
        `on_failure`(world 不再反写 NPC)。返回 Decision 供观测/日志。
        """
        percept = port.observe(self.person_id)
        self.perceive(percept, percept.tick)
        d = self.decide(cfg, percept.tick, can_preempt)
        self._execute(port, d, percept.tick)
        return d

    def _execute(self, port, decision: Decision, now_tick: int) -> None:
        """把意图交给 world 的动词, 失败自己处理(Deny/Ack 都是数据)。"""
        intent = decision.intent
        if isinstance(intent, MoveTo):
            r = port.try_move(self.person_id, intent.dest)
            if isinstance(r, Ack) and not r.ok:
                self.on_failure(intent.dest, r.reason, now_tick)
            elif isinstance(r, Ack) and r.ok:
                # WP-12: 起身离开 → 弃掉体内那份。world 在 preempt 时已释放 claim,
                # 食物/床回到世界(不浪费), 也没“中止也扣一份”。
                self._intake.clear()
        elif isinstance(intent, Interact):
            r = port.try_take(self.person_id, intent.target_id)
            if isinstance(r, Deny):
                self.on_failure(intent.target_id, r.reason, now_tick,
                                retry_ticks=(r.retry_ticks or None))
            elif isinstance(r, Grant):
                # 切到别的东西(而非继续当前目标) → 旧的那份弃掉
                self._intake = [ag for ag in self._intake
                                if ag.grant.entity_id == r.entity_id]
                self.intake_add(r)
        elif isinstance(intent, Buy):
            r = port.try_buy(self.person_id, intent.item_id, intent.qty)
            if isinstance(r, Ack) and not r.ok:
                self.on_failure(intent.item_id, r.reason, now_tick)
        elif isinstance(intent, Wander):
            r = port.try_wander(self.person_id, intent.dest)
            if isinstance(r, Grant):
                self.intake_add(r)          # 闲逛的 fun 由这份 Grant 自己涨
        elif isinstance(intent, Idle):
            # 身上没事 → 把活动名收回 idle(否则“闲逛”会粘着不走)
            if not self._intake:
                self.set_activity("idle")

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

    def __repr__(self) -> str:  # pragma: no cover
        return f"Person({self.person_id})"
