"""GOAP-lite —— 手写后向搜索规划器(决策的策略层)。

定位: person/brain 里"深层目标 → 行动序列"的小型规划器, 与 Indicator(反射层)
分工:
  - Indicator : 当下"用哪个容器里/手边物品"的即时反射;
  - 本 planner : 当目标需要"先做前置步骤"才能满足时(如: 要吃但食物在冰箱里,
                得先 take 再 eat), 产出跨步骤的 plan 供 Person 逐条执行。

**模型**: 状态是**离散布尔事实**的集合(set of str)。动作是单调增事实:
  - pre  : 前提事实(全在 state 里才能执行)
  - add  : 执行后新增的事实
搜索方向: 从目标事实集出发**后向**, 找能把所需事实补上的动作序列
(符合 ADR-0004 "手写后向搜索" 的初衷; 用布尔事实把连续需求离散化成可搜索)。

返回值是**正向执行顺序**的动作名列表; 无法达成返回 None。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Action:
    """一条规划动作(只增事实的单调动作)。"""
    name: str
    pre: frozenset[str] = frozenset()
    add: frozenset[str] = frozenset()

    def __str__(self) -> str:  # pragma: no cover - debug
        return f"Action({self.name}, pre={sorted(self.pre)}, add={sorted(self.add)})"


def _solve(
    actions: list[Action],
    initial: frozenset[str],
    need: frozenset[str],
    memo: dict[frozenset[str], list[str] | None],
) -> list[str] | None:
    """后向递归: 从 need 出发, 返回达成它所需动作的正向序列。"""
    if need in memo:
        return memo[need]
    if need <= initial:
        memo[need] = []
        return []
    missing = need - initial
    for a in actions:
        added = a.add & missing
        if not added:
            continue
        # 后向一步: 去掉 a 能补的, 补上 a 的前提
        new_need = (need - a.add) | a.pre
        if new_need == need:          # 没进展, 防死循环
            continue
        sub = _solve(actions, initial, new_need, memo)
        if sub is not None:
            plan = sub + [a.name]
            memo[need] = plan
            return plan
    memo[need] = None
    return None


def backward_plan(
    actions: Iterable[Action],
    initial: Iterable[str],
    goal: Iterable[str],
) -> list[str] | None:
    """由目标后向搜索动作序列(正向执行序)。不可达返回 None。"""
    return _solve(
        list(actions),
        frozenset(initial),
        frozenset(goal),
        {},
    )
