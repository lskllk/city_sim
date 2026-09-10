"""brain —— decide() 纯函数 + utility。

定位: 由 Percept + signals 决定下一个 Intent(做什么)。纯函数: 不得修改任何
入参、不得访问全局状态。utility 打分迁移自旧 person/brain/indicator.py。
"""
from __future__ import annotations

from math import cos, pi
from typing import Any, Mapping

from citysim.core.config import SIGNALS, SimConfig
from citysim.core.types import (
    DecisionTrace,
    Idle,
    Intent,
    Interact,
    MoveTo,
    Percept,
)
from citysim.npc.memory import MemBase, MemItem


def perceive_into(mem: MemBase, percept: Percept, tick: int) -> None:
    """感知 → 记忆(写入): 把当前可见实体 upsert 进记忆库。非纯函数。

    同地 re-obs: 现场为准, 整行覆盖(located/owner/claimed/afford/price/…)并刷新
    believe/remember/last_seen。只 upsert 可见实体, 不做证伪删行(由上层策略定)。
    """
    for v in percept.visible:
        # TODO: affordances 多键 dict → 决定单值 or dict(MemItem.afford 现单值)
        afford, value = (next(iter(v.affordances.items()), ("", 0.0)))
        # owner 直接存世界真值 id(person_id/company_id/""=无主)：判定"自己的"靠
        # decide 的 self_id 比对, 不再用 "me" 哨兵。claimed 语义待对齐。
        claimed = not v.claimable
        row = mem.get(v.entity_id)
        if row is None:
            mem.set(MemItem(
                item_id=v.entity_id, located=v.location_id,
                owner=v.owner, claimed=claimed, afford=afford, value=float(value),
                price=v.price, believe=1.0, remember=1.0, last_seen=tick))
        else:
            mem.update(
                v.entity_id, located=v.location_id, owner=v.owner,
                claimed=claimed, afford=afford or row.afford,
                value=float(value) if value else row.value,
                price=v.price, believe=1.0, remember=1.0, last_seen=tick)


BELIEF_MIN = 0.3   # 记忆行 believe 低于此 → 不作为决策候选
FORGET_DEFAULT = 0.1  # remember 低于此 → 遗忘删除(默认阈值)


def forget(mem: MemBase, now_tick: int, half_life_ticks: int,
           forget_threshold: float = FORGET_DEFAULT) -> int:
    """遗忘策略: 按 last_seen 把 remember 半衰衰减, 低于阈值删行。

    返回值 = 本次被遗忘删除的 item 数。何时调用/半衰/阈值由上层定(如每游戏日)。
    """
    gone = 0
    for r in mem.items():
        dt = max(0, now_tick - r.last_seen)
        if dt <= 0:
            continue
        rem = r.remember * (0.5 ** (dt / max(1, half_life_ticks)))
        if rem < forget_threshold:
            mem.delete(r.item_id)
            gone += 1
        else:
            mem.update(r.item_id, remember=rem)
    return gone


def decide(
    signals: Mapping[str, float],
    personality: Mapping[str, float],
    mem: MemBase,
    location_id: str,             # 自身状态: 我在哪(决策不看环境 percept)
    cfg: SimConfig,
    now_tick: int,                # 当前 tick(过滤失败冷却 cool_until)
    self_id: str = "",            # 自身身份 id(判定"自己的"用品)
) -> Intent:
    """决策主算法。纯函数。铁律:

      决策只读【记忆 mem + 自身状态 signals/personality/location】,
      绝不看环境/现场(percept/world)。现场真值只在感知写入(observe)与执行失败
      反证时进入记忆; decide 自己永远不查现场。

    流程: 候选收集 → 评分(异地乘移动折扣) → 排序 → 选优分流(只凭记忆行字段)。
    """
    cands = _gather_candidates(mem, signals, cfg, now_tick)
    scored, ranked, relevant = _score_candidates(
        cands, personality, location_id, cfg)
    return _choose(scored, ranked, relevant, cfg, self_id, location_id)


def _gather_candidates(mem: MemBase, signals: Mapping[str, float],
                       cfg: SimConfig, now_tick: int):
    """[阶段1] 候选收集: 记忆行 → 有缺口的需求候选。

    取 afford∈SIGNALS 且 value>0 且 believe>=BELIEF_MIN 且 need=1-signal>0;
    且未被失败冷却屏蔽(cool_until<=now)。返回 [(row, sig, need), ...]。
    """
    out = []
    for row in mem.items():
        if row.cool_until and row.cool_until > now_tick:
            continue          # 失败冷却中(如厕所刚被占), 稍后再看
        sig = row.afford
        if sig not in SIGNALS or row.value <= 0 or row.believe < BELIEF_MIN:
            continue
        need = 1.0 - float(signals.get(sig, 1.0))
        if need <= 0:
            continue
        out.append((row, sig, need))
    return out


