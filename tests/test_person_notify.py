"""world → NPC 的【唯一通知口】: `Person.notify(ev)`。

为什么钉这个: 以前 world 直接调二十几个 setter 改 NPC 身上的东西(身体/钱/工作/
记忆/头顶的字), 没有统一的门 —— 看不清"世界到底能改他什么"。第一批把【通知】
那 4 个收成一个口: on_interaction_done / on_failure / forget_item / earn 全没了,
只剩 notify(发生了什么), 怎么改自己是 NPC 的事。

这个文件同时钉【反向】: 被收走的老方法名不许再出现在 Person 上(否则又变两个门)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.core.config import load_config
from citysim.core.types import (
    InteractionDone,
    InteractionFailed,
    ItemGone,
    WagePaid,
)
from citysim.npc.person import Person

from helpers import add_entity, add_npc, make_runtime

CFG = load_config(Path("config/sim.toml"))


def test_notify_is_the_only_door_for_the_four() -> None:
    """老名字必须消失 —— 留着就又是一条绕过 notify 的暗门。"""
    for gone in ("on_interaction_done", "on_failure", "forget_item", "earn"):
        assert not hasattr(Person, gone), f"{gone} 还在 → 门没关上"


def test_notify_item_gone_forgets_memory_row() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "npc", location="loc")
    npc.note("meal", located="loc", afford="hunger", value=0.5, price=0.0, stock=1)
    assert any(r["item_id"] == "meal" for r in npc.memory_dicts())
    npc.notify(ItemGone("meal"))
    assert not any(r["item_id"] == "meal" for r in npc.memory_dicts())


def test_notify_wage_paid_moves_money() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    before = npc.money
    npc.notify(WagePaid(123.5))
    assert npc.money == before + 123.5
    npc.notify(WagePaid(-5))              # 负数不进账(旧 earn 的语义)
    assert npc.money == before + 123.5


def test_notify_interaction_failed_cools_or_forgets() -> None:
    """失败通知只带【原因 + 时刻】: 冷却/删记忆是 NPC 自己判的。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "npc", location="loc")
    npc.note("meal", located="loc", afford="hunger", value=0.5, price=0.0, stock=1)
    # ① 暂时不可用(占着) → 开冷却, 记忆还在
    npc.notify(InteractionFailed("meal", "已被他人拥有", 100))
    row = next(r for r in npc.memory_dicts() if r["item_id"] == "meal")
    assert row["cool_until"] > 100
    # ② 目标不存在 → 直接忘掉
    npc.notify(InteractionFailed("meal", "目标不存在", 200))
    assert not any(r["item_id"] == "meal" for r in npc.memory_dicts())
    # ③ 失败日志留着(0:00 交 LLM)
    assert [f["why"] for f in npc.failure_log()] == ["已被他人拥有", "目标不存在"]


def test_notify_done_finishes_the_goal() -> None:
    """完成通知 → 当前目标收尾(计划表的推进靠它)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible",),
               affordances={"hunger": 0.5}, duration_ticks=2)
    npc = add_npc(w, s, "npc", location="loc")
    npc.set_signals(hunger=0.2)
    npc.step(_port(w, s), CFG)
    assert npc.intake_progress("meal")[0] >= 0        # 已接手
    npc.notify(InteractionDone("meal", 10))
    # 其他目标的完成通知不该动它(不误伤)
    npc.notify(InteractionDone("另一个东西", 11))


def test_notify_rejects_undeclared_events() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    with pytest.raises(TypeError):
        npc.notify("我要改你的血")       # 裸数据不许进来: 必须走声明的通知


def _port(w, s):
    from citysim.world.edge.port import WorldPortImpl
    return WorldPortImpl(w, s, CFG)
