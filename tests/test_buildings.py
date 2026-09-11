"""建筑类型库 + 自动布局: 面积∝容量、零重叠、不出画布。"""
from __future__ import annotations

from citysim.gateway.scenarios import load_scene
from citysim.world.buildings import build_locations, load_building_types


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


def test_explicit_geometry_kept() -> None:
    data = {"canvas": {"w": 100, "h": 100},
            "locations": {"room_001": {"name": "X", "x": 1, "y": 2, "w": 3, "h": 4}}}
    out = build_locations(data)
    assert out["room_001"]["x"] == 1 and out["room_001"]["h"] == 4
