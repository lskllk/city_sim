"""world/engine —— 世界执行器(推进一个 tick 的世界演化 + 决策编排)。

按 World↔Person 契约: 上帝(World 侧)执行"世界进程"并广播心跳, 只发事件不写 Person。
systems 为执行环境(duck: interaction/travel/pulses/日志), 由上层构造传入,
本模块不 import sim(避免 world→sim 反向依赖)。
"""
from __future__ import annotations

import zlib

from citysim.npc import semantic as _sem

from typing import Any, Mapping

from citysim.core.config import SimConfig
from citysim.core.types import (
    Buy,
    Idle,
    Interact,
    MoveTo,
    intent_kind,
    intent_target,
)
from citysim.world.drive import due_npcs
from citysim.world.itemdefs import load_item_defs
from citysim.world.pulses import apply as apply_pulses
from citysim.world.perception import build_percept
from citysim.world.travel import Travel
from citysim.world.world import Entity, entity_from_def


def _travel_cost(systems, cfg: SimConfig, a: str, b: str) -> int:
    """跨地点移动耗时: 优先 travel_costs 矩阵, 缺省回落 cfg.move_ticks。"""
    if systems.travel_costs:
        c = systems.travel_costs.get(f"{a}|{b}") or \
            systems.travel_costs.get(f"{b}|{a}")
        if c is not None:
            return c
    return cfg.move_ticks


def _route_between(world, systems, a: str, b: str):
    """有路网且两端都接得上 → 沿路最短路径; 否则 None(上层降级)。"""
    roads = getattr(systems, "roads", None)
    if roads is None or not roads.ok:
        return None
    pa, pb = world.door_point(a), world.door_point(b)
    if pa is None or pb is None:
        return None
    return roads.route(pa, pb)


def _sleeping(world, systems, pid: str) -> bool:
    act = systems.interaction.active.get(pid)
    if act is None:
        return False
    ent = world.entities.get(act.entity_id)
    return ent is not None and ent.is_sleepable


def _busy(world, systems, pid: str) -> bool:
    """忙碌 = 有进行中交互 或 正在跨地点移动。"""
    return (systems.interaction.active.get(pid) is not None
            or pid in systems.travel)


def _kill(world, systems, pid: str) -> None:
    """NPC 死亡: 清残留 → 从世界销毁 → 发布死亡事件。"""
    npc = world.npcs.get(pid)
    if npc is None:
        return
    systems.interaction.release_active(world, pid)   # 清 claim
    systems.travel.pop(pid, None)                    # 清旅行
    world.npcs.pop(pid, None)                        # 从世界销毁
    world.bus.publish(world.bus.make(
        world.clock_tick, "npc_died", pid,
        {"name": npc.name, "loc": world.loc_of(pid)}))


# --- 传播(传闻) -----------------------------------------------------------
#
# 规则(docs/design.md §2.6):
#   - 信任只有两档: 同址(同一个 home) 0.9~1.0; 否则 0.4~0.7
#   - 按 (a,b) **确定性派生** —— 每对人一个固定值, 零存储、可回放
#   - 传出去的 believe = 说话人自己信的程度 × 对听者的信任
#   - “对方已知就不说” → 消息播完自己就停, 不会全城皆知
#
# 注意: 这里**不做** trust 的演化(mind.md 的 verify) —— 那是后续插件。

BELIEF_FLOOR = 0.3      # 低于此就不值得再传了
SAY_COOLDOWN = 240      # 同一话题这么 tick 内不重复说(4 小时)
TRUST_SAME_HOME = (0.9, 1.0)
TRUST_OTHER = (0.4, 0.7)


def _unit_hash(key: str) -> float:
    """把字符串稳定地映到 [0,1)。**不用内置 hash()** —— 它每进程随机化, 回放会飘。"""
    return (zlib.crc32(key.encode("utf-8")) % 10_000) / 10_000.0


def trust_between(a, b) -> float:
    """a 有多信 b 说的话(0..1)。同址(同一个 home) → 高信任档。"""
    same = bool(a.home) and a.home == b.home
    lo, hi = TRUST_SAME_HOME if same else TRUST_OTHER
    k = a.person_id if a.person_id < b.person_id else b.person_id
    j = b.person_id if a.person_id < b.person_id else a.person_id
    return lo + (hi - lo) * _unit_hash("%s|%s" % (k, j))


