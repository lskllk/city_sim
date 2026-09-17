"""world → NPC 的【指令口】: `Person.assign(cmd)`。

第二批: 把 6 个散装 setter 收成一个门 —— 它们都是"上面的人(老板/作者/计划器)
说'你以后照这个做'", 不是"世界告诉你发生了什么"(那走 notify)。

    set_work     → assign(Work(...))
    set_shift    → assign(Shift(...))
    set_wage     → assign(Wage(...))
    set_role     → assign(Role(...))
    clear_work   → assign(Unwork())
    set_plan     → assign(Plan(...))

钉两件事: ① 每个指令的语义; ② **老名字必须消失**(留着就又是一条暗门)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.core.config import load_config
from citysim.core.types import Plan, Role, Shift, Unwork, Wage, Work
from citysim.npc.person import Person

from helpers import add_entity, add_npc, make_runtime

CFG = load_config(Path("config/sim.toml"))


def test_assign_is_the_only_door_for_the_six() -> None:
    """老名字必须消失 —— 留着就又有一条绕过 assign 的暗门。"""
    for gone in ("set_work", "set_shift", "set_wage", "set_role", "clear_work",
                 "set_plan"):
        assert not hasattr(Person, gone), f"{gone} 还在 → 门没关上"


def test_assign_work_binds_everything_and_writes_role() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    npc.assign(Work("org", "shop", "counter", 480, 1140, 7.5))
    assert npc.work == {"company": "org", "shop": "shop", "station": "counter",
                        "open": 480, "close": 1140, "wage": 7.5}
    assert npc.role == "worker"                    # Work 默认带上角色


def test_assign_work_without_role_keeps_existing_role() -> None:
    """改岗不该顺手把人设里的角色擦掉。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    npc.assign(Role("guardian"))
    npc.assign(Work("org", "shop", "counter", 480, 1140, 5.0, role=""))
    assert npc.work["company"] == "org"
    assert npc.role == "guardian"


def test_assign_unwork_clears_binding_only() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    npc.assign(Work("org", "shop", "counter", 480, 1140, 5.0))
    npc.assign(Unwork())
    assert npc.work == {}
    assert npc.role == "worker"                    # 角色不因为撤岗就丢


def test_assign_shift_and_wage_need_a_job_and_clamp() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    # 没工作 → 班次/时薪写不进去(老 set_shift/set_wage 的语义)
    npc.assign(Shift(0, 100))
    npc.assign(Wage(99))
    assert npc.work == {}
    npc.assign(Work("org", "shop", "counter", 480, 1140, 5.0))
    npc.assign(Shift(-10, 99999))                  # 夹到合法范围
    npc.assign(Wage(-3))                           # 时薪不许负
    assert (npc.work["open"], npc.work["close"]) == (0, 1440)
    assert npc.work["wage"] == 0.0


def test_assign_plan_replaces_but_keeps_a_need_goal() -> None:
    """0 点计划器灌新计划 → 不能把【需求】goal 清掉(否则睡觉被饥饿中止)。"""
    from citysim.world.perception import build_percept
    w, s, _ = make_runtime(CFG)
    add_entity(w, "bed", tags=("sleepable",), affordances={"energy": 0.5},
               duration_ticks=800)
    npc = add_npc(w, s, "npc", energy=0.2)
    npc.perceive(build_percept(w, npc), 0)
    npc.decide(CFG, 100)
    assert npc._goal is not None and npc._goal.source == "need"
    npc.assign(Plan([]))
    assert npc._goal is not None                   # 需求 goal 不被清


def test_assign_rejects_undeclared_commands() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    with pytest.raises(TypeError):
        npc.assign({"set": "hunger", "value": 1.0})   # 裸数据不许进来