def _score_candidates(cands, personality: Mapping[str, float],
                      location_id: str, cfg: SimConfig):
    """[阶段2+3] 评分+排序: eff=need^power×value×personality×believe;

    异地(row.located≠location_id)乘 move_penalty。返回 (scored, ranked, relevant)。
    """
    power = cfg.utility_power
    needs: dict[str, float] = {}
    scored = []
    for row, sig, need in cands:
        needs[sig] = need
        eff = (need ** power) * row.value \
            * float(personality.get(sig, 1.0)) * row.believe
        # 异地(MoveTo)成本直接在此乘折扣; 不为"是否本地"单独留分支
        if row.located and row.located != location_id:
            eff *= cfg.move_penalty
        scored.append((row.item_id, sig, eff, row.located, row))
    scored.sort(key=lambda x: (-x[2], x[0]))
    ranked = tuple((s[0], round(s[2], 4)) for s in scored)
    relevant = tuple(sorted(needs.items(), key=lambda kv: (-kv[1], kv[0])))
    return scored, ranked, relevant


def _choose(scored, ranked, relevant, cfg: SimConfig, self_id: str,
            location_id: str) -> Intent:
    """[阶段4] 选优分流 —— 只凭记忆行字段, 不看现场。全不够格则 Idle。

    不判断"是否本地": 异地成本已在 _score_candidates 乘过 move_penalty。
    统一先过"能不能用"(自己的 owner==self_id / 免费公共 owner=="" 且 price<=0);
    能用者: 在异地 → MoveTo, 否则 → Interact。在售/他人所有的跳过。
    """
    thresh = cfg.utility_threshold
    for item_id, sig, eff, loc, row in scored:
        if eff <= thresh:
            continue
        # 能不能用: 自己的 or 免费公共; 否则(在售/他人所有)跳过
        mine = bool(self_id) and row.owner == self_id
        free_public = row.owner == "" and row.price <= 0
        if not (mine or free_public):
            continue
        if not loc:                       # 无地点信息 → 不可达
            continue
        if loc != location_id:            # 异地 → 前往(成本已入分)
            return MoveTo(
                dest=loc,
                trace=DecisionTrace(
                    ranked=ranked,
                    reason=f"记忆: {item_id} 能解 {sig} → 去 {loc}",
                    used_fact_ids=(),
                    relevant_signals=relevant))
        return Interact(
            target_id=item_id,
            trace=DecisionTrace(
                ranked=ranked,
                reason=f"目标 {item_id} (score={eff:.3f})",
                used_fact_ids=(),
                relevant_signals=relevant))
    return Idle(
        trace=DecisionTrace(
            ranked=ranked,
            reason="信号充足或没有值得做的目标",
            used_fact_ids=(),
            relevant_signals=relevant))


# ----------------------------------------------------------------------
# 清醒度 / 重评节律(主循环调度用)
# 生物钟与清醒度系数已参数化进 config [wake](见 SimConfig), 本模块零魔法数字。
# ----------------------------------------------------------------------

def circadian(hour_f: float, cfg: SimConfig) -> float:
    """纯生物钟分量(0..1): 单余弦拟合, 峰在 cfg.peak_hour, 谷在 ±12h。

    circ = circadian_min + circadian_amp * peakcurve(hour)
    峰(peak) → min+amp; 谷(peak±12) → min。
    """
    phase = 2.0 * pi * (hour_f - cfg.peak_hour) / 24.0
    curve = (1.0 + cos(phase)) / 2.0          # 峰=1, 谷=0
    return cfg.circadian_min + cfg.circadian_amp * curve


def arousal(hour_f: float, energy: float, hunger: float,
            cfg: SimConfig) -> float:
    """清醒度 0..1: 生物钟 × (energy_floor + energy_gain·energy), 饥饿轻微拖累。"""
    energy = max(0.0, min(1.0, float(energy)))
    hunger = max(0.0, min(1.0, float(hunger)))
    level = circadian(hour_f, cfg) * (cfg.energy_floor + cfg.energy_gain * energy)
    level -= cfg.hunger_penalty * (1.0 - hunger)
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
