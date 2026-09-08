"""snapshot —— 世界 → JSON(纯读观察者)。Person 化后的新契约。

铁律:
  - 禁止 build_percept()(会清空 NPC 信箱) / 禁止碰 rng_pool / 禁止写内核字段。
  - 只读 Person 门面方法(person.snapshot / memory_dicts / last_intent …), 不碰内部字段。

契约变更(去 kb/archetype):
  - npc 去掉了 kb(知识图) / kb_counts / last_percept / archetype / used_facts。
  - 记忆改按 item 行全属性显示: memory = person.memory_dicts()(每 item: 属性+believe+remember)。
  - intent 保留 kind/target/reason/ranked/relevant_signals。
  - act_class 保留(服务端按 active/travel 推导)。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.types import intent_kind, intent_target

# TASK002: WS 消息协议版本(协议变化时递增; 本契约变更故 +1)
PROTOCOL_VERSION = 2


def envelope(kind: str, payload: dict) -> dict:
    return {"kind": kind, "protocol_version": PROTOCOL_VERSION,
            "payload": payload}


def encode_event(ev: dict) -> dict:
    d = dict(ev)
    kind = str(d.get("kind", d.get("type", "?")))
    d.setdefault("type", kind)
    d.setdefault("event_id", f"{kind}:{d.get('tick')}:{d.get('subject', '')}")
    d.setdefault("source", d.get("subject"))
    if d.get("target") is None and isinstance(d.get("payload"), dict):
        d["target"] = d["payload"].get("target")
    return d


_ICONS = {"sleepable": "🛏", "toilet": "🚽", "edible": "🍱",
          "entertain": "📺", "drink": "🚰", "consumable": "🍽"}
_TAG_PRIORITY = ("sleepable", "toilet", "edible",
                 "entertain", "drink", "consumable")
_EVENT_KINDS = ("interaction_done", "intent_failed", "decision", "perceived",
                "bought", "stock_changed", "npc_died")


def fmt_clock(hour_f: float) -> str:
    m = int(round(hour_f * 60)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def icon_of(entity) -> str:
    for t in _TAG_PRIORITY:
        if t in entity.tags:
            return _ICONS[t]
    return "📦"


def parse_log_line(line: str) -> dict | None:
    parts = line.split("\t")
    if not parts:
        return None
    kind = parts[0]
    if kind == "D":
        if len(parts) < 5:
            return None
        return {"tick": int(parts[1]), "kind": "decision",
                "subject": parts[2], "target": parts[4],
                "intent": parts[3], "payload": {}}
    if kind == "E":
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


def _intent_detail(it) -> dict | None:
    """把 Person.last_intent 展开为前端可读详情(只保留在 types 契约上的字段)。"""
    if it is None:
        return None
    return {
        "kind": intent_kind(it), "target": intent_target(it),
        "reason": it.trace.reason,
        "ranked": [{"id": i, "score": round(s, 4)}
                   for i, s in it.trace.ranked],
        "relevant_signals": [[k, round(v, 4)] for k, v
                             in it.trace.relevant_signals],
    }


def _recent_events(systems, pid: str) -> list:
    recent = []
    for ev in (systems.ui_events or [])[-500:]:
        if ev.get("subject") == pid:
            recent.append(dict(ev))
            if len(recent) >= 50:
                break
    return recent


def _npc_base(world, systems, pid: str, p) -> dict:
    act = systems.interaction.active.get(pid)
    tv = systems.travel.get(pid)
    loc = world.loc_of(pid)
    center = world.region_center(loc) or (0.0, 0.0)
    return {
        "id": pid, "name": p.name, "loc": loc,
        "home": p.home, "position": [float(x) for x in center],
        "activity": p.current_activity,
        "act_class": act_class_of(world, systems, pid),
        "money": round(p.money, 2),
        "signals": dict(p.signals),
        "active": None if act is None else {
            "entity": act.entity_id, "remaining": act.remaining_ticks,
            "total": act.total_ticks},
        "travel": None if tv is None else {
            "from": tv.from_loc, "to": tv.to_loc,
            "depart": tv.depart_tick, "arrive": tv.arrive_tick},
    }


def build_snapshot(world, systems, cfg, speed: str,
                   events: list[dict], tps: int | None = None) -> dict:
    tick = world.clock_tick
    npcs = []
    for pid, p in sorted(world.npcs.items()):
        mem = p.memory_dicts()
        npcs.append({
            **_npc_base(world, systems, pid, p),
            "intent": _intent_detail(p.last_intent),
            "memory": mem,
            "memory_counts": len(mem),
            "events": _recent_events(systems, pid),
        })
    ents = [{"id": e.entity_id, "name": e.name, "loc": e.location_id,
             "tags": sorted(e.tags), "stock": e.stock,
             "claimed_by": e.claimed_by, "icon": icon_of(e),
             "position": None if e.position is None else
                          [float(e.position[0]), float(e.position[1])],
             "affordances": dict(e.affordances), "price": e.price,
             "owner": e.owner, "duration_ticks": e.duration_ticks,
             "attrs": dict(e.attrs),
             "on_start": [dict(x) for x in (e.on_start or [])],
             "on_complete": [dict(x) for x in (e.on_complete or [])]}
            for _, e in sorted(world.entities.items())]
    slot_of: dict[str, int] = {}
    by_loc: dict[str, list[str]] = {}
    for e in ents:
        by_loc.setdefault(e["loc"], []).append(e["id"])
    for ids in by_loc.values():
        for i, eid in enumerate(sorted(ids)):
            slot_of[eid] = i
    for e in ents:
        e["shelf_index"] = slot_of.get(e["id"], 0)
    return {"type": "snapshot", "tick": tick,
            "day": tick // cfg.ticks_per_day + 1,
            "hour_f": round(world.hour_f(), 4),
            "clock": fmt_clock(world.hour_f()),
            "speed": speed, "running": speed != "pause",
            "tps": tps if tps is not None else 0,
            "entities": ents, "npcs": npcs, "events": events}


def build_npc_state(world, systems, pid: str) -> dict | None:
    npc = world.npcs.get(pid)
    if npc is None:
        return None
    return {
        **_npc_base(world, systems, pid, npc),
        "intent": _intent_detail(npc.last_intent),
        "memory_counts": len(npc.memory_dicts()),
    }


def build_npc_detail(world, systems, pid: str) -> dict | None:
    npc = world.npcs.get(pid)
    if npc is None:
        return None
    mem = npc.memory_dicts()
    return {
        **_npc_base(world, systems, pid, npc),
        "intent": _intent_detail(npc.last_intent),
        "memory": mem,
        "memory_counts": len(mem),
        "events": _recent_events(systems, pid),
    }


def do_query(runner, args: dict) -> dict | None:
    what = args.get("what")
    if what == "npc_state":
        return build_npc_state(runner.world, runner.systems,
                               args.get("npc_id", ""))
    if what == "npc_detail":
        return build_npc_detail(runner.world, runner.systems,
                                args.get("npc_id", ""))
    return None


def hello_payload(runner) -> dict:
    from citysim.gateway.scenarios import DEFAULT_SCENE
    import json as _json
    locs_path = DEFAULT_SCENE
    try:
        all_scene = _json.loads(Path(locs_path).read_text(encoding="utf-8"))
    except OSError:
        all_scene = {"canvas": {"w": 1280, "h": 760}, "locations": {}}
    used = {e.location_id for e in runner.world.entities.values()}
    used |= {runner.world.loc_of(n.person_id) for n in runner.world.npcs.values()}
    loc_map = all_scene.get("locations", {})
    if used:
        loc_map = {k: v for k, v in loc_map.items() if k in used}
    locs = {"canvas": all_scene.get("canvas", {"w": 1280, "h": 760}),
            "locations": loc_map}
    from citysim.core.config import SIGNALS
    return {"type": "hello", "protocol": PROTOCOL_VERSION,
            "scenario": runner.params["scenario"],
            "seed": runner.params["seed"],
            "n_npc": runner.params["n_npc"],
            "tell_p": runner.params["tell_p"],
            "signals": list(SIGNALS),
            "locations": locs}
