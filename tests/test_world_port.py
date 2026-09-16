"""WP-02..04: `WorldPortImpl` 的 world 侧行为(权限/仲裁/原子)。

端口是 NPC 主动拉的入口; 这些测试钉【world 侧的决定权】。
按票逐步补齐: WP-02 observe/try_move, WP-03 try_take, WP-04 try_buy。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
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
