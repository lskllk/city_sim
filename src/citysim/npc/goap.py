"""goap —— 反向规划器(迁移自旧 planner)。

单调增布尔事实集; 从目标后向搜索动作序列(正向执行序)。M4 会把动作库改成
JSON 加载(config/actions/*.json), 本模块先保留 Python 定义, 接口不变。
"""
from __future__ import annotations

from dataclasses import dataclass
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


# --- 取食领域动作(事实: food_in_container -> food_at_hand -> fed) --------
_TAKE_FOOD = Action("take_food", pre=frozenset({"food_in_container"}),
                    add=frozenset({"food_at_hand"}))
_EAT_FOOD = Action("eat", pre=frozenset({"food_at_hand"}),
                   add=frozenset({"fed"}))


def hunger_plan() -> tuple[str, ...] | None:
    """饿+食物在容器里 的 GOAP 计划: (take_food, eat)。不可达返回 None。"""
    plan = backward_plan([_TAKE_FOOD, _EAT_FOOD],
                         {"food_in_container"}, {"fed"})
    return tuple(plan) if plan else None
