"""★ 定死的原则: 放在某【住所】里的东西, 该住所的【所有授权人】都能免费使用。

编辑器把食物/床/马桶摆进某住所 → 屋里的东西对 owner/open_to(能进门的人)都是
自家财产, 不看 price/owner。以前 `for_sale = price>0 and owner != self` 会把它
当商品: 同住的人(甚至户主本人)走 Buy → 没公司/没前台 → 成交失败 → **家里有饭吃
不上, 活活饿死**。这里把原则钉进测试, 防回归。
"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.core.types import Buy, Interact
from citysim.gateway.scenarios import load_scene
from citysim.world.edge.port import WorldPortImpl
from citysim.world.edge.perception import build_percept

CFG = load_config("config/sim.toml")


def _home_scene() -> dict:
    """一个住所 + 两个住客 + 一份带默认价(5.0)的餐食。"""
    return {
        "canvas": {"w": 400, "h": 300},
        "locations": {
            "home": {"type": "home_standard", "name": "家",
                     "x": 100, "y": 100, "w": 40, "h": 40},
            "shop": {"type": "shop_small", "name": "店",
                     "x": 200, "y": 100, "w": 40, "h": 40},
        },
        "entities": [
            # 不写 price → 继承 itemdef 的 5.0(以前正是这样被判成"商品")
            {"id": "meal_simple_001", "type": "meal_simple",
             "at": "home", "stock": 5},
        ],
        "npcs": [
            {"id": "npc_a", "name": "甲", "home": "home", "money": 100},
            {"id": "npc_b", "name": "乙", "home": "home", "money": 100},
            {"id": "npc_out", "name": "丙", "home": "shop", "money": 100},
        ],
    }


def _load(tmp_path):
    p = tmp_path / "scene.json"
    p.write_text(json.dumps(_home_scene(), ensure_ascii=False),
                 encoding="utf-8")
    return load_scene(p)


def _decide_at(w, s, pid: str, tick: int = 0):
    """让某人看一次现场并决策(饥饿压到很低, 保准想吃)。"""
    npc = w.npcs[pid]
    npc.set_signal("hunger", 0.05)
    world_loc = w.loc_of(pid)
    npc.perceive(build_percept(w, npc), tick)
    assert world_loc == w.loc_of(pid)          # build_percept 是纯读
    return npc.decide(CFG, tick).intent


def test_is_household_covers_owner_and_open_to_only(tmp_path) -> None:
    """授权口径 = 门禁口径: 户主 + open_to 是; 外人不是。"""
    w, _s, _r = _load(tmp_path)
    meal = w.entities["meal_simple_001"]
    assert w.is_residence("home") is True
    assert w.is_residence("shop") is False
    assert w.is_household(meal, "npc_a") is True     # 户主
    assert w.is_household(meal, "npc_b") is True     # 同住授权人
    assert w.is_household(meal, "npc_out") is False  # 外人
    # 店里的东西永远不是家用物品
    w.spawn_item_type("meal_simple", "shop")
    shop_meal = [e for e in w.entities.values()
                 if e.location_id == "shop" and e.item_type == "meal_simple"][0]
    assert w.is_household(shop_meal, "npc_out") is False


def test_residents_eat_home_food_for_free_not_buy(tmp_path) -> None:
    """★ 核心回归: 同住的所有授权人, 面对"有价"的家用食物都走 Interact(免费),
    而不是 Buy(家里没有公司/前台, 走 Buy 必然失败 → 饿死)。"""
    w, _s, _r = _load(tmp_path)
    for pid in ("npc_a", "npc_b"):
        w.place_npc(pid, "home")
        intent = _decide_at(w, _s, pid)
        assert isinstance(intent, Interact), (pid, intent)
        assert intent.target_id == "meal_simple_001"


def test_authorized_interact_on_priced_home_item_is_not_blocked(tmp_path) -> None:
    """引擎的"在售商品·需购买"兜底不能拦自家住所里的东西 —— 包括户主
    (原始实体 owner=""、price=5, 以前会被误拦)。"""
    w, s, _r = _load(tmp_path)
    for pid in ("npc_a", "npc_b"):
        w.place_npc(pid, "home")
        npc = w.npcs[pid]
        WorldPortImpl(w, s, CFG).try_take(pid, "meal_simple_001")
        blocked = [e for e in s.ui_events
                   if e.get("kind") == "intent_failed"
                   and e["payload"].get("why") == "在售商品·需购买"]
        assert not blocked, (pid, blocked)


def test_takeaway_delivered_home_food_is_shared(tmp_path) -> None:
    """买回家的东西也归住所用: 送货进家(itemdef 价 5.0) → 同住者仍免费吃。"""
    w, s, _r = _load(tmp_path)
    home = w.entities["meal_simple_001"]
    other = w.spawn_item_type("meal_simple", "home")
    other.owner = "npc_a"                     # 甲买回来的
    other.price = 5.0
    assert w.is_household(other, "npc_b") is True
    assert w.is_household(home, "npc_b") is True
    w.place_npc("npc_b", "home")
    intent = _decide_at(w, s, "npc_b")
    assert isinstance(intent, Interact)
    # 且不是买
    assert not isinstance(intent, Buy)
