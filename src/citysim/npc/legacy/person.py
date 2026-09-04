"""Person 领域模型（分层草稿, 自建模块）。

设计决策: Person 拆分多份数据变化速率不同的子对象, 避免全字段平铺在一个 dataclass。

    Person
     ├─ identity  身份      (const, 几乎不变)
     ├─ life      人生轨迹  (long term, 缓慢变)
     └─ state     实时状态  (short term, 每 tick 变)
          └─ body  生理

本模块是"新设计"的可独立运行草稿, 目前与 life_sim.models 里的旧平铺 Person 并存;
引擎仍用旧 Person, 迁移完成前此文件不会替换它。据此可以在不破坏现有引擎的前提下
继续打磨分层结构（字段/默认值/方法）。等到引擎迁移时, 用本文件的类替换 models.Person。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

# --- 依赖: 包内相对导入(旧 try/except ImportError 双路径已按 M0 清除) ---
from .brain.arousal import arousal as _arousal
from .brain.review import ReviewClock
from .brain.planner import Action as _PAction, backward_plan as _backward_plan


# ---- GOAP 取食(容器演示)领域动作 -------------------------------
# 事实: food_in_container=食物在冰箱里; food_at_hand=已拿到手边; fed=吃饱。
# 动作单调增事实: 取(take)把"在容器"变成"在手边"; 吃(eat)把"在手边"变成"吃饱"。
_TAKE_FOOD = _PAction("take_food", pre=frozenset({"food_in_container"}),
                      add=frozenset({"food_at_hand"}))
_EAT_FOOD = _PAction("eat", pre=frozenset({"food_at_hand"}),
                     add=frozenset({"fed"}))
_GOAP_ACTIONS = [_TAKE_FOOD, _EAT_FOOD]
_PLAN_ZH = {"take_food": "取食物", "eat": "吃"}


class MemoryStream:
    """逐人记忆流的占位实现(原 life_sim.memory 模块已删, demo/迁移期用)。

    分层 Person 保留 memory 槽位但本阶段决策不读它; 具体记忆读写待
    memory 层重建后接入。目前仅保证可实例化、可空存。
    """

    def __init__(self, *a, **k) -> None:
        self._nodes: list = []

    @classmethod
    def from_storage(cls, *a, **k) -> "MemoryStream":
        return cls()

    def to_storage(self) -> dict:
        return {}

    def add(self, *a, **k) -> None:
        return None


# =====================================================================
# 基础消耗(代谢基线) —— "什么都不做也在掉"的部分
# 单位: 归一 0..1(1=最佳, 0=最大需求), 参数 = 每 tick 的 delta(负=下降)。
# 一天 = 1440 tick。故"24h 耗尽饥饿" ≈ -1.0/1440 ≈ -0.0007 /tick(归一)。
# 语义约定:
#   - 纯活动/零基线(social/fun/comfort/temperature): 不做不掉 => delta=0
#   - health: 健康时不掉(病态另由条件触发) => 0
#   - bladder: 事件驱动(进食→延迟→积累), 不走基础线性 => 0(见 event sink)
# 留倍率槽: activity/personality 可乘性修正(如醒着掉更快/特质慢些)。
# =====================================================================
@dataclass
class BasalMetabolism:
    """每 tick 基础消耗表(归一 delta)。可整体乘 activity/personality 倍率。"""

    # 信号 -> 每 tick 消耗(负)。正数不用于基础消耗(那是恢复)。
    deltas: dict[str, float] = field(default_factory=lambda: {
        "hunger": -1.0 / 1440.0,     # 约一天(24h)耗尽饥饿
        "thirst": -1.0 / 720.0,      # 约半天(12h)渴到顶
        "energy": -1.0 / 2880.0,     # 慢: 约 2 天(休息也掉得缓)
        "health": 0.0,               # 健康不掉(病态另行触发)
        "fun": -1.0 / 2880.0,        # 娱乐随时间缓降(约2天), 需看电视等回升
        "social": 0.0, "comfort": 0.0,
        "temperature": 0.0,          # 环境驱动(以后), 非基础线性
        "bladder": 0.0 ,              # 事件驱动(进食→延迟), 非基础线性
    })
    # 可选项: 环境/活动整体放大(如醒着 =1.0, 睡觉 energy 消耗近 0)
    activity_scale: dict[str, float] = field(default_factory=dict)

    def step(
        self,
        signals: dict[str, float],
        personality: dict[str, float] | None = None,
    ) -> None:
        """对一个归一 signals 应用本 tick 的基础消耗(原位改, 夹 0..1)。

        personality: {信号: 倍率}(默认 1) → 特质让人某项掉得更快/慢。
        activity_scale: 同上第二层(默认 1) → 由当前活动覆盖(如睡觉 energy)。
        """
        pers = personality or {}
        for s, d in self.deltas.items():
            if d == 0.0 or s not in signals:
                continue
            mul = float(pers.get(s, 1.0)) * float(self.activity_scale.get(s, 1.0))
            v = signals[s] + d * mul
            signals[s] = max(0.0, min(1.0, v))

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"BasalMetabolism(deltas={self.deltas})"



# =====================================================================
# 身份层 —— const, 玩家/世界创建时固定, 几乎不再变
# =====================================================================
@dataclass
class Identity:
    person_id: str
    name: str
    gender: str                # 男 | 女
    birthday: str              # YYYY-MM-DD
    # 性格特质(不同"类型"的特质聚成一册)。值类型各不同: bool 标签 / 数值档位
    traits: dict[str, Any] = field(default_factory=dict)  # 例: 勤劳/节俭/好奇/礼貌/威严/务实

    def birthday_date(self) -> date:
        """解析生日串为 date(无依赖 age 字段)。"""
        y, m, d = self.birthday.split("-")
        return date(int(y), int(m), int(d))


# =====================================================================
# 人生轨迹层 —— long term, 变化缓慢(按天/年)
# =====================================================================
@dataclass
class Life:
    age: int = 0
    family_id: str = ""
    home: str = ""             # 家庭住址(对应世界里的地点/place_id)
    role: str = "retired"      # worker | shopper | student | retired
    skills: dict[str, int] = field(default_factory=dict)   # 技能名 -> 等级
    # 亲属关系: 对方 person_id -> 关系名(配偶/父母/子女/兄弟姐妹)
    kinship: dict[str, str] = field(default_factory=dict)


# =====================================================================
# 生理层 —— short term 里的"身体", 每 tick 衰减/恢复
# 统一约定: 数值越大越健康/越充足(0..100, hp 例外 0=死)
# =====================================================================
@dataclass
class Body:
    energy: int = 80        # 精力  越大越充沛
    hunger: int = 80        # 饥饿  越大越饱腹
    thirst: int = 80        # 口渴  越大越不渴
    temperature: int = 80   # 体温  越大越温暖
    bladder: int = 80       # 排泄  越大排泄物积累越少
    health: int = 80        # 健康  越大越健康
    hp: int = 100           # 生命值 与年龄/健康/各生理状态有关, 到 0 = 死亡

    def is_alive(self) -> bool:
        return self.hp > 0

    def status_signals(self) -> dict[str, float]:
        """导出 0..1 归一化信号, 供 Utility/观测使用(0=耗尽, 1=充足)。"""
        lo, hi = 0, 100
        def _n(v: int) -> float:
            return max(0.0, min(1.0, (v - lo) / (hi - lo)))
        return {
            "energy": _n(self.energy),
            "hunger": _n(self.hunger),
            "thirst": _n(self.thirst),
            "temperature": _n(self.temperature),
            "bladder": _n(self.bladder),
            "health": _n(self.health),
            "hp": _n(self.hp),
        }


# =====================================================================
# 实时状态层 —— short term variable data(位置 + 活动 + 生理)
# =====================================================================
@dataclass
class RealtimeState:
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)  # world x y z
    current_activity: str = "idle"   # walk eat sleep work shop school ...
    body: Body = field(default_factory=Body)


# =====================================================================
# 个人持有容器 —— 属该个体的"财物"(随交互实时改写)
# 说明: 与身/心分层不同, 这是"归这个人所有"的动态资源, 常随交互增减。
#   items 里的对象实现 brain.indicator 的 Item 契约(可交互物品)。
# =====================================================================
@dataclass
class Inventory:
    money: int = 0                      # 资金(可为户/个人)
    items: list[Any] = field(default_factory=list)   # 持有的物品对象(可交互物品)

    # --- 实时改写 -----------------------------------------------------
    def add_money(self, amount: int) -> None:
        self.money += amount

    def spend(self, amount: int) -> bool:
        """尝试花费 amount, 余额不足返回 False(不扣款)。"""
        if amount < 0 or self.money < amount:
            return False
        self.money -= amount
        return True

    def add_item(self, item: Any) -> None:
        self.items.append(item)

    def remove_item(self, item: Any) -> bool:
        """移除指定物品(按同一性)。成功返回 True。"""
        try:
            self.items.remove(item)
            return True
        except ValueError:
            return False

    def find(self, **attrs: Any) -> Any | None:
        """按属性找持有的第一个物品(如 kind='food')。"""
        for it in self.items:
            if all(getattr(it, k, None) == v for k, v in attrs.items()):
                return it
        return None


# =====================================================================
# Person —— 组装各层 + 内建决策节律 + Indicator 决策 + 分tick 恢复
# =====================================================================
@dataclass
class Person:
    identity: Identity
    life: Life = field(default_factory=Life)
    state: RealtimeState = field(default_factory=RealtimeState)

    # 逐人记忆(横切, 不属于上面任一"变化速率层")
    memory: MemoryStream = field(default_factory=MemoryStream)
    # 个人持有(财物, 随交互实时改写)
    inventory: Inventory = field(default_factory=Inventory)
    # 决策节律(横切): 本个体距下次重评的剩余 tick(收进 Person)
    review: ReviewClock = field(default_factory=ReviewClock)

    # 基础消耗(代谢基线): 每 tick 什么都不做也在掉(归一 delta)
    metabolism: BasalMetabolism = field(default_factory=BasalMetabolism)
    personality: dict[str, float] = field(default_factory=dict)  # {信号: 消耗倍率}

    # ---- 决策/恢复所需(由装配点注入) ---------------------------------
    brain: Any = None                       # Indicator | None(装配注入)
    curves: dict = field(default_factory=dict)   # 曲线库: 名->Curve(默认空=全线性)
    item_source: Callable[[], list] | None = field(default=None)  # ()->容器物品

    # ---- GOAP 取食(世界侧钩子, 由沙箱注入; None=不启用) -------------
    food_taker: Callable[[], Any] | None = field(default=None)
    #     ()-> 从某容器(冰箱)取出一份可吃物品交给 Person, 取不到返回 None
    on_interaction_complete: Callable[[Any], None] | None = field(default=None)
    #     一件交互自然结束时回调(吃完→消耗; 任务→世界侧改写如移动/购买)

    # ---- 自洽策略接管(世界侧注入; None=用内置 Indicator+GOAP 择物) ---
    #     decider(person, stats) -> {"target":Item|task|None, "reason":str,
    #                                 "plan":[zh...], "goap":{...}|None} 或 None
    decider: Callable[["Person", dict], dict | None] | None = field(default=None)

    # ---- 运行状态真源(归一 0..1, 含生理+心理, 供 Indicator/恢复) ------
    signals: dict[str, float] = field(default_factory=dict)
    hour_f: float = 8.0                     # 当日时刻(供清醒度)
    asleep: bool = False                    # 睡着(睡眠交互中)

    # ---- 排泄: 事件驱动累加(进食/进水 → pending → 转压力 → 厕所排空) ---
    bladder_pending: float = 0.0            # 待转化的排泄负荷(0..上限无界)

    # ---- 正在进行的交互(分tick 恢复) ---------------------------------
    active_item: Any = None                 # 当前交互物品(Item)
    active_remaining: int = 0               # 距完成还差几 tick
    active_elapsed: int = 0                 # 已作用几 tick(观测)

    # ---- 最近一次决策的观测(前端展示) --------------------------------
    last_decision: dict = field(default_factory=dict)

    # --- 便捷代理 -----------------------------------------------------
    @property
    def person_id(self) -> str:
        return self.identity.person_id

    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def current_activity(self) -> str:
        return self.state.current_activity

    @current_activity.setter
    def current_activity(self, v: str) -> None:  # type: ignore[no-redef]
        self.state.current_activity = v

    def review_remaining(self) -> int:
        """距下次重评还剩几 tick(观测)。"""
        return self.review.remaining()

    # --- 装配 / 状态设置 ---------------------------------------------
    def setup_brain(
        self,
        curves: dict | None = None,
        threshold: float = 0.08,
        personality: dict[str, float] | None = None,
    ) -> None:
        """装配 Indicator(需先设好 item_source)。curves 缺省=全线性。"""
        if curves is not None:
            self.curves = curves
        from .brain.indicator import Indicator  # 延迟导入避免环
        self.brain = Indicator(
            item_source=(self.item_source or (lambda: [])),
            threshold=threshold,
            personality=personality,
            curves=self.curves,
        )

    def set_state(self, **kw: float) -> None:
        """直接设定归一状态(0..1)。便捷测试/初始化。"""
        self.signals.update(kw)
        # 同步到 body(0..100, 若字段存在)
        b = self.state.body
        for s, v in kw.items():
            if hasattr(b, s):
                setattr(b, s, max(0, min(100, round(v * 100))))

    # --- 状态读取 -----------------------------------------------------
    def status_signals(self) -> dict[str, float]:
        """归一状态(运行真源)。若有 body 字段且 signals 未初始化, 从 body 读。"""
        if self.signals:
            return dict(self.signals)
        return {k: v for k, v in self.state.body.status_signals().items()}

    # --- 决策 + 节律 + 恢复 (每 tick 主入口) ---------------------------
    SLEEP_WAKE_E = 0.99   # 精力达此水平视为"睡饱", 自动醒
    SLEEP_DECIDE_TICKS = 480  # 入睡后, 距下次 decide 固定为 8 小时(480 tick)
    # 排泄: 每 tick 从 pending 转入"膀胱"的速率(约每分钟 0.02 → 0.4 负荷约 20 分钟)
    BLADDER_CONVERT = 0.02
    EAT_HUNGER = 0.42     # 饱腹低于此视为"饿"; 且手边无散落食物时才走 GOAP 取→吃

    # --- GOAP 取食辅助 ------------------------------------------------
    def _want_eat(self, stats: dict[str, float]) -> bool:
        """饿不饿: 饱腹信号越低越饿。"""
        return stats.get("hunger", 1.0) < self.EAT_HUNGER

    def _no_loose_edible(self) -> bool:
        """手边/散落可用物品里有没有能直接补饥饿的(有则不急着从容器取)。"""
        src = self.item_source() if callable(self.item_source) else []
        for it in src:
            eff = getattr(it, "effects", None) or {}
            if eff.get("hunger", 0.0) > 0:
                return False
        return True

    def _plan_take_eat(self) -> list[str] | None:
        """GOAP 反向搜索: 初始=食物在容器里(无在手), 目标=吃饱 → [取, 吃]。"""
        try:
            return _backward_plan(_GOAP_ACTIONS, {"food_in_container"}, {"fed"})
        except Exception:
            return None

    def _is_sleep_item(self, it: Any) -> bool:
        """判断一件物品是否属于"睡觉"(上床休息)。"""
        try:
            if getattr(it, "interaction", None) in ("sleep", "睡"):
                return True
            nm = (getattr(it, "name", "") or "")
            return nm in ("床", "bed", "睡觉")
        except Exception:
            return False

    def _is_toilet_item(self, it: Any) -> bool:
        """判断一件物品是否用于"排泄/如厕"(会清空膀胱)。"""
        try:
            if getattr(it, "interaction", None) in ("toilet", "wc", "厕所"):
                return True
            nm = (getattr(it, "name", "") or "")
            return any(k in nm for k in ("厕所", "马桶", "洗手间"))
        except Exception:
            return False

    @staticmethod
    def _bladder_load(it: Any) -> float:
        """这件可吃/可喝物品带来的排泄负荷(attrs.bladder, 缺省 0)。"""
        try:
            return float(((getattr(it, "attrs", None) or {}).get("bladder") or 0.0))
        except Exception:
            return 0.0

    def _make_decision(self) -> str | None:
        """执行一次全量决策。被 到点 或 睡醒 调用。

        若装配了 ``decider``(如沙箱里的家庭经济循环)则交给它裁决; 否则
        退回内置路径(GOAP 取食 take→eat + Indicator 择物)。
        """
        stats = self.status_signals()
        picked: Any = None
        goap: dict | None = None
        reason = ""
        ranked: list = []

        if self.decider is not None:
            # ---- 自洽策略接管 ----
            out = (self.decider(self, stats) or {})
            picked = out.get("target")
            if picked is not None:
                self._begin_interaction(picked)
            else:
                self._end_interaction()
            goap = out.get("goap") or None
            reason = out.get("reason", "")
            ranked = out.get("ranked", []) or []
            plan = out.get("plan", []) or []
        else:
            # ---- 内置: GOAP 取食(take→eat) ----
            trace: dict = {}
            if (self._want_eat(stats) and self.food_taker is not None
                    and self._no_loose_edible()):
                food = self.food_taker()
                if food is not None:
                    plan = self._plan_take_eat()
                    zh = [_PLAN_ZH.get(a, a) for a in plan] if plan else []
                    goap = {"plan": list(plan or []), "zh": zh, "goal": "fed",
                            "note": ("食物在冰箱里 → 先取再吃" if zh
                                     else "冰箱空, 取不到食物")}
                    self._begin_interaction(food)   # 取到的这份直接开吃
                    picked = food
                    reason = goap["note"]
            # ---- 内置: Indicator 择物 ----
            if picked is None:
                if self.brain is not None and hasattr(self.brain, "decide_trace"):
                    trace = self.brain.decide_trace(stats)
                    picked = trace.get("picked")
                else:
                    picked = self.brain.decide(stats) if self.brain else None
                if picked is not None:
                    self._begin_interaction(picked)
                else:
                    self._end_interaction()
                reason = trace.get("reason", "") if trace else ""
                ranked = trace.get("ranked", []) if trace else []

        # ---- 排下次重评 ----
        a = _arousal(self.hour_f, stats.get("energy", 0.5), stats.get("hunger", 0.5))
        if self.asleep:
            # 睡着: 下次 decide 固定 8 小时(480 tick), 不按清醒度算
            self.review.schedule_ticks(self.SLEEP_DECIDE_TICKS)
        elif picked is not None and (self.decider is not None or goap is not None):
            # 接管/取食: 排到这次活动做完, 免得中途被打断 / 重复取
            self.review.schedule_ticks(max(1, self._duration_of(picked)))
        else:
            self.review.refresh(a)

        # ---- 观测 ----
        picked_id = getattr(picked, "item_id", None) if picked else None
        picked_name = (getattr(picked, "name", picked_id) if picked else None)
        plan_ui = (out.get("plan", []) or []) if self.decider is not None else \
                  ((goap or {}).get("zh", []) or []) if goap else []
        self.last_decision = {
            "tick": self.review.remaining(),
            "picked_id": picked_id,
            "picked_name": picked_name,
            "reason": reason,
            "ranked": ranked,
            "goap": goap,
            "plan": plan_ui,
        }
        return self._activity_name()

    def tick(self, ctx: Any = None) -> str | None:
        """推进本 tick: 基础消耗 → 恢复 → (睡着则睡饱自动醒) → 节律决策。"""
        clock = getattr(ctx, "clock", None)
        if clock is not None:
            self.hour_f = clock.hour_f
        if not self.signals:
            self.signals = self.status_signals()
        # 基础消耗(什么不做也掉, 含娱乐缓降)
        self.metabolism.step(self.signals, self.personality)
        # 推进恢复(分 tick 补 active_item 的效果)
        self._step_recovery()
        # 排泄: 待转化负荷 → 膀胱压力(事件驱动, 非线性基线)
        self._step_elimination()

        # ---- 睡眠态: 清醒度=0(不按节律重评), 只睡到精力满 ----
        if self.asleep:
            e = self.signals.get("energy", 0.0)
            # 若当前仍在睡且没睡饱 → 继续睡(跳过决策/重评)
            if self.active_item is not None and e < self.SLEEP_WAKE_E:
                return self._activity_name()
            # 睡饱/结束 → 醒来, 做一次决策
            self.asleep = False
            self._end_interaction()
            return self._make_decision()

        # ---- 醒着: 正常节律 ----
        self.review.step()
        if not self.review.is_due():
            return self._activity_name()
        return self._make_decision()

    # --- 恢复: 分 tick 把 active_item 的 effects 落到 signals ---------
    def _step_recovery(self) -> None:
        if self.active_item is None or self.active_remaining <= 0:
            return
        it = self.active_item
        dur = self._duration_of(it)
        for s, delta in getattr(it, "effects", {}).items():
            # 每 tick 分摊: delta / duration (慢动作低速率, 快动作高速率)
            step = delta / dur if dur else delta
            if s in self.signals:
                self.signals[s] = max(0.0, min(1.0, self.signals[s] + step))
            # 同步到 body
            b = self.state.body
            if hasattr(b, s):
                setattr(b, s, max(0, min(100, round(getattr(b, s) + step * 100))))
        self.active_elapsed += 1
        self.active_remaining -= 1
        if self.active_remaining <= 0:
            finished = self.active_item
            self._end_interaction()
            # 一件交互自然完成 → 通知世界(如: 把吃完的这份食物放回冰箱)
            if (finished is not None and self.on_interaction_complete is not None):
                try:
                    self.on_interaction_complete(finished)
                except Exception:
                    pass

    @staticmethod
    def _duration_of(it: Any) -> int:
        """该交互的期望时长(tick/分钟)。读顶层 duration_min; 未写(或非法)默认 30。"""
        try:
            d = getattr(it, "duration_min", None)
            return max(1, int(d)) if d else 30
        except Exception:
            return 30

    def _begin_interaction(self, it: Any) -> None:
        self.active_item = it
        self.active_remaining = self._duration_of(it)
        self.active_elapsed = 0
        # 若这件是"睡觉"类 → 入睡(清醒度=0, 睡到精力满才醒)
        if self._is_sleep_item(it):
            self.asleep = True
        # 若这件是"如厕"类 → 清空膀胱(压力归零, pending 清空)
        if self._is_toilet_item(it):
            self.bladder_pending = 0.0
            self.signals["bladder"] = 1.0
            b = self.state.body
            if hasattr(b, "bladder"):
                b.bladder = 100
        # 进食/进水 → 累加排泄负荷(延迟到膀胱)
        elif self._bladder_load(it) > 0:
            self.bladder_pending += self._bladder_load(it)

    def _step_elimination(self) -> None:
        """把待转化排泄负荷按固定速率转入膀胱(信号下降=更想如厕)。

        无 pending 时膀胱不掉(空腹不会凭空想尿); 不封顶则叠加到顶(clamp)。
        """
        if self.bladder_pending <= 0:
            return
        step = min(self.BLADDER_CONVERT, self.bladder_pending)
        self.bladder_pending -= step
        cur = self.signals.get("bladder", 1.0)
        self.signals["bladder"] = max(0.0, min(1.0, cur - step))
        b = self.state.body
        if hasattr(b, "bladder"):
            b.bladder = max(0, min(100, round(self.signals["bladder"] * 100)))

    def _end_interaction(self) -> None:
        self.active_item = None
        self.active_remaining = 0
        self.active_elapsed = 0
        self.asleep = False

    def _activity_name(self) -> str | None:
        if self.active_item is not None:
            return getattr(self.active_item, "name",
                           getattr(self.active_item, "item_id", None))
        return self.state.current_activity or "idle"

    # --- 兼容旧入口 ---------------------------------------------------
    def update(self, ctx: Any = None) -> str | None:
        """旧名入口 → 等价 tick(兼容既有调用)。"""
        return self.tick(ctx)

