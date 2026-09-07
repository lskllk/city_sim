"""snapshot —— 世界 → JSON(纯读观察者, display_m5_ui G0)。

铁律(design 第三节, 逐字遵守):
  - 禁止 build_percept()(会清空 NPC 信箱) / 禁止碰 rng_pool / 禁止写内核字段。
  - 事件只从 systems.log_lines 尾读; 本模块不挂 subscribe_log。

TASK002 —— Observation Contract:
  - PROTOCOL_VERSION + envelope(): 统一 WS 消息外壳(kind/protocol_version/payload)。
  - encode_event(): 把 ui_events 条目 canonical 化为稳定 Event 结构。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from citysim.core.types import intent_kind, intent_target
from citysim.viz.kb_export import export_kb_json
from citysim.viz.trace_export import export_trace_chain

# TASK002: WS 消息协议版本(协议变化时递增)
PROTOCOL_VERSION = 1


def envelope(kind: str, payload: dict) -> dict:
    """统一消息外壳: 消息类型 + 协议版本 + 内容分离。"""
    return {"kind": kind, "protocol_version": PROTOCOL_VERSION,
            "payload": payload}


def encode_event(ev: dict) -> dict:
    """ui_events 条目 → canonical Event 结构(保留原字段以兼容旧观察器)。

    canonical: event_id / tick / type / source / target / payload。
    只加不删; 无 event_id 时按 kind:tick:subject 生成稳定回退 id。
    """
    d = dict(ev)
    kind = str(d.get("kind", d.get("type", "?")))
    d.setdefault("type", kind)
    d.setdefault("event_id", f"{kind}:{d.get('tick')}:{d.get('subject', '')}")
    d.setdefault("source", d.get("subject"))
    if d.get("target") is None and isinstance(d.get("payload"), dict):
        d["target"] = d["payload"].get("target")
    return d

# 实体 tag -> emoji(不许按中文名匹配, M4 纪律)
_ICONS = {"sleepable": "🛏", "toilet": "🚽",
          "edible": "🍱", "entertain": "📺", "drink": "🚰",
          "consumable": "🍽"}
_TAG_PRIORITY = ("sleepable", "toilet", "edible",
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
        # D tick pid intent target
        if len(parts) < 5:
            return None
        return {"tick": int(parts[1]), "kind": "decision",
                "subject": parts[2], "target": parts[4],
                "intent": parts[3],
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
                "intent": "", "payload": payload}
    return None


def act_class_of(world, systems, pid: str) -> str:
    """服务端推导活动类别(g5-life 01/B5): 按 active 实体 tags。"""
    if pid in systems.travel:
        return "move"
    act = systems.interaction.active.get(pid)
    if act is None:
        return "idle"
    ent = world.entities.get(act.entity_id)
    if ent is None:
        return "idle"
    t = ent.tags
    if "sleepable" in t:
        return "sleep"
    if "toilet" in t:
        return "toilet"
    if "drink" in t:
        return "drink"
    if "entertain" in t:
        return "fun"
    if "edible" in t:
        return "eat"
    return "idle"


def build_snapshot(world, systems, cfg, speed: str,
                   events: list[dict], tps: int | None = None) -> dict:
    tick = world.clock_tick
    npcs = []
    for pid, p in sorted(world.npcs.items()):
        act = systems.interaction.active.get(pid)
        tv = systems.travel.get(pid)
        it = p.last_intent
        used = []
        if it is not None and it.trace.used_fact_ids and p.kb is not None:
            used = export_trace_chain(p.kb, it.trace.used_fact_ids).get(
                "facts", [])
        recent = []
        for ev in (systems.ui_events or [])[-500:]:
            if ev.get("subject") == pid:
                recent.append(dict(ev))
                if len(recent) >= 50:
                    break
        npcs.append({
            "id": pid, "name": p.name, "loc": p.location_id,
            "position": [float(x) for x in p.position],
            "archetype": p.archetype_id,
            "activity": p.current_activity,
            "act_class": act_class_of(world, systems, pid),
            "signals": {k: round(v, 4) for k, v in p.signals.items()},
            "active": None if act is None else {
                "entity": act.entity_id, "remaining": act.remaining_ticks,
                "total": act.total_ticks},
            "travel": None if tv is None else {
                "from": tv.from_loc, "to": tv.to_loc,
                "depart": tv.depart_tick, "arrive": tv.arrive_tick},
            "intent": None if it is None else {
                "kind": intent_kind(it), "target": intent_target(it),
                "reason": it.trace.reason,
                "ranked": [{"id": i, "score": round(s, 4)}
                           for i, s in it.trace.ranked],
                "relevant_signals": [[k, round(v, 4)] for k, v
                                      in it.trace.relevant_signals],
                "used_facts": used},
            "last_percept": None if p.last_percept is None else {
                "tick": p.last_percept.tick,
                "loc": p.last_percept.location_id,
                "position": [float(x) for x in p.last_percept.position],
                "observed": list(p.last_percept.observed_entity_ids)},
            "kb": export_kb_json(p.kb) if p.kb is not None else
                 {"nodes": [], "edges": []},
            "kb_counts": kb_counts(p.kb),
            "events": recent,
        })
    ents = [{"id": e.entity_id, "name": e.name, "loc": e.location_id,
             "tags": sorted(e.tags), "stock": e.stock,
             "claimed_by": e.claimed_by, "icon": icon_of(e),
             "position": None if e.position is None else
                          [float(e.position[0]), float(e.position[1])],
             # TASK004-ext: 只读静态属性/效果(itemdef/scene 已存在, 无语义改动)
             "affordances": dict(e.affordances), "price": e.price,
             "owner": e.owner, "duration_ticks": e.duration_ticks,
             "attrs": dict(e.attrs),
             "on_start": [dict(x) for x in (e.on_start or [])],
             "on_complete": [dict(x) for x in (e.on_complete or [])]}
            for _, e in sorted(world.entities.items())]
    # 实体房间内槽位(按 id 定序, g5-life 04)
    slot_of: dict[str, int] = {}
    by_loc: dict[str, list[str]] = {}
    for e in ents:
        by_loc.setdefault(e["loc"], []).append(e["id"])
    for ids in by_loc.values():
        for i, eid in enumerate(sorted(ids)):
            slot_of[eid] = i
    for e in ents:
        e["shelf_index"] = slot_of.get(e["id"], 0)   # g5 canvasrecode 3.2
    return {"type": "snapshot", "tick": tick,
            "day": tick // cfg.ticks_per_day + 1,
            "hour_f": round(world.hour_f(), 4),
            "clock": fmt_clock(world.hour_f()),
            "speed": speed, "running": speed != "pause",
            "tps": tps if tps is not None else 0,
            "entities": ents, "npcs": npcs, "events": events}


def build_npc_state(world, systems, pid: str) -> dict | None:
    """轻查询(g5-life 02): 信号+意图+活动, 供状态页 1Hz 实时。"""
    npc = world.npcs.get(pid)
    if npc is None:
        return None
    it = npc.last_intent
    act = systems.interaction.active.get(pid)
    tv = systems.travel.get(pid)
    return {
        "id": pid, "name": npc.name, "loc": npc.location_id,
        "activity": npc.current_activity,
        "act_class": act_class_of(world, systems, pid),
        "signals": {k: round(v, 4) for k, v in npc.signals.items()},
        "active": None if act is None else {
            "entity": act.entity_id, "remaining": act.remaining_ticks,
            "total": act.total_ticks},
        "travel": None if tv is None else {
            "from": tv.from_loc, "to": tv.to_loc,
            "depart": tv.depart_tick, "arrive": tv.arrive_tick},
        "intent": None if it is None else {
            "kind": intent_kind(it), "target": intent_target(it),
            "reason": it.trace.reason},
        "kb_counts": kb_counts(npc.kb),
    }


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
    for ev in (systems.ui_events or [])[-500:]:
        if ev.get("subject") == pid:
            recent.append(dict(ev))
            if len(recent) >= 50:
                break
    st = build_npc_state(world, systems, pid) or {}
    return {
        "id": pid, "name": npc.name, "loc": npc.location_id,
        "position": [float(x) for x in npc.position],
        "archetype": npc.archetype_id,
        "activity": npc.current_activity,
        "signals": {k: round(v, 4) for k, v in npc.signals.items()},
        "intent": None if it is None else {
            "kind": intent_kind(it), "target": intent_target(it), "reason": it.trace.reason,
            "ranked": [{"id": i, "score": round(s, 4)}
                       for i, s in it.trace.ranked],
            "relevant_signals": [[k, round(v, 4)] for k, v
                                  in it.trace.relevant_signals],
            "used_facts": used},
        "last_percept": None if npc.last_percept is None else {
            "tick": npc.last_percept.tick,
            "loc": npc.last_percept.location_id,
            "position": [float(x) for x in npc.last_percept.position],
            "observed": list(npc.last_percept.observed_entity_ids)},
        "kb": export_kb_json(npc.kb) if npc.kb is not None else
             {"nodes": [], "edges": []},
        "kb_counts": kb_counts(npc.kb),
        "events": recent,
        "act_class": st.get("act_class", "idle"),
    }


def _fact_payload(ev: dict) -> tuple:
    p = ev.get("payload", {})
    return (p.get("subject"), p.get("relation"), p.get("obj"))


def do_query(runner, args: dict) -> dict | None:
    what = args.get("what")
    if what == "npc_state":
        return build_npc_state(runner.world, runner.systems,
                               args.get("npc_id", ""))
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
    """hello: 用单一场景(elm_lane)的 canvas/locations; 只发本场景实际用到的
    房间(canvasrecode 2/9: 相机用【全部声明房间】bbox, 只在 hello/reset/resize 算)。"""
    from citysim.gateway.scenarios import DEFAULT_SCENE
    import json as _json
    locs_path = DEFAULT_SCENE
    try:
        all_scene = _json.loads(Path(locs_path).read_text(encoding="utf-8"))
    except OSError:
        all_scene = {"canvas": {"w": 1280, "h": 760}, "locations": {}}
    used = {e.location_id for e in runner.world.entities.values()}
    used |= {n.location_id for n in runner.world.npcs.values()}
    loc_map = all_scene.get("locations", {})
    if used:
        loc_map = {k: v for k, v in loc_map.items() if k in used}
    locs = {"canvas": all_scene.get("canvas", {"w": 1280, "h": 760}),
            "locations": loc_map}
    from citysim.core.config import SIGNALS
    return {"type": "hello", "protocol": 1,
            "scenario": runner.params["scenario"],
            "seed": runner.params["seed"],
            "n_npc": runner.params["n_npc"],
            "kb_mode": runner.params["kb_mode"],
            "tell_p": runner.params["tell_p"],
            "signals": list(SIGNALS),
            "locations": locs}
