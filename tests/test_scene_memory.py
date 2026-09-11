"""场景初始记忆(memory 段)加载契约 + 同商品合并规则。"""
from __future__ import annotations

from citysim.gateway.scenarios import load_scene

NPC = "npc_wang_er"
SHOP = "meal_simple_003"
TV_SHOP = "media_tv_002"
TV_HOME = "media_tv_001"


def _rows(person) -> dict:
    return {m["item_id"]: m for m in person.memory_dicts()}


def test_scene_memory_loaded_into_person() -> None:
    w, _s, _r = load_scene()
    rows = _rows(w.npcs[NPC])
    shop = rows[SHOP]
    assert shop["located"] == "market_001"
    assert shop["afford"] == "hunger"
    assert shop["value"] == 0.5
    assert shop["price"] == 3.0
    assert rows[TV_SHOP]["located"] == "market_001"
    assert rows[TV_SHOP]["price"] == 60.0
    assert rows[TV_HOME]["located"] == "apt_001"


def test_same_goods_merged_single_entity_with_stock() -> None:
    """同一商品(同类型/地点/归属/售价)只建一个实体, 数量记在 stock。"""
    w, _s, _r = load_scene()
    tvs = [e for e in w.entities.values()
           if e.location_id == "market_001" and e.item_type == "media_tv"]
    assert len(tvs) == 1
    assert tvs[0].entity_id == TV_SHOP
    assert tvs[0].stock == 2          # 合并 ×2
    assert tvs[0].price == 60.0       # 有售价
    meals = [e for e in w.entities.values()
             if e.location_id == "market_001" and e.item_type == "meal_simple"]
    assert len(meals) == 1 and meals[0].entity_id == SHOP