def _npc_point(world, systems, pid: str) -> tuple[float, float] | None:
    """NPC 【此刻】的世界坐标。

    · 在途: 按 (now - depart)/(arrive - depart) 沿 waypoints 折线插值
      —— 和前端用的是同一个式子(所以"路过"两边看到的是同一个位置)
    · 不在途: 用所在地点的中心
    """
    tv = systems.travel.get(pid)
    if tv is not None and len(tv.waypoints) >= 2:
        span = tv.arrive_tick - tv.depart_tick
        t = 1.0 if span <= 0 else max(0.0, min(
            1.0, (world.clock_tick - tv.depart_tick) / float(span)))
        pts = tv.waypoints
        seg = [0.0]
        total = 0.0
        for i in range(1, len(pts)):
            dx = pts[i][0] - pts[i - 1][0]
            dy = pts[i][1] - pts[i - 1][1]
            total += (dx * dx + dy * dy) ** 0.5
            seg.append(total)
        if total <= 0.0:
            return float(pts[0][0]), float(pts[0][1])
        want = total * t
        for i in range(1, len(pts)):
            if seg[i] >= want:
                span_len = seg[i] - seg[i - 1]
                k = 0.0 if span_len <= 0 else (want - seg[i - 1]) / span_len
                x = pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * k
                y = pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k
                return x, y
        return float(pts[-1][0]), float(pts[-1][1])
    loc = world.locations.get(world.loc_of(pid))
    if not loc:
        return None
    x = float(loc.get("x", 0.0)) + float(loc.get("w", 0.0)) * 0.5
    y = float(loc.get("y", 0.0)) + float(loc.get("h", 0.0)) * 0.5
    return x, y


def _loc_center(loc: Mapping[str, Any]) -> tuple[float, float]:
    return (float(loc.get("x", 0.0)) + float(loc.get("w", 0.0)) * 0.5,
            float(loc.get("y", 0.0)) + float(loc.get("h", 0.0)) * 0.5)


def _perceive_signs(world, systems) -> None:
    """招牌 = 会说话的世界: 走进半径就"看到"招牌上那几条消息。

    —— 这是【感知】而不是【传播】——
    不走 _notify_due 的那套(说概率/听概率/一对一/话题冷却): 招牌不挑人、不等对方
    愿意听, 只要你路过。写进去的 source = "sign:<bid>"、believe = 招牌自己那个档,
    所以它在传播里仍然只是"听说的", 也能被别人转述出去。

    只在【新消息 / 价格库存变了】时才写 —— 否则站在门口每 tick 都刷一遍。
    """
    signs = [(bid, loc["sign"]) for bid, loc in sorted(world.locations.items())
             if isinstance(loc, dict) and loc.get("sign")]
    if not signs:
        return
    for pid in sorted(world.npcs):
        npc = world.npcs.get(pid)
        if npc is None:
            continue
        pt = _npc_point(world, systems, pid)
        if pt is None:
            continue
        for bid, sign in signs:
            loc = world.locations.get(bid) or {}
            cx, cy = _loc_center(loc)
            dx, dy = pt[0] - cx, pt[1] - cy
            if (dx * dx + dy * dy) ** 0.5 > float(sign.get("radius", 12.0)):
                continue                       # 还没走到看得见的地方
            for eid in sign.get("messages", ()):
                ent = world.entities.get(eid)
                if ent is None:
                    continue                   # 招牌上写了不存在的货 → 忽略
                afford, value = next(iter(ent.affordances.items()), ("", 0.0))
                seen = npc.see_sign(
                    eid, world.clock_tick, located=ent.location_id,
                    name=ent.name, price=float(ent.price),
                    stock=int(ent.stock), believe=float(sign.get("believe", 0.7)),
                    source="sign:%s" % bid, afford=afford, value=float(value),
                    item_type=ent.item_type)
                if not seen:
                    continue
                # 路过的人头顶冒一句 —— 没有它, 玩家根本不知道招牌起作用了
                _set_bubble(systems, npc,
                            _sem.sign_line(ent.name, _price_word(
                                {"price": ent.price, "stock": ent.stock})),
                            "sign", world.clock_tick)
                world.bus.publish(world.bus.make(
                    world.clock_tick, "saw_sign", pid,
                    {"audience": [pid], "sign": bid, "item_id": eid,
                     "price": ent.price, "company": sign.get("company", "")}))


