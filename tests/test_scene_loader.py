"""场景加载: 编辑器导出的显式几何 / 人物 gender+traits / 画布 能被后端消费。"""
from __future__ import annotations

import json

from citysim.gateway.scenarios import load_scene


def _write(tmp_path, data: dict) -> str:
    p = tmp_path / "scene.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_scene_explicit_geometry_gender_traits(tmp_path) -> None:
    data = {
        "canvas": {"w": 800, "h": 600},
        "locations": {
            "bld_001": {"type": "home_standard", "name": "1 号",
                        "x": 24.5, "y": 13.0, "w": 10.95, "h": 10.95},
        },
        "npcs": [{
            "id": "npc_gao_jun", "name": "高军", "gender": "male",
            "birthday": "1988-03-02", "role": "engineer", "money": 300,
            "home": "bld_001", "traits": {"night_owl": True},
            "personality": {"hunger": 0.9}},
        ],
        "entities": [{"id": "bed_basic_001", "type": "bed_basic",
                      "at": "bld_001", "owner": "npc_gao_jun", "stock": 2}],
    }
    world, _s, _r = load_scene(_write(tmp_path, data))
    loc = world.locations["bld_001"]
    assert (loc["x"], loc["y"], loc["w"], loc["h"]) == (24.5, 13.0, 10.95, 10.95)
    assert loc["kind"] == "home"
    assert world.canvas == {"w": 800, "h": 600}
    p = world.npcs["npc_gao_jun"]
    assert p.gender == "male"
    assert p.role == "engineer"
    assert p.home == "bld_001"
    e = world.entities["bed_basic_001"]
    assert e.location_id == "bld_001" and e.stock == 2 and e.owner == "npc_gao_jun"


def test_scene_floor_units(tmp_path) -> None:
    """多楼层: part_of 子地点透传; 每层一个家 → 各自成为独立私有住所。"""
    data = {
        "canvas": {"w": 800, "h": 600},
        "locations": {
            "bld_007": {"type": "home_standard", "name": "7 号",
                        "x": 10.0, "y": 10.0, "w": 12.0, "h": 12.0},
            "bld_007_f1": {"type": "home_standard", "name": "7 号 · 1层",
                           "part_of": "bld_007",
                           "x": 10.0, "y": 10.0, "w": 12.0, "h": 12.0},
            "bld_007_f2": {"type": "home_standard", "name": "7 号 · 2层",
                           "part_of": "bld_007",
                           "x": 10.0, "y": 10.0, "w": 12.0, "h": 12.0},
        },
        "npcs": [
            {"id": "npc_jia", "name": "甲", "birthday": "1990-01-01",
             "home": "bld_007_f1", "money": 100},
            {"id": "npc_yi", "name": "乙", "birthday": "1991-01-01",
             "home": "bld_007_f2", "money": 100},
        ],
        "entities": [
            {"id": "bed_basic_001", "type": "bed_basic", "at": "bld_007_f1",
             "owner": "npc_jia"},
            {"id": "bed_basic_002", "type": "bed_basic", "at": "bld_007_f2",
             "owner": "npc_yi"},
        ],
    }
    world, _s, _r = load_scene(_write(tmp_path, data))
    # part_of 透传 + 同 footprint 的显式几何原样保留
    f2 = world.locations["bld_007_f2"]
    assert f2["part_of"] == "bld_007"
    assert (f2["x"], f2["y"], f2["w"], f2["h"]) == (10.0, 10.0, 12.0, 12.0)
    assert world.locations["bld_007"].get("part_of") is None
    # 每层各自成户(不是一个信息池): 各自 owner → 私有
    assert world.locations["bld_007_f1"]["owner"] == "npc_jia"
    assert world.locations["bld_007_f2"]["owner"] == "npc_yi"
    assert world.is_public(world.locations["bld_007_f2"]) is False
    # 物件落在各自楼层
    assert world.entities["bed_basic_001"].location_id == "bld_007_f1"
    assert world.entities["bed_basic_002"].location_id == "bld_007_f2"


