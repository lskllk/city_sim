"""sim/pulses —— 场景脉冲(世界侧确定性脚本, elm_lane B 地基)。

每 tick 由 run_tick 开头调用 apply(): 把匹配当天/时刻的脉冲应用到实体
(改库存/永久停业), 从而驱动"知识自己变旧 → refute/改道/谣言"。

normalize(raw, ticks_per_day):
  raw 形如 {"at":"daily HH:MM"|"day N HH:MM", "op":..., "target":..., "value":n}
  → 归一为 {mode:'daily'|'once', minute:0..1439, day, op, target, value}
"""
from __future__ import annotations

from typing import Any


def _parse_minute(hhmm: str) -> int:
    hh, _, mm = hhmm.partition(":")
    return int(hh) * 60 + int(mm)


def normalize(raw: list[dict], ticks_per_day: int) -> list[dict]:
    out = []
    for p in raw or []:
        at = str(p.get("at", ""))
        if at.startswith("daily "):
            out.append({"mode": "daily", "minute": _parse_minute(at[len("daily "):]),
                        "day": 0, "op": p["op"], "target": p["target"],
                        "value": p.get("value")})
        elif at.startswith("day "):
            rest = at[len("day "):]
            day_s, _, hhmm = rest.partition(" ")
            out.append({"mode": "once", "day": int(day_s),
                        "minute": _parse_minute(hhmm), "op": p["op"],
                        "target": p["target"], "value": p.get("value")})
    return out


def _apply_op(world, p: dict, tick: int) -> None:
    e = world.entities.get(p["target"])
    if e is None:
        return
    op = p["op"]
    before = e.stock
    if op == "set_stock":
        if p["value"] is not None:
            e.stock = int(p["value"])
    elif op == "close_forever":
        e.open_hours = []                 # 永久停业 → 感知为空 → refute
        if p["value"] is not None:
            e.stock = int(p["value"])
    # TASK001 可观察世界变化: audience=[] 只进日志/UI, 不塞信箱
    world.bus.publish(world.bus.make(
        tick, "stock_changed", e.entity_id,
        {"audience": [], "op": op, "stock_before": before,
         "stock_after": e.stock}))


def apply(world, scheduled: list[dict], tick: int, ticks_per_day: int) -> None:
    for p in scheduled:
        if p["mode"] == "daily":
            if tick % ticks_per_day == p["minute"]:
                _apply_op(world, p, tick)
        else:  # once
            if tick == p["day"] * ticks_per_day + p["minute"]:
                _apply_op(world, p, tick)
