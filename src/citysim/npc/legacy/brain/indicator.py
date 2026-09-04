"""Indicator — 交互裁决器(大脑)。

**定位**: person/brain 里的"挑一件物品去做"的裁决器。它**不保存数据**：
  - 物品清单(容器)每 tick 由世界实时供给(经 ``item_source`` 拉取, 可变化);
  - 打分所需的状态从 Person 的 RealtimeState 派生传入(0..1 归一水平)。

**职责管线**:
  1. 打分   score_all : 用 Person 当前状态, 对容器内**所有**物品打分
                        (例: 现在去吃(食物)多少分 / 去用(电视)多少分)
  2. 排序   rank     : 按分降序
  3. 后处理 select   : 对排序结果做 selector(受人物状态/性格影响; 此处留框架)
  4. 返回   decide   : 选出目标物品并返回 => Person.update 的最终决策物品

**Item(契约, 世界侧供给)**: 本模块只声明它必须具备的字段, 世界据此产出。
  - effects   对状态的影响(增量, -1..1)
  - effect_curves(可选) 每 effect 选用的非线性曲线名(缺省 linear)
  - owner     归属(属某个人 / 某角色 / None=公共)
  - position  空间位置(x, y, z)

**非线性**: 打分把每个 effect 的缺口 need=1-level 经其曲线(curve_pack)映射成
权重。默认 'linear'(weight=need) 等价旧行为; 传入 ``curves`` 曲线库后, 各
物品可为不同需求指定不同曲线(如饥饿陡升、娱乐平缓), 见 world/curves.py。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


# ---------------------------------------------------------------------------
# 物品契约(世界供给; 本模块只读, 不自建/不持久)
# ---------------------------------------------------------------------------
class Item(Protocol):
    """交互物品的最小契约 —— 世界容器里的物品需具备以下可读面。"""

    @property
    def item_id(self) -> str: ...

    @property
    def kind(self) -> str: ...            # 物品类型(食物/电视/床...)

    @property
    def effects(self) -> dict[str, float]: ...   # state字段名 -> 交互后增量(0..1)

    @property
    def effect_curves(self) -> dict[str, str]: ...  # 可选: 每 effect 指定曲线名

    @property
    def owner(self) -> str | None: ...     # 归属: person_id / role / None=公共

    @property
    def position(self) -> tuple[float, float, float]: ...  # x, y, z

    def curve_for(self, signal: str) -> str: ...  # 该 effect 的曲线名(默认 'linear')


# 容器提供方: 每 tick 从世界拉取"当前可用物品清单"(实时可变)
ItemSource = Callable[[], list[Item]]

# 曲线库: name -> 曲线对象(curve_pack 的 Curve, 需具 .sample(need)->weight)
CurveLibrary = dict[str, Any]


# ---------------------------------------------------------------------------
# 打分结果
# ---------------------------------------------------------------------------
@dataclass
class ScoredItem:
    """一个被打分的物品。"""

    item: Item
    score: float = 0.0
    driving: list[dict] = field(default_factory=list)  # 各状态贡献(观测)


# ---------------------------------------------------------------------------
# Indicator —— 裁决器
# ---------------------------------------------------------------------------
class Indicator:
    """从当前物品容器里选出一个"现在最该交互"的物品。

    不保存任何数据: 物品从 ``item_source`` 实时取, 状态每次由调用方传入。
    """

    def __init__(
        self,
        item_source: ItemSource,
        threshold: float = 0.5,
        personality: dict[str, float] | None = None,
        curves: CurveLibrary | None = None,
    ) -> None:
        self._source = item_source            # () -> list[Item] (世界容器)
        self._threshold = threshold           # 分数低于此 => 不值得做(返回 None)
        # 人物差异: 状态名 -> 关注倍率(性格/特质在此倾斜; 默认恒等 1)
        self._personality: dict[str, float] = personality or {}
        # 非线性曲线库(need->weight)。'linear' 恒内置; 未提供则全线性。
        self._curves: dict[str, Any] = dict(curves or {})

    # --- 数据获取(不缓存, 每次现取) -----------------------------------
    def _live_items(self) -> list[Item]:
        """从世界容器拉取当前物品清单。"""
        items = self._source() if callable(self._source) else []
        return list(items)

    # --- 1. 打分核心 ---------------------------------------------------
    def _curve_weight(self, item: Item, signal: str, need: float) -> float:
        """把原始缺口 need(0..1) 经该 effect 选定的曲线映射成 0..1 权重。

        - 未指定/未找到曲线 => 线性(weight = need), 保持旧行为;
        - 曲线库里的对象需实现 ``.sample(need) -> weight``(world.curves.Curve)。
        归一夹取到 0..1。
        """
        name = "linear"
        try:
            name = item.curve_for(signal) if hasattr(item, "curve_for") else "linear"
        except Exception:
            name = "linear"
        curve = self._curves.get(name)
        if curve is None:
            return max(0.0, min(1.0, float(need)))   # 线性恒等
        try:
            w = curve.sample(float(need))
        except Exception:
            w = need
        return max(0.0, min(1.0, float(w)))

    def _weight_for(self, item: Item, signal: str, level: float) -> float:
        """该 effect 的最终权重 = 曲线(need) × 性格倍率。

        level: 当前状态 0..1(越大越不缺); need = 1 - level。
        """
        need = 1.0 - level
        base = self._curve_weight(item, signal, need)
        return base * float(self._personality.get(signal, 1.0))

    def score_one(self, item: Item, stats: dict[str, float]) -> float:
        """单个物品得分 = 对 RealtimeState 各状态影响 × 当前对该状态的需求权重。

        effects: {state字段: 增量}。增量>0 补充/改善, 增量<0 消耗。
        每个 effect 用其选定曲线把缺口映射成权重(默认线性=缺口本身)。
        补充(正)在缺时价值大; 消耗(负)在缺时是负担。
        """
        total = 0.0
        for signal, delta in item.effects.items():
            level = float(stats.get(signal, 0.5))
            weight = self._weight_for(item, signal, level)
            total += delta * weight
        return total

    def score_all(self, stats: dict[str, float]) -> list[ScoredItem]:
        """对当前容器内所有物品打分。``stats`` = RealtimeState 派生 0..1 信号。"""
        out: list[ScoredItem] = []
        for item in self._live_items():
            score = self.score_one(item, stats)
            driving = [
                {"signal": s, "delta": d,
                 "level": round(float(stats.get(s, 0.5)), 3),
                 "need": round(1.0 - float(stats.get(s, 0.5)), 3),
                 "curve": item.curve_for(s) if hasattr(item, "curve_for") else "linear",
                 "weight": round(self._weight_for(item, s, float(stats.get(s, 0.5))), 3),
                 "contrib": round(d * self._weight_for(item, s, float(stats.get(s, 0.5))), 3)}
                for s, d in item.effects.items()
            ]
            out.append(ScoredItem(item=item, score=score, driving=driving))
        return out

    # --- 2. 排序 -------------------------------------------------------
    def rank(self, scored: list[ScoredItem]) -> list[ScoredItem]:
        """按分降序排序(供后处理/观测)。"""
        return sorted(scored, key=lambda s: s.score, reverse=True)

    # --- 3. 后处理 selector(框架, 可覆写) ------------------------------
    def select(
        self,
        ranked: list[ScoredItem],
        stats: dict[str, float],
    ) -> Item | None:
        """在排序结果上做最终挑选。

        默认规则(框架): 只接受分数超过阈值的最高分物品, 否则返回 None(→idle)。
        若要加入"人物性格/当前活动/可得性/距离"等约束, 覆写本方法即可
        (ranked 已降序, 可用 stats / self._personality 做门槛或重排)。
        """
        for s in ranked:
            if s.score > self._threshold:
                return s.item
        return None

    # --- 4. 统一入口 ---------------------------------------------------
    def decide(self, stats: dict[str, float]) -> Item | None:
        """完整裁决: 取容器 -> 打分 -> 排序 -> selector -> 返回目标物品。

        Person.update 调用此方法得到"本 tick 要交互的物品"(None = 无事可做/idle)。
        """
        scored = self.score_all(stats)
        ranked = self.rank(scored)
        return self.select(ranked, stats)

    def decide_trace(self, stats: dict[str, float]) -> dict:
        """裁决 + 完整观测一次返回(前端展示用)。

        返回:
          - picked:   选中的物品(或 None=idle)
          - picked_id/name
          - reason:   人话缘由(选中物品的主要 driving 状态缺口/曲线)
          - ranked:   降序的全部物品评分 [{id,name,score,driving:[...]}]
        """
        scored = self.score_all(stats)
        ranked = self.rank(scored)
        picked = self.select(ranked, stats)

        def _driving_list(sc):
            return [
                {"signal": d["signal"], "level": d["level"], "need": d["need"],
                 "curve": d.get("curve", "linear"), "weight": d["weight"],
                 "contrib": d["contrib"]}
                for d in sc.driving
            ]

        ranked_ui = [
            {"id": sc.item.item_id,
             "name": getattr(sc.item, "name", sc.item.item_id),
             "score": round(sc.score, 3),
             "driving": _driving_list(sc)}
            for sc in ranked
        ]
        reason = ""
        picked_ui = None
        if picked is not None:
            picked_ui = next((r for r in ranked_ui if r["id"] == picked.item_id), None)
            if picked_ui and picked_ui["driving"]:
                parts = []
                for d in picked_ui["driving"]:
                    if d["contrib"] > 0:
                        parts.append(f"{d['signal']}缺{1-d['level']:.2f}"
                                     f"(曲线{d['curve']}→权重{d['weight']:.2f})")
                reason = " + ".join(parts) if parts else "评分最高"
        return {"picked": picked, "picked_id": picked.item_id if picked else None,
                "picked_name": (getattr(picked, "name", None) or picked.item_id)
                               if picked else None,
                "reason": reason, "ranked": ranked_ui}

    # --- 观测 ----------------------------------------------------------
    def scores(self, stats: dict[str, float]) -> dict[str, float]:
        """容器内全部物品当前得分(前端条形/观测)。"""
        return {s.item.item_id: round(s.score, 3) for s in self.score_all(stats)}

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Indicator(threshold={self._threshold})"
