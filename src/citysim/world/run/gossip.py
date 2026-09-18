"""world/run/gossip —— 传闻: 搭话/信任/气泡

一轮传播是【一对一】的: 说的人和听的人各用掉本轮名额, 说过的这轮
不再听、听过的这轮不再说。信任只分两档(同屋高 / 路人低), 由
person_id 对的稳定哈希决定(不用内置 hash(), 回放才不飘)。
"""
from __future__ import annotations

import zlib
from citysim.npc import semantic as _sem
from typing import Any, Mapping


BELIEF_FLOOR = 0.3      # 低于此就不值得再传了
SAY_COOLDOWN = 240      # 同一话题这么 tick 内不重复说(4 小时)
TRUST_OTHER = (0.4, 0.7)
TRUST_SAME_HOME = (0.9, 1.0)



def trust_between(a, b) -> float:
    """a 有多信 b 说的话(0..1)。同址(同一个 home) → 高信任档。"""
    same = bool(a.home) and a.home == b.home
    lo, hi = TRUST_SAME_HOME if same else TRUST_OTHER
    k = a.person_id if a.person_id < b.person_id else b.person_id
    j = b.person_id if a.person_id < b.person_id else a.person_id
    return lo + (hi - lo) * _unit_hash("%s|%s" % (k, j))



# --- 传播(传闻) -----------------------------------------------------------
#
# 规则:
#   - 信任只有两档: 同址(同一个 home) 0.9~1.0; 否则 0.4~0.7
#   - 按 (a,b) **确定性派生** —— 每对人一个固定值, 零存储、可回放
#   - 传出去的 believe = 说话人自己信的程度 × 对听者的信任
#   - “对方已知就不说” → 消息播完自己就停, 不会全城皆知
#
# 注意: 这里**不做** trust 的演化(那是后续插件的事)。

BELIEF_FLOOR = 0.3      # 低于此就不值得再传了
SAY_COOLDOWN = 240      # 同一话题这么 tick 内不重复说(4 小时)
TRUST_SAME_HOME = (0.9, 1.0)
TRUST_OTHER = (0.4, 0.7)


def _unit_hash(key: str) -> float:
    """把字符串稳定地映到 [0,1)。**不用内置 hash()** —— 它每进程随机化, 回放会飘。"""
    return (zlib.crc32(key.encode("utf-8")) % 10_000) / 10_000.0



def _notify_due(world, systems, npc, ev, cfg) -> None:
    """这一轮张嘴: 把【刚才那句值得说的话】说给【一个】同地的人听。

    —— 2026-09-15: 改成【一对一搭桥】+【跟谁说得看关系】——
    旧版是"一对多": 一个人张嘴就能同时告诉身边所有人。
    现在三道骰子, 都过才成一条桥:
      ① 我这一轮想不想开口      tell_p × tell_bias
      ② 愿不愿意【跟这个人】说  同屋 tell_same_home / 路人 tell_stranger
      ③ 对方愿不愿意停下来听     listen_p
    而且【只搭一条桥】: 说的人这轮不再听、听的人这轮不再说(说的不听/听的不说),
    一个场地里只有"在说的"和"在听的"才配对。

    说什么由语义层决定(见 : `ev` 是 Person
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
               # ★ tags 必须一起传: "囤货"判据要 consumable —— 没有 tags 的行
               #   永远买不了(实测: 只"听说"过店里苹果的人全饿死了)
               tags=tuple(fact.get("tags", ()) or ()),
               stock=int(fact.get("stock", -1)),
               shelf_life_ticks=int(fact.get("shelf_life_ticks", 0)),
               believe=float(fact.get("believe", 1.0)) * trust,
               source=npc.person_id)
    item_name = str(fact.get("item", _item_name(world, item_id)))
    now = str(fact.get("now", _price_word(fact)))
    # 听者头顶: “王伟说：简餐8块”（看得见是谁跟他说的）
    rep = _sem.report(tick, npc.person_id, item_id, item_name, now, who=npc.name)
    _set_bubble(systems, other,
                _sem.render(rep, speaker_name=npc.name,
                            ticks_per_day=cfg.ticks_per_day),
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
