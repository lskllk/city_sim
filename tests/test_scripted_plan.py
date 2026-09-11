"""TASK006: 固定日计划(ScriptedPlanner) + 计划快照(前端 viz) 单测。"""
from __future__ import annotations

from citysim.core.types import Interact, MoveTo
from citysim.npc.person import Identity, Person
from citysim.npc.planner import ScriptedPlanner
from citysim.npc.schedule import PlanEntry


def test_scripted_planner_rebases_to_day_start() -> None:
    pl = ScriptedPlanner({"p": [
        {"at_minute": 480, "intent": "interact", "target": "food"},
        {"at_minute": 840, "intent": "interact", "target": "tv"},
    ]})
    p = Person(identity=Identity("p", "p"))
    res = pl.plan_for_person(p, 1440)                 # 第 2 天
    assert res.source == "scripted"
    assert [e.at_tick for e in res.entries] == [1920, 2280]
    assert all(isinstance(e.intent, Interact) for e in res.entries)


def test_scripted_planner_accepts_clock_time() -> None:
    pl = ScriptedPlanner({"p": [
        {"at": "08:00", "intent": "interact", "target": "food"},
    ]})
    res = pl.plan_for_person(Person(identity=Identity("p", "p")), 1440)
    assert res.entries[0].at_tick == 1440 + 480          # 次日 08:00


def test_scripted_planner_same_tick_keeps_script_order() -> None:
    pl = ScriptedPlanner({"p": [
        {"at_minute": 720, "intent": "interact", "target": "shop"},
        {"at_minute": 720, "intent": "interact", "target": "food"},
    ]})
    res = pl.plan_for_person(Person(identity=Identity("p", "p")), 0)
    assert [e.intent.target_id for e in res.entries] == ["shop", "food"]


def test_scripted_planner_buy() -> None:
    pl = ScriptedPlanner({"p": [
        {"at": "12:00", "intent": "buy", "target": "market_1", "qty": 3},
    ]})
    res = pl.plan_for_person(Person(identity=Identity("p", "p")), 0)
    assert res.entries[0].intent.qty == 3


def test_scripted_planner_move_to() -> None:
    pl = ScriptedPlanner({"p": [{"at_minute": 60, "intent": "move_to",
                                 "dest": "home"}]})
    res = pl.plan_for_person(Person(identity=Identity("p", "p")), 0)
    assert isinstance(res.entries[0].intent, MoveTo)


def test_plan_snapshot_shape() -> None:
    p = Person(identity=Identity("p", "p"))
    p.set_plan([PlanEntry("e0", 100, Interact("food")),
                PlanEntry("e1", 200, MoveTo(dest="home"))])
    snap = p.plan_snapshot()
    assert snap == [
        {"id": "e0", "at_tick": 100, "status": "pending",
         "intent": "interact", "target": "food"},
        {"id": "e1", "at_tick": 200, "status": "pending",
         "intent": "move_to", "target": "home"},
    ]
