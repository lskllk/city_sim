"""npc/person/body —— 身体: 信号 / 消化 / 膀胱 / 活动

信号怎么涨落、消化怎么推进、身上有东西时「我在干什么」都在这里。

我拥有的字段: _bladder_pending, _finished, _intake, _signals, _starve_ticks
我只读的字段: _moving, _personality, _queued, _work
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping
from citysim.core.config import SIGNALS


if TYPE_CHECKING:  # pragma: no cover
    from citysim.core.config import SimConfig
    from citysim.core.types import Intent, Percept


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


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


@dataclass
class _ActiveGrant:
    """体内正在消化的一份 Grant。

    `total` = max(1, duration_ticks); 每 tick 加 `value/total`, `remaining` 递减到 0
    就算吃完 —— 这就是“吃东西→饥饿下来”的循环, 现在归 NPC 自己。
    """
    grant: "Grant"
    total: int
    remaining: int


class BodyMixin:
    """见文件头(它拥有哪些字段)。"""


    def heartbeat(self, now_tick: int, cfg: "SimConfig", *,
                  sleep: bool | None = None, busy: bool = False) -> bool:
        """身体每 tick 演化(世界广播心跳, Person 内部自己做, 上帝不改 signals)。

        顺序 = 代谢(睡眠冻结 energy; busy 暂不对任何信号生效) → hp(饿死/恢复) → 排泄(pending→膀胱) → 消化。
        返回是否仍存活(死则不再往下)。

        sleep=None(默认) 时【自己判】: 体内 intake 里有没有 sleepable 的东西
        (世界不再反向告诉 NPC“你在睡”)。
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
        # 消化: 体内 intake 逐 tick 均摊加信号。
        # 放在代谢/排泄【之后】—— 与旧 InteractionSystem.step 的相对顺序一致。
        self._digest(now_tick, cfg)
        return True


    def _digest(self, now_tick: int = 0, cfg: "SimConfig | None" = None) -> None:
        """推进体内 intake: 每 tick 加 value/total。

        结束(通用): ① 目标信号已满(>=1.0) → **满了优先结束**;
                   ② 到 duration_ticks → 到点结束;
                   ③ 工作工位: 一旦【不在班】 → 立刻下班(不再挂着占着台)。
        都走【自然完成】(world 收尾)。

        消化时会有一点【副作用】: 吃进去的东西会攒尿 —— 按吸收的 hunger 折算
        (`cfg.bladder_per_hunger`)。这是 NPC 自己的消化规则, 不是每个物品
        各自写在数据里的一份配置。
        """
        for ag in list(self._intake):
            g = ag.grant
            tags = tuple(getattr(g, "tags", ()) or ())
            off_duty = ("work" in tags and bool(self._work)
                        and cfg is not None
                        and not self._on_shift(now_tick, cfg))
            if g.signal:
                step = g.value / ag.total
                self.add_signal(g.signal, step)
                if g.signal == "hunger" and cfg is not None:
                    self.add_bladder_pending(step * cfg.bladder_per_hunger)
            ag.remaining -= 1
            saturated = bool(g.signal) and self.signal(g.signal) >= 1.0
            if ag.remaining <= 0 or saturated or off_duty:
                self._intake.remove(ag)
                self._finished.append(g.handle)


    def intake_add(self, grant: "Grant") -> None:
        """把 world 签发的 Grant 收进体内开始消化。"""
        if any(ag.grant.handle == grant.handle for ag in self._intake):
            return                                 # 同一份已持有(handle 唯一)
        total = max(1, int(grant.duration_ticks))
        self._intake.append(_ActiveGrant(grant=grant, total=total, remaining=total))


    def take_finished(self) -> list[str]:
        """取走本 tick 消化完的 handle(供 world 做收尾: 扣货/回收)。取走即清。"""
        out = self._finished
        self._finished = []
        return out


    def intake_progress(self, entity_id: str = "") -> tuple[int, int]:
        """当前在消化那份的 (剩余, 总时长); 没在消化/不匹配 → (0, 0)。

        进度归 NPC 自己(体内 _intake); 快照要显示进度条就取这里,
        不要再去看 world 的 ActiveInteraction(那边已不存进度)。
        """
        for ag in self._intake:
            if not entity_id or ag.grant.entity_id == entity_id:
                return ag.remaining, ag.total
        return 0, 0


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


    @property
    def signals(self) -> Mapping[str, float]:
        """只读视图(调用方要按名读信号用 signal() 更省)。"""
        return dict(self._signals)


    def signal(self, name: str) -> float:
        return self._signals.get(name, 1.0)


    # ------------------------------------------------------------------
    # 状态写 —— 位置 / 膀胱 / 钱(“我在干什么”已改成【只读推导】: 见 activity())
    def add_bladder_pending(self, delta: float) -> None:
        self._bladder_pending = max(0.0, self._bladder_pending + float(delta))


    @property
    def bladder_pending(self) -> float:
        return self._bladder_pending


    def activity(self) -> tuple[str, str]:
        """我此刻在干什么 —— (行为大类, 显示文字)。**纯读自身状态, 不查世界**。

        以前这些是 world 写进来的: 6 处 `set_activity(...)` 把“苹果”/“idle”/
        “闲逛”写到 NPC 身上, `act_class_of` 再去 world 的 travel/roaming/
        interaction 里猜大类。但“我在干什么”本来就是我自己最清楚的事 ——
        现在从 _intake(消化中的那份 Grant, 带 tags) + _moving/_queued 自己推。
        """
        if self._intake:
            g = self._intake[-1].grant          # 最后接下的那份 = 当前主要动作
            cls = self._class_of_tags(g.tags)
            if cls == "wander":
                return "wander", "闲逛"
            return cls, (g.name or "")
        if self._moving:
            return "move", ""
        if self._queued:
            return "idle", "queue"              # 在柜台排队(成交在柜台那边异步发生)
        return "idle", "idle"


    @property
    def activity_class(self) -> str:
        """行为大类: move/eat/sleep/toilet/work/wander/idle(前端/时间线配色)。"""
        return self.activity()[0]


    @property
    def current_activity(self) -> str:
        """显示文字。吃/睡时是【那件东西的名字】(前端显示“吃饭 · 苹果”)。"""
        return self.activity()[1]


    @staticmethod
    def _class_of_tags(tags: "Sequence[str]") -> str:
        """物件的 tags → 行为大类(数据驱动: 新物件不用改这里)。"""
        t = set(tags or ())
        if "sleepable" in t:
            return "sleep"
        if "toilet" in t:
            return "toilet"
        if "edible" in t:
            return "eat"
        if "work" in t or "station" in t:
            return "work"
        if "roam" in t:
            return "wander"
        return "idle"