def _notify_due(world, systems, npc, ev) -> None:
    """这一轮张嘴: 把【刚才那句值得说的话】说给【一个】同地的人听。

    —— 2026-09-15: 改成【一对一搭桥】+【跟谁说得看关系】——
    旧版是"一对多": 一个人张嘴就能同时告诉身边所有人。
    现在三道骰子, 都过才成一条桥:
      ① 我这一轮想不想开口      tell_p × tell_bias
      ② 愿不愿意【跟这个人】说  同屋 tell_same_home / 路人 tell_stranger
      ③ 对方愿不愿意停下来听     listen_p
    而且【只搭一条桥】: 说的人这轮不再听、听的人这轮不再说(说的不听/听的不说),
    一个场地里只有"在说的"和"在听的"才配对。

    说什么由语义层决定(见 docs/design.md §2.7): `ev` 是 Person
    攒好的 SemanticEvent(DOUBT > SURPRISE > INTENT > STATE), 没话可说就不说。
    """
    tick = world.clock_tick
    if systems.talked_tick != tick:          # 新的一轮 → 清空搭桥名册
        systems.talked.clear()
        systems.talked_tick = tick
    if npc.person_id in systems.talked:
        return                               # 这一轮已经在说/在听了

    fact: dict = {}
    if ev is not None:
        fact = dict(ev.slots or {})
    item_id = str(fact.get("item_id", ""))
    if not item_id:
        # 刚发生的意外已经冒过泡了 —— 但【新闻要能带走】:
        # 退一步从记忆里挑一件"值得转述"的(不是自家东西/没有 afford 的不要)
        picked = _sem.pick_retellable(npc.memory_dicts(), home=npc.home,
                                      knows=lambda _i: False)
        if picked is None:
            return                           # 没话可说就不说(不硬造话题)
        fact = dict(picked)
        item_id = str(picked.get("item_id", ""))
        fact["item"] = _item_name(world, item_id)
        fact["now"] = _price_word(fact)

    tell_p = float(getattr(systems, "tell_p", 0.0))
    listen_p = float(getattr(systems, "listen_p", 1.0))
    if tell_p <= 0.0 or listen_p <= 0.0:
        return
    rng = getattr(systems, "rng", None)
    if rng is None:
        return
    if rng.random() >= tell_p * npc.tell_bias:      # ① 我想不想说
        return
    same_mul = float(getattr(systems, "tell_same_home", 1.0))
    str_mul = float(getattr(systems, "tell_stranger", 0.15))
    loc = world.loc_of(npc.person_id)
    # 先收集所有过闸的人, 再【按权重抽一个】——
    # 不能"按 id 顺序取第一个过闸的": 同屋的人永远排在路人前面,
    # 于是"路人概率低"根本不起作用(抽签必须真的抽)。
    cands: list[tuple[float, str]] = []
    for other_id in sorted(world.npcs):
        if other_id == npc.person_id or world.loc_of(other_id) != loc:
            continue
        if other_id in systems.talked:            # 他这轮已经在说/在听了
            continue
        other = world.npcs[other_id]
        same_home = bool(npc.home) and npc.home == other.home
        pair_mul = same_mul if same_home else str_mul
        if rng.random() >= pair_mul:              # ② 愿不愿意跟这个人说
            continue
        if rng.random() >= listen_p:              # ③ 他愿不愿意听
            continue
        if not _may_tell(world, systems, npc, other, fact):
            continue                              # 六条硬规则(对方已知就不说)
        cands.append((pair_mul, other_id))
    if not cands:
        return
    total = sum(w for w, _ in cands)
    roll = rng.random() * total
    other_id = cands[-1][1]
    acc = 0.0
    for w_, oid in cands:                         # 同屋权重大 → 中签多
        acc += w_
        if roll < acc:
            other_id = oid
            break
    other = world.npcs[other_id]

    # 搭上这一条桥 —— 双方名额都用掉, 本轮不再参与
    systems.talked.add(npc.person_id)
    systems.talked.add(other_id)
    npc.mark_said("item.%s" % item_id, tick)
    trust = trust_between(npc, other)
    other.note(item_id, tick=tick,
               located=str(fact.get("located", "")),
               afford=str(fact.get("afford", "")),
               value=float(fact.get("value", 0.0)),
               price=float(fact.get("price", 0.0)),
               item_type=str(fact.get("item_type", "")),
               stock=int(fact.get("stock", -1)),
               shelf_life_ticks=int(fact.get("shelf_life_ticks", 0)),
               believe=float(fact.get("believe", 1.0)) * trust,
               source=npc.person_id)
    item_name = str(fact.get("item", _item_name(world, item_id)))
    now = str(fact.get("now", _price_word(fact)))
    # 听者头顶: “王伟说：简餐8块”（看得见是谁跟他说的）
    rep = _sem.report(tick, npc.person_id, item_id, item_name, now, who=npc.name)
    _set_bubble(systems, other, _sem.render(rep, speaker_name=npc.name),
                "told", tick)
    # 说者头顶: “跟林静说：简餐8块”（另一半桥 —— 谁给谁说一眼看得出）
    _set_bubble(systems, npc, _sem.say_line(other.name, item_name, now),
                "say", tick)
    world.bus.publish(world.bus.make(
        tick, "told", npc.person_id,
        {"audience": [other_id], "item_id": item_id,
         "from": npc.person_id, "to": other_id,
         "believe": round(trust, 3)}))


