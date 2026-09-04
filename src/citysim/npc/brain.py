"""brain —— decide() 纯函数 + utility。

定位: 由 Percept + signals 决定下一个 Intent(做什么)。纯函数: 不得修改任何
入参、不得访问全局状态。utility 打分迁移自旧 person/brain/indicator.py。
"""
from __future__ import annotations

from math import cos, pi
from typing import Any, Mapping

from citysim.core.config import SIGNALS, SimConfig
from citysim.core.types import DecisionTrace, EntityView, Intent, Percept
from citysim.npc.goap import hunger_plan

# 分数低于此 => 不值得做(→ idle)。沿用旧 Person.setup_brain 默认 threshold。
# 需求急迫度幂次: weight = deficit**power; 线性会让"精力差 12%"也去打盹/喝水。
# 幂>1 放大真实缺口, 压住无谓微需求; 两值现由 sim.toml [utility] 承载(13)。


def _utility(
    e: EntityView,
    signals: Mapping[str, float],
    personality: Mapping[str, float],
    power: float,
) -> float:
    """候选实体效用分: u(e) = Σ_s affordance_delta_s * need_weight(s)。

    need_weight = 缺口 need(=1-level) 经急迫幂次映射 × 性格倍率(personality)。
    仅信号键参与打分; 供食/产物等语义经 EntityView.provides/food_source 承载。
    """
    total = 0.0
    for s, delta in e.affordances.items():
        if s not in SIGNALS:
            continue
        level = float(signals.get(s, 0.5))
        need = 1.0 - level
        weight = (need ** power) * float(personality.get(s, 1.0))
        total += float(delta) * weight
    return total


def _hungry_plan(candidates: tuple[EntityView, ...], cfg: SimConfig,
                 signals: Mapping[str, float],
                 actions=None) -> tuple[str, tuple[str, ...]] | None:
    """饿且无散落 edible 时, 找提供食物的 container → (target_id, plan)。"""
    if signals.get("hunger", 1.0) >= cfg.eat_hunger_threshold:
        return None
    if any("edible" in e.tags for e in candidates):
        return None
    for e in candidates:
        if "container" in e.tags and e.food_source:
            plan = hunger_plan(actions)
            if plan:
                return (e.entity_id, plan)
    return None


def _is_edible_obj(kb: Any, obj: Any) -> bool:
    """判 obj 是否可食类别(m5-rectify 11): 直接类别 'edible', 或经 KB is_a
    (meal_simple is_a edible) 归到类别。不再硬编码品名。"""
    if obj == "edible":
        return True
    return any(f.subject == obj and f.obj == "edible"
               for f in kb.query(relation="is_a"))


def _kb_go_intent(kb: Any, percept: Percept, signals: Mapping[str, float],
                  cfg: SimConfig) -> Intent | None:
    """M5: 饿了但视野无食物时, 按 KB 里"哪里有食物"发起 move_to。

    谓词由 KB 派生: contains/sells 命中可食 obj 且 conf>=0.3 → 该地有食;
    需要 located_at 才知道去哪。返回 move_to(loc)。kb=None 时永不走此分支。
    """
    if signals.get("hunger", 1.0) >= cfg.eat_hunger_threshold:
        return None
    # 视野里有可吃的就不该出走(看得到 -> 已由可见路径处理)
    if any("edible" in e.tags and e.claimable for e in percept.visible):
        return None
    visible_ids = {e.entity_id for e in percept.visible}
    sources: list[tuple[str, Any]] = []
    for f in kb.query(relation="contains"):
        if f.obj == "edible" and f.confidence >= 0.3:
            sources.append((f.subject, f))
    for f in kb.query(relation="sells"):
        if _is_edible_obj(kb, f.obj) and f.confidence >= 0.3:
            sources.append((f.subject, f))
    if not sources:
        return None
    # 稳定: 按 (subject) 排序取第一个知识源
    for subj, fact in sorted(sources, key=lambda t: t[0]):
        if subj in visible_ids:
            continue
        loc_facts = kb.query(subject=subj, relation="located_at")
        if not loc_facts:
            continue
        loc = loc_facts[0].obj
        if not loc:
            continue
        # T5①: 目标就在当前地点则不该发起 move_to(避免 30t 原地打转)
        if loc == percept.location_id:
            continue
        used = (fact.fact_id, loc_facts[0].fact_id)
        trace = DecisionTrace(
            ranked=((subj, 0.0),),
            reason=f"知识: {subj} 有食物 → 去 {loc}",
            used_fact_ids=used,
        )
        return Intent(kind="move_to", target_id=loc, trace=trace)
    return None


