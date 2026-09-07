"""TASK002 —— Observation Contract: envelope / event canonical / 事件确实被产生。

FastAPI 相关 e2e 用 importorskip 保护(minimal 环境无 viz 依赖也可跑其余部分)。
"""
from __future__ import annotations

import json
from pathlib import Path

from citysim.core.config import load_config
from citysim.gateway.snapshot import encode_event, envelope, PROTOCOL_VERSION
from citysim.sim.pulses import normalize
from citysim.sim.loop import run_tick

from helpers import add_entity, add_npc, make_runtime, seed_reviews

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


# --- envelope ----------------------------------------------------------
def test_envelope_shape_and_protocol_version() -> None:
    m = envelope("snapshot", {"tick": 1})
    assert m == {"kind": "snapshot", "protocol_version": 1, "payload": {"tick": 1}}
    assert PROTOCOL_VERSION == 1


def test_envelope_json_serializable() -> None:
    m = envelope("event", {"event_id": "e1", "tick": 1, "type": "x"})
    assert json.loads(json.dumps(m))["kind"] == "event"


# --- event canonical ---------------------------------------------------
def test_encode_event_canonical_fields() -> None:
    enc = encode_event({"event_id": "ev7", "tick": 5, "kind": "told",
                        "subject": "npc_wang",
                        "payload": {"audience": ["npc_li"]}})
    assert enc["event_id"] == "ev7"
    assert enc["tick"] == 5
    assert enc["type"] == "told"
    assert enc["source"] == "npc_wang"
    assert enc["target"] is None            # payload 无 target → null
    assert enc["payload"] == {"audience": ["npc_li"]}


def test_encode_event_keeps_legacy_and_promotes_target() -> None:
    ev = {"tick": 8, "kind": "decision", "subject": "npc_li",
          "intent": "move_to", "target": "market", "payload": {}}
    enc = encode_event(ev)
    assert enc["target"] == "market"
    assert enc["intent"] == "move_to"       # 原字段保留(兼容旧观察器)
    assert enc["type"] == "decision"
    assert enc["event_id"] == "decision:8:npc_li"   # 回退 id 稳定


# --- 事件确实被产生(内核级, 不依赖 gateway) ---------------------------
def test_perceived_and_learned_events_produced() -> None:
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "water_1", location="loc", tags=("drink", "consumable"),
               affordances={"thirst": 0.6}, stock=1000)
    npc = add_npc(w, s, "npc", rng_pool=rng, seed=3, thirst=0.3)
    seed_reviews(w, s)
    run_tick(w, s, CFG, rng)                # 重评: 感知 → perceived + learned
    kinds = [u["kind"] for u in s.ui_events]
    assert "perceived" in kinds
    assert "learned" in kinds
    perc = next(u for u in s.ui_events if u["kind"] == "perceived")
    assert "water_1" in perc["payload"]["observed_entity_ids"]
    assert perc["payload"]["location_id"] == "loc"
    assert "event_id" in perc and "event_id" in next(
        u for u in s.ui_events if u["kind"] == "learned")
    learned = next(u for u in s.ui_events if u["kind"] == "learned")
    assert learned["payload"]["source_kind"] == "OBSERVED"
    assert "fact_id" in learned["payload"]


def test_stock_changed_event_produced() -> None:
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "market_1", location="loc", tags=("edible",),
               affordances={"hunger": 0.4}, stock=10)
    s.pulses = normalize([{"at": "day 0 00:01", "op": "set_stock",
                           "target": "market_1", "value": 3}], 1440)
    run_tick(w, s, CFG, rng)
    evs = [u for u in s.ui_events if u["kind"] == "stock_changed"]
    assert evs and evs[0]["payload"]["stock_before"] == 10
    assert evs[0]["payload"]["stock_after"] == 3
    assert evs[0]["event_id"]


def test_decision_event_has_stable_event_id() -> None:
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "food_1", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, stock=1)
    npc = add_npc(w, s, "npc", rng_pool=rng, seed=3, hunger=0.1)
    seed_reviews(w, s)
    run_tick(w, s, CFG, rng)
    dec = next(u for u in s.ui_events if u["kind"] == "decision")
    assert dec["event_id"] == f"dec:{dec['tick']}:npc"


def test_snapshot_payload_has_no_stream_events() -> None:
    """TASK002: 事件走独立消息; snapshot 本体不带事件流(只留各 NPC 近况)。"""
    from citysim.gateway.scenarios import build_scenario
    from citysim.gateway.snapshot import build_snapshot
    w, s, rng = build_scenario("elm_lane", seed=3)
    for _ in range(30):
        run_tick(w, s, CFG, rng)
    snap = build_snapshot(w, s, CFG, "1x", [])
    assert snap["events"] == []


# --- gateway 层 e2e(需 fastapi, 可选) ---------------------------------
def test_gateway_pushes_snapshot_and_events() -> None:
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")
    import asyncio
    from citysim.gateway.server import SimRunner

    class _FakeWS:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send_text(self, s: str) -> None:
            self.sent.append(s)

    runner = SimRunner()
    fake = _FakeWS()
    runner.clients.add(fake)
    runner.advance(30)                       # 产生 decision/perceived/… 事件
    asyncio.run(runner.push())
    msgs = [json.loads(m) for m in fake.sent]
    assert msgs and msgs[0]["kind"] == "snapshot"
    assert all(m.get("protocol_version") == 1 for m in msgs)
    events = [m["payload"] for m in msgs if m["kind"] == "event"]
    kinds = {e["kind"] for e in events}
    assert {"decision", "perceived"} <= kinds
    assert all(e.get("type") and e.get("event_id") for e in events)
