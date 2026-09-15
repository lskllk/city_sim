"""命名规则(lint): id 语法/编号/唯一性/引用闭合 + 姓名池规则。

规则见 docs/naming.md。这里是可执行约束, 防止命名再次变乱。
- 类型: category_variant (item) / kind_variant (building)
- 地点: <slug>_<NNN>          例 apt_001 / market_001
- 实体: <itemtype>_<NNN>       例 bed_basic_001 (不带人名/地点)
- NPC:  npc_<姓拼音>_<名拼音>   例 npc_wang_er
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from citysim.gateway.scenarios import load_scene, DEMO_SCENE, NAV_SCENE
from citysim.world.buildings import load_building_types
from citysim.world.itemdefs import load_item_defs
from citysim.world.names import new_name

ROOT = Path(__file__).resolve().parents[1]
SCENES_DIR = ROOT / "config" / "scenes"


# 详细命名校验跑【测试自带的副本】(test_fixtures/elm_lane.json):
# 不依赖 config/scenes/ —— 用户随时会改/删那边, 测试不该跟着挂。
# 用户自己的场景靠下面 test_every_scene_file_loads 做同一套校验。
SCENE = json.loads(
    (ROOT / "tests" / "fixtures" / "elm_lane.json").read_text(encoding="utf-8"))
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# 楼层单元是 <建筑id>_f<N>(多楼层契约, 见 docs/20260914/checklist.md §4.6)
SEQ_ID_RE = re.compile(r"^[a-z][a-z0-9_]*_\d{3}(_f\d+)?$")


def test_every_scene_file_loads() -> None:
    """config/scenes/*.json 每一个都要: ① 能装进世界 ② 自己的 id/引用说得通。

    ② 很重要: 场景是作者手画的, 悬空引用(如 at="" 的孤儿物件)只有这里能拦住。
    """
    files = sorted(SCENES_DIR.glob("*.json"))
    assert files, "config/scenes 里一个场景文件都没有"
    for f in files:
        w, _s, _r = load_scene(f)
        assert w.locations or w.entities, f
        _check_scene(json.loads(f.read_text(encoding="utf-8")), where=f.name)


def _check_scene(scene: dict, where: str) -> None:
    """一份场景数据的 id 格式 + 引用闭合(与上面各 test_* 同一套规则)。"""
    locs = set(scene.get("locations", {}))
    for loc in locs:
        assert SEQ_ID_RE.match(loc), f"{where}: 地点应为 <slug>_<NNN>: {loc}"
    for e in scene.get("entities", []):
        assert e["id"].startswith(e["type"] + "_"), f"{where}: {e}"
        assert e["at"] in locs, f"{where}: 悬空引用(物件不在任何地点): {e}"
    for n in scene.get("npcs", []):
        assert re.match(r"^npc_[a-z0-9_]+$", n["id"]), f"{where}: {n['id']}"
        assert n.get("home", "") in locs or n.get("home", "") == "",             f"{where}: 住所不存在: {n['id']} → {n.get('home')}"


def _items() -> dict:
    return load_item_defs()


def _blds() -> dict:
    return load_building_types()


def test_types_are_category_variant() -> None:
    for t in _items():
        assert ID_RE.match(t), t
        assert "_" in t, f"item type 应为 category_variant: {t}"
    for t in _blds():
        assert ID_RE.match(t), t
        assert "_" in t, f"building type 应为 kind_variant: {t}"


def test_location_ids_are_slug_and_seq() -> None:
    for loc in SCENE["locations"]:
        assert SEQ_ID_RE.match(loc), f"地点应为 <slug>_<NNN>: {loc}"


def test_entity_ids_are_type_and_seq() -> None:
    for e in SCENE["entities"]:
        assert re.match(rf"^{re.escape(e['type'])}_\d{{3}}$", e["id"]), e


def test_npc_ids_are_npc_pinyin() -> None:
    for n in SCENE["npcs"]:
        assert re.match(r"^npc_[a-z0-9_]+$", n["id"]), n["id"]


def test_all_ids_unique() -> None:
    ids = ([e["id"] for e in SCENE["entities"]]
           + list(SCENE["locations"]) + [n["id"] for n in SCENE["npcs"]])
    assert len(ids) == len(set(ids))


def test_references_resolve() -> None:
    locs = set(SCENE["locations"])
    ents = {e["id"] for e in SCENE["entities"]}
    npc_ids = {n["id"] for n in SCENE["npcs"]}
    types = set(_items())
    blds = set(_blds())

    for loc, spec in SCENE["locations"].items():
        assert spec["type"] in blds, (loc, spec["type"])
    for e in SCENE["entities"]:
        assert e["type"] in types, e
        assert e["at"] in locs, e
        owner = e.get("owner", "")
        assert owner == "" or owner in npc_ids or owner.startswith("org_"), e
    for n in SCENE["npcs"]:
        home = n.get("home", "")
        assert home == "" or home in locs, n
        for item_id, rec in (n.get("memory") or {}).items():
            assert item_id in ents, item_id
            if rec.get("located"):
                assert rec["located"] in locs, rec
    for npc_id, plan in (SCENE.get("plans") or {}).items():
        assert npc_id in npc_ids, npc_id
        for it in plan:
            if "target" in it:
                assert it["target"] in ents, it
            if "dest" in it:
                assert it["dest"] in locs, it
    for pair in SCENE.get("travel", {}).get("pairs", {}):
        for x in pair.split("|"):
            assert x in locs, pair
    for t, d in _items().items():
        for eff in (d.on_start + d.on_complete):
            it = (eff or {}).get("item_type")
            if it:
                assert it in types, (t, it)


def test_scene_loads_and_ids_consistent() -> None:
    w, _s, _r = load_scene(DEMO_SCENE)
    assert set(w.locations) == set(SCENE["locations"])
    assert {e.entity_id for e in w.entities.values()} == {e["id"] for e in SCENE["entities"]}
    assert set(w.npcs) == {n["id"] for n in SCENE["npcs"]}


# --- 姓名池 -----------------------------------------------------------
def test_name_pool_rules() -> None:
    a = new_name(7)
    b = new_name(7)
    assert a == b                                   # 同 seed 可复现
    assert re.match(r"^npc_[a-z]+_[a-z]+$", a.person_id), a.person_id
    assert 2 <= len(a.name) <= 4 and a.name == a.surname + a.given
    f = new_name(3, gender="female")
    assert ID_RE.match(f.person_id)
    sibling = f.with_surname(a)
    assert sibling.surname == a.surname and sibling.given == f.given