def test_missing_floor_unit_materialized(tmp_path) -> None:
    """楼层单元没导出但被 npc.home 引用 → 后端按父建筑补出该单元。

    真实现象: 编辑器里先把楼层数调到 10 并「填满住户」, 再减回 6 导出 ——
    楼上的 home 还在, 对应地点没了。不补的话人会落在幽灵地点上(没床没饭、
    占用统计也数不到)。
    """
    data = {
        "canvas": {"w": 800, "h": 600},
        "locations": {
            "bld_007": {"type": "home_small", "name": "7 号",
                        "x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0},
            "bld_007_f1": {"type": "home_small", "name": "7 号 · 1层",
                           "part_of": "bld_007",
                           "x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0},
        },
        "npcs": [
            {"id": "npc_a", "name": "甲", "birthday": "1990-01-01",
             "home": "bld_007_f1", "money": 100},
            {"id": "npc_b", "name": "乙", "birthday": "1991-01-01",
             "home": "bld_007_f3", "money": 100},     # ← locations 里没有
        ],
    }
    world, _s, _r = load_scene(_write(tmp_path, data))
    assert "bld_007_f3" in world.locations
    u = world.locations["bld_007_f3"]
    assert u["part_of"] == "bld_007"
    assert (u["x"], u["y"], u["w"], u["h"]) == (0.0, 0.0, 10.0, 10.0)
    # 人落在补出的真实地点上(不是幽灵 id), 且该层独立成户
    assert world.loc_of("npc_b") == "bld_007_f3"
    assert world.locations["bld_007_f3"]["owner"] == "npc_b"
    assert world.locations["bld_007"]["owner"] == ""      # 父建筑不继承归属


def test_knowledge_seeds_many_npcs(tmp_path) -> None:
    """场景级 knowledge: 一次让一批人知道某处的货(超市在哪/卖什么)。"""
    data = {
        "canvas": {"w": 800, "h": 600},
        "locations": {
            "shop_1": {"type": "shop_small", "name": "超市",
                       "x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0},
            "home_1": {"type": "home_small", "name": "1 号",
                       "x": 20.0, "y": 0.0, "w": 10.0, "h": 10.0},
        },
        "entities": [
            {"id": "food_apple_1", "type": "food_apple", "at": "shop_1",
             "price": 5, "stock": 100},
        ],
        "npcs": [
            {"id": "npc_a", "name": "甲", "birthday": "1990-01-01",
             "home": "home_1", "money": 100},
            {"id": "npc_b", "name": "乙", "birthday": "1991-01-01",
             "home": "home_1", "money": 100},
        ],
        "knowledge": [
            {"who": "all", "from": "shop_1", "items": [], "believe": 0.8},
        ],
    }
    world, _s, _r = load_scene(_write(tmp_path, data))
    for pid in ("npc_a", "npc_b"):
        row = world.npcs[pid].memory_dicts()
        ids = {r["item_id"] for r in row}
        assert "food_apple_1" in ids, pid
        r = next(r for r in row if r["item_id"] == "food_apple_1")
        assert r["located"] == "shop_1"      # 知道在哪
        assert r["price"] == 5               # 知道价格
        assert abs(r["believe"] - 0.8) < 1e-6  # “听说” → 打折
        assert r["afford"] == "hunger"       # 知道能解什么需求


def test_knowledge_can_target_subset(tmp_path) -> None:
    """who 可以是名单: 只让指定的人知道。"""
    data = {
        "canvas": {"w": 800, "h": 600},
        "locations": {
            "shop_1": {"type": "shop_small", "name": "超市",
                       "x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0},
            "home_1": {"type": "home_small", "name": "1 号",
                       "x": 20.0, "y": 0.0, "w": 10.0, "h": 10.0},
        },
        "entities": [{"id": "meal_simple_1", "type": "meal_simple",
                      "at": "shop_1", "price": 8, "stock": 10}],
        "npcs": [
            {"id": "npc_a", "name": "甲", "birthday": "1990-01-01",
             "home": "home_1"},
            {"id": "npc_b", "name": "乙", "birthday": "1991-01-01",
             "home": "home_1"},
        ],
        "knowledge": [{"who": ["npc_a"], "from": "shop_1"}],
    }
    world, _s, _r = load_scene(_write(tmp_path, data))
    assert "meal_simple_1" in {r["item_id"] for r in world.npcs["npc_a"].memory_dicts()}
    assert "meal_simple_1" not in {r["item_id"] for r in world.npcs["npc_b"].memory_dicts()}
