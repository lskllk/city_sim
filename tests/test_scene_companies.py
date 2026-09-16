"""场景能声明公司(编辑器可编) —— 让场景【无头也能跑】(有店主/岗位/交易)。

以前公司只能在游戏里点建筑"注册"出来 → 场景 JSON 里没有公司 → load_scene
建不出公司 → 无头跑就没有店/岗位/成交。
"""
from __future__ import annotations

import json
from pathlib import Path

from citysim.core.config import load_config
from citysim.gateway.scenarios import load_scene
from citysim.sim.loop import run_tick

CFG = load_config(Path("config/sim.toml"))


def _scene(**over) -> dict:
    base = {
        "scene": "t", "display_name": "t", "canvas": {"w": 600, "h": 400},
        "locations": {
            "shop": {"type": "shop_small", "name": "s",
                     "x": 300, "y": 100, "w": 40, "h": 40},
            "home": {"type": "home_small", "name": "h",
                     "x": 100, "y": 100, "w": 40, "h": 40},
        },
        "companies": [{
            "id": "org_shop", "name": "甲店", "shops": ["shop"], "cash": 3000,
            "open": "08:00", "close": "19:00", "wage_per_hour": 12,
            "hiring_slots": 1, "restock_to": 30,
        }],
        "entities": [
            {"id": "m", "type": "meal_simple", "at": "home", "stock": 50},
            {"id": "c", "type": "station_counter", "at": "shop"},
        ],
        "npcs": [{"id": "a", "name": "A", "home": "home", "money": 100,
                  "init": {}}],
        "travel": {"default": 20, "pairs": {}},
    }
    base.update(over)
    return base


def _load(tmp_path, data):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_scene(p)


def test_company_from_scene_is_built_and_binds_shop(tmp_path) -> None:
    w, _s, _r = _load(tmp_path, _scene())
    c = w.companies["org_shop"]
    assert c.shops == ("shop",) and c.name == "甲店"
    assert (c.open_minute, c.close_minute) == (480, 1140)   # "08:00"/"19:00"
    assert c.wage_per_hour == 12.0 and c.hiring_slots == 1
    assert w.locations["shop"]["company"] == "org_shop"     # 店挂上公司


def test_headless_scene_can_hire_from_declared_company(tmp_path) -> None:
    w, s, rng = _load(tmp_path, _scene())
    for _ in range(1500):                                   # 跑到招人时刻
        run_tick(w, s, CFG, rng)
    assert w.companies["org_shop"].staff, "无头场景里也应该招到人"


def test_no_companies_section_is_fine(tmp_path) -> None:
    w, _s, _r = _load(tmp_path, _scene(companies=[]))
    assert w.companies == {}


def test_scene_preassigns_company_staff(tmp_path) -> None:
    """作者直选: 场景里写 staff → load_scene 就把人绑成员工(不等招聘时刻)。"""
    scene = _scene()
    scene["entities"].append(
        {"id": "c2", "type": "station_counter", "at": "shop"})
    scene["companies"][0]["staff"] = [
        {"npc": "a", "station": "c"},
        {"npc": "b"},                       # 不给 station → 自动挑空台
    ]
    scene["npcs"].append({"id": "b", "name": "B", "home": "home", "money": 100,
                          "init": {}})
    w, _s, _r = _load(tmp_path, scene)
    a, b = w.npcs["a"], w.npcs["b"]
    assert a.role == "worker" and a.work["station"] == "c"
    assert b.role == "worker" and b.work["station"] in ("c", "c2")
    assert {n for n, _w in w.companies["org_shop"].staff} == {"a", "b"}


def test_editor_scene_worker_is_staffed_headless(tmp_path) -> None:
    """模拟编辑器导出: 公司 + 预置员工 + 装修(前台) → 无头跑起来员工在岗。

    这正是"商铺能编物件"的意义: 没有前台 → 员工没工位 → 永远不上岗。
    """
    from citysim.world.engine import staffed_counters
    scene = _scene()
    scene["companies"][0].update({"open": "00:00", "close": "24:00",
                                  "staff": ["a"]})
    w, s, rng = _load(tmp_path, scene)
    assert w.npcs["a"].work["station"] == "c"     # 自动挑到店里的前台
    for _ in range(120):
        run_tick(w, s, CFG, rng)
    assert len(staffed_counters(w, s, "shop")) == 1   # 人在台上
