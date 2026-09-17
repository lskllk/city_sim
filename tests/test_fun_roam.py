"""第 3~5 步的测试: 闲逛(观察窗口) + 地点行 + 新奇量 + 选址公式。

旧的专用机制(try_wander / systems.roaming / roam Grant)已删 —— 现在闲逛是
**NPC 自己的事**: 走到目的地, 在那儿观察一段窗口(60t), 收工结算。
"""
from __future__ import annotations

import pathlib

from citysim.core.config import load_config
from citysim.core.types import Idle, Interact, Wander
from citysim.npc.brain.memory_io import place_id

from helpers import add_entity, add_npc, make_runtime

CFG = load_config(pathlib.Path("config/sim.toml"))


def _port(w, s):
    from citysim.world.edge.port import WorldPortImpl
    return WorldPortImpl(w, s, CFG)


# --- 观察窗口(committed goal) -------------------------------------------

def test_wandering_opens_a_window_and_cools_down_decisions() -> None:
    """闲逛 = committed goal + 一段观察窗口 → 期间饿到底也不切走(决策冷却)。

    窗口在 `_advance` 里开(到了目的地才开始计时) —— 不再有 world 侧 Grant。
    """
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", fun=0.2)
    npc.set_places(["loc"])                  # 只有这一个可逛地点 → 就地开逛
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    port = _port(w, s)

    d = npc.decide(CFG, 0)
    assert isinstance(d.intent, Wander) and d.intent.dest == "loc"
    npc._execute(port, d, 0)                 # 已在该地 → 什么都不用做

    d2 = npc.decide(CFG, 1)                  # 推进一拍 → 开窗口
    assert isinstance(d2.intent, Wander)
    assert npc._goal.roam_until == 1 + CFG.fun_roam_ticks

    npc.set_signal("hunger", 0.0)            # 饿到底
    d3 = npc.decide(CFG, 2)
    assert not isinstance(d3.intent, Interact)   # 冷却: 不切去吃饭


def test_window_expires_then_settles_fun() -> None:
    """窗口到期 → 收工结算: 补 fun(基础 + 新奇), 然后才轮得到别的需求。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", fun=0.2)
    npc.set_places(["loc"])
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    port = _port(w, s)
    npc._execute(port, npc.decide(CFG, 0), 0)
    npc.decide(CFG, 1)                        # 开窗口
    end = npc._goal.roam_until
    before = npc.signal("fun")
    npc.set_signal("hunger", 0.0)             # 窗口到期那一刻已经饿了
    d = npc.decide(CFG, end + 1)              # 越过窗口 → 结算 + 收工
    assert npc.signal("fun") > before         # 有回报(基础 + 新奇)
    assert isinstance(d.intent, Interact)     # 收工之后, 需求才抢得到


# --- 地点行 + 新奇量 -----------------------------------------------------

def test_place_row_is_written_and_stays_out_of_candidates() -> None:
    """观察会写一行地点记忆(去过凭证); 它 afford="" → 不进决策候选。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="loc")
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    row = next((r for r in npc.memory_dicts()
                if r["item_id"] == place_id("loc")), None)
    assert row is not None and row["located"] == "loc"
    assert row["afford"] == "" and "place" in row["tags"]
    assert npc._mem.get(place_id("loc")).attrs["visits"] >= 1
    assert npc.decide(CFG, 0).intent.__class__ is Idle   # 地点行不产生候选


def test_first_sight_is_max_novelty_repeat_is_near_zero() -> None:
    """新奇量: 第一次见 = 1/件; 立刻再看 ≈ 0(remember 已满)。"""
    from citysim.world.edge.perception import build_percept
    from citysim.npc.brain.memory_io import perceive_into
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "n", location="loc")
    first = perceive_into(npc._mem, build_percept(w, npc), 0)
    second = perceive_into(npc._mem, build_percept(w, npc), 1)
    assert first >= 2.0                        # 1 件货 + 1 行地点
    assert second == 0.0


def test_forgot_place_becomes_novel_again() -> None:
    """忘了的旧东西再看 → 也算新奇(1 − remember)。"""
    from citysim.world.edge.perception import build_percept
    from citysim.npc.brain.memory_io import perceive_into
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "n", location="loc")
    perceive_into(npc._mem, build_percept(w, npc), 0)
    npc._mem.update(place_id("loc"), remember=0.3)      # 假装忘了
    again = perceive_into(npc._mem, build_percept(w, npc), 999)
    assert again > 0.5                                   # ≈ 0.7


# --- 选址公式 -----------------------------------------------------------

def test_wander_dest_prefers_never_visited_over_visited_empty() -> None:
    """没去过的(乐观初值) 比【去过但空空如也】的明显更容易被抽到。

    这就是"没什么东西的建筑 → 很小概率会去"那条 —— 去过一次之后, 乐观初值
    没了, 只剩那条地点行本身(权重 1); 而没去过的是乐观初值(权重 3)。
    """
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="home", fun=0.2)
    npc.set_places(["fresh", "empty_done"])
    npc.note(place_id("empty_done"), located="empty_done", afford="", stock=1,
             tags=("place",))                    # 去过但没东西(只有地点行)
    hits = {"fresh": 0, "empty_done": 0}
    for t in range(0, 6000, 60):
        hits[npc._wander_dest(CFG, t)] += 1
    assert hits["fresh"] > 0 and hits["empty_done"] > 0     # 都是加权随机
    assert hits["fresh"] > hits["empty_done"]               # 但没去过的更常去


def test_wander_dest_deterministic() -> None:
    def pick() -> list[str]:
        w, s, _ = make_runtime(CFG)
        npc = add_npc(w, s, "same", location="a", fun=0.2)
        npc.set_places(["b", "c", "d"])
        return [npc._wander_dest(CFG, t) for t in (0, 60, 120, 180)]
    assert pick() == pick()


# ---------------------------------------------------------------------------
# fun 的收支 + 闲逛的优先级(这些不随机制改动而变)
# ---------------------------------------------------------------------------
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
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)        # 先看见饭
    d = npc.decide(CFG, 100)
    assert isinstance(d.intent, Interact) and d.intent.target_id == "meal"


def test_wandering_reports_activity_class() -> None:
    """闲逛期间: 行为大类 = wander(前端时间线靠它上色)。

    判据是 goal(一段观察窗口), 不再是 roam Grant —— 所以 activity() 要看 goal。
    """
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="loc", fun=0.2)
    npc.set_places(["loc"])
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    port = _port(w, s)
    npc._execute(port, npc.decide(CFG, 0), 0)
    npc.decide(CFG, 1)                       # 开窗口
    assert npc.activity() == ("wander", "闲逛")
    assert npc.activity_class == "wander"
