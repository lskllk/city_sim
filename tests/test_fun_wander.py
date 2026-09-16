"""fun(娱乐) + 闲逛(Wander)。

    · 上班涨 / 空闲掉 / 吃·睡·厕所不变
    · fun 低 → 闲逛(最低优先级); 任何需求都能打断
    · 选址: 热闹(draw) + 路近 排前; top-N 内随机; 同人同窗口可复现
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Idle, Interact, Wander
from citysim.world.port import WorldPortImpl

from helpers import add_entity, add_npc, make_runtime

CFG = load_config(Path("config/sim.toml"))


def _port(w, s) -> WorldPortImpl:
    return WorldPortImpl(w, s, CFG)


# ---------------------------------------------------------------------------
# fun 收支
# ---------------------------------------------------------------------------
def test_work_raises_fun() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "station", location="loc", tags=("work", "station"),
               affordances={}, duration_ticks=600)
    npc = add_npc(w, s, "n", location="loc", fun=0.5)
    npc.intake_add(_port(w, s).try_take("n", "station"))
    npc.heartbeat(600, CFG)                        # 10:00
    assert npc.signal("fun") > 0.5


def test_idle_drops_fun() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", fun=0.5)
    npc.heartbeat(600, CFG)
    assert npc.signal("fun") < 0.5


def test_eating_does_not_change_fun() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", hunger=0.2, fun=0.5)
    npc.intake_add(_port(w, s).try_take("n", "meal"))
    npc.heartbeat(600, CFG)
    assert npc.signal("fun") == 0.5               # 吃饭既不涨也不掉


def test_sleeping_does_not_change_fun() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "bed", location="loc", tags=("sleepable",),
               affordances={}, duration_ticks=100)
    npc = add_npc(w, s, "n", location="loc", energy=0.3, fun=0.5)
    npc.intake_add(_port(w, s).try_take("n", "bed"))
    npc.heartbeat(1200, CFG)
    assert npc.signal("fun") == 0.5


# ---------------------------------------------------------------------------
# 闲逛: 最低优先级 / 可被任何需求打断
# ---------------------------------------------------------------------------
def test_low_fun_falls_back_to_wander() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="home", fun=0.2)
    npc.set_places({"home": 1.0, "plaza": 9.0, "far": 3.0})
    npc.set_travel_costs({"home|plaza": 10, "home|far": 200})
    d = npc.decide(CFG, 100)
    assert isinstance(d.intent, Wander)
    assert d.intent.dest != "home"                # 不在“原地闲逛”
    assert d.intent.dest in ("plaza", "far")


def test_need_beats_wander() -> None:
    """闲逛最低优先级: 饿了 → 去吃饭, 不是去闲逛。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", fun=0.2, hunger=0.1)
    npc.set_places({"loc": 1.0, "plaza": 9.0})
    from citysim.world.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)        # 先看见饭
    d = npc.decide(CFG, 100)
    assert isinstance(d.intent, Interact) and d.intent.target_id == "meal"


def test_lively_and_near_wins() -> None:
    """选址: draw/(1+路费) 高的排前面。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="home", fun=0.2)
    npc.set_places({"home": 1.0, "near": 6.0, "busy_far": 9.0})
    npc.set_travel_costs({"home|near": 5, "home|busy_far": 500})
    top = npc._wander_dest(CFG, 100)
    assert top in ("near", "busy_far")


def test_wander_pick_is_deterministic() -> None:
    def pick() -> str:
        w, s, _ = make_runtime(CFG)
        npc = add_npc(w, s, "same", location="a", fun=0.2)
        npc.set_places({"a": 1.0, "b": 5.0, "c": 5.0, "d": 5.0})
        return npc._wander_dest(CFG, 100)
    assert pick() == pick()


# ---------------------------------------------------------------------------
# 端口 try_wander
# ---------------------------------------------------------------------------
def test_try_wander_moves_then_roams() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "plaza", location="town", tags=("building",), affordances={})
    npc = add_npc(w, s, "n", location="home", fun=0.2)
    port = _port(w, s)
    port.try_wander("n", "plaza")                 # 没到 → 起 travel
    assert "n" in s.travel
    w.place_npc("n", "plaza")                     # 直接落地
    g = port.try_wander("n", "plaza")             # 到了 → Grant + roaming
    assert hasattr(g, "value") and g.signal == "fun"
    assert "n" in s.roaming
    a = port.try_wander("n", "plaza")             # 已在逛 → 不重复发
    assert a.ok and a.reason == "roaming"


def test_roam_grant_raises_fun() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="plaza", fun=0.2)
    npc.set_places({"home": 1.0, "plaza": 9.0})
    port = _port(w, s)
    grant = port.try_wander("n", "plaza")
    npc.intake_add(grant)
    f0 = npc.signal("fun")
    npc.heartbeat(600, CFG)
    assert npc.signal("fun") > f0


def test_roaming_cleared_when_leaving() -> None:
    """人离开那个地方(被打断去干别的) → world 侧的 roaming 也要清掉。"""
    from citysim.world import engine as E
    w, s, _ = make_runtime(CFG)
    add_entity(w, "plaza", location="plaza", tags=("building",), affordances={})
    npc = add_npc(w, s, "n", location="plaza", fun=0.2)
    _port(w, s).try_wander("n", "plaza")
    assert "n" in s.roaming
    w.place_npc("n", "home")                       # 人走了
    E.tick(w, s, CFG)
    assert "n" not in s.roaming


def test_wandering_cools_down_decisions() -> None:
    """闲逛中(体内有 roam grant) → 决策冷却: 就算饿到底也不切走(committed)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", fun=0.2)
    npc.set_places({"loc": 1.0, "plaza": 9.0})
    from citysim.world.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    grant = _port(w, s).try_wander("n", "loc")     # 已在 loc → 开 roam
    npc.intake_add(grant)
    npc.set_signal("hunger", 0.0)
    assert isinstance(npc.decide(CFG, 100).intent, Idle)
