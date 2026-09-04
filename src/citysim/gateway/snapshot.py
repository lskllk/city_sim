"""snapshot —— 世界 → JSON(纯读观察者, display_m5_ui G0)。

铁律(design 第三节, 逐字遵守):
  - 禁止 build_percept()(会清空 NPC 信箱) / 禁止碰 rng_pool / 禁止写内核字段。
  - 事件只从 systems.log_lines 尾读; 本模块不挂 subscribe_log。
"""
from __future__ import annotations

import json
from pathlib import Path

from citysim.viz.kb_export import export_kb_json
from citysim.viz.trace_export import export_trace_chain

# 实体 tag -> emoji(不许按中文名匹配, M4 纪律)
_ICONS = {"sleepable": "🛏", "toilet": "🚽", "container": "🧊",
          "edible": "🍱", "entertain": "📺", "drink": "🚰",
          "consumable": "🍽"}
_TAG_PRIORITY = ("sleepable", "toilet", "container", "edible",
                 "entertain", "drink", "consumable")
_EVENT_KINDS = ("told", "interaction_done", "intent_failed", "decision")


def fmt_clock(hour_f: float) -> str:
    m = int(round(hour_f * 60)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def icon_of(entity) -> str:
    for t in _TAG_PRIORITY:
        if t in entity.tags:
            return _ICONS[t]
    return "📦"


def kb_counts(kb) -> dict:
    if kb is None:
        return {"overlay": 0, "tombstones": 0, "archetype": 0}
    return {"overlay": len(kb.overlay), "tombstones": len(kb.tombstones),
            "archetype": len(kb.archetype.facts)}


def parse_log_line(line: str) -> dict | None:
    parts = line.split("\t")
    if not parts:
        return None
    kind = parts[0]
    if kind == "D":
        # D tick pid intent target plan
        if len(parts) < 5:
            return None
        return {"tick": int(parts[1]), "kind": "decision",
                "subject": parts[2], "target": parts[4],
                "intent": parts[3], "plan": parts[5] if len(parts) > 5 else "",
                "payload": {}}
    if kind == "E":
        # E tick ekind subject payload(k=v;k=v)
        payload: dict = {}
        if len(parts) > 4 and parts[4]:
            for kv in parts[4].split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    payload[k.strip()] = v.strip()
        return {"tick": int(parts[1]), "kind": parts[2],
                "subject": parts[3], "target": payload.get("target", ""),
                "intent": "", "plan": "", "payload": payload}
    return None


def build_snapshot(world, systems, cfg, speed: str,
                   events: list[dict]) -> dict:
    tick = world.clock_tick
    npcs = []
    for pid, p in sorted(world.npcs.items()):
        act = systems.interaction.active.get(pid)
        tv = systems.travel.get(pid)
        it = p.last_intent
        npcs.append({
            "id": pid, "name": p.name, "loc": p.location_id,
            "activity": p.current_activity,
            "signals": {k: round(v, 4) for k, v in p.signals.items()},
            "active": None if act is None else {
                "entity": act.entity_id, "remaining": act.remaining_ticks,
                "total": act.total_ticks},
            "travel": None if tv is None else {
                "from": tv.from_loc, "to": tv.to_loc,
                "depart": tv.depart_tick, "arrive": tv.arrive_tick},
            "intent": None if it is None else {
                "kind": it.kind, "target": it.target_id,
                "reason": it.trace.reason},
            "kb": kb_counts(p.kb),
        })
    ents = [{"id": e.entity_id, "name": e.name, "loc": e.location_id,
             "tags": sorted(e.tags), "stock": e.stock,
             "claimed_by": e.claimed_by, "icon": icon_of(e)}
            for _, e in sorted(world.entities.items())]
    return {"type": "snapshot", "tick": tick,
            "day": tick // cfg.ticks_per_day + 1,
            "hour_f": round(world.hour_f(), 4),
            "clock": fmt_clock(world.hour_f()),
            "speed": speed, "running": speed != "pause",
            "entities": ents, "npcs": npcs, "events": events}


def build_npc_detail(world, systems, pid: str) -> dict | None:
    """npc_detail: 状态/为什么(used_fact_ids 追溯树)/知识图/最近 50 条事件。"""
    npc = world.npcs.get(pid)
    if npc is None:
        return None
    it = npc.last_intent
    used = []
    if it is not None and it.trace.used_fact_ids and npc.kb is not None:
        used = export_trace_chain(npc.kb, it.trace.used_fact_ids).get(
            "facts", [])
    recent = []
    for line in (systems.log_lines or [])[-500:]:
        ev = parse_log_line(line)
        if ev is not None and ev.get("subject") == pid:
            recent.append(ev)
            if len(recent) >= 50:
                break
    return {
        "id": pid, "name": npc.name, "loc": npc.location_id,
        "activity": npc.current_activity,
        "signals": {k: round(v, 4) for k, v in npc.signals.items()},
        "intent": None if it is None else {
            "kind": it.kind, "target": it.target_id, "reason": it.trace.reason,
            "ranked": [{"id": i, "score": round(s, 4)}
                       for i, s in it.trace.ranked],
            "plan": list(it.trace.plan),
            "used_facts": used},
        "kb": export_kb_json(npc.kb) if npc.kb is not None else
             {"nodes": [], "edges": []},
        "kb_counts": kb_counts(npc.kb),
        "events": recent,
    }


def _fact_payload(ev: dict) -> tuple:
    p = ev.get("payload", {})
    return (p.get("subject"), p.get("relation"), p.get("obj"))


def do_query(runner, args: dict) -> dict | None:
    what = args.get("what")
    if what == "npc_detail":
        return build_npc_detail(runner.world, runner.systems,
                                args.get("npc_id", ""))
    if what == "kb_graph":
        npc = runner.world.npcs.get(args.get("npc_id", ""))
        if npc is None or npc.kb is None:
            return None
        return export_kb_json(npc.kb)
    if what == "trace":
        npc = runner.world.npcs.get(args.get("npc_id", ""))
        if npc is None or npc.kb is None:
            return None
        return export_trace_chain(npc.kb, [args.get("fact_id", "")])
    if what == "who_knows":
        # 找出 KB 里"相信"该 (subject, relation, obj) 的所有 npc
        subj, rel, obj = args.get("subject"), args.get("relation"), \
            args.get("obj")
        hits = []
        for pid, npc in runner.world.npcs.items():
            if npc.kb is not None and npc.kb.knows(subj, rel, obj):
                hits.append(pid)
        return {"subject": subj, "relation": rel, "obj": obj, "npcs": hits}
    return None


def hello_payload(runner) -> dict:
    locs_path = (Path(__file__).resolve().parents[3] / "config"
                 / "locations.json")
    try:
        locs = json.loads(locs_path.read_text(encoding="utf-8"))
    except OSError:
        locs = {"canvas": {"w": 1200, "h": 700}, "locations": {}}
    from citysim.core.config import SIGNALS
    return {"type": "hello", "protocol": 1,
            "scenario": runner.params["scenario"],
            "seed": runner.params["seed"],
            "n_npc": runner.params["n_npc"],
            "kb_mode": runner.params["kb_mode"],
            "tell_p": runner.params["tell_p"],
            "signals": list(SIGNALS),
            "locations": locs}