def _may_tell(world, systems, npc, other, fact: Mapping[str, Any]) -> bool:
    """允许把这条事实说给 other 吗? —— 传播的硬规则**集中在这里**。

    ① 对方已经知道 → 不说。**这条本身就是天然的衰减器**: 传开后能说的人
       越来越少, 链条自己停(所以不需要 hops 计数器)。
    ② 别把“他刚告诉我的”再告诉他 —— 靠记忆行的 source 认人。
    ③ 告诉他他自己家里有什么 = 废话。
    ④ 我自己家里的东西也不是新闻(没人跟邻居介绍自家马桶)。
    ⑤ 我自己都不太信的（believe < BELIEF_FLOOR）, 不值得传。
    ⑥ 话题冷却: 同一件事短时间内不复读 —— **对不同人也算**, NPC 不是复读机。
    """
    item_id = str(fact.get("item_id", ""))
    if not item_id:
        return False
    if other.remembers(item_id):                      # ①
        return False
    src = str(fact.get("source", ""))
    if src and src == other.person_id:                # ②
        return False
    located = str(fact.get("located", ""))
    if other.home and located == other.home:          # ③
        return False
    if npc.home and located == npc.home:              # ④
        return False
    if float(fact.get("believe", 1.0)) < BELIEF_FLOOR:  # ⑤
        return False
    topic = "item.%s" % item_id
    if world.clock_tick - npc.said_at(topic) < SAY_COOLDOWN:   # ⑥
        return False
    return True


def _item_name(world, item_id: str) -> str:
    e = world.entities.get(item_id)
    return e.name if e is not None else item_id


def _price_word(fact: Mapping[str, Any]) -> str:
    price = float(fact.get("price", 0.0))
    return _sem.money_word(price) if price > 0 else "有货"


def _set_bubble(systems, npc, text: str, kind: str, now_tick: int) -> None:
    """给某人头顶挂一句话(瞬时, 到点自己消失)。

    【只在我关注的地方冒泡】: bubble_watch = 观察集(选中的那个人 + 选中建筑
    里的人)。满城同时冒泡 = 没有信息。None = 不限(无头工具/测试)。
    """
    if not text:
        return
    watch = getattr(systems, "bubble_watch", None)
    if watch is not None and npc.person_id not in watch:
        return
    ttl = int(getattr(systems, "bubble_ttl", 40) or 40)
    npc.set_bubble(text, int(now_tick) + ttl, kind)


def _expiry(world, shelf_life: int) -> int:
    """新货的到期刻。0 = 不会坏。"""
    return (world.clock_tick + int(shelf_life)) if shelf_life > 0 else 0


