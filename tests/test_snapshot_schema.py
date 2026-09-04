"""display_m5_ui G0: snapshot schema —— 字段齐全、JSON 可序列化、travel 可插值。"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.gateway.scenarios import build_scenario
from citysim.gateway.snapshot import build_npc_detail, build_snapshot, fmt_clock
from citysim.sim.loop import run_tick

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
            "travel", "intent", "kb"} <= set(n0)
    assert set(SIGNALS) <= set(n0["signals"])
    assert n0["kb"]["overlay"] >= 0 and n0["kb"]["archetype"] >= 0
    e0 = snap["entities"][0]
    assert {"id", "name", "loc", "tags", "stock", "icon"} <= set(e0)


def test_travel_fields_present_for_interpolation() -> None:
    """stale_kb 场景应有 NPC 旅行; travel 提供 from/to/depart/arrive。"""
    w, s = _run("stale_kb", 8)          # 首段 home→kitchen 旅行窗口(1~31t)
    snap = build_snapshot(w, s, CFG, "1x", [])
    travels = [n for n in snap["npcs"] if n["travel"] is not None]
    assert travels, "stale_kb 场景里应有人正在跨房间移动"
    tv = travels[0]["travel"]
    assert {"from", "to", "depart", "arrive"} <= set(tv)
    assert tv["arrive"] > tv["depart"]


def test_npc_detail_returns_trace_and_kb() -> None:
    w, s = _run("stale_kb", 300)
    detail = build_npc_detail(w, s, "npc_00")
    assert detail is not None
    assert {"signals", "intent", "kb", "events"} <= set(detail)
    assert "used_facts" in detail["intent"]
    assert isinstance(detail["kb"]["edges"], list)


def test_fmt_clock_roundtrip() -> None:
    assert fmt_clock(0.0) == "00:00"
    assert fmt_clock(8.25) == "08:15"
    assert fmt_clock(23.99) == "23:59"
