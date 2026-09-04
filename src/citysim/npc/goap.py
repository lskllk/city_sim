"""goap —— 反向规划器 + 动作库 JSON 加载(M4 4.3)。

动作从 config/actions/*.json 加载(每文件一个动作: action/pre/add/zh/bind),
转成 Action(name, pre, add)。谓词由世界侧派生喂给 decide(如容器可食 =>
container_has_edible)。本模块只做规划, 不依赖 world。
"""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_ACTIONS_DIR = Path(__file__).resolve().parents[3] / "config" / "actions"


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


# ----------------------------------------------------------------------
# 动作库 JSON 加载
# ----------------------------------------------------------------------
@functools.lru_cache(maxsize=2)
def _read_dir(directory: str):
    actions: dict[str, Action] = {}
    zh: dict[str, str] = {}
    for p in sorted(Path(directory).glob("*.json")):
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        name = data["action"]
        actions[name] = Action(name=name,
                               pre=frozenset(data.get("pre", [])),
                               add=frozenset(data.get("add", [])))
        zh[name] = data.get("zh", name)
    return actions, zh


def load_actions(directory: str | Path | None = None):
    """读 config/actions/*.json -> ({name: Action}, {name: zh})。"""
    d = _ACTIONS_DIR if directory is None else Path(directory)
    return _read_dir(str(d))


def hunger_plan() -> tuple[str, ...] | None:
    """饿 + 容器里有食物 的 GOAP 计划(动作名来自 JSON)。不可达返回 None。

    初始事实: 已站在容器(at_container) 且 容器有可食(container_has_edible);
    目标: 吃饱(fed)。
    """
    actions, _ = load_actions()
    if not actions:
        return None
    plan = backward_plan(
        list(actions.values()),
        {"at_container", "container_has_edible"},
        {"fed"},
    )
    return tuple(plan) if plan else None
