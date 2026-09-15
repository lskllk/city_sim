"""路网寻路(world/roads.py)契约测试。

钉死三件事:
1. **确实取最短** —— 平行的两条路, 选里程小的那条; 把小的换成大的能翻转。
2. **接入是投影到边** —— 门在边中间时走投影点, 不绕到远处的节点。
3. **接不上/不连通 → None** —— 上层降级, 不返回假路径。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.gateway.scenarios import NAV_SCENE, load_scene
from citysim.world.roads import RoadGraph

ROOT = Path(__file__).resolve().parents[1]


def _node(x: float, y: float) -> dict:
    return {"xy": [x, y]}


def _edge(a: str, b: str, pa, pb, *, oneway: bool = False) -> dict:
    return {"a": a, "b": b, "geom": [list(pa), list(pb)],
            "oneway": oneway, "speed": 1.3, "width": 4.0}


def _diamond(mid_upper_y: float, mid_lower_y: float) -> dict:
    """n1(0,0) — n2(100,0) 之间两条路: 经 n3(50, mid_upper_y) / n4(50, mid_lower_y)。"""
    return {
        "nodes": {"n1": _node(0, 0), "n2": _node(100, 0),
                  "n3": _node(50, mid_upper_y), "n4": _node(50, mid_lower_y)},
        "edges": {
            "e1": _edge("n1", "n3", (0, 0), (50, mid_upper_y)),
            "e2": _edge("n3", "n2", (50, mid_upper_y), (100, 0)),
            "e3": _edge("n1", "n4", (0, 0), (50, mid_lower_y)),
            "e4": _edge("n4", "n2", (50, mid_lower_y), (100, 0)),
        },
    }


# ----------------------------------------------------------------------
# 1. 确实取最短
# ----------------------------------------------------------------------
def test_picks_shorter_of_two_parallel_routes() -> None:
    """上路 100 m, 下路 412 m → 必须走上路(经 n3)。"""
    g = RoadGraph(_diamond(mid_upper_y=0.0, mid_lower_y=200.0), m_per_tick=10.0)
    r = g.route((0.0, 0.0), (100.0, 0.0))
    assert r is not None
    assert r.length == pytest.approx(100.0)
    assert r.ticks == 10
    assert (50.0, 0.0) in r.waypoints          # 经上路的中间节点
    assert (50.0, 200.0) not in r.waypoints     # 没走下路


def test_flips_when_the_other_route_becomes_shorter() -> None:
    """把两条路的远近换过来 → 选择必须翻转(排除"总是走第一条边"的假实现)。"""
    g = RoadGraph(_diamond(mid_upper_y=200.0, mid_lower_y=0.0), m_per_tick=10.0)
    r = g.route((0.0, 0.0), (100.0, 0.0))
    assert r is not None
    assert r.length == pytest.approx(100.0)
    assert (50.0, 0.0) in r.waypoints           # 这次是 n4
    assert (50.0, 200.0) not in r.waypoints


def test_shortcut_edge_wins() -> None:
    """直接加一条更短的边 → 里程立刻降到该边长度。"""
    m = _diamond(mid_upper_y=0.0, mid_lower_y=200.0)
    m["edges"]["e5"] = _edge("n1", "n2", (0, 0), (60, 0))   # 60 m 直连, 但 n2 在 (100,0)
    # e5 的 geom 只到 (60,0), 与 b=n2(100,0) 不一致 → 以 geom 为准, 长度 60
    g = RoadGraph(m, m_per_tick=10.0)
    r = g.route((0.0, 0.0), (100.0, 0.0))
    assert r is not None
    assert r.length < 100.0                     # 走了更短的 e5(不足 100)


# ----------------------------------------------------------------------
# 2. 接入 = 投影到边(可分裂)
# ----------------------------------------------------------------------
def test_door_in_middle_of_edge_does_not_detour_to_node() -> None:
    """门在边中点: 直接投影过去(+50 m), 而不是先跑到 n1 再折回(会 >150 m)。"""
    m = {
        "nodes": {"n1": _node(0, 0), "n2": _node(100, 0)},
        "edges": {"e1": _edge("n1", "n2", (0, 0), (100, 0))},
    }
    g = RoadGraph(m, m_per_tick=10.0)
    r = g.route((50.0, 0.0), (100.0, 10.0))
    assert r is not None
    assert r.length == pytest.approx(60.0)      # 50(投影→n2) + 10(门)
    assert r.waypoints[0] == (50.0, 0.0)        # 起点就是门
    assert r.waypoints[-1] == (100.0, 10.0)     # 终点就是门


# ----------------------------------------------------------------------
# 3. 接不上 / 不连通 / 空图 → None(上层降级)
# ----------------------------------------------------------------------
def test_disconnected_returns_none() -> None:
    m = {
        "nodes": {"n1": _node(0, 0), "n2": _node(100, 0),
                  "n3": _node(500, 0), "n4": _node(600, 0)},
        "edges": {"e1": _edge("n1", "n2", (0, 0), (100, 0)),
                  "e2": _edge("n3", "n4", (500, 0), (600, 0))},
    }
    g = RoadGraph(m, m_per_tick=10.0)
    assert g.route((0.0, 0.0), (500.0, 0.0)) is None


def test_empty_map_returns_none() -> None:
    g = RoadGraph({}, m_per_tick=10.0)
    assert not g.ok
    assert g.route((0.0, 0.0), (10.0, 0.0)) is None


def test_oneway_is_respected() -> None:
    m = {
        "nodes": {"n1": _node(0, 0), "n2": _node(100, 0)},
        "edges": {"e1": _edge("n1", "n2", (0, 0), (100, 0), oneway=True)},
    }
    g = RoadGraph(m, m_per_tick=10.0)
    assert g.route((0.0, 0.0), (100.0, 0.0)) is not None    # 顺向可走
    assert g.route((100.0, 0.0), (0.0, 0.0)) is None        # 逆向不可走


def test_ticks_follow_m_per_tick() -> None:
    m = {
        "nodes": {"n1": _node(0, 0), "n2": _node(95, 0)},
        "edges": {"e1": _edge("n1", "n2", (0, 0), (95, 0))},
    }
    assert RoadGraph(m, m_per_tick=10.0).route((0, 0), (95, 0)).ticks == 10
    assert RoadGraph(m, m_per_tick=5.0).route((0, 0), (95, 0)).ticks == 19


# ----------------------------------------------------------------------
# 4. 真实场景: nav 验证图
# ----------------------------------------------------------------------
def test_scenefornav_takes_the_upper_route() -> None:
    """scenefornav: 上路 133.29 m / 13 tick; 下路(经 n_005/n_006)不被选中。"""
    w, s, _r = load_scene(NAV_SCENE)
    assert s.roads is not None and s.roads.ok
    a = w.door_point("bld_001")
    b = w.door_point("bld_002")
    assert a is not None and b is not None

    r = s.roads.route(a, b)
    assert r is not None
    assert r.length == pytest.approx(133.29, abs=0.05)
    assert r.ticks == 13

    # 上路: n_002 → n_001 → n_003 →(沿 e_003)投影点; 下路会经过 n_005/n_006
    assert (381.0, 300.0) in r.waypoints
    assert (381.0, 315.0) in r.waypoints
    assert (345.0, 334.0) not in r.waypoints
    assert (477.0, 335.0) not in r.waypoints

    # 沿路一定比直线长(旧的"直线/10"降级口径是 114.56 m)
    import math
    assert r.length > math.dist(a, b)


def test_scenefornav_reroutes_when_winning_edge_is_removed() -> None:
    """拆掉上路关键边 e_002 → 必须改走下路, 且里程等于手工算的下路值。

    这是对"真在评估备选"最硬的验证: 不是返回预置答案。
    """
    import json
    import math

    w, _s, _r = load_scene(NAV_SCENE)
    raw = json.loads(
        NAV_SCENE.read_text(encoding="utf-8"))
    m = dict(raw["map"])
    edges = {k: v for k, v in m["edges"].items() if k != "e_002"}
    m["edges"] = edges

    a = w.door_point("bld_001")
    b = w.door_point("bld_002")
    g = RoadGraph(m, m_per_tick=10.0)
    r = g.route(a, b)
    assert r is not None

    # 手工算下路: 门→(348.711,300)→n_002→n_005→n_006→n_004→(463,315)→门
    expect = (
        math.dist(a, (348.711, 300.0))
        + math.dist((348.711, 300.0), (345.0, 300.0))
        + math.dist((345.0, 300.0), (345.0, 334.0))
        + math.dist((345.0, 334.0), (477.0, 335.0))
        + math.dist((477.0, 335.0), (477.0, 315.0))
        + math.dist((477.0, 315.0), (463.0, 315.0))
        + math.dist((463.0, 315.0), b)
    )
    assert r.length == pytest.approx(expect, abs=0.05)
    assert r.length > 200.0                       # 明显比上路的 133.29 长
    assert (345.0, 334.0) in r.waypoints          # 确实改走了下路
    assert (381.0, 300.0) not in r.waypoints      # 不再经过上路中段