def _deliver(world, pid: str, npc, shop, qty: int, home: str):
    """把 qty 件送进家中的同类容器(合并到 stock); 无则新建一个。

    "商店一种货物不要重叠" → 同类只保留一个实体, 数量记在 stock 上。

    保质期取【最早到期】(方案 A): 一格只要有一份旧了, 整格算旧。
    代价是略微低估保质期; 好处是不用给每份建档(实体数不膨胀)。
    """
    shelf = int(getattr(shop, "shelf_life_ticks", 0))
    for e in sorted(world.entities.values(), key=lambda x: x.entity_id):
        if (e.item_type == shop.item_type and e.location_id == home
                and e.owner == pid and e.stock != -1):
            e.stock += qty
            exp = _expiry(world, shelf)
            if exp and (e.expires_tick == 0 or exp < e.expires_tick):
                e.expires_tick = exp          # 合并取最早到期
            world.layout_location(home)
            return e
    d = load_item_defs().get(shop.item_type)
    if d is None:
        return None
    e = entity_from_def(d, home)
    e.owner = pid
    e.stock = qty
    # 不设 persist_empty: 食物是消耗品 —— 吃光/坏掉就该销毁
    # (货架那种“空着也要留着”的才在 itemdef 里写 persist_empty=true)
    # 以【实际卖出那件货】的保质期为准(shop 的 shelf_life 本就是从 itemdef 带入的),
    # 这样两分支口径一致; 也让测试/场景可以改单件货的保质期。
    e.shelf_life_ticks = shelf
    e.expires_tick = _expiry(world, shelf)
    world.spawn_entity(e)
    world.layout_location(home)
    return e


def _execute_buy(world, systems, cfg: SimConfig, pid: str, npc,
                 intent: Buy) -> None:
    """成交: 扣钱 + 减店铺库存 + 送货到家容器(合并库存, 不另生成多个实体)。"""
    shop = world.entities.get(intent.item_id)
    qty = max(1, int(getattr(intent, "qty", 1)))
    home = npc.home or world.loc_of(pid)
    why = ""
    if shop is None:
        why = "目标不存在"
    elif shop.location_id != world.loc_of(pid):
        why = "目标不在此地"
    elif shop.owner != "":
        why = "已被他人拥有"
    elif shop.price <= 0:
        why = "非卖品"
    elif shop.stock != -1 and shop.stock < qty:
        why = "库存不足"
    elif npc.money < shop.price * qty:
        # 理论上到不了: brain 已经按钱跳过了买不起的候选(这里只是兵库)。
        why = "钱不够"
    if why:
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid,
            {"target": intent.item_id, "why": why}))
        npc.on_failure(intent.item_id, why, world.clock_tick)
        return
    cost = shop.price * qty
    npc.pay(cost)
    if shop.stock != -1:
        shop.stock -= qty
    container = _deliver(world, pid, npc, shop, qty, home)
    world.bus.publish(world.bus.make(
        world.clock_tick, "bought", pid,
        {"item": shop.entity_id, "qty": qty, "price": cost,
         "home": home, "money": round(npc.money, 2),
         "container": container.entity_id if container else ""}))
    if container is not None:
        # 送货进家: 写记忆时**必须带 afford/value** —— 否则他不知道家里
        # 这堆东西能吃, 就永远不会回家吃(买了也饿死)。
        cafford, cvalue = next(iter(container.affordances.items()), ("", 0.0))
        npc.note(container.entity_id, tick=world.clock_tick,
                 located=home, owner=pid, stock=container.stock,
                 afford=cafford, value=float(cvalue),
                 believe=1.0,                      # 自己买回来的 = 亲眼所见
                 item_type=container.item_type, tags=container.tags, source="",
                 shelf_life_ticks=int(container.shelf_life_ticks),
                 expires_tick=int(container.expires_tick))
    npc.on_interaction_done(intent.item_id, world.clock_tick)



def _can_preempt(world, systems, pid, source) -> bool:
    """计划只能硬中止可打断的交互; 需求轨(need)始终可。"""
    if source == "need":
        return True
    act = systems.interaction.active.get(pid)
    if act is None:
        return True
    ent = world.entities.get(act.entity_id)
    return bool(ent is not None and ent.interruptible)


