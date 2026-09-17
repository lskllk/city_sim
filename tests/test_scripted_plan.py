"""固定日计划(ScriptedPlanner) + 计划快照(前端 viz) 单测。

ScriptedPlanner 是现在【唯一】的计划来源(场景 JSON 的 `plans` 段):
把作者写的脚本按天重新基准成 PlanEntry[]。它不查记忆 —— 作者负责 target 存在。
"""
from __future__ import annotations

from citysim.core.types import Interact, MoveTo, Plan
from citysim.npc.person import Identity, Person
from citysim.npc.planner import ScriptedPlanner, entries_from_spec
from citysim.npc.schedule import PlanEntry


def _p() -> Person:
    return Person(identity=Identity("p", "p"))


def test_rebases_to_day_start() -> None:
    pl = ScriptedPlanner({"p": [
        {"at_minute": 480, "intent": "interact", "target": "food"},
        {"at_minute": 840, "intent": "interact", "target": "tv"},
    ]})
    entries = pl.plan_for_person(_p(), 1440)          # 第 2 天
    assert [e.at_tick for e in entries] == [1920, 2280]
    assert all(isinstance(e.intent, Interact) for e in entries)


def test_accepts_clock_time() -> None:
    pl = ScriptedPlanner({"p": [
        {"at": "08:00", "intent": "interact", "target": "food"},
    ]})
    entries = pl.plan_for_person(_p(), 1440)
    assert entries[0].at_tick == 1440 + 480          # 次日 08:00


def test_same_tick_keeps_script_order() -> None:
    pl = ScriptedPlanner({"p": [
        {"at_minute": 720, "intent": "interact", "target": "shop"},
        {"at_minute": 720, "intent": "interact", "target": "food"},
    ]})
    entries = pl.plan_for_person(_p(), 0)
    assert [e.intent.target_id for e in entries] == ["shop", "food"]


def test_buy() -> None:
    pl = ScriptedPlanner({"p": [
        {"at": "12:00", "intent": "buy", "target": "market_1", "qty": 3},
    ]})
    assert pl.plan_for_person(_p(), 0)[0].intent.qty == 3


def test_move_to() -> None:
    pl = ScriptedPlanner({"p": [{"at_minute": 60, "intent": "move_to",
                                 "dest": "home"}]})
    assert isinstance(pl.plan_for_person(_p(), 0)[0].intent, MoveTo)


def test_unknown_person_gets_no_plan() -> None:
    """脚本里没写这个人 → 空计划(不是崩, 也不是默认计划)。"""
    assert ScriptedPlanner({"other": []}).plan_for_person(_p(), 0) == []


def test_bad_entries_are_dropped_not_crashed() -> None:
    """结构不对/时间非法的条目直接丢掉 —— 脚本是手写的, 不能一条错就炸。"""
    entries = entries_from_spec([
        {"intent": "interact", "target": "x"},          # 没时间 → 丢
        {"at": "99:99", "intent": "interact", "target": "x"},   # 时间非法 → 丢
        {"at": "08:00", "intent": "interact"},          # 没 target → 丢
        {"at": "08:00", "intent": "??", "target": "x"},  # 未知 intent → 丢
        "not a dict",                                    # 非 dict → 丢
        {"at": "09:00", "intent": "interact", "target": "keep"},
    ], 0)
    assert [e.intent.target_id for e in entries] == ["keep"]


def test_plan_snapshot_shape() -> None:
    p = _p()
    p.assign(Plan([PlanEntry("e0", 100, Interact("food")),
                   PlanEntry("e1", 200, MoveTo(dest="home"))]))
    snap = p.plan_snapshot()
    assert snap == [
        {"id": "e0", "at_tick": 100, "status": "pending",
         "intent": "interact", "target": "food"},
        {"id": "e1", "at_tick": 200, "status": "pending",
         "intent": "move_to", "target": "home"},
    ]


# --- 端到端: 场景 plans 段 → 装上 ScriptedPlanner → 每天 0 点重新发计划 -----
# 这条链(scenarios 装配 + engine 第 10 步)以前没有测试覆盖。
def test_scene_plans_reach_the_npc_end_to_end(tmp_path) -> None:
    import json

    from citysim.core.config import load_config
    from citysim.gateway.scenarios import load_scene
    from citysim.sim.loop import run_tick

    cfg = load_config("config/sim.toml")
    scene = {
        "scene": "t", "display_name": "t", "canvas": {"w": 600, "h": 400},
        "locations": {
            "home": {"type": "home_small", "name": "h",
                     "x": 100, "y": 100, "w": 40, "h": 40},
        },
        "entities": [{"id": "m", "type": "meal_simple", "at": "home",
                      "stock": 50}],
        "npcs": [{"id": "a", "name": "A", "home": "home", "money": 100,
                  "init": {}}],
        "plans": {"a": [{"at": "08:00", "intent": "move_to", "dest": "home"}]},
        "travel": {"default": 20, "pairs": {}},
    }
    p = tmp_path / "s.json"
    p.write_text(json.dumps(scene, ensure_ascii=False), encoding="utf-8")
    w, s, rng = load_scene(p)

    assert s.planner is not None, "场景写了 plans → 该装上计划器"
    snap = w.npcs["a"].plan_snapshot()
    assert [e["intent"] for e in snap] == ["move_to"]      # 当天计划已应用

    for _ in range(cfg.ticks_per_day):                     # 跑到次日 0 点
        run_tick(w, s, cfg, rng)
    snap = w.npcs["a"].plan_snapshot()
    assert [e["at_tick"] for e in snap] == [cfg.ticks_per_day + 480]


def test_no_plans_section_means_no_planner(tmp_path) -> None:
    """"没有计划器" = 纯 utility 驱动 —— 这是个明确状态, 不是"装个空计划器"。"""
    import json

    from citysim.gateway.scenarios import load_scene

    scene = {
        "scene": "t", "display_name": "t", "canvas": {"w": 600, "h": 400},
        "locations": {"home": {"type": "home_small", "name": "h",
                               "x": 100, "y": 100, "w": 40, "h": 40}},
        "entities": [{"id": "m", "type": "meal_simple", "at": "home",
                      "stock": 50}],
        "npcs": [{"id": "a", "name": "A", "home": "home", "money": 100,
                  "init": {}}],
        "travel": {"default": 20, "pairs": {}},
    }
    p = tmp_path / "s.json"
    p.write_text(json.dumps(scene, ensure_ascii=False), encoding="utf-8")
    w, s, _rng = load_scene(p)
    assert s.planner is None
    assert w.npcs["a"].plan_snapshot() == []
