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
                       future_weight: float = 0.0, thrift: float = 1.0):
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
        if _self_use(row, self_id, home):
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
    return out


def _self_use(row, self_id: str, home: str) -> bool:
    """我能不能【免费直接使用】它(单一口径, 候选/打分/分流共用)。

    免费自用 = 自己的 / 我自己家的 / 住所授权(free_use, 含本公司店员) /
    无主且免费的公共。注意 `free_use` 是感知时由世界算好的。
    """
    if self_id and row.owner == self_id:
        return True
    if home and row.located == home:
        return True
    if bool(getattr(row, "free_use", False)):
        return True
    if bool(getattr(row, "household", False)):
        return True
    return row.owner == "" and row.price <= 0