def _preempt(world, systems, pid, source) -> None:
    """抢占当前交互: need=软挂起(可恢复), plan=硬中止(触发 on_complete)。"""
    if source == "need":
        systems.interaction.suspend(world, pid)
    else:
        systems.interaction.abort(world, pid)


def _apply(world, systems, cfg, pid, npc, decision) -> None:
    """执行一条 Decision: 继续(同目标)/挂起/中止/提交。"""
    intent = decision.intent
    active = systems.interaction.active.get(pid)

    if isinstance(intent, MoveTo):
        dest = intent.dest or world.loc_of(pid)
        trv = systems.travel.get(pid)
        if trv is not None and trv.to_loc == dest:
            return                                   # 已在去往该地途中
        if active is not None:
            if not _can_preempt(world, systems, pid, decision.source):
                return
            _preempt(world, systems, pid, decision.source)
        here = world.loc_of(pid)
        if dest == here:
            return
        ok, why = world.entry_check(dest, pid)
        if not ok:                               # 无权/已满: 不出发, 记一次失败
            world.bus.publish(world.bus.make(
                world.clock_tick, "intent_failed", pid,
                {"target": dest, "why": why}))
            npc.on_failure(dest, why, world.clock_tick)
            return
        route = _route_between(world, systems, here, dest)
        if route is None:                        # 无路网 → 直线/固定耗时降级
            cost = _travel_cost(systems, cfg, here, dest)
            wps: tuple[tuple[float, float], ...] = ()
        else:
            cost = route.ticks
            wps = route.waypoints
        systems.travel[pid] = Travel(
            from_loc=here, to_loc=dest,
            depart_tick=world.clock_tick,
            arrive_tick=world.clock_tick + cost,
            waypoints=wps)
        return
    if isinstance(intent, Buy):
        if active is not None:
            if not _can_preempt(world, systems, pid, decision.source):
                return
            _preempt(world, systems, pid, decision.source)
        _execute_buy(world, systems, cfg, pid, npc, intent)
        return

    if isinstance(intent, Interact):
        tid = intent.target_id
        # 防御: 在售商品不能拿 Interact “白拿” —— 得走 Buy 付钱。
        # (模板计划器已不再挑它们; 但 ScriptedPlanner / LLM 计划可能写错。)
        ent = world.entities.get(tid)
        if ent is not None and ent.price > 0 and ent.owner != pid:
            why = "在售商品·需购买"
            world.bus.publish(world.bus.make(
                world.clock_tick, "intent_failed", pid,
                {"target": tid, "why": why}))
            npc.on_failure(tid, why, world.clock_tick)
            return
        if active is not None and active.entity_id == tid:
            return                                   # 继续当前交互
        if active is not None:
            if not _can_preempt(world, systems, pid, decision.source):
                return
            _preempt(world, systems, pid, decision.source)
        if systems.interaction.resume(world, npc, tid):
            return                                   # 恢复挂起进度
        systems.interaction.submit(world, npc, intent)
        return

    # Idle: 不主动释放(由 Person 决定何时结束); 仅空转


