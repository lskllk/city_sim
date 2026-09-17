"""npc/brain/stockpile —— 囤货 = 目标存量模型。

这里没有任何"每种东西囤几个"的魔法数字: 目标存量由【保质期】推导 ——
    目标 = 每天消耗份数 × 保质期天数 × stock_fill × thrift
也就是"在坏掉之前我吃得完多少"。短保的东西自然囤得少。
"""
from __future__ import annotations

from citysim.core.config import SimConfig
from citysim.npc.memory import MemBase


def _home_stock(mem: MemBase, home: str) -> dict[str, float]:
    """我家里每种“能提供什么”还剩几个(按 afford 汇总 stock)。

    只看 located == home 的行 —— 店里的货不算“我家的存货”。
    """
    out: dict[str, float] = {}
    if not home:
        return out
    for row in mem.items():
        if row.located != home or not row.afford:
            continue
        out[row.afford] = out.get(row.afford, 0.0) + max(0.0, float(row.stock))
    return out


def _stock_target(cfg: SimConfig, sig: str, value: float,
                  shelf_life: int, thrift: float) -> float:
    """我该囤多少【份】(不是 0..1, 就是份数)。

        每天消耗份数 = (-metabolism[sig] × ticks_per_day) / value
        目标 = 每天消耗份数 × 保质期天数 × stock_fill × thrift

    —— “在它坏掉之前我吃得完多少”。短保的东西自然囤得少。
    不会坏的东西(无保质期)按 stock_default_days 算。
    """
    if value <= 0.0:
        return 0.0
    daily_drain = -min(0.0, float(cfg.metabolism.get(sig, 0.0)))         * float(cfg.ticks_per_day)
    if daily_drain <= 0.0:
        return 0.0
    per_day = daily_drain / value                     # 每天吃几份
    days = (float(shelf_life) / float(cfg.ticks_per_day)
            if shelf_life > 0 else cfg.stock_default_days)
    return per_day * days * cfg.stock_fill * max(0.0, float(thrift))


def _future_need(cfg: SimConfig, have: float, sig: str, value: float,
                 shelf_life: int, thrift: float) -> float:
    """【预期需求】= 家里缺口 / 目标存量(0..1)。

    这就是“囤货”: 不是“饿了才去买”, 而是“家里快没存货了 → 提前补”。

    目标存量【不是魔法数字】, 而是从保质期推导出来的:
        每天消耗份数 = (-metabolism[sig] × ticks_per_day) / value
        目标 = 每天消耗份数 × 保质期天数 × stock_fill × thrift
    —— 即“在它坏掉之前我吃得完多少”。所以**短保的东西自然囤得少**。
    不会坏的东西(无保质期)按 stock_default_days 算。
    """
    target = _stock_target(cfg, sig, value, shelf_life, thrift)
    if target <= 0.0:
        return 0.0
    return min(1.0, max(0.0, (target - have) / target))
