"""建筑类型库 + 自动布局: 面积∝容量、零重叠、不出画布。"""
from __future__ import annotations

from citysim.gateway.scenarios import load_scene
from citysim.world.buildings import (DOOR_SIDES, build_locations,
                                     load_building_types)


def test_type_library_has_kinds_and_capacity() -> None:
    types = load_building_types()
    assert types["home_standard"].kind == "home"
    assert types["home_standard"].capacity == 6
    assert types["shop_supermarket"].capacity == 100
    assert types["work_site"].kind == "work"


def test_area_proportional_to_capacity_and_no_overlap() -> None:
    w, _s, _r = load_scene()
    locs = w.locations
    ratios = [(v["w"] * v["h"]) / v["capacity"] for v in locs.values()]
    assert (max(ratios) - min(ratios)) / max(ratios) < 0.002   # 取整误差内一致
    assert locs["market_001"]["capacity"] == 100
    assert locs["apt_001"]["capacity"] == 6
    area_ratio = (locs["market_001"]["w"] * locs["market_001"]["h"]) / \
        (locs["apt_001"]["w"] * locs["apt_001"]["h"])
    assert abs(area_ratio - 100 / 6) / (100 / 6) < 0.002

    ids = list(locs)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = locs[ids[i]], locs[ids[j]]
            overlap = not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                           or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])
            assert not overlap, (ids[i], ids[j])
    for v in locs.values():
        assert v["x"] >= 0 and v["y"] >= 0
        assert v["x"] + v["w"] <= 1280 + 1 and v["y"] + v["h"] <= 800 + 1


def test_every_type_has_valid_doors() -> None:
    for t in load_building_types().values():
        assert t.doors, t.type
        for d in t.doors:
            assert d["side"] in DOOR_SIDES, (t.type, d)
            assert -0.5 <= d["offset"] <= 0.5, (t.type, d)


def test_door_points_world_geom() -> None:
    """进出口定义 → 世界点: 南门的 y 应落在房间下边, 法线朝 +y。"""
    data = {"canvas": {"w": 100, "h": 100},
            "locations": {"apt_001": {"type": "home_standard"}}}
    out = build_locations(data)["apt_001"]
    dp = out["door_points"]
    assert len(dp) == 1
    d = dp[0]
    assert d["side"] == "south"
    assert abs(d["x"] - (out["x"] + out["w"] / 2)) < 0.05
    assert abs(d["y"] - (out["y"] + out["h"])) < 0.05
    assert d["nx"] == 0.0 and d["ny"] == 1.0


def test_unknown_type_falls_back_to_south_door() -> None:
    data = {"canvas": {"w": 100, "h": 100},
            "locations": {"x": {"x": 0, "y": 0, "w": 10, "h": 20}}}
    out = build_locations(data)["x"]
    assert len(out["door_points"]) == 1
    assert out["door_points"][0]["side"] == "south"


def test_typed_explicit_geometry_kept() -> None:
    """已知 type 的建筑也要保留显式几何(编辑器摆放的位置不被自动布局覆盖)。"""
    data = {"canvas": {"w": 800, "h": 600}, "locations": {
        "bld_001": {"type": "home_small", "x": 401.13, "y": 291.13,
                    "w": 7.746, "h": 7.746}}}
    out = build_locations(data)["bld_001"]
    assert (out["x"], out["y"], out["w"], out["h"]) == (401.13, 291.13, 7.746, 7.746)
    assert out["kind"] == "home"


def test_explicit_geometry_kept() -> None:
    data = {"canvas": {"w": 100, "h": 100},
            "locations": {"room_001": {"name": "X", "x": 1, "y": 2, "w": 3, "h": 4}}}
    out = build_locations(data)
    assert out["room_001"]["x"] == 1 and out["room_001"]["h"] == 4


def test_home_name_is_door_no() -> None:
    w, _s, _r = load_scene()
    # 住宅无显式 name → 由 id 序号派生门牌号
    assert w.locations["apt_001"]["name"] == "1 号"
    assert w.locations["apt_002"]["name"] == "2 号"
    # 有显式 name 的地点保留语义名
    assert w.locations["market_001"]["name"] == "大超市"
    assert w.locations["plaza_001"]["name"] == "街心广场"


def test_name_precedence() -> None:
    data = {"canvas": {"w": 100, "h": 100}, "locations": {
        "apt_007": {"type": "home_standard"},                # → 7 号
        "apt_008": {"type": "home_standard", "name": "甲宅"},  # 显式优先
    }}
    out = build_locations(data)
    assert out["apt_007"]["name"] == "7 号"
    assert out["apt_008"]["name"] == "甲宅"
