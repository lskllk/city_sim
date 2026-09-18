"""传闻(gossip)要把【这条东西是什么】一起带过去 —— tags 是其中关键的一项。

踩过的坑(实测: 5/6 个人在 D25 前饿死):
    店里的苹果在"只听说过"的人记忆里 tags=[] —— 而"囤货"的判据要求
    `consumable` 标签 → 那条行【永远买不了】→ 家里饭吃光后就只能干等着饿死。
    同一件东西, 亲眼见过的人 tags=['consumable','edible'] → 他会去买。
所以"说"的时候必须把 tags 一起递过去(听的人不能只拿到价格和地点)。
"""
from __future__ import annotations

import json
import pathlib

from citysim.core.config import load_config
from citysim.npc import brain
from citysim.world.run.gossip import _notify_due

from helpers import add_npc, make_runtime

CFG = load_config(pathlib.Path("config/sim.toml"))


def _two_talkers(tell_p: float = 1.0):
    w, s, _ = make_runtime(CFG)
    s.tell_p = tell_p
    s.listen_p = 1.0
    a = add_npc(w, s, "a", location="loc", home="home")
    b = add_npc(w, s, "b", location="loc", home="home")
    return w, s, a, b


def _knows_apple(npc) -> None:
    npc.note("apple", located="shop", afford="hunger", value=0.35, price=5.0,
             stock=10, tags=("consumable", "edible"),
             item_type="food_apple", shelf_life_ticks=4320)


def test_gossip_hands_over_tags_not_just_price() -> None:
    """听的人拿到的行必须带 tags —— 否则那条行在决策里等于"不能用"。"""
    w, s, a, b = _two_talkers()
    _knows_apple(a)
    for _ in range(200):
        w.clock_tick += 1
        _notify_due(w, s, a, None, CFG)      # ev=None → 从记忆里挑一件值得说的
        if b._mem.get("apple") is not None:
            break
    row = b._mem.get("apple")
    assert row is not None, "两轮都该传到"
    assert "consumable" in row.tags
    assert row.afford == "hunger" and row.price > 0
    assert row.source == "a" and row.believe <= 1.0     # 听来的: 不如亲眼硬


def test_hearsay_food_is_buyable_so_the_listener_can_stock_up() -> None:
    """★ 这条就是那个饿死 bug 的护栏:

    只"听说过"店里有吃的、自己家里又没有的人, 必须能把它当【囤货】候选 —
    否则他只会坐着饿死。
    """
    w, s, a, b = _two_talkers()
    _knows_apple(a)
    for _ in range(200):
        w.clock_tick += 1
        _notify_due(w, s, a, None, CFG)
        if b._mem.get("apple") is not None:
            break
    cands = brain._gather_candidates(
        b._mem, b.signals, w.clock_tick, self_id="b", home=b.home, cfg=CFG,
        future_weight=CFG.stock_future_weight, thrift=1.0)
    assert [r.item_id for r, *_ in cands] == ["apple"]
    assert cands[0][4] == "future"          # 买 = 囤货(为家里补)


# --- 长局里踩到的三个真坑 (每一个都单独能让全城饿死) -----------------------

def test_sold_out_shelf_keeps_its_shell_so_restock_can_find_it(tmp_path) -> None:
    """★ 货架卖空【要留壳】。

    卖空那一刻实体被销毁 → "开门前补货"找不到"这家店卖什么" → 永远不再补。
    实测: 1000 份苹果卖光后全城断粮, D87 全灭。
    """
    data = {
        "canvas": {"w": 400, "h": 300},
        "locations": {"shop": {"type": "shop_small", "name": "店",
                               "x": 100, "y": 100, "w": 40, "h": 40}},
        "entities": [{"id": "apple", "type": "food_apple", "at": "shop",
                      "price": 5.0, "stock": 1}],
        "npcs": [],
    }
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    from citysim.gateway.scenarios import load_scene
    w, _s, _r = load_scene(p)
    assert w.entities["apple"].persist_empty is True


def test_favor_returns_to_neutral_so_bad_luck_is_not_permanent(tmp_path) -> None:
    """★ 好感度每天向中性回升。

    没有它好感度【只降不升】: 白跑七次掉到 0 → 打分里"fav<=0 不成立"
    → 那家店的货永久不进候选 → 再也不去买。
    """
    w, s, _ = make_runtime(CFG)
    a = add_npc(w, s, "a", location="loc", home="home")
    for _ in range(8):
        a.bump_favor("shop", -CFG.favor_no_service_down, CFG)
    assert a.favor_of("shop", CFG.favor_neutral) == 0.0     # 被拉黑了
    for _ in range(40):                                      # 每天一次
        a.drift_favor(CFG)
    assert a.favor_of("shop", CFG.favor_neutral) == CFG.favor_neutral


def test_a_dead_worker_frees_his_station_so_the_shop_can_rehire(tmp_path) -> None:
    """★ 死人要从公司名册撤下 —— 否则他那工位永远算"有人占", 永远补不上人。

    实测链条: 唯一店员一死 → 店没人守台 → 全城排队买不到饭 → 全灭。
    """
    from citysim.world.model.companies import Company
    from citysim.world.run.engine import _kill
    w, s, _ = make_runtime(CFG)
    a = add_npc(w, s, "a", location="loc", home="home")
    w.companies["org"] = Company(company_id="org", staff=(("a", 3.0),))
    _kill(w, s, "a")
    assert w.companies["org"].staff == ()
