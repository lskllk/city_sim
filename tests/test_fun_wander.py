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
    npc.set_places(["plaza", "far"])
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
    npc.set_places(["plaza"])
    from citysim.world.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)        # 先看见饭
    d = npc.decide(CFG, 100)
    assert isinstance(d.intent, Interact) and d.intent.target_id == "meal"



def test_wander_pick_is_deterministic() -> None:
    def pick() -> str:
        w, s, _ = make_runtime(CFG)
        npc = add_npc(w, s, "same", location="a", fun=0.2)
        npc.set_places(["b", "c", "d"])
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
    npc.set_places(["plaza"])
    port = _port(w, s)
    grant = port.try_wander("n", "plaza")
    npc.intake_add(grant)
    f0 = npc.signal("fun")
    npc.heartbeat(600, CFG)
    assert npc.signal("fun") > f0


def test_roaming_cleared_when_leaving() -> None:
    """人离开那个地方(被打断去干别的) → world 侧的 roaming 也要清掉。"""
    from citysim.world.tick import engine as E
    w, s, _ = make_runtime(CFG)
    add_entity(w, "plaza", location="plaza", tags=("building",), affordances={})
    npc = add_npc(w, s, "n", location="plaza", fun=0.2)
    _port(w, s).try_wander("n", "plaza")
    assert "n" in s.roaming
    w.place_npc("n", "home")                       # 人走了
    E.tick(w, s, CFG)
    assert "n" not in s.roaming


def test_wandering_cools_down_decisions() -> None:
    """闲逛(committed fun goal + roam grant) → 饿到底也不切走(决策冷却)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", fun=0.2)
    npc.set_places(["loc"])                  # 只有这一个可逛地点 → 就地开逛
    from citysim.world.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    port = _port(w, s)
    d = npc.decide(CFG, 0)                         # fun 低 → 决定闲逛
    assert isinstance(d.intent, Wander) and d.intent.dest == "loc"
    npc._execute(port, d, 0)                       # 已在该地 → 开 roam
    assert any("roam" in ag.grant.tags for ag in npc._intake)
    npc.set_signal("hunger", 0.0)                 # 饿到底
    d2 = npc.decide(CFG, 1)
    assert not isinstance(d2.intent, Interact)     # 冷却: 不切去吃饭
