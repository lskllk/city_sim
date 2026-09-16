"""柜台交易: 前台 = 销售位。一个前台同一时刻只服务 1 人, 后面的人排队。

用户定的口径:
  · 公司设立一个销售前台 → 就只能招一个人；同时交易的人只能一位，后面排队
  · 两个前台 = 两条线路(每 tick 最多成交 2 份)
  · 没开门 / 没前台 / 柜台没人 → 交易不成立(顾客排队, 等不住就走)
"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.gateway.scenarios import load_scene
from citysim.world import engine as E
from helpers import add_counter, register_company, staff_counter

CFG = load_config("config/sim.toml")


def _scene(n_npc: int = 2, open_minute: int = 0, close_minute: int = 1440) -> dict:
    return {
        "scene": "t", "display_name": "柜台", "canvas": {"w": 400, "h": 300},
        "locations": {
            "shop": {"type": "shop_small", "name": "店", "x": 100, "y": 100,
                     "w": 40, "h": 40},
            "home": {"type": "home_small", "name": "家", "x": 200, "y": 100,
                     "w": 40, "h": 40},
        },
        "entities": [{"id": "food_apple_001", "type": "food_apple", "at": "shop",
                      "price": 5, "stock": 99}],
        "npcs": [{"id": "npc_%d" % i, "name": "顾客%d" % i, "home": "home",
                  "money": 500, "init": {}} for i in range(n_npc)]
                + [{"id": "npc_staff", "name": "店员", "home": "home",
                    "money": 0, "init": {}},
                   {"id": "npc_staff2", "name": "店员2", "home": "home",
                    "money": 0, "init": {}}],
        "travel": {"default": 20, "pairs": {}},
    }


def _load(tmp_path, data, counters: int = 1):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    w, s, r = load_scene(p)
    register_company(w, "shop")
    made = add_counter(w, "shop", counters) if counters else []
    # 用户定的闸门: 员工站在销售台, 交易才能进行 → 每个前台配一个店员
    for i, c in enumerate(made):
        pid = "npc_staff" if i == 0 else "npc_staff2"
        staff_counter(w, s, pid, "shop", c.entity_id)
        st = w.npcs[pid]
        st.set_signals(hunger=1.0, energy=1.0, bladder=1.0)
    if made:
        E.tick(w, s, CFG)                  # 热身一 tick: 店员先站上台(claim)
    comp = w.companies["org_test"]
    comp.open_minute, comp.close_minute = 0, 1440
    for pid in list(w.npcs):
        if pid.startswith("npc_staff"):
            continue
        npc = w.npcs[pid]
        npc.note("food_apple_001", tick=0, located="shop", afford="hunger",
                 value=0.35, price=5.0, stock=99, believe=1.0, source="",
                 tags=("edible", "consumable"), shelf_life_ticks=4320)
        npc.set_signals(hunger=0.1)
        w.place_npc(pid, "shop")           # 直接站在店里(省掉走路)
    return w, s


def test_one_counter_serves_one_per_tick(tmp_path) -> None:
    """1 个前台: 每个 tick 最多成交 1 份 —— 两个顾客不会同一 tick 都买到。"""
    w, s = _load(tmp_path, _scene(2), counters=1)
    E.enqueue_buy(w, s, "npc_0", "shop", "food_apple_001", 1)
    E.enqueue_buy(w, s, "npc_1", "shop", "food_apple_001", 1)
    E.tick(w, s, CFG)
    spent = [500 - w.npcs[p].money for p in ("npc_0", "npc_1")]
    assert sorted(spent) == [0.0, 5.0], spent        # 只有队首买到
    assert s.queued.get("npc_1") == "shop"           # 另一个还在排
    E.tick(w, s, CFG)
    assert 500 - w.npcs["npc_1"].money == 5.0


def test_two_counters_two_lines(tmp_path) -> None:
    """2 个前台 = 两条线路: 同一 tick 能服务 2 个人。"""
    w, s = _load(tmp_path, _scene(2), counters=2)
    E.enqueue_buy(w, s, "npc_0", "shop", "food_apple_001", 1)
    E.enqueue_buy(w, s, "npc_1", "shop", "food_apple_001", 1)
    E.tick(w, s, CFG)
    assert 500 - w.npcs["npc_0"].money == 5.0
    assert 500 - w.npcs["npc_1"].money == 5.0


def test_no_counter_no_trade(tmp_path) -> None:
    """没有前台 → 服务不了 → 放弃并记一次白跑(好感掉)。

    注: 好感【尚未接进决策】(feature 没做完), 所以“再也
    不来”还不成立 —— 这里只钉“一直白跑、好感一直掉、一分钱没花”。
    """
    w, s = _load(tmp_path, _scene(1), counters=0)
    npc = w.npcs["npc_0"]
    E.enqueue_buy(w, s, "npc_0", "shop", "food_apple_001", 1)
    for _ in range(E.QUEUE_GIVEUP + 3):
        E.tick(w, s, CFG)
    assert npc.money == 500.0                        # 一分没花
    assert npc.favor_of("shop") < 1.0                 # 白跑一次记住了
    assert any(e.get("kind") == "intent_failed"
               for e in s.ui_events)
    # 再跑很久: 好感会被反复白跑压到见底, 但【钱始终没花】
    for _ in range(4000):
        E.tick(w, s, CFG)
    assert npc.favor_of("shop") <= 0.05, npc.favor_of("shop")
    assert npc.money == 500.0


def test_closed_shop_does_not_serve(tmp_path) -> None:
    """没开门 → 排队等, 不当场成交。"""
    w, s = _load(tmp_path, _scene(1), counters=1)
    comp = w.companies["org_test"]
    comp.open_minute, comp.close_minute = 480, 1140   # 08:00–19:00
    E.enqueue_buy(w, s, "npc_0", "shop", "food_apple_001", 1)
    for _ in range(5):
        E.tick(w, s, CFG)
    assert w.npcs["npc_0"].money == 500.0
    assert s.queued.get("npc_0") == "shop"


def test_multi_qty_is_sold_one_by_one(tmp_path) -> None:
    """想买 3 份 → 柜台一份一份卖(3 个 tick), 不是一次给 3 份。"""
    w, s = _load(tmp_path, _scene(1), counters=1)
    E.enqueue_buy(w, s, "npc_0", "shop", "food_apple_001", 3)
    for i in range(3):
        E.tick(w, s, CFG)
        assert 500 - w.npcs["npc_0"].money == 5.0 * (i + 1), i
    assert "npc_0" not in s.queued                    # 买够了 → 出队
