"""场景初始记忆(memory 段)加载契约 + 同商品合并规则。"""
from __future__ import annotations

from citysim.gateway.scenarios import load_scene, DEMO_SCENE, NAV_SCENE

NPC = "npc_wang_er"
SHOP = "meal_simple_003"


def _rows(person) -> dict:
    return {m["item_id"]: m for m in person.memory_dicts()}


def test_scene_memory_loaded_into_person() -> None:
    w, _s, _r = load_scene(DEMO_SCENE)
    rows = _rows(w.npcs[NPC])
    shop = rows[SHOP]
    assert shop["located"] == "market_001"
    assert shop["afford"] == "hunger"
    assert shop["value"] == 0.5
    assert shop["price"] == 3.0


def test_same_goods_merged_single_entity_with_stock() -> None:
    """同一商品(同类型/地点/归属/售价)只建一个实体, 数量记在 stock。"""
    w, _s, _r = load_scene(DEMO_SCENE)
    meals = [e for e in w.entities.values()
             if e.location_id == "market_001" and e.item_type == "meal_simple"]
    assert len(meals) == 1 and meals[0].entity_id == SHOP
    assert meals[0].stock == 50       # 货架库存
    assert meals[0].price == 3.0      # 有售价
