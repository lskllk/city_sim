"""A：出门"买"的边际收益要扣掉【家里已有的供货】。

根因(用户报的 bug): "买回来"是送到【家】的, 人还在店门口 —— 需求一点没变。
不扣已有供货的话, "手里还有 5 个苹果"完全没进入评分, 而在店里再买一个不要
路费、回家吃却要走 23 tick → 于是每个 tick 再买一个(实测 2 天买 81 次、花 ¥470)。

最小改动 + 不重复建模:
  · 复用现成的 _home_stock(没有新状态);
  · 只作用于【不在本家】的行(出门去拿的); 吃家里现成的不扣(吃本身就是满足);
  · 与 fut(囤货)分工: 供贷抵消管"眼前够不够吃", fut 管"存货占目标的比例"。
"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.gateway.scenarios import load_scene
from citysim.world import engine as E
from citysim.world.world import entity_from_def
from citysim.world.itemdefs import load_item_defs

CFG = load_config("config/sim.toml")


def _scene(price: float = 5.0) -> dict:
    return {
        "scene": "t", "display_name": "供贷", "canvas": {"w": 400, "h": 300},
        "locations": {
            "shop": {"type": "shop_small", "name": "店", "x": 300, "y": 100,
                     "w": 40, "h": 40},
            "home": {"type": "home_small", "name": "家", "x": 20, "y": 100,
                     "w": 40, "h": 40},
        },
        "entities": [{"id": "food_apple_001", "type": "food_apple", "at": "shop",
                      "price": price, "stock": 99}],
        "npcs": [{"id": "npc_a", "name": "甲", "home": "home", "money": 500,
                  "init": {}}],
        "travel": {"default": 20, "pairs": {}},
    }


def _load(tmp_path, data: dict):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_scene(p)


def _stock_home(world, npc, n: int) -> str:
    e = entity_from_def(load_item_defs()["food_apple"], npc.home)
    e.owner = npc.person_id
    e.stock = n
    world.spawn_entity(e)
    return e.entity_id


def _meta(cands, item_id):
    return next(((sig, need, want, drv) for row, sig, need, want, drv in cands
                 if row.item_id == item_id), None)


def _cands(world, npc):
    from citysim.npc.brain import _gather_candidates
    return _gather_candidates(npc._mem, npc.signals, world.clock_tick,
                              home=npc.home, cfg=CFG,
                              future_weight=CFG.stock_future_weight)


def test_full_pantry_kills_the_need_to_buy(tmp_path) -> None:
    """家里够吃 → 在售那条的边际需求归零(不再"手里有饭还去买")。"""
    w, _s, _r = _load(tmp_path, _scene())
    npc = w.npcs["npc_a"]
    npc.set_signals(hunger=0.5)                   # 饿 0.5
    npc.note("food_apple_001", tick=0, located="shop", afford="hunger",
             value=0.35, price=5.0, stock=99, believe=1.0, source="")
    # 家里 5 个苹果 = 1.75 的需求量 → 早就够了
    cid = _stock_home(w, npc, 5)
    npc.note(cid, tick=0, located=npc.home, owner=npc.person_id,
             afford="hunger", value=0.35, price=0.0, stock=5, believe=1.0,
             source="", tags=("edible", "consumable"))
    m = _meta(_cands(w, npc), "food_apple_001")
    assert m is not None
    assert m[1] == 0.0, "家里够吃还去买(%r)" % (m,)


def test_partial_pantry_leaves_only_the_gap(tmp_path) -> None:
    """家里只有 1 个(0.35)而缺口 0.5 → 边际需求只剩 0.15，不是 0.5。"""
    w, _s, _r = _load(tmp_path, _scene())
    npc = w.npcs["npc_a"]
    npc.set_signals(hunger=0.5)
    npc.note("food_apple_001", tick=0, located="shop", afford="hunger",
             value=0.35, price=5.0, stock=99, believe=1.0, source="")
    cid = _stock_home(w, npc, 1)
    npc.note(cid, tick=0, located=npc.home, owner=npc.person_id,
             afford="hunger", value=0.35, price=0.0, stock=1, believe=1.0,
             source="", tags=("edible", "consumable"))
    sig, need, _want, _drv = _meta(_cands(w, npc), "food_apple_001")
    assert abs(need - 0.15) < 1e-9, need              # 0.5 − 0.35


def test_eating_own_food_is_not_offset(tmp_path) -> None:
    """吃家里现成的不扣供贷 —— 扣了就不吃饭了。"""
    w, _s, _r = _load(tmp_path, _scene())
    npc = w.npcs["npc_a"]
    npc.set_signals(hunger=0.5)
    cid = _stock_home(w, npc, 5)
    npc.note(cid, tick=0, located=npc.home, owner=npc.person_id,
             afford="hunger", value=0.35, price=0.0, stock=5, believe=1.0,
             source="", tags=("edible", "consumable"))
    sig, need, _want, _drv = _meta(_cands(w, npc), cid)
    assert abs(need - 0.5) < 1e-9, need               # 该吃还是得吃


def test_no_repeat_buying_loop(tmp_path) -> None:
    """端到端: 站在店里 + 家里够吃 → 不会每 tick 买一个(旧版刷爆钱包)。"""
    w, s, _r = _load(tmp_path, _scene())
    npc = w.npcs["npc_a"]
    npc.set_signals(hunger=0.4)
    cid = _stock_home(w, npc, 8)
    npc.note(cid, tick=0, located=npc.home, owner=npc.person_id,
             afford="hunger", value=0.35, price=0.0, stock=8, believe=1.0,
             source="", tags=("edible", "consumable"))
    w.place_npc("npc_a", "shop")                  # 他就在店里
    spent = 0.0
    for _ in range(200):
        m0 = npc.money
        E.tick(w, s, CFG)
        spent += max(0.0, m0 - npc.money)
    assert spent == 0.0, "家里够吃还在店里连买(花了 ¥%.0f)" % spent
