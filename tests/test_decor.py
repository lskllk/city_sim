"""装修: 公司给店里摆装修件(马桶/销售前台), 从公司账出钱。

用户定的口径: 装修是【公司经营动作】—— 面板上按一下, 世界多一件设施、
公司账少一笔钱; 装修件不是可零售的货(不进市场货架)。
"""
from __future__ import annotations

from citysim.world.econ.market import (decorate, fixture_catalog, is_fixture,
                                  market_catalog, purchase)
from helpers import make_runtime, register_company


def _world():
    from citysim.core.config import load_config
    w, _s, _r = make_runtime(load_config("config/sim.toml"))
    w.locations["shop"] = {"kind": "shop", "name": "店", "x": 0, "y": 0,
                           "w": 10, "h": 10}
    comp = register_company(w, "shop", cash=1000.0)
    return w, comp


def test_fixture_catalog_and_semantics() -> None:
    catalog = {f["type"]: f for f in fixture_catalog()}
    assert "toilet_basic" in catalog and "station_counter" in catalog
    assert catalog["toilet_basic"]["price"] == 120.0
    assert is_fixture("toilet_basic") and not is_fixture("food_apple")


def test_decorate_spends_cash_and_places_entity() -> None:
    w, comp = _world()
    res = decorate(w, comp, "shop", "toilet_basic")
    assert res["ok"] and res["cost"] == 120.0
    assert comp.cash == 880.0
    placed = [e for e in w.entities.values() if e.item_type == "toilet_basic"]
    assert len(placed) == 1 and placed[0].location_id == "shop"
    assert placed[0].persist_empty


def test_decorate_rejects_bad_inputs() -> None:
    w, comp = _world()
    assert not decorate(w, comp, "elsewhere", "toilet_basic")["ok"]
    assert not decorate(w, comp, "shop", "food_apple")["ok"]      # 不是装修件
    comp.cash = 10.0
    assert not decorate(w, comp, "shop", "toilet_basic")["ok"]    # 钱不够
    assert comp.cash == 10.0


def test_market_does_not_sell_fixtures() -> None:
    w, comp = _world()
    assert "toilet_basic" not in {c["type"] for c in market_catalog()}
    assert not purchase(w, comp, "shop", "toilet_basic", 1)["ok"]


def test_market_catalog_lists_goods_with_wholesale_price() -> None:
    cat = {c["type"]: c for c in market_catalog()}
    assert "food_apple" in cat and cat["food_apple"]["price"] == 3.0
    assert "toilet_basic" not in cat          # 装修件不是货
    assert all("name" in c for c in cat.values())
