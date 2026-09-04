"""brain —— decide() 纯函数 + utility。

定位: 由 Percept + signals 决定下一个 Intent(做什么)。纯函数: 不得修改任何
入参、不得访问全局状态。utility 打分迁移自旧 person/brain/indicator.py。
"""
from __future__ import annotations

from typing import Any, Mapping

from citysim.core.config import SIGNALS, SimConfig
from citysim.core.types import DecisionTrace, EntityView, Intent, Percept
from citysim.npc.goap import hunger_plan

# 分数低于此 => 不值得做(→ idle)。沿用旧 Person.setup_brain 默认 threshold。
UTILITY_THRESHOLD = 0.08


def _utility(
    e: EntityView,
    signals: Mapping[str, float],
    personality: Mapping[str, float],
) -> float:
    """候选实体效用分: u(e) = Σ_s affordance_delta_s * need_weight(s)。

    need_weight = 缺口 need(=1-level) × 性格倍率(personality)。缺省线性曲线
    (旧 Indicator: curve 缺省 linear=need)。非信号键(如 "provides:edible"
    这类 M2 临时标记)不参与打分。
    """
    total = 0.0
    for s, delta in e.affordances.items():
        if s not in SIGNALS:
            continue
        level = float(signals.get(s, 0.5))
        need = 1.0 - level
        weight = need * float(personality.get(s, 1.0))
        total += float(delta) * weight
    return total


def _hungry_plan(candidates: tuple[EntityView, ...], cfg: SimConfig,
                 signals: Mapping[str, float]) -> tuple[str, tuple[str, ...]] | None:
    """饿且无散落 edible 时, 找提供食物的 container → (target_id, plan)。"""
    if signals.get("hunger", 1.0) >= cfg.eat_hunger_threshold:
        return None
    if any("edible" in e.tags for e in candidates):
        return None
    for e in candidates:
        if "container" in e.tags and e.affordances.get("provides:edible", 0.0) > 0:
            plan = hunger_plan()
            if plan:
                return (e.entity_id, plan)
    return None


def decide(
    percept: Percept,
    signals: Mapping[str, float],
    personality: Mapping[str, float],
    kb: Any,                      # KnowledgeBase | None; M5 前传 None
    cfg: SimConfig,
    rng: Any,                     # random.Random, 固定种子保回放确定性
) -> Intent:
    """纯函数: 返回下一个 Intent。不修改任何入参、不访问全局状态。"""
    candidates = [e for e in percept.visible if e.claimable]

    # --- GOAP: 饿 → 从容器 取→吃 (优先于逐项打分) ---
    goap = _hungry_plan(tuple(candidates), cfg, signals)
    if goap is not None:
        target_id, plan = goap
        trace = DecisionTrace(
            ranked=((target_id, 0.0),),
            reason="饿: 食物在容器里, 先取再吃",
            plan=plan,
        )
        return Intent(kind="interact", target_id=target_id, trace=trace)

    # --- utility 打分 + 排序 ---
    scored = [(e.entity_id, _utility(e, signals, personality)) for e in candidates]
    ranked = tuple(sorted(scored, key=lambda t: (-t[1], t[0])))

    if not ranked or ranked[0][1] <= UTILITY_THRESHOLD:
        return Intent(
            kind="idle",
            target_id=None,
            trace=DecisionTrace(ranked=ranked, reason="信号充足或没有值得做的目标"),
        )

    best = ranked[0][1]
    tied = [x for x in ranked if x[1] == best]
    chosen = rng.choice(tied) if len(tied) > 1 else tied[0]
    entity_id, score = chosen

    return Intent(
        kind="interact",
        target_id=entity_id,
        trace=DecisionTrace(
            ranked=ranked,
            reason=f"目标 {entity_id} (utility={score:.3f})",
        ),
    )
