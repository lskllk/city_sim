"""建筑进入权限: owner/open_to/public + 容量上限 + 引擎移动拦截。"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Decision, MoveTo
from citysim.gateway.scenarios import load_scene
from citysim.world.engine import _apply

from helpers import add_npc, make_runtime

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def test_scene_binds_home_owner_and_public() -> None:
    w, _s, _r = load_scene()
    # 住所: 首个住客=户主, 默认私人
    assert w.locations["apt_001"]["owner"] == "npc_wang_er"
    assert w.locations["apt_002"]["owner"] == "npc_li_si"
    assert w.locations["apt_001"]["public"] is False
    # 商铺/广场: 无主 → 公共
    assert w.locations["market_001"]["public"] is True
    assert w.locations["plaza_001"]["public"] is True


def test_entry_check_forbidden_and_allowed() -> None:
    w, _s, _r = load_scene()
    assert w.entry_check("apt_001", "npc_li_si") == (False, "无权进入")
    assert w.entry_check("apt_001", "npc_wang_er")[0] is True
    assert w.entry_check("market_001", "npc_li_si")[0] is True


def test_public_full_blocks_entry() -> None:
    w, s, rng = make_runtime(CFG)
    w.locations = {"market": {"name": "超市", "kind": "shop", "capacity": 1,
                              "owner": "", "open_to": [], "public": True}}
    add_npc(w, s, "npc_full", location="market", rng_pool=rng)
    add_npc(w, s, "npc_a", location="home", rng_pool=rng)
    assert w.entry_check("market", "npc_a") == (False, "已满")


def test_move_blocked_forbidden_but_public_ok() -> None:
    w, s, rng = make_runtime(CFG, log=True)
    w.locations = {
        "home_a": {"name": "1 号", "kind": "home", "capacity": 6,
                   "owner": "npc_a", "open_to": [], "public": False},
        "plaza": {"name": "广场", "kind": "public", "capacity": 60,
                  "owner": "", "open_to": [], "public": True},
        "market": {"name": "超市", "kind": "shop", "capacity": 100,
                   "owner": "", "open_to": [], "public": True},
    }
    add_npc(w, s, "npc_a", location="home_a", rng_pool=rng)
    b = add_npc(w, s, "npc_b", location="plaza", rng_pool=rng)
    # 进别人家 → 不出发
    _apply(w, s, CFG, "npc_b", b,
           Decision(intent=MoveTo(dest="home_a"), source="plan"))
    assert "npc_b" not in s.travel
    # 公共场所 → 正常出发
    _apply(w, s, CFG, "npc_b", b,
           Decision(intent=MoveTo(dest="market"), source="plan"))
    assert s.travel["npc_b"].to_loc == "market"


def test_resident_can_enter_own_home() -> None:
    w, s, rng = make_runtime(CFG, log=True)
    w.locations = {
        "home_a": {"name": "1 号", "kind": "home", "capacity": 6,
                   "owner": "npc_a", "open_to": [], "public": False},
        "plaza": {"name": "广场", "kind": "public", "capacity": 60,
                  "owner": "", "open_to": [], "public": True},
    }
    a = add_npc(w, s, "npc_a", location="plaza", rng_pool=rng)
    _apply(w, s, CFG, "npc_a", a,
           Decision(intent=MoveTo(dest="home_a"), source="reflex"))
    assert s.travel["npc_a"].to_loc == "home_a"
