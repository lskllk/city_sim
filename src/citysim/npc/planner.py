"""planner —— 计划【从哪来】: 把作者写的计划脚本变成当天的 PlanEntry[]。

分工:
  schedule.py  计划表的【运行时状态机】(今天这批条子怎么执行/到期/中断)
  planner.py   计划【从哪来】(明天的条子由谁产出) —— 只有这一件事

现状只有一种来源: 场景 JSON 的 `plans` 段(导演脚本 —— 作者负责 target 存在,
执行时不查记忆)。不设计划器 = **纯 utility 驱动**。

★ 为什么不做"时刻表"式的日计划器:
  吃饭/睡觉是【需求】, 由 utility 主导(energy 到点自然去睡) —— 写进计划表
  等于用时钟驱动行为。计划表只留【有事在等人】的承诺: 上班 / 上学 / 约会。
  (原来还挂着一套 LLM 计划器: 它让模型输出 "at HH:MM → interact 谁",
   正是上面被否掉的"时刻 → 行为", 所以整条路已删除。)
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from citysim.core.types import Buy, Interact, MoveTo
from citysim.npc.schedule import PlanEntry


def parse_clock(s: str) -> int | None:
    """"HH:MM" → 当天分钟 0..1439; 非法返回 None。"""
    hh, sep, mm = s.strip().partition(":")
    if sep == "" or not (hh.isdigit() and mm.isdigit()):
        return None
    h, m = int(hh), int(mm)
    if 0 <= h < 24 and 0 <= m < 60:
        return h * 60 + m
    return None


def _at_minute(item: Mapping[str, Any]) -> int | None:
    """条目时间: 优先 'at'("HH:MM"), 兼容 'at_minute'(int, 0..1439)。"""
    if "at" in item:
        return parse_clock(str(item["at"]))
    v = item.get("at_minute")
    if isinstance(v, int) and 0 <= v < 1440:
        return v
    return None


def entries_from_spec(spec: Any, day_start_tick: int,
                      prefix: str = "p") -> list[PlanEntry]:
    """计划脚本 → PlanEntry[]（按 at_tick 排序; 结构不对的那条丢掉, 不崩）。

    spec: [{"id","at":"HH:MM"|"at_minute", "intent":"interact|buy|move_to",
            "target"|"dest": ...}, ...]
    同刻保持脚本顺序(稳定排序)。
    """
    if not isinstance(spec, list):
        return []
    out: list[PlanEntry] = []
    for i, item in enumerate(spec):
        if not isinstance(item, dict):
            continue
        minute = _at_minute(item)
        if minute is None:
            continue
        eid = str(item.get("id") or f"{prefix}{i}")
        at = day_start_tick + minute
        kind = item.get("intent")
        if kind == "interact" and item.get("target"):
            out.append(PlanEntry(eid, at, Interact(str(item["target"]))))
        elif kind == "buy" and item.get("target"):
            out.append(PlanEntry(eid, at,
                                 Buy(str(item["target"]),
                                     qty=max(1, int(item.get("qty", 1))))))
        elif kind == "move_to" and item.get("dest"):
            out.append(PlanEntry(eid, at, MoveTo(dest=str(item["dest"]))))
    out.sort(key=lambda e: e.at_tick)
    return out


class ScriptedPlanner:
    """按场景里写死的脚本发计划: 每天把同一张表重新基准到当天 0:00。

    它是【导演脚本】不是推理 —— 作者负责 target 存在; 缺了也不崩
    (执行时会被世界 Deny「目标不存在」, NPC 记一次失败并跳过该条)。
    """

    def __init__(self, plans: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        self._plans = {k: [dict(x) for x in v] for k, v in plans.items()}

    def plan_for_person(self, person, day_start_tick: int) -> list[PlanEntry]:
        return entries_from_spec(self._plans.get(person.person_id, []),
                                 day_start_tick)
