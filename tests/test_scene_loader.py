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
