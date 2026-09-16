"""WP-02..04: `WorldPortImpl` 的 world 侧行为(权限/仲裁/原子)。

端口是 NPC 主动拉的入口; 这些测试钉【world 侧的决定权】。
按票逐步补齐: WP-02 observe/try_move, WP-03 try_take, WP-04 try_buy。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.ports import Ack, Deny, Grant
from citysim.core.types import Percept
from citysim.world.port import WorldPortImpl

from helpers import add_entity, add_npc, make_runtime, register_company

CFG = load_config(Path("config/sim.toml"))


def _port(w, s) -> WorldPortImpl:
    return WorldPortImpl(w, s, CFG)


# --- observe (WP-02) -------------------------------------------------------
def test_observe_returns_percept_for_self() -> None:
    w, s, _ = make_runtime(CFG)
    add_npc(w, s, "npc", location="home")
    p = _port(w, s).observe("npc")
    assert isinstance(p, Percept)
    assert p.location_id == "home"


# --- try_move (WP-02) ------------------------------------------------------
def test_try_move_sets_travel() -> None:
    w, s, _ = make_runtime(CFG)
    add_npc(w, s, "npc", location="home")
    ack = _port(w, s).try_move("npc", "work")
    assert ack.ok
    assert s.travel["npc"].to_loc == "work"


def test_try_move_same_location_is_noop() -> None:
    w, s, _ = make_runtime(CFG)
    add_npc(w, s, "npc", location="home")
    assert _port(w, s).try_move("npc", "home").ok
    assert "npc" not in s.travel


def test_try_move_denied_by_capacity_leaves_npc_put() -> None:
    """目的地已满 → 不出发, 返回 ok=False, 且不写 travel。"""
    w, s, _ = make_runtime(CFG)
    w.locations["full"] = {"capacity": 1}
    add_npc(w, s, "a", location="full")           # 占满
    add_npc(w, s, "b", location="home")
    ack = _port(w, s).try_move("b", "full")
    assert not ack.ok
    assert "b" not in s.travel
    assert w.loc_of("b") == "home"


# --- try_take (WP-03) ------------------------------------------------------
def test_try_take_free_item_returns_grant() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    add_npc(w, s, "npc", location="loc")
    r = _port(w, s).try_take("npc", "meal")
    assert isinstance(r, Grant)
    assert (r.signal, r.value, r.duration_ticks) == ("hunger", 0.5, 20)
    assert s.interaction.active["npc"].entity_id == "meal"


def test_try_take_denied_for_unowned_priced_item() -> None:
    """非授权人 + 在售 + 有主 → Deny(在售商品·需购买)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="shop", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    w.entities["meal"].price = 5.0
    w.entities["meal"].owner = "org_test"
    add_npc(w, s, "npc", location="shop")
    r = _port(w, s).try_take("npc", "meal")
    assert isinstance(r, Deny)
    assert "在售" in r.reason


# --- try_buy (WP-04) -------------------------------------------------------
def test_try_buy_enqueues_not_settles() -> None:
    """买是异步的: try_buy ok=True 只表示【已入队】, 货没扣。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "shop", location="town", tags=("building",), affordances={})
    add_entity(w, "meal", location="shop", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20, stock=10)
    w.entities["meal"].price = 5.0
    register_company(w, ["shop"])
    add_npc(w, s, "npc", location="shop", money=100.0)
    ack = _port(w, s).try_buy("npc", "meal", 2)
    assert isinstance(ack, Ack) and ack.ok
    assert s.queued.get("npc") == "shop"        # 入队了
    assert w.entities["meal"].stock == 10       # 还没扣货(异步)

