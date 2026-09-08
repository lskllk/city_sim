"""brain —— decide() 纯函数 + utility。

定位: 由 Percept + signals 决定下一个 Intent(做什么)。纯函数: 不得修改任何
入参、不得访问全局状态。utility 打分迁移自旧 person/brain/indicator.py。
"""
from __future__ import annotations

from math import cos, pi
from typing import Any, Mapping

from citysim.core.config import SIGNALS, SimConfig
from citysim.core.types import (
    Buy,
    DecisionTrace,
    Idle,
    Intent,
    Interact,
    MoveTo,
    Percept,
)

# 分数低于此 => 不值得做(→ idle)。沿用旧 Person.setup_brain 默认 threshold。
# 需求急迫度幂次: weight = deficit**power; 线性会让"精力差 12%"也去打盹/喝水。
# 幂>1 放大真实缺口, 压住无谓微需求; 两值现由 sim.toml [utility] 承载(13)。


def decide(
    percept: Percept,
    signals: Mapping[str, float],
    personality: Mapping[str, float],
    kb: Any,
    cfg: SimConfig,
    money: float = 0.0,           # 资金(只减不增; 决定能否 Buy)
) -> Intent:
    """纯函数: 从 KB 打分, 按分数分流 interact/buy/move_to。

    打分 = need^power × afford值 × 性格倍率 × 置信度;
    异地候选另乘移动折扣 move_penalty(移动成本折算进分, 不做本地绝对优先)。
    视野可 claim 且同地:
      - 在售商品(price>0 且 owner="")且资金富余 → buy(搬回家); 否则跳过;
      - 其它 → interact。
    不同地点且有 located_at → move_to。
    """
    visible = {e.entity_id: e for e in percept.visible if e.claimable}
    power = cfg.utility_power
    thresh = cfg.utility_threshold

    scored = []
    needs: dict[str, float] = {}           # TASK001 结构化 trace: 相关信号缺口
    for f in kb.query(relation="affords"):
        sig = f.obj
        if sig not in SIGNALS or f.value <= 0 or f.confidence < 0.3:
            continue
        need = 1.0 - float(signals.get(sig, 0.5))
        if need <= 0:
            continue
        needs[sig] = need
        score = (need ** power) * f.value \
            * float(personality.get(sig, 1.0)) * f.confidence

        loc = ""
        loc_facts = kb.query(subject=f.subject, relation="located_at")
        if loc_facts:
            loc = str(loc_facts[0].obj)
        local = (loc == percept.location_id)
        if loc and not local:
            # 异地候选需付出移动成本(耗时/精力) → 效用折扣。
            # 不做本地绝对优先: 折扣直接进分数, 异地足够好时自然压过本地。
            score *= cfg.move_penalty
        scored.append((f.subject, sig, score, loc, local, f))

    # 按打折后分数降序, subject 稳定(不设本地绝对优先 —— 异地已带移动折扣)
    scored.sort(key=lambda x: (-x[2], x[0]))
    ranked = tuple((s[0], s[2]) for s in scored)
    relevant = tuple(sorted(needs.items(), key=lambda kv: (-kv[1], kv[0])))

    for subject, sig, score, loc, local, fact in scored:
        if score <= thresh:
            continue
        loc_facts = kb.query(subject=subject, relation="located_at")
        used = (fact.fact_id,) + tuple(lf.fact_id for lf in loc_facts[:1])
        if local:
            e = visible.get(subject)
            if e is None:
                continue
            if e.price > 0 and e.owner == "":
                # 在售商品只能买(严格搬回家), 不能就地用。
                # 买不起 → 跳过; 买得起但资金无富余(愿买度低)→ 也跳过,
                # 落到下一候选(可能是本地免费/可用的替代) —— 钱越少越不买。
                if money < e.price:
                    continue
                willing = _willingness(money, e.price, cfg.buy_margin)
                if willing * score <= thresh:
                    continue
                return Buy(
                    item_id=subject,
                    trace=DecisionTrace(
                        ranked=ranked,
                        reason=(f"购买 {subject} 解 {sig} "
                                f"(score={score:.3f}×愿买{willing:.2f}, "
                                f"价格={e.price:.1f})"),
                            used_fact_ids=used,
                            relevant_signals=relevant))
            return Interact(
                target_id=subject,
                trace=DecisionTrace(
                    ranked=ranked,
                    reason=f"目标 {subject} (score={score:.3f})",
                    used_fact_ids=used,
                    relevant_signals=relevant))
        if loc:
            return MoveTo(
                dest=loc,
                trace=DecisionTrace(
                    ranked=ranked,
                    reason=f"知识: {subject} 能解 {sig} → 去 {loc}",
                    used_fact_ids=used,
                    relevant_signals=relevant))

    return Idle(
        trace=DecisionTrace(
            ranked=ranked,
            reason="信号充足或没有值得做的目标",
            relevant_signals=relevant))


def _willingness(money: float, price: float, margin: float) -> float:
    """愿买度 0..1: 资金相对价格越富余越愿买。

    willing = clamp01((money - price) / (price * margin)).
    money <= price → 0; money >= price*(1+margin) → 1。钱越少越不买。
    """
    if price <= 0:
        return 1.0
    return max(0.0, min(1.0, (money - price) / (price * max(margin, 1e-6))))


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
