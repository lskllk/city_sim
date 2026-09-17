"""npc/brain/decide —— 纯打分: 候选 → 打分 → 选优(无状态)。

给定「记忆 + 自身状态」选一个 Intent, 不回写任何东西。
【何时重算 + 怎么把手上的事做完】在 npc/person/goal.py。

  decide_scored()  入口: 连打分一起回(观测/调试要看"为什么选了它")
  _choose()        把选中的候选分派成 Interact / Buy / MoveTo / Idle
"""
from __future__ import annotations

from typing import Mapping
from citysim.core.config import SimConfig
from citysim.core.types import Buy, DecisionTrace, Idle, Intent, Interact, MoveTo
from citysim.npc.memory import MemBase

from citysim.npc.brain.candidates import MAX_BUY_QTY, _gather_candidates, _self_use
from citysim.npc.brain.scoring import _score_candidates


def decide_scored(
    signals: Mapping[str, float],
    personality: Mapping[str, float],
    mem: MemBase,
    location_id: str,
    cfg: SimConfig,
    now_tick: int,
    self_id: str = "",
    travel_ticks: Mapping[str, int] | None = None,
    money: float = float("inf"),
    home: str = "",
    favor: Mapping[str, float] | None = None,
    workplace: str = "",
    leave_cost: float = 0.0,
) -> tuple[Intent, float]:
    """决策主算法(纯函数): 候选收集 → 评分 → 排序 → 选优分流, 多回一个得分。

    铁律: 只读【记忆 mem + 自身状态 signals/personality/location】,
      绝不看环境/现场(percept/world)。现场真值只在感知写入与执行失败反证时
      进入记忆; 打分自己永远不查现场。

    注: 记忆里的行**全部**参选(没有 fallback_need / REFLEX 筛选层),
      唯一的阀值在得分上(cfg.utility_threshold)。
    **只在空闲时调** —— 手上有事就做完再决策, 没有迟滞/抢占这一层。
    """
    cands = _gather_candidates(
        mem, signals, now_tick, self_id=self_id, home=home, cfg=cfg,
        future_weight=cfg.stock_future_weight,
        thrift=float(personality.get("thrift", 1.0)))
    scored, ranked, relevant = _score_candidates(
        cands, personality, location_id, cfg, travel_ticks, money, self_id,
        hour_f=(now_tick % max(1, cfg.ticks_per_day)) / 60.0,
        favor=favor, home=home,
        workplace=workplace, leave_cost=leave_cost)
    return _choose(scored, ranked, relevant, cfg, self_id, location_id, home)


def _choose(scored, ranked, relevant, cfg: SimConfig, self_id: str,
            location_id: str, home: str = "") -> tuple[Intent, float]:
    """[阶段4] 选优分流 —— 只凭记忆行字段, 不看现场。全不够格则 Idle。

    返回 (intent, score): Idle 时 score = 0。
    不判断"是否本地": 异地成本已算进 cost(真实行走 tick)。
    自己的/自家住所里的(授权人)/免费公共 → Interact; **在售 → Buy**(要付钱)。
    """
    thresh = cfg.utility_threshold
    for item_id, sig, eff, loc, row, qty, driver in scored:
        if eff <= thresh:
            continue
        # 免费自用 → Interact; 在售(只会是囤货候选) → Buy。
        self_use = _self_use(row, self_id, home)
        for_sale = row.price > 0 and not self_use
        if not (self_use or for_sale):
            continue
        if not loc:                       # 无地点信息 → 不可达
            continue
        if loc != location_id:            # 异地 → 前往(到地方下一 tick 再动手)
            return MoveTo(
                dest=loc,
                trace=DecisionTrace(
                    ranked=ranked,
                    reason=f"记忆: {item_id} 能解 {sig} → 去 {loc}",
                    features={"driver": driver},
                    relevant_signals=relevant)), eff
        if for_sale:                      # 在店里 → 付钱买(不再白拿)
            n = max(1, min(int(qty), MAX_BUY_QTY))   # 一次补到目标存量(且钱够)
            return Buy(
                item_id=item_id, qty=n,
                trace=DecisionTrace(
                    ranked=ranked,
                    reason=f"买 {item_id} ×{qty} (¥{row.price:g}, score={eff:.3f})",
                    features={"driver": driver},
                    relevant_signals=relevant)), eff
        return Interact(
            target_id=item_id,
            trace=DecisionTrace(
                ranked=ranked,
                reason=f"目标 {item_id} (score={eff:.3f})",
                features={"driver": driver},
                relevant_signals=relevant)), eff
    return Idle(
        trace=DecisionTrace(
            ranked=ranked,
            reason="信号充足或没有值得做的目标",
            relevant_signals=relevant)), 0.0
