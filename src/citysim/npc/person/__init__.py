"""npc.person —— 一个人的门面: 身份 + 装配 + 对外那一拍。

一个类分布在多个文件里(mixin), 每个文件管一个方面:
  body.py    身体: 信号 / 消化 / 膀胱 / 活动
  goal.py    目标: 何时重算 / 走完 / 放弃
  speech.py  说话: 气泡 / 语义草稿 / 惊讶
  work.py    工作: 雇佣 / 班次 / 出勤 + 好感
  memo.py    记忆门面: 记一笔 / 还记不记得

这里只管【装配(__init__ 把一个人的全部状态列一遍) + 对外
那一拍(step / notify / perceive)】。

门面拥有剩下的字段(各组不认领的):
  _age _identity _home _money _places _travel_costs _tell_bias _personality
  _perceived_loc _name_of _failures _moving _queued
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Mapping
from citysim.core.ports import Ack, Deny, Grant
from citysim.core.types import (
    Bought,
    Buy,
    Decision,
    InteractionDone,
    InteractionFailed,
    Interact,
    ItemGone,
    MoveTo,
    WagePaid,
    Wander,
    intent_target,
)
from citysim.npc import brain, semantic
from citysim.npc.memory import MemBase
from citysim.npc.schedule import Schedule

from citysim.npc.person.body import BodyMixin
from citysim.npc.person.goal import GoalMixin
from citysim.npc.person.memo import MemoMixin
from citysim.npc.person.speech import SpeechMixin
from citysim.npc.person.work import WorkMixin

# 原来就住在 person 模块里的名字 —— 保持可导入(外部/测试在用)
from citysim.npc.person.body import (  # noqa: F401
    _ActiveGrant, _clamp, apply_metabolism, full_signals,
    signals_as_percent,
)
from citysim.npc.person.goal import _Goal  # noqa: F401

if TYPE_CHECKING:  # pragma: no cover
    # 只出现在类型标注里(运行时用不到) —— 别让清 import 的脚本删掉
    from citysim.core.config import SimConfig
    from citysim.core.types import Intent, Percept


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


class Person(BodyMixin, GoalMixin, SpeechMixin,
             WorkMixin, MemoMixin):
    """见模块头。各方面在 body/decide/speech/work/memo.py。"""

    def __init__(
        self,
        identity: Identity | None = None,
        *,
        signals: Mapping[str, float] | None = None,
        personality: Mapping[str, float] | None = None,
        home: str = "",
        tell_bias: float = 1.0,
        money: float = 100.0,
    ) -> None:
        self._identity: Identity = identity or Identity(person_id="anon", name="匿名")
        self._signals: dict[str, float] = full_signals()
        self._personality: dict[str, float] = dict(personality or {})
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
        self._intake: list[_ActiveGrant] = []   # 体内正在消化
        self._finished: list[str] = []          # 本 tick 消化完的 handle(取走即清)
        # —— “我此刻在干什么”: 纯自身状态推导(world 不再写 set_activity 进来) ——
        self._moving: bool = False    # 上次 try_move 成功了(在途; 到站后 step 里清)
        self._queued: bool = False    # 刚 try_buy 成功 → 在店里等柜台(异步成交)
        self._bubble: tuple[str, int, str] | None = None   # (文字, 到期的 tick, 类型)
        # —— 语义层: 值得说的草稿 + 话题冷却 ——
        self._say_queue: list = []          # [SemanticEvent](未措辞的结构化真值)
        self._said_at: dict[str, int] = {}  # topic -> 上次说的 tick(别复读自己)
        self._name_of = None                # 注入: npc_id -> 名字(渲染“王哥说…”用)
        self._failures: list[dict] = []  # 失败日志(0:00 交 LLM)
        if signals:
            self.set_signals(**dict(signals))

    def step(self, port, cfg: "SimConfig") -> Decision:
        """★ 主动拉: 观察 → 感知 → 决策 → 执行。

        与 process 的区别: 不再等 world 把 Percept 推过来; NPC 自己
        `port.observe(...)`, 决策后自己拿意图去 `port.try_*(...)`, 失败自己
        `notify(InteractionFailed)`(world 不再反写 NPC)。返回 Decision 供观测/日志。
        """
        percept = port.observe(self.person_id)
        self.perceive(percept, percept.tick)
        d = self.decide(cfg, percept.tick)
        self._execute(port, d, percept.tick)
        return d


    def _execute(self, port, decision: Decision, now_tick: int) -> None:
        """把意图交给 world 的动词, 失败自己处理(Deny/Ack 都是数据)。

        ★ “我在干什么”也在这里自己记: 上一步的 move/queue 标志先清掉, 成功了再立 ——
          move 立了之后会一直生效到下一次 step(在途时 world 不叫 step, 正好表示“还在走”)。
        """
        intent = decision.intent
        self._moving = False
        if isinstance(intent, MoveTo):
            r = port.try_move(self.person_id, intent.dest)
            if isinstance(r, Ack) and not r.ok:
                self._on_failed(intent.dest, r.reason, now_tick)
            elif isinstance(r, Ack) and r.ok:
                # 起身离开 → 弃掉体内那份。world 在 preempt 时已释放 claim,
                # 食物/床回到世界(不浪费), 也没“中止也扣一份”。
                self._intake.clear()
                self._moving = True
        elif isinstance(intent, Interact):
            r = port.try_take(self.person_id, intent.target_id)
            if isinstance(r, Deny):
                self._on_failed(intent.target_id, r.reason, now_tick,
                                retry_ticks=(r.retry_ticks or None))
            elif isinstance(r, Grant):
                # 切到别的东西(而非继续当前目标) → 旧的那份弃掉
                self._intake = [ag for ag in self._intake
                                if ag.grant.entity_id == r.entity_id]
                self.intake_add(r)
        elif isinstance(intent, Buy):
            r = port.try_buy(self.person_id, intent.item_id, intent.qty)
            if isinstance(r, Ack) and not r.ok:
                self._on_failed(intent.item_id, r.reason, now_tick)
            elif isinstance(r, Ack) and r.ok:
                self._queued = True          # 已入队 → 在店里等柜台
        elif isinstance(intent, Wander):
            r = port.try_wander(self.person_id, intent.dest)
            if isinstance(r, Grant):
                self.intake_add(r)          # 闲逛的 fun 由这份 Grant 自己涨
            elif isinstance(r, Ack) and r.ok:
                # 闲逛是两段式: 没到 dest 时 try_wander 复用移动 → 也在途
                self._moving = True
            elif isinstance(r, Ack):
                self._on_failed(intent.dest, r.reason, now_tick)


    def notify(self, ev) -> None:
        """★ world → NPC 的【唯一通知口】: 世界只说“发生了什么”。

        以前是外面的世界直接调 on_interaction_done / on_failure / forget_item /
        earn 四个 setter 改这个人; 现在只递一张【通知】进来, 怎么改自己是
        NPC 自己的事(写记忆、开冷却、结束目标、进账…)。

        对齐铁律: 世界不替 NPC 写认知 —— 它只把理由和结果交回去。
        """
        if isinstance(ev, Bought):
            self._remember_delivery(ev)
            return
        # 一次请求收了尾 → 不再在柜台排队(activity() 自己就不再报 queue)
        if isinstance(ev, (InteractionDone, InteractionFailed)):
            self._queued = False
        if isinstance(ev, InteractionDone):
            g = self._goal
            if g is not None and intent_target(g.intent) == ev.entity_id:
                self._finish_goal(g)
        elif isinstance(ev, InteractionFailed):
            self._on_failed(ev.target_id, ev.why, ev.tick, ev.retry_ticks)
        elif isinstance(ev, ItemGone):
            self._mem.delete(ev.entity_id)
        elif isinstance(ev, WagePaid):
            if ev.amount > 0:
                self._money += float(ev.amount)
        else:                                # pragma: no cover - 开发期挡错
            raise TypeError(f"未声明的通知 {ev!r}")


    def _on_failed(self, target_id: str, why: str, now_tick: int,
                   retry_ticks: int | None = None) -> None:
        """交互失败的内政: 证伪/冷却记忆 + 失败日志 + 推进(同 notify 的旧身)。

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


    def failure_log(self) -> list[dict]:
        """观测: 失败日志只读快照(0:00 交 LLM 用)。"""
        return list(self._failures)


    def perceive(self, percept: "Percept", tick: int) -> None:
        """现场 → 记忆(写入)。非纯函数。感知即知道自己当前在哪。

        注意顺序: **先拿“预期 vs 观察”**, 再写记忆 —— 写完就没落差了。
        """
        self._perceived_loc = percept.location_id
        for ev in self._spot_surprises(percept, tick):
            self._push_speech(ev)
        brain.perceive_into(self._mem, percept, tick)


    def _remember_delivery(self, ev: "Bought") -> None:
        """买到的东西落到哪个容器 → 写进记忆。

        靠它, 下次决策才能算出"家里还剩几个"(囤货模型) —— 而不必当期看到家里。
        """
        if ev.container:
            self.note(
                ev.container, tick=ev.tick,
                located=ev.home, owner=self.person_id,
                stock=ev.stock,
                afford=ev.afford,
                value=ev.value,
                believe=1.0,                    # 自己买回来的 = 亲眼所见
                item_type=ev.item_type,
                tags=tuple(ev.tags), source="",
                shelf_life_ticks=ev.shelf_life_ticks,
                expires_tick=ev.expires_tick)


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


    def pay(self, amount: float) -> bool:
        """扣钱(只减不增); 钱不够返回 False。"""
        if self._money < amount:
            return False
        self._money -= amount
        return True


    def is_alive(self) -> bool:
        return self._signals.get("hp", 1.0) > 0.0


    # --- 语义层: 攒“值得说的事”, 按优先级取 ---------------------------
    def set_name_lookup(self, fn) -> None:
        """装配: 注入 npc_id -> 名字(世界侧提供, 本层只存不查)。"""
        self._name_of = fn


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


    @property
    def last_intent(self) -> "Intent | None":
        return self._last_intent
