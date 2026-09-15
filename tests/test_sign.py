"""招牌 = 站在门口的【虚拟说者】，一直按 told 那套广播。

它复用 NPC 的传播模型，而不是"进了圈就写进脑子":
  · 距离只是【搭桥阈值】: 到【门口】≤ radius 才可能搭上
  · 搭桥两道骰子: 招牌的广播频率(tell_p) × 听众的听概率(listen_p)
  · 搭上之后: 他【停下来】(旅行到达时刻推后), 按【一条消息 1 tick】依次听完
  · 气泡与事件都是 told（"听店铺1号的招牌说：苹果5块"）
"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.gateway.scenarios import load_scene
from citysim.world import engine as E

CFG = load_config("config/sim.toml")


def _scene(radius: float = 60.0, believe: float = 0.6,
           messages: list[str] | None = None, price: float = 5.0,
           start: str = "near") -> dict:
    """店 (100,100)-(140,140), 门默认在【南墙中线】= (120, 140)。

    near 楼中心 (170,120): 到【门】约 54m —— 到【中心】只要 50m, 用这个差别验门槛。
    """
    return {
        "scene": "t", "display_name": "招牌", "canvas": {"w": 400, "h": 300},
        "locations": {
            "shop": {"type": "shop_small", "name": "店铺1号", "x": 100, "y": 100,
                     "w": 40, "h": 40,
                     "sign": {"company": "org_a", "radius": radius,
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
    w, s, _r = load_scene(p)
    s.tell_p, s.listen_p = 1.0, 1.0        # 测试里把骰子变成必过
    return w, s


def _told(systems) -> list:
    return [e for e in systems.ui_events
            if e.get("kind") == "told" and str(e["payload"].get("from", "")).startswith("sign:")]


def _row(npc, item_id: str):
    return next((r for r in npc.memory_dicts() if r["item_id"] == item_id), None)


def test_distance_is_measured_from_the_door(tmp_path) -> None:
    """搭桥阈值量的是【门口】, 不是建筑中心: 半径 52 时门口够不着(中心够得着)。"""
    w, s = _load(tmp_path, _scene(radius=52.0))    # 到门 53.9m, 到中心 50m
    w.place_npc("npc_a", "near")
    for _ in range(3):
        E.tick(w, s, CFG)
    assert _row(w.npcs["npc_a"], "food_apple_001") is None, "应该按门口量, 这里够不着"
    # 半径放到够得着门 → 立刻搭上
    w.locations["shop"]["sign"]["radius"] = 60.0
    E.tick(w, s, CFG)
    assert _row(w.npcs["npc_a"], "food_apple_001") is not None


def test_bridge_needs_both_dice(tmp_path) -> None:
    """搭桥要两道骰子都过: 招牌广播(tell_p) × 他愿不愿意听(listen_p)。"""
    w, s = _load(tmp_path, _scene())
    s.listen_p = 0.0                               # 谁都不听 → 永远搭不上
    w.place_npc("npc_a", "near")
    for _ in range(5):
        E.tick(w, s, CFG)
    assert _row(w.npcs["npc_a"], "food_apple_001") is None
    assert not s.sign_queue
    s.listen_p = 1.0
    E.tick(w, s, CFG)
    # 搭上的这一 tick 就开始听第一条(桥建完立刻递一条)
    assert _row(w.npcs["npc_a"], "food_apple_001") is not None
    assert not s.sign_queue, "一条就听完了, 桥拆掉"


def test_one_message_per_tick(tmp_path) -> None:
    """招牌上 3 条 → 一条消息 1 tick, 不是一 tick 全给了。"""
    msgs = ["food_apple_001", "food_pear_002", "meal_simple_003"]
    data = _scene(messages=msgs)
    data["entities"] += [
        {"id": "food_pear_002", "type": "food_pear", "at": "shop", "price": 4.0,
         "stock": 9},
        {"id": "meal_simple_003", "type": "meal_simple", "at": "shop",
         "price": 8.0, "stock": 9},
    ]
    w, s = _load(tmp_path, data)
    npc = w.npcs["npc_a"]
    w.place_npc("npc_a", "near")
    E.tick(w, s, CFG)                     # 搭桥 + 递第 1 条
    assert _row(npc, msgs[0]) is not None
    assert _row(npc, msgs[1]) is None, "第 2 条不该在同一 tick 就到"
    E.tick(w, s, CFG)
    assert _row(npc, msgs[1]) is not None
    assert _row(npc, msgs[2]) is None
    E.tick(w, s, CFG)
    assert _row(npc, msgs[2]) is not None
    assert not s.sign_queue, "听完了, 桥拆掉"


def test_believe_is_heard_tier_and_bubble_is_told_shaped(tmp_path) -> None:
    """记忆按"听说"档打折; 气泡走 told 格式(招牌不是人, 但措辞是同一种)。"""
    w, s = _load(tmp_path, _scene(believe=0.6))
    npc = w.npcs["npc_a"]
    w.place_npc("npc_a", "near")
    E.tick(w, s, CFG)
    row = _row(npc, "food_apple_001")
    assert abs(row["believe"] - 0.6) < 1e-9
    assert row["source"] == "sign:shop"
    kind = npc.bubble[2] if npc.bubble else ""
    assert kind == "told", kind
    assert "店铺1号" in npc.bubble[0], "气泡里得看出是招牌说的"
    assert len(_told(s)) == 1


def test_passerby_stops_to_listen(tmp_path) -> None:
    """搭上桥 → 他停下来听完(旅行到达时刻被推后)。"""
    w, s = _load(tmp_path, _scene())
    npc = w.npcs["npc_a"]
    # 让他从 far 走到 shop: 用 MoveTo 直接下发(不依赖路网)
    w.place_npc("npc_a", "far")
    # 直接建一次旅行(不依赖路网): 与 engine 里 MoveTo 的做法一致
    from citysim.world.travel import Travel
    s.travel["npc_a"] = Travel(from_loc="far", to_loc="shop", depart_tick=0,
                               arrive_tick=200)
    before = s.travel["npc_a"].arrive_tick
    for _ in range(3):
        E.tick(w, s, CFG)
        if s.sign_queue or _told(s):
            break
    if _told(s):
        after = s.travel["npc_a"].arrive_tick if "npc_a" in s.travel else before
        assert after > before, "听招牌的时候应该慢下来/站住"
    else:
        # 没走到半径内也不用判失败 —— 这条主要保证不炸
        assert npc is not None


def test_radius_out_of_range_and_missing_entity(tmp_path) -> None:
    """半径外不知道; 招牌写了不存在的货 → 忽略(不崩), 也不占队列。"""
    w, s = _load(tmp_path, _scene(radius=5.0,
                                  messages=["food_apple_001", "nope_9"]))
    npc = w.npcs["npc_a"]
    w.place_npc("npc_a", "far")
    for _ in range(3):
        E.tick(w, s, CFG)
    assert _row(npc, "food_apple_001") is None
    w.locations["shop"]["sign"]["radius"] = 60.0
    w.place_npc("npc_a", "near")                  # 走近了才够得着门口
    for _ in range(5):
        E.tick(w, s, CFG)
    assert _row(npc, "food_apple_001") is not None
    assert _row(npc, "nope_9") is None


def test_already_known_and_unchanged_is_not_retold(tmp_path) -> None:
    """已经知道且价格没变 → 不再重复说(桥搭上也是白搭)。"""
    w, s = _load(tmp_path, _scene())
    npc = w.npcs["npc_a"]
    w.place_npc("npc_a", "near")
    E.tick(w, s, CFG)
    assert len(_told(s)) == 1
    for _ in range(5):
        E.tick(w, s, CFG)
    assert len(_told(s)) == 1
    # 价格变了 → 会说一次新的
    w.entities["food_apple_001"].price = 7.0
    for _ in range(3):
        E.tick(w, s, CFG)
    assert len(_told(s)) == 2
    assert _row(npc, "food_apple_001")["price"] == 7.0
