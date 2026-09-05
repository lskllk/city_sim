"""display_m5_ui G0: snapshot schema + 网关只读护栏。

字段齐全、JSON 可序列化、travel 可插值; 且网关只读观察不扰动模拟。
"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.gateway.scenarios import build_scenario
from citysim.gateway.snapshot import build_npc_detail, build_snapshot, fmt_clock
from citysim.sim.loop import run_tick
from citysim.viz.kb_export import export_kb_json

CFG = load_config()
SIGNALS = ("energy", "hunger", "thirst", "bladder", "temperature",
           "health", "fun", "social", "comfort", "hp")


def _run(scenario, ticks):
    w, s, rng = build_scenario(scenario, seed=3, n_npc=4)
    for _ in range(ticks):
        run_tick(w, s, CFG, rng)
    return w, s


def test_snapshot_json_serializable_with_required_fields() -> None:
    w, s = _run("stale_kb", 500)
    snap = build_snapshot(w, s, CFG, "3x", [])
    json.dumps(snap, ensure_ascii=False)             # 可序列化
    assert snap["type"] == "snapshot"
    assert isinstance(snap["tick"], int)
    assert isinstance(snap["day"], int)
    assert ":" in snap["clock"]
    assert isinstance(snap["entities"], list) and snap["entities"]
    assert isinstance(snap["npcs"], list) and snap["npcs"]
    n0 = snap["npcs"][0]
    assert {"id", "name", "loc", "activity", "signals", "active",
            "travel", "intent", "kb", "kb_counts", "events"} <= set(n0)
    assert set(SIGNALS) <= set(n0["signals"])
    assert isinstance(n0["kb"]["nodes"], list)
    assert isinstance(n0["kb"]["edges"], list)
    assert n0["kb_counts"]["overlay"] >= 0 and n0["kb_counts"]["archetype"] >= 0
    assert isinstance(n0["events"], list)
    e0 = snap["entities"][0]
    assert {"id", "name", "loc", "tags", "stock", "icon"} <= set(e0)


def test_travel_fields_present_for_interpolation() -> None:
    """travel 字段渲染 from/to/depart/arrive(插值用; 直接注入 Travel 验证 schema)。"""
    w, s = _run("elm_lane", 8)
    from citysim.sim.loop import Travel
    s.travel["npc_wang"] = Travel(from_loc="apt_101", to_loc="plaza",
                                  depart_tick=2, arrive_tick=6)
    snap = build_snapshot(w, s, CFG, "1x", [])
    travels = [n for n in snap["npcs"] if n["travel"] is not None]
    assert travels, "travel 字段应被渲染"
    tv = travels[0]["travel"]
    assert {"from", "to", "depart", "arrive"} <= set(tv)
    assert tv["arrive"] > tv["depart"]


def test_npc_detail_returns_trace_and_kb() -> None:
    w, s = _run("stale_kb", 300)
    detail = build_npc_detail(w, s, "npc_wang")
    assert detail is not None
    assert {"signals", "intent", "kb", "events"} <= set(detail)
    assert "used_facts" in detail["intent"]
    assert isinstance(detail["kb"]["edges"], list)


def test_fmt_clock_roundtrip() -> None:
    assert fmt_clock(0.0) == "00:00"
    assert fmt_clock(8.25) == "08:15"
    assert fmt_clock(23.99) == "23:59"


def _headless(seed=3, ticks=2000):
    world, systems, rng = build_scenario("demo", seed=seed, n_npc=5)
    for _ in range(ticks):
        run_tick(world, systems, CFG, rng)
    return world, systems


def test_gateway_does_not_perturb_sim() -> None:
    """逐 tick 建快照 + 周期 query 不得扰动模拟(日志逐行相同、事件序号不消耗)。"""
    w_a, s_a = _headless()
    a_lines = list(s_a.log_lines)
    a_seq = w_a.bus.seq

    w, s, rng = build_scenario("demo", seed=3, n_npc=5)
    for t in range(2000):
        run_tick(w, s, CFG, rng)
        build_snapshot(w, s, CFG, "1x", [])          # 每 tick 建快照
        if t % 50 == 0:
            for pid in w.npcs:
                build_npc_detail(w, s, pid)          # 全部 query
                if w.npcs[pid].kb is not None:
                    export_kb_json(w.npcs[pid].kb)
    assert s.log_lines == a_lines                    # 日志逐行相同
    assert w.bus.seq == a_seq                        # 事件序号未被消耗
