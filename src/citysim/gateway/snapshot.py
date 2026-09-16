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

from typing import Collection

from pathlib import Path

from citysim.core.types import intent_kind, intent_target
from citysim.emojis import SEMANTIC_EMOJI
from citysim.world.engine import act_class_of

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


# tag -> 语义 key; 字形统一取自 citysim.emojis(由 emojis_by_category 生成)
_ICON_KEYS = {"sleepable": "bed", "toilet": "toilet", "edible": "food",
              "consumable": "meal"}
_TAG_PRIORITY = ("sleepable", "toilet", "edible", "consumable")
# Event Log 不显示的观测噪声(高频遥测, 不是"任务变更")
_HIDDEN_EVENT_KINDS = frozenset({"perceived"})

# 每帧 snapshot 里每个 NPC 携带的最近事件上限。
# 注意: 这是每 1/60s 重发的字段, 取值过大会让 payload 随时间无上限增长,
# 进而撑爆 WS 带宽/拖垮观察器(实测 200 时约 3 天后单帧 ~85KB、带宽持续上升)。
NPC_EVENT_LIMIT = 20


def fmt_clock(hour_f: float) -> str:
    m = int(round(hour_f * 60)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def icon_of(entity) -> str:
    for t in _TAG_PRIORITY:
        if t in entity.tags:
            return SEMANTIC_EMOJI[_ICON_KEYS[t]]
    return SEMANTIC_EMOJI["box"]




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
    """最近 NPC_EVENT_LIMIT 条与该 NPC 相关的事件(倒序扫描取最新; 隐藏高频遥测)。

    ui_events 是定长环形缓冲, 只扫其现有内容。上限刻意取小: 该字段每帧
    随 snapshot 下发, 必须"有界且小", 否则长跑会拖垮 WS(见 NPC_EVENT_LIMIT)。
    """
    out = []
    for ev in reversed(systems.ui_events):
        if ev.get("kind") in _HIDDEN_EVENT_KINDS:
            continue
        # 与自己相关 = 我是 subject(我干的/发生在我身上), 或我在 audience
        # (别人讲给我听 —— 否则“听谁说”永远不会出现在听者的日志里)
        aud = (ev.get("payload") or {}).get("audience") or ()
        if isinstance(aud, str):
            aud = (aud,)
        if ev.get("subject") == pid or pid in aud:
            out.append(dict(ev))
            if len(out) >= NPC_EVENT_LIMIT:
                break
    out.reverse()
    return out


def economy_block(world, systems) -> dict:
    """经济观测块(小): 公司账/招聘启事/在岗人数 + 每个店的前台数与排队人数。

    刻意只放【数字】不放对象 —— 这块每帧都随 snapshot 下发, 必须很小。
    细节(员工是谁、队里都是谁)走 query 或 hello。
    """
    from citysim.world.engine import COUNTER_ITEM, staffed_counters
    counters: dict[str, int] = {}
    for e in world.entities.values():
        if e.item_type == COUNTER_ITEM:
            counters[e.location_id] = counters.get(e.location_id, 0) + 1
    comps = []
    for cid, c in sorted(world.companies.items()):
        comps.append({
            "id": cid, "name": c.name, "owner": c.owner,
            "cash": round(c.cash, 2),
            "hiring_open": bool(c.hiring_open), "hiring_slots": int(c.hiring_slots),
            "wage_per_hour": float(c.wage_per_hour),
            "open_minute": int(c.open_minute), "close_minute": int(c.close_minute),
            "staff": [{"npc": n, "wage": w} for n, w in c.staff],
            "shops": list(c.shops),
        })
    on_duty: dict[str, int] = {}
    for shop_id in counters:
        on_duty[shop_id] = len(staffed_counters(world, systems, shop_id))
    queues = {sid: list(q) for sid, q in sorted(systems.shop_queue.items()) if q}
    return {"companies": comps, "counters": counters, "on_duty": on_duty,
            "queues": queues}


def _npc_core(world, systems, pid: str, p) -> dict:
    """NPC 的【渲染 + 列表】字段。

    刻意不含 intent/memory/events —— 它们会随时间越滚越大, 每帧发给每个人
    是长跑时单帧膨胀到上百 KB 的元凶。那三项只给 focus_npc(见 _npc_rich)。
    """
    act = systems.interaction.active.get(pid)
    tv = systems.travel.get(pid)
    loc = world.loc_of(pid)
    center = world.region_center(loc) or (0.0, 0.0)
    station = str((p.work or {}).get("station", ""))
    # 在岗 = 当前交互就是自己绑的那个工位(不是“有工作绑定”就算在岗)
    on_post = bool(act is not None and station and act.entity_id == station)
    return {
        "id": pid, "name": p.name, "loc": loc,
        "gender": p.gender,
        "home": p.home, "position": [float(x) for x in center],
        "activity": p.current_activity,
        # 上岗信息(公司画布要画"谁守着哪个台"): 空 = 没工作
        "work": p.work or None,
        "on_post": on_post,
        "role": p.role,
        "act_class": act_class_of(world, systems, pid),
        "money": round(p.money, 2),
        "age": p.age,
        "role": p.role,
        "signals": dict(p.signals),
        "active": None if act is None else _active_view(p, act),
        "travel": None if tv is None else {
            "from": tv.from_loc, "to": tv.to_loc,
            "depart": tv.depart_tick, "arrive": tv.arrive_tick,
            "waypoints": [[round(x, 2), round(y, 2)]
                          for x, y in tv.waypoints]},
        "plan": p.plan_snapshot(world.clock_tick),      # 当天计划表(时间线 viz; 每天才变)
        # 气泡: 瞬时事件(~40 tick)。前端自己按 until 决定何时消失,
        # 所以过期不需要再推一帧“空气泡”。
        "bubble": _bubble_of(p),
    }


def _active_view(p, act) -> dict:
    """进度来自 NPC 自己的 intake(WP-08); world 的 ActiveInteraction 不再存进度。"""
    rem, total = p.intake_progress(act.entity_id)
    return {"entity": act.entity_id, "remaining": rem, "total": total}


def _bubble_of(p) -> dict | None:
    b = getattr(p, "bubble", None)
    if b is None:
        return None
    text, until, kind = b
    return {"text": text, "until": int(until), "kind": kind}


def _npc_base(world, systems, pid: str, p) -> dict:
    """渲染/列表层(不含 memory/events/intent)。"""
    return _npc_core(world, systems, pid, p)


def _npc_rich(world, systems, pid: str, p) -> dict:
    """【被选中】的那个: 额外带意图 / 记忆 / 事件(仅供 Inspector)。"""
    d = _npc_core(world, systems, pid, p)
    mem = p.memory_dicts()
    d["intent"] = _intent_detail(p.last_intent)
    d["memory"] = mem
    d["memory_counts"] = len(mem)
    d["events"] = _recent_events(systems, pid)
    d["timeline"] = list(getattr(systems, "activity_log", {}).get(pid, ()))
    return d


def build_snapshot(world, systems, cfg, speed: str,
                   events: list[dict], tps: int | None = None,
                   only: Collection[str] | None = None,
                   gone: dict | None = None,
                   rich: Collection[str] | None = None,
                   entities_only: Collection[str] | None = None) -> dict:
    """世界 → JSON 快照(纯读)。

    only: 只下发这些 npc_id(观察驱动)。None = 全量。
    渲染状态未变的 NPC 不出现在帧里 —— 客户端 merge 并保留上次值,
    所以“在家不动”的 NPC 不需要反复重发位置。

    gone: {"npcs": [...], "entities": [...]} —— 上帧之后【消失】的 id
    (死亡 / 被消耗 / 被删)。客户端是合并式更新, 不告诉它就会留幽灵。

    rich: 带 memory/events/intent 的 id(只有被选中的那个); 其余只给渲染层。

    entities_only: 只下发这些 entity_id(物品几乎不变 → 变了才推);
    None = 全量。注意 shelf_index 仍按【全量】算, 所以货架位次不因过滤而错位。
    """
    tick = world.clock_tick
    rich_ids = rich or ()
    npcs = []
    for pid, p in sorted(world.npcs.items()):
        if only is not None and pid not in only:
            continue
        npcs.append(_npc_rich(world, systems, pid, p) if pid in rich_ids
                    else _npc_base(world, systems, pid, p))
    ents = [{"id": e.entity_id, "name": e.name, "loc": e.location_id,
             "item_type": e.item_type,
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
    if entities_only is not None:
        ents = [e for e in ents if e["id"] in entities_only]
    out = {"type": "snapshot", "tick": tick,
           "day": tick // cfg.ticks_per_day + 1,
           "hour_f": round(world.hour_f(), 4),
           "clock": fmt_clock(world.hour_f()),
           "speed": speed, "running": speed != "pause",
           "tps": tps if tps is not None else 0,
           "entities": ents, "npcs": npcs, "events": events,
           # 经济观测块(小: 只有数字) —— 公司面板/公司画布靠它实时更新
           "economy": economy_block(world, systems)}
    if gone and (gone.get("npcs") or gone.get("entities")):
        out["gone"] = gone          # 空的时候不占位(绝大多数帧都是空)
    return out


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


def _fixture_catalog() -> list:
    from citysim.world.market import fixture_catalog
    return fixture_catalog()


def _market_info(runner) -> dict:
    """批发市场(静态): 在不在 + 能进什么货/批发价。【货物管理】页读它。"""
    from citysim.world.market import market_catalog, market_places
    places = market_places(runner.world)
    return {"exists": bool(places), "places": places,
            "items": market_catalog()}


def hello_payload(runner) -> dict:
    from citysim.gateway.scenarios import DEFAULT_SCENE, default_scene_path
    import json as _json
    locs_path = default_scene_path() or DEFAULT_SCENE
    try:
        all_scene = _json.loads(Path(locs_path).read_text(encoding="utf-8"))
    except OSError:
        all_scene = {"canvas": {"w": 1280, "h": 760}, "locations": {}}
    # 用 world 上【算好的】几何(kind/capacity/pattern + 显式或自动布局的 x/y/w/h),
    # 不是原始 scene 文本。
    # 全部下发: 编辑器导出的空建筑也要在观察器里可见(占用为 0)。
    loc_map = dict(runner.world.locations)
    # canvas 优先取世界加载时记录的场景值(支持编辑器导出的非默认画布)
    canvas = getattr(runner.world, "canvas", None) or \
        all_scene.get("canvas", {"w": 1280, "h": 760})
    locs = {"canvas": canvas, "locations": loc_map}
    from citysim.core.config import SIGNALS
    return {"type": "hello", "protocol": PROTOCOL_VERSION,
            "scene_error": getattr(runner, "build_error", ""),
            # 编辑器原始地图(节点/路段/建筑含 rot/doors); 无则 {}
            "map": getattr(runner.world, "map", {}) or {},
            "scenario": runner.params["scenario"],
            "seed": runner.params["seed"],
            "n_npc": runner.params["n_npc"],
            # 下发【实际生效的】传播参数(不是面板里那个可能没用的默认值):
            # params 里为 None = 跟随模拟配置 → 这里取 systems 上的真值。
            # 公司(只读观测): 账 / 老板 / 员工。经营面板以后在此基础上做写侧。
            "companies": [
                {"id": cid, "name": comp.name, "cash": round(comp.cash, 2),
                 "owner": comp.owner, "shops": list(comp.shops),
                 "staff": [{"npc": n, "wage": w} for n, w in comp.staff]}
                for cid, comp in sorted(runner.world.companies.items())],
            # 装修件目录(静态): 【装修管理】页按它列可放的东西与价格。
            "fixtures": _fixture_catalog(),
            # 批发市场(静态): 在不在 + 可进货清单。【货物管理】页读它。
            "market": _market_info(runner),
            "tell_p": runner.systems.tell_p,
            "listen_p": runner.systems.listen_p,
            "tell_same_home": runner.systems.tell_same_home,
            "tell_stranger": runner.systems.tell_stranger,
            "signals": list(SIGNALS),
            "locations": locs}
