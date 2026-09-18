"""npc/brain/candidates —— 候选收集: 记忆里的每一行 → 一条候选。

两条路分开:
  · 免费自用(自家/住所授权/公共/本公司店员) → 满足【当前】需求,
    driver="now"(就地吃/睡/用, 出门只是走过去);
  · 在售 → 只当【囤货】, driver="future", need 按目标存量缺口算
    (家里存货涨上来 → 缺口归零 → 不会重复买)。
无家者没有囤货概念 → 退化为"就地买来吃"。
"""
from __future__ import annotations

import math
from typing import Mapping
from citysim.core.config import SimConfig
from citysim.npc.memory import MemBase

from citysim.npc.brain.stockpile import _future_need, _home_stock, _stock_target

MAX_BUY_QTY = 30      # 单次购买上限(只是防手滑; 真正的量由目标存量决定)


def _gather_candidates(mem: MemBase, signals: Mapping[str, float],
                       now_tick: int,  *, self_id: str = "", home: str = "",
                       cfg: SimConfig | None = None,
                       future_weight: float = 0.0, thrift: float = 1.0,
                       location_id: str = "", workplace: str = ""):
    """[阶段1] 候选收集。**用=免费自用; 买=只补货**, 两条路分开:

    1. 免费自用(自家/住所授权/公共/本公司店员) → 满足当前需求
       need = 1 − signal, driver="now"(就地吃/睡/用, 出门只是走过去)。
    2. 在售(非自用) → 只当【囤货】: need = w × 目标存量缺口, driver="future"。
       家里存货涨上来 → 缺口自然归零 → 不会重复买(不再需要“供贷抵消”补丁)。
       无家者没有“囤货”概念 → 退化为“就地买来吃”。

    硬门槛: afford/value 缺失 / stock==0 / 失败冷却中的行 → 不进候选。
    返回 [(row, sig, need, want, driver), ...]。
    """
    stock = _home_stock(mem, home) if (cfg is not None and home) else {}
    out = []
    for row in mem.items():
        if row.cool_until and row.cool_until > now_tick:
            continue
        sig = row.afford
        if not sig or row.value <= 0:
            continue
        if int(getattr(row, "stock", -1)) == 0:
            continue
        now = 1.0 - float(signals.get(sig, 1.0))
        if _self_use(row, self_id, home, workplace):
            out.append((row, sig, now, 1, "now"))
            continue
        if row.price <= 0:            # 别人的东西又不卖 → 用不了
            continue
        if not home:                   # 无家: 买来就地吃(送货到当前位置)
            out.append((row, sig, now, 1, "now"))
            continue
        # 囤货: 只对【会消耗的】且【不在家】的货
        consumable = "consumable" in tuple(getattr(row, "tags", ()) or ())
        if not consumable or row.located == home:
            continue
        have = float(stock.get(sig, 0.0))
        shelf = int(getattr(row, "shelf_life_ticks", 0))
        fut = _future_need(cfg, have, sig, row.value, shelf, thrift)
        if fut <= 0.0:
            continue
        target = _stock_target(cfg, sig, row.value, shelf, thrift)
        want = max(1, int(math.ceil(target - have))) if target > 0 else 1
        out.append((row, sig, future_weight * fut, want, "future"))

    # ★ 没辙了: 某个需求【一个候选都没有】→ 去"我记得能解它的地方"看看。
    #   (地点行记着"这儿能解什么"; 到了那儿会触发一次观察 → 重新发现那样东西。)
    #   只在这条需求彻底没着落时才生 —— 有真候选时它不该来抢。
    got = {sig for _r, sig, *_ in out}
    home_like = {home} if home else set()
    for row in mem.items():
        if row.afford or "place" not in (row.tags or ()):
            continue
        if row.located in home_like or row.located == location_id:
            continue                       # 已经在家/就在这儿 → 不用"去看看"
        for sig in sorted(row.attrs.get("affords") or ()):
            if sig in got:
                continue
            need = 1.0 - float(signals.get(sig, 1.0))
            if need <= 0.0:
                continue
            got.add(sig)
            out.append((row, sig, need, 1, "explore"))
    return out


def _self_use(row, self_id: str, home: str, workplace: str = "") -> bool:
    """我能不能【免费直接使用】它(单一口径, 候选/打分/分流共用)。

    免费自用 = 自己的 / 我自己家的 / ★我上班的店 / 住所授权(free_use) /
    无主且免费的公共。

    ★ 为什么要认 `workplace`: `free_use`(含"本公司店员免费用")是【感知时】
      由世界按【观察者】算好的标记 —— 而听来的行没有它(也不可能有: 同一个东西
      对不同的人结论不同)。于是店员只靠记忆时, 会把自己店里"免费能拿"的货
      当成"要排队买" → 他去排自己店的队 → 没人守台 → 全店死锁(实测全城饿死)。
      "我是这家店的店员"是【关于自己的第一手知识】, 不该依赖那条标记。
    """
    if self_id and row.owner == self_id:
        return True
    if home and row.located == home:
        return True
    if workplace and row.located == workplace:
        return True
    if bool(getattr(row, "free_use", False)):
        return True
    if bool(getattr(row, "household", False)):
        return True
    return row.owner == "" and row.price <= 0
