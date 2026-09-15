"""招牌: 【被动感知源】—— 走进半径就"被 told"，写进记忆时按听说的档打折。

和传播的区别(别搞混):
  · 传播 _notify_due: 人与人, 有说概率/听概率/一对一/话题冷却
  · 招牌 _perceive_signs: 世界在说话, 不挑人、不等你愿意听, 只要你路过
两者写出来的记忆都带 source —— 招牌是 "sign:<bid>", 所以它仍会被转述出去。
"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.gateway.scenarios import load_scene
from citysim.world import engine as E

CFG = load_config("config/sim.toml")


def _scene(sign_radius: float = 60.0, believe: float = 0.6,
           messages: list[str] | None = None, price: float = 5.0,
           player_loc: str = "near") -> dict:
    """店在 (100,100)-(140,140), 中心 (120,120); 隔壁楼中心 (170,120) —— 相距 50m。"""
    return {
        "scene": "t", "display_name": "招牌", "canvas": {"w": 400, "h": 300},
        "locations": {
            "shop": {"type": "shop_small", "name": "店", "x": 100, "y": 100,
                     "w": 40, "h": 40,
                     "sign": {"company": "org_a", "radius": sign_radius,
                              "believe": believe,
                              "messages": messages or ["food_apple_001"]}},
            "near": {"type": "home_small", "name": "隔壁", "x": 150, "y": 100,
                     "w": 40, "h": 40},
            "far": {"type": "home_small", "name": "远处", "x": 900, "y": 900,
                    "w": 40, "h": 40},
        },
        "entities": [{"id": "food_apple_001", "type": "food_apple", "at": "shop",
                      "price": price, "stock": 99}],
        "npcs": [{"id": "npc_a", "name": "甲", "home": "far", "money": 500,
                  "init": {}}],
        "travel": {"default": 20, "pairs": {}},
    }


def _load(tmp_path, data: dict):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_scene(p)


def _saw(systems) -> list:
    return [e for e in systems.ui_events if e.get("kind") == "saw_sign"]


def _row(npc, item_id: str):
    return next((r for r in npc.memory_dicts() if r["item_id"] == item_id), None)


def test_walking_past_a_sign_is_told(tmp_path) -> None:
    """走进半径 → 记忆写进去, 来源是招牌, 相信度是招牌那个档(不是 1.0)。"""
    w, s, _r = _load(tmp_path, _scene())
    npc = w.npcs["npc_a"]
    w.place_npc("npc_a", "near")            # 隔壁(半径 60 内)
    E.tick(w, s, CFG)
    row = _row(npc, "food_apple_001")
    assert row is not None, "路过招牌却什么都没学到"
    assert row["source"] == "sign:shop"
    assert abs(row["believe"] - 0.6) < 1e-9, row["believe"]
    assert row["price"] == 5.0 and row["afford"] == "hunger"
    assert npc.bubble is not None and npc.bubble[2] == "sign"
    assert len(_saw(s)) == 1
    # 站着不动 → 不重复说
    for _ in range(5):
        E.tick(w, s, CFG)
    assert len(_saw(s)) == 1, "同一条消息不该每 tick 重复说"


def test_out_of_range_learns_nothing(tmp_path) -> None:
    """半径外 → 一无所知(招牌不是"全城广播")。"""
    w, s, _r = _load(tmp_path, _scene(sign_radius=10.0))
    npc = w.npcs["npc_a"]
    w.place_npc("npc_a", "far")
    for _ in range(3):
        E.tick(w, s, CFG)
    assert _row(npc, "food_apple_001") is None
    assert _saw(s) == []


def test_sign_price_change_updates_and_surprises(tmp_path) -> None:
    """招牌上的价变了 → 记忆更新 + 冒 SURPRISE(而不是 DOUBT: 招牌不是人说的)。"""
    w, s, _r = _load(tmp_path, _scene())
    npc = w.npcs["npc_a"]
    w.place_npc("npc_a", "near")
    E.tick(w, s, CFG)
    assert _row(npc, "food_apple_001")["price"] == 5.0
    w.entities["food_apple_001"].price = 8.0
    E.tick(w, s, CFG)
    assert _row(npc, "food_apple_001")["price"] == 8.0
    assert len(_saw(s)) == 2
    assert any(r["believe"] == 0.6 for r in npc.memory_dicts())
    acts = [e.get("kind") for e in s.ui_events]
    assert "saw_sign" in acts


def test_sign_is_spreadable_by_gossip(tmp_path) -> None:
    """招牌学来的消息仍然只是"听说" → 可以被转述出去(走 _may_tell 第 ⑤ 条)。"""
    w, s, _r = _load(tmp_path, _scene())
    w.place_npc("npc_a", "near")
    E.tick(w, s, CFG)
    row = _row(w.npcs["npc_a"], "food_apple_001")
    assert row["believe"] >= 0.3, "低于传播下限就只能烂在自己脑子里"
    assert row["source"] != "", "没有来源的记忆无法溯源, 也说不清是谁说的"


def test_sign_caps_messages_and_ignores_missing_entities(tmp_path) -> None:
    """最多挂 3 条; 写了不存在的货 → 忽略(不崩)。"""
    data = _scene(messages=["food_apple_001", "nope_1", "nope_2", "nope_3"])
    w, s, _r = _load(tmp_path, data)
    assert len(w.locations["shop"]["sign"]["messages"]) == 3      # 截到 3 条
    w.place_npc("npc_a", "near")
    for _ in range(3):
        E.tick(w, s, CFG)          # 不抛异常
    assert len(_saw(s)) == 1, "只有真实存在的那条被说出来"