def tick(world, systems, cfg: SimConfig) -> None:
    """推进一个 tick 的世界演化(唯一执行入口)。世界进程在此, loop 只薄转发。"""
    world.clock_tick += 1

    # 0. 场景脉冲(世界脚本): 在 NPC 感知前改库存/停业
    if systems.pulses:
        apply_pulses(world, systems.pulses, world.clock_tick, cfg.ticks_per_day)

    # 0b. 过期变质: 到点的食物 stock 归 0(壳留着 —— 货架/容器可能 persist_empty)。
    #     只在【从有到无】的那一刻发一条事件, 不每 tick 刷。
    for eid in sorted(world.entities):
        e = world.entities[eid]
        if e.expires_tick and e.expires_tick <= world.clock_tick and e.stock != 0:
            e.stock = 0
            world.bus.publish(world.bus.make(
                world.clock_tick, "spoiled", eid,
                {"item_type": e.item_type, "loc": e.location_id}))
            # 【数量为 0 就销毁】: 除非它是货架/容器(persist_empty)
            if not e.persist_empty:
                world.entities.pop(eid, None)
                for other in world.npcs.values():
                    other.forget_item(eid)     # 别人脑子里的那行也清掉


    # 1. 心跳(身体演化收进 Person; 世界只广播, 不改 signals): 代谢+hp+排泄
    died: list[str] = []
    for pid, npc in world.npcs.items():
        alive = npc.heartbeat(world.clock_tick, cfg,
                              sleep=_sleeping(world, systems, pid),
                              busy=_busy(world, systems, pid))
        if not alive:
            died.append(pid)
    for pid in died:
        _kill(world, systems, pid)             # 死亡销毁 + 日志

    # 3. 交互推进(含睡眠唤醒提前完成)
    systems.interaction.step(world, cfg)

    # 5a. 旅行到期: 落到目标 region(世界进程, 先于重评)
    for pid in sorted(systems.travel):
        trv = systems.travel[pid]
        if world.clock_tick >= trv.arrive_tick:
            systems.travel.pop(pid)
            ok, why = world.entry_check(trv.to_loc, pid)   # 到达时再验(可能满)
            if ok:
                world.place_npc(pid, trv.to_loc)
            else:
                world.bus.publish(world.bus.make(
                    world.clock_tick, "entry_denied", pid,
                    {"loc": trv.to_loc, "why": why}))
                npc = world.npcs.get(pid)
                if npc is not None:
                    npc.on_failure(trv.to_loc, why, world.clock_tick)

    # 5a2. 招牌: 路过就"被 told"(被动感知源, 不是人与人的传播)
    _perceive_signs(world, systems)

    # 5b. 决策: 先对全部该决策者算 Decision(同一世界快照), 再统一仲裁执行
    #     仲裁 = 继续/挂起/中止/提交。
    due = due_npcs(world, systems)
    decisions: list[tuple[str, Any, Any]] = []
    for npc_id in due:
        npc = world.npcs.get(npc_id)
        if npc is None:
            continue
        active = systems.interaction.active.get(npc_id)
        can_preempt = True
        if active is not None:
            aent = world.entities.get(active.entity_id)
            can_preempt = bool(aent is not None and aent.interruptible)
        percept = build_percept(world, npc)
        decision = npc.process(percept, cfg, can_preempt)
        # 语义层: 攒下的“值得说的话”变成头顶气泡。
        # 放在 process 之后 —— 感知(预期 vs 观察)就在 process 里发生,
        # 同一 tick 冒出来才跟得上画面。【谁都可能冒】, 不看闲不闲。
        said = npc.pending_speech(world.clock_tick, SAY_COOLDOWN)
        if said is not None:
            _set_bubble(systems, npc,
                        _sem.render(said, speaker_name=npc.name), said.act,
                        world.clock_tick)
        intent = decision.intent
        kind = intent_kind(intent)
        target = intent_target(intent)
        if isinstance(intent, Idle):
            _notify_due(world, systems, npc, said)   # 空闲才把这话说给别人听
        # 观测去重: 只在【任务变更】时记一条; 持续同一任务/空闲不刷屏。
        # 签名始终更新(含 idle), 否则"吃→空闲→再吃同一个"会被吞掉。
        sig = f"{decision.source}:{kind}:{target or ''}"
        if sig != systems.last_decision.get(npc_id):
            systems.last_decision[npc_id] = sig
            if kind != "idle" and systems.log_lines is not None:
                systems.log_lines.append(
                    f"D\t{world.clock_tick}\t{npc_id}\t{kind}\t{target or ''}")
                systems.ui_events.append({
                    "event_id": f"dec:{world.clock_tick}:{npc_id}",
                    "tick": world.clock_tick, "kind": "decision",
                    "subject": npc_id, "intent": kind,
                    "target": target or "", "source": decision.source,
                    "payload": {},
                })
        decisions.append((npc_id, npc, decision))

    for npc_id, npc, decision in decisions:
        _apply(world, systems, cfg, npc_id, npc, decision)

    # 5.5 遗忘(0 点) + 夜间计划(LLM/规则模板生成次日计划)
    if world.clock_tick % cfg.ticks_per_day == 0:
        for npc in world.npcs.values():
            npc.on_day(cfg, world.clock_tick)
        planner = getattr(systems, "planner", None)
        if planner is not None:
            for npc in world.npcs.values():
                res = planner.plan_for_person(npc, world.clock_tick)
                npc.set_plan(res.entries)