def _kb_afford_intent(kb: Any, percept: Percept, signals: Mapping[str, float],
                      signal: str, threshold: float,
                      afford_objs: tuple[str, ...],
                      tag_hint: str, action_verb: str) -> Intent | None:
    """通用觅补: 某需求低(signal<threshold)且视野无可用物(tag_hint)时,
    按注入知识(affords {afford_objs} + located_at)去"解需求之地"。

    与 _kb_go_intent(食) 对称: 不是引擎硬编码"回自家", 而是由每人 INJECTED
    的 affords/located_at 事实驱动(elm_lane: 只注入自家寝位/自家水源)。
    """
    if signals.get(signal, 1.0) >= threshold:
        return None
    if any(tag_hint in e.tags and e.claimable for e in percept.visible):
        return None
    visible_ids = {e.entity_id for e in percept.visible}
    cands = [(f.subject, f) for f in kb.query(relation="affords")
             if f.obj in afford_objs and f.confidence >= 0.3]
    if not cands:
        return None
    for subj, fact in sorted(cands, key=lambda t: t[0]):
        if subj in visible_ids:
            continue
        loc_facts = kb.query(subject=subj, relation="located_at")
        if not loc_facts:
            continue
        loc = loc_facts[0].obj
        if not loc or loc == percept.location_id:
            continue
        return Intent(
            kind="move_to", target_id=loc,
            trace=DecisionTrace(ranked=((subj, 0.0),),
                                reason=f"知识: {subj} 能{action_verb} → 去 {loc}"),
        )
    return None


def decide(
    percept: Percept,
    signals: Mapping[str, float],
    personality: Mapping[str, float],
    kb: Any,                      # KnowledgeBase | None; M5 前传 None
    cfg: SimConfig,
    rng: Any,                     # random.Random, 固定种子保回放确定性
    actions: Any = None,          # GOAP 动作库(装配期注入); None 用默认
) -> Intent:
    """纯函数: 返回下一个 Intent。不修改任何入参、不访问全局状态。"""
    candidates = [e for e in percept.visible if e.claimable]
    thresh = cfg.utility_threshold
    power = cfg.utility_power

    # --- GOAP: 饿 → 从容器 取→吃 (优先于逐项打分) ---
    goap = _hungry_plan(tuple(candidates), cfg, signals, actions)
    if goap is not None:
        target_id, plan = goap
        trace = DecisionTrace(
            ranked=((target_id, 0.0),),
            reason="饿: 食物在容器里, 先取再吃",
            plan=plan,
        )
        return Intent(kind="interact", target_id=target_id, trace=trace)

    # --- M5 KB: 视野无食物但知识说别处有 → move_to(kb!=None 才走, 保平价) ---
    if kb is not None:
        mv = _kb_go_intent(kb, percept, signals, cfg)
        if mv is not None:
            return mv

    # --- KB 觅补(睡/渴): 需求低、本地无可用 → 按注入知识去自家 (对称于觅食) ---
    if kb is not None:
        sl = _kb_afford_intent(kb, percept, signals,
                               "energy", 0.35, ("sleep", "energy"),
                               "sleepable", "睡")
        if sl is not None:
            return sl
        dr = _kb_afford_intent(kb, percept, signals,
                               "thirst", 0.4, ("drink", "thirst"),
                               "drink", "喝水")
        if dr is not None:
            return dr

    # --- utility 打分 + 排序 ---
    scored = [(e.entity_id, _utility(e, signals, personality, power))
              for e in candidates]
    ranked = tuple(sorted(scored, key=lambda t: (-t[1], t[0])))

    if not ranked or ranked[0][1] <= thresh:
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


# ----------------------------------------------------------------------
# 清醒度 / 重评节律(主循环调度用, 迁移自旧 brain/arousal.py + review.py)
# ----------------------------------------------------------------------
TROUGH_HOUR = 3.0      # 生物钟低谷时刻(困)
PEAK_HOUR = 15.0       # 峰值时刻(最清醒)


def circadian(hour_f: float) -> float:
    """纯生物钟分量(0..1): 余弦拟合, 谷≈0.15, 峰≈1.0。"""
    phase = 2.0 * pi * (hour_f - PEAK_HOUR) / 24.0
    base = (cos(phase) + 1.0) / 2.0
    return 0.15 + 0.85 * base


def arousal(hour_f: float, energy: float, hunger: float) -> float:
    """清醒度 0..1: 生物钟 × 精力乘性, 饥饿轻微拖累。"""
    energy = max(0.0, min(1.0, float(energy)))
    hunger = max(0.0, min(1.0, float(hunger)))
    level = circadian(hour_f) * (0.4 + 0.6 * energy)
    level -= 0.2 * (1.0 - hunger)
    return max(0.0, min(1.0, level))


def review_interval_ticks(
    arousal_value: float,
    cfg: SimConfig,
    rng: Any = None,
) -> int:
    """清醒度(0..1) -> 距下次重评的 tick 间隔, clamp 到 [review_min, review_max]。

    清醒度高 => 间隔短; 可选 rng 抖动 ±1 避免同拍。
    """
    a = max(0.0, min(1.0, float(arousal_value)))
    lo, hi = cfg.review_min_ticks, cfg.review_max_ticks
    span = hi - lo
    interval = int(round(hi - span * a))
    interval = max(lo, interval)
    if rng is not None:
        interval = max(lo, interval + int(rng.randint(-1, 1)))
    return interval
