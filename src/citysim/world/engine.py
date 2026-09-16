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
from citysim.world.port import WorldPortImpl
from citysim.world.world import entity_from_def


# 移动耗时 / 路线 / 抢占 的共享 helper 已搬到 world/port.py(WP-02)。


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






COUNTER_ITEM = "station_counter"   # 销售前台: 1 个 = 1 个销售位
QUEUE_GIVEUP = 180                # 排队等超过这么久就放弃(3 小时; 白跑一次要记住)


def _counters(world, shop_id: str) -> list:
    """这家店的销售前台(实体) —— 每个前台 = 1 个店员 + 每 tick 最多成交 1 份。"""
    return [e for e in sorted(world.entities.values(), key=lambda x: x.entity_id)
            if e.item_type == COUNTER_ITEM and e.location_id == shop_id]


def _is_open(world, cfg: SimConfig, shop_id: str) -> bool:
    """营业中吗? 找这家店所属公司的营业时间(店铺自己不受 open_to 管)。"""
    cid = str((world.locations.get(shop_id) or {}).get("company", ""))
    comp = world.companies.get(cid)
    if comp is None:
        return True                       # 没公司 → 由"不能卖"那条拦, 不在这里管
    minute = world.clock_tick % max(1, cfg.ticks_per_day)
    return int(comp.open_minute) <= minute < int(comp.close_minute)


def enqueue_buy(world, systems, pid: str, shop_id: str, item_id: str,
                qty: int) -> None:
    """顾客到店 → 排队(不立刻成交)。一个前台只服务队首; 两条前台=两条队。"""
    if systems.queued.get(pid) == shop_id:
        return
    systems.shop_queue.setdefault(shop_id, []).append(pid)
    systems.queued[pid] = shop_id
    systems.buy_left[pid] = (item_id, max(1, int(qty)))
    systems.queued_since[pid] = world.clock_tick
    npc = world.npcs.get(pid)
    if npc is not None:
        npc.set_activity("queue")


def _leave_queue(world, systems, pid: str, why: str = "") -> None:
    shop_id = systems.queued.pop(pid, "")
    systems.buy_left.pop(pid, None)
    systems.queued_since.pop(pid, None)
    if shop_id:
        q = systems.shop_queue.get(shop_id) or []
        if pid in q:
            q.remove(pid)
        if not q:
            systems.shop_queue.pop(shop_id, None)
    npc = world.npcs.get(pid)
    if npc is not None:
        npc.set_activity("idle")
    if why:
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid, {"target": shop_id, "why": why}))
        if npc is not None:
            npc.on_failure(shop_id, why, world.clock_tick)


def _active_at(world, systems, counter_id: str) -> str:
    """这个前台此刻是谁在守着? 没有 → ""。"""
    for pid, act in systems.interaction.active.items():
        if act is not None and act.entity_id == counter_id:
            return pid
    return ""


def staffed_counters(world, systems, shop_id: str) -> list:
    """【有员工在岗】的前台 —— 这才算产能。

    ★ 用户定的闸门: 员工站在销售台, 交易才能进行。
      半个员工的都没有 → 一台也开不了 → 顾客只能排队(等不住就走, 好感掉)。
    """
    out = []
    for c in _counters(world, shop_id):
        pid = _active_at(world, systems, c.entity_id)
        if not pid:
            continue
        npc = world.npcs.get(pid)
        if npc is None:
            continue
        w = npc.work
        if w.get("station") == c.entity_id:      # 守的是自己该守的台
            out.append((c, pid))
    return out


def _serve_shops(world, systems, cfg: SimConfig) -> None:
    """每 tick 让每个店服务队首: 一个【有人的】前台最多成交 1 份。

    没开门 / 没前台 / 前台没人站着 → 服务不了 → 顾客继续等(等不住就走,
    记一次白跑: 好感掉一截)。这就是"员工在销售台交易才能进行"的落地处。
    """
    # 在岗计时(工资按在岗时间算): 有员工站在台上 → 他这一 tick 算上班
    for shop_id in sorted(world.locations):
        for _c, pid in staffed_counters(world, systems, shop_id):
            npc = world.npcs.get(pid)
            if npc is not None:
                npc.worked(1)
    for shop_id in sorted(systems.shop_queue):
        queue = list(systems.shop_queue.get(shop_id) or [])
        if not queue:
            continue
        seats = len(staffed_counters(world, systems, shop_id))
        open_now = _is_open(world, cfg, shop_id)
        served = 0
        for pid in queue:
            npc = world.npcs.get(pid)
            if npc is None:
                _leave_queue(world, systems, pid)
                continue
            waited = systems.queued_since.get(pid, world.clock_tick)
            if world.clock_tick - waited > QUEUE_GIVEUP:
                # 白跑一趟要记住: 好感掉一截(慢变量, 会慢慢回到中性)。
                # 这是"惩罚 = 状态调制产出"的同一套 —— 不改行为, 只改印象。
                shop_id_q = systems.queued.get(pid, "")
                _leave_queue(world, systems, pid,
                             "没人招待" if (not open_now or seats <= 0) else "排队太久")
                npc.bump_favor(shop_id_q, -cfg.favor_no_service_down, cfg)
                continue
            if not open_now or seats <= 0:
                continue                     # 服务不了: 继续等(等不住会走)
            if served >= seats:
                break                        # 前台用满了 → 后面的人排着
            item_id, left = systems.buy_left.get(pid, ("", 0))
            shop = world.entities.get(item_id)
            if shop is None:
                _leave_queue(world, systems, pid, "目标不存在")
                continue
            seats_ok = _serve_one(world, systems, cfg, pid, npc, shop)
            if seats_ok:
                served += 1
                _, left = systems.buy_left.get(pid, (item_id, 0))
                if left <= 1:
                    _leave_queue(world, systems, pid)
                else:
                    systems.buy_left[pid] = (item_id, left - 1)


def _serve_one(world, systems, cfg: SimConfig, pid: str, npc, shop) -> bool:
    """柜台成交 1 份(钱/货/记忆/好感都走这一处)。"""
    if shop.stock == 0:
        _leave_queue(world, systems, pid, "卖光了")
        return False
    one = Buy(item_id=shop.entity_id, qty=1)
    before = npc.money
    _execute_buy(world, systems, cfg, pid, npc, one, from_counter=True)
    if npc.money < before:                   # 真成交了 → 好感 +一点
        npc.bump_favor(shop.location_id, cfg.favor_trade_up, cfg)
        return True
    return False


def _is_registered_shop(world, shop) -> bool:
    """这家店登记过公司吗? 没登记 → 不许卖(用户定的开零售前提)。"""
    cid = str((world.locations.get(str(shop.location_id)) or {}).get("company", ""))
    return bool(cid) and cid in world.companies


def _restock_if_open(world, systems, cfg: SimConfig) -> None:
    """每天开门那一刻, 各公司补一次货(只补货架, 不动任何 NPC)。"""
    from citysim.world.market import restock_all
    minute = world.clock_tick % max(1, cfg.ticks_per_day)
    day = world.clock_tick // max(1, cfg.ticks_per_day)
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        if int(comp.open_minute) != minute:
            continue
        if systems.last_restock_day == day:
            continue                       # 同一开门时刻只补一次
        systems.last_restock_day = day
        restock_all(world)


def _company_of_shop(world, shop):
    """这家店归哪个公司? 先看实体, 再看它所在的建筑(含楼层单元的父建筑)。"""
    cid = str(getattr(shop, "owner", "")) or ""
    loc = str(getattr(shop, "location_id", ""))
    for lid in (loc, (world.locations.get(loc) or {}).get("part_of", "")):
        if not lid:
            continue
        c = str((world.locations.get(str(lid)) or {}).get("company", ""))
        if c:
            cid = c
            break
    return world.companies.get(cid) if cid else None


def _credit_shop(world, shop, amount: float):
    """把一笔货款记到店铺所属公司的账上。返回 Company 或 None。"""
    comp = _company_of_shop(world, shop)
    if comp is None or amount <= 0:
        return None
    comp.cash += float(amount)
    return comp


def pay_wages(world, cfg: SimConfig) -> None:
    """公司给店员发工资(每天一次, 由 tick 在 wage_minute 那一刻调)。

    钱从公司账上出 → 员工个人进账。**发不出就是发不出**(没有"欠薪"概念):
    公司现金不足 → 发事件 wage_failed, 那个人这天没收入(→ 会穷 → 会饿)。
    这是"惩罚 = 状态调制产出"的同一套: 不搞门禁, 让钱自己说话。
    """
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        for npc_id, wage in comp.staff:
            npc = world.npcs.get(npc_id)
            if npc is None:
                continue
            # ★ 一天结一次, 按【在岗时间】算: 出勤多少小时就领多少小时的钱。
            #   没到岗 = 没收入(不搞欠薪/扣款 —— 惩罚就是"少拿钱", 见 R2)。
            hours = npc.reset_worked() / 60.0
            due = round(hours * float(wage), 2)
            if due <= 0.0:
                continue                        # 一天没上班 → 不发也不记
            if comp.cash < due:
                world.bus.publish(world.bus.make(
                    world.clock_tick, "wage_failed", npc_id,
                    {"audience": [npc_id], "company": cid,
                     "wage": due, "hours": round(hours, 2),
                     "cash": round(comp.cash, 2)}))
                continue
            comp.cash -= due
            npc.earn(due)
            world.bus.publish(world.bus.make(
                world.clock_tick, "wage_paid", npc_id,
                {"audience": [npc_id], "company": cid, "wage": due,
                 "hours": round(hours, 2),
                 "cash": round(comp.cash, 2), "money": round(npc.money, 2)}))


def vacant_counters(world, company) -> list:
    """公司旗下【空着的】前台(没有任何员工绑定它)。= 岗位数。"""
    taken = {str(n) for n, _w in company.staff}
    out = []
    for shop_id in company.shops:
        for c in _counters(world, shop_id):
            if not any(world.npcs.get(pid) is not None
                       and world.npcs[pid].work.get("station") == c.entity_id
                       for pid in taken):
                out.append((shop_id, c))
    return out


def _willing(world, pid: str) -> float:
    """应聘意愿: 没角色的都愿意(1.0); 已经有工作/角色的 = 0(不跳槽)。"""
    npc = world.npcs.get(pid)
    if npc is None:
        return 0.0
    if npc.work or npc.role:
        return 0.0
    return 1.0


def hire_at(world, systems, cfg: SimConfig) -> list[dict]:
    """每天一次的招聘桥接 —— 外面架构只是【媒婆】。

    ★ 用户定的规矩(这一版按它改):
      · **招不招人是公司说了算**: 只有【发布了招聘启事】的公司才参与撮合;
        有空工位 ≠ 要招人。启事上写着这次招几个、时薪多少。
      · **NPC 有意愿**才可能被匹配: 没角色的人意愿 = 1.0(已有工作的 = 0)。
      · 媒婆只做撮合: 名额、时薪都由公司给, 这边一个都不自己加。

    匹配规则先按【随机】(架构留好: 以后换成熟练度/距离/工资竞争力都在这一个
    函数里)。被招到: 写角色 + 绑定销售台 + 记进公司员工 + 写一份上班计划表
    (daily: 每天重复 → 只在应聘/离职那天改一次)。
    """
    hired: list[dict] = []
    rng = getattr(systems, "rng", None)
    if rng is None:
        return hired
    willing = [pid for pid in sorted(world.npcs) if _willing(world, pid) > 0.0]
    if not willing:
        return hired
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        if not comp.hiring_open or comp.hiring_slots <= 0:
            continue                          # 没发布招聘 → 一个人也不招
        vac = vacant_counters(world, comp)
        if not vac:
            continue
        staff = list(comp.staff)
        quota = min(int(comp.hiring_slots), len(vac))
        got = 0
        for shop_id, counter in vac[:quota]:
            if not willing:
                break
            pick = willing.pop(rng.randrange(len(willing)))     # ← 随机匹配
            npc = world.npcs[pick]
            npc.set_work(cid, shop_id, counter.entity_id,
                         comp.open_minute, comp.close_minute)
            npc.set_role("worker")
            staff.append((pick, float(comp.wage_per_hour)))
            _write_work_plan(world, cfg, npc, comp, shop_id, counter.entity_id)
            got += 1
            hired.append({"company": cid, "npc": pick, "shop": shop_id,
                          "station": counter.entity_id})
            world.bus.publish(world.bus.make(
                world.clock_tick, "hired", pick,
                {"audience": [pick], "company": cid, "shop": shop_id,
                 "station": counter.entity_id,
                 "wage_per_hour": float(comp.wage_per_hour)}))
        comp.staff = tuple(staff)
        comp.hiring_slots = max(0, int(comp.hiring_slots) - got)   # 招到几个扣几个
        if comp.hiring_slots <= 0 or not vacant_counters(world, comp):
            comp.hiring_open = False           # 招满 / 没空位 → 启事自动撤下
    return hired


def _write_work_plan(world, cfg: SimConfig, npc, comp, shop_id: str,
                     station_id: str) -> None:
    """上班计划表(只在应聘/离职时写一次):

        <开门时刻> 去公司  →  <开门时刻> 守台
    两条都是 daily(每天重复) → 跨天由 Schedule.roll_day 自动顺延,
    所以"其他时候都保持不动"。

    守台就是一次普通 Interact(可被打断): 饿了/憋了会被需求顶掉 →
    正是用户要的"很想上厕所或者饿了才从工作下来"。
    """
    from citysim.npc.schedule import PlanEntry
    at = int(comp.open_minute)          # 计划表内部用绝对 tick, roll_day 会顺延
    npc.set_plan([
        PlanEntry("work_go", at, MoveTo(dest=shop_id), daily=True),
        PlanEntry("work_stand", at, Interact(target_id=station_id), daily=True),
    ])


def assign_station(world, systems, cfg: SimConfig, company,
                   npc_id: str, station_id: str) -> dict:
    """把员工【分派到】某个销售台(或 station_id="" 撤销分配)。

    用户要的: 招来的人得能手动指定站哪个台, 否则可能没位置(或分错台)。
    只改世界真值(work 绑定 + 上班计划表), 不做任何模拟计算。
    返回 {"ok", "why", "npc", "station"(, "shop")}。
    """
    npc = world.npcs.get(npc_id)
    if npc is None:
        return {"ok": False, "why": "没有这个人", "npc": npc_id, "station": ""}
    if npc_id not in [n for n, _w in company.staff]:
        return {"ok": False, "why": "不是这家公司的员工",
                "npc": npc_id, "station": ""}
    if station_id == "":
        npc.clear_work()
        return {"ok": True, "why": "", "npc": npc_id, "station": ""}
    shop_id = ""
    for sid in company.shops:
        for c in _counters(world, sid):
            if c.entity_id == station_id:
                shop_id = sid
                break
        if shop_id:
            break
    if not shop_id:
        return {"ok": False, "why": "这个台不是公司的",
                "npc": npc_id, "station": ""}
    for other in world.npcs.values():
        if other.person_id == npc_id:
            continue
        if other.work.get("station") == station_id:
            return {"ok": False, "why": "这个台已经有别人在守",
                    "npc": npc_id, "station": ""}
    npc.set_work(company.company_id, shop_id, station_id,
                 company.open_minute, company.close_minute)
    _write_work_plan(world, cfg, npc, company, shop_id, station_id)
    return {"ok": True, "why": "", "npc": npc_id, "station": station_id,
            "shop": shop_id}


def _hire_due(world, cfg: SimConfig, last_tick: int) -> bool:
    """到点了吗(每天 hire_minute 一次)。"""
    day, minute = divmod(world.clock_tick, max(1, cfg.ticks_per_day))
    if minute != int(cfg.hire_minute):
        return False
    return last_tick < day * cfg.ticks_per_day + cfg.hire_minute


def _wage_due(world, cfg: SimConfig, last_tick: int) -> bool:
    """挂工资那一刻: 恰好跨过当天的 wage_minute。用 tick 判, 不存状态。"""
    day, minute = divmod(world.clock_tick, max(1, cfg.ticks_per_day))
    if minute != int(cfg.wage_minute):
        return False
    # 同一 tick 只发一次(引擎每 tick 只调一次, 这里再兜一层: 当天未发过)
    return last_tick < day * cfg.ticks_per_day + cfg.wage_minute


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
                 intent: Buy, from_counter: bool = False) -> None:
    """成交: 扣钱 + 减店铺库存 + 送货到家容器(合并库存, 不另生成多个实体)。

    from_counter=True 表示这是【柜台服务出来的那 1 份】(由 _serve_shops 调)。
    普通路径(_apply)现在【不再直接成交】→ 先排队, 见 enqueue_buy。
    """
    shop = world.entities.get(intent.item_id)
    qty = max(1, int(getattr(intent, "qty", 1)))
    home = npc.home or world.loc_of(pid)
    why = ""
    if shop is None:
        why = "目标不存在"
    elif shop.location_id != world.loc_of(pid):
        why = "目标不在此地"
    elif shop.owner and str(shop.owner) not in world.companies:
        # 只拦“别人的个人物品”; 归【公司】的货是可以卖的(顾客买 = 零售)。
        why = "已被他人拥有"
    elif shop.price <= 0:
        why = "非卖品"
    elif not _is_registered_shop(world, shop):
        # 用户拍板: 【没有注册公司的店不能卖】。店铺建筑没挂公司 →
        # 它的货架不生效(既不合规, 也给编辑器一个能看见的错误)。
        why = "这家店没有登记公司"
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
    # ★ 定死三条规则: 免费自用的东西(住所授权 / 公共无主 / 本公司店员)
    #   一律不扣钱 —— 即使有人写了 Buy 意图, 引擎也不收钱。
    free = world.free_use(shop, pid)
    cost = 0.0 if free else shop.price * qty
    if cost:
        npc.pay(cost)
    # ★ 双分录: 买家付的钱进【店铺所属公司】的账。
    #   以前这钱凭空消失 → 城里只有支出没有收入, 所有人慢慢破产饿死。
    #   没登记公司的店 → 仍然"钱消失"(旧行为; 让店主=公司是下一步的事)。
    comp = _credit_shop(world, shop, cost) if cost else None
    if shop.stock != -1:
        shop.stock -= qty
    container = _deliver(world, pid, npc, shop, qty, home)
    # WP-13: 送货信息随 `bought` 事件交回 NPC —— 由 NPC 自己写记忆,
    # world 不再反写 NPC。(afford/value 必须带上: 否则他不知道家里这堆能吃。)
    cafford, cvalue = (next(iter(container.affordances.items()), ("", 0.0))
                       if container is not None else ("", 0.0))
    world.bus.publish(world.bus.make(
        world.clock_tick, "bought", pid,
        {"item": shop.entity_id, "qty": qty, "price": cost,
         "home": home, "money": round(npc.money, 2),
         "company": comp.company_id if comp else "",
         "container": container.entity_id if container else "",
         "afford": cafford, "value": float(cvalue),
         "stock": int(container.stock) if container is not None else 0,
         "item_type": container.item_type if container is not None else "",
         "tags": list(container.tags) if container is not None else [],
         "shelf_life_ticks": int(container.shelf_life_ticks) if container else 0,
         "expires_tick": int(container.expires_tick) if container else 0}))
    npc.on_interaction_done(intent.item_id, world.clock_tick)



def tick(world, systems, cfg: SimConfig) -> None:
    """推进一个 tick 的世界演化(唯一执行入口)。世界进程在此, loop 只薄转发。"""
    world.clock_tick += 1

    # 0. 场景脉冲(世界脚本): 在 NPC 感知前改库存/停业
    if systems.pulses:
        apply_pulses(world, systems.pulses, world.clock_tick, cfg.ticks_per_day)

    # 0a0. 开门前补货: 公司用现钱向市场进货, 把货架补到目标(见 market.restock_all)
    _restock_if_open(world, systems, cfg)

    # 0a-1. 招聘桥接(每天 hire_minute 一次): 空前台 ← 无角色的人(随机匹配)
    if _hire_due(world, cfg, systems.last_hire_tick):
        hire_at(world, systems, cfg)
        systems.last_hire_tick = world.clock_tick

    # 0a. 发工资(每天 wage_minute 那一刻): 公司的账 → 员工个人。
    #     放在最前面: 与任何人的决策无关, 只是世界的收付节奏。
    if _wage_due(world, cfg, systems.last_wage_tick):
        pay_wages(world, cfg)
        systems.last_wage_tick = world.clock_tick

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


    # 5a3. 柜台服务: 每个店按前台数服务队首(每 tick 每个前台成交 1 份)
    _serve_shops(world, systems, cfg)

    # 5b. 决策: NPC 主动拉(WP-05/06; WP-00 选 B: 顺序执行, due 已排序 → 确定性仍在)。
    #     每人一轮: observe → decide → try_*(端口立即落账, 失败自己处理)。
    port = WorldPortImpl(world, systems, cfg)
    due = due_npcs(world, systems)
    for npc_id in due:
        npc = world.npcs.get(npc_id)
        if npc is None:
            continue
        active = systems.interaction.active.get(npc_id)
        can_preempt = True
        if active is not None:
            aent = world.entities.get(active.entity_id)
            can_preempt = bool(aent is not None and aent.interruptible)
        decision = npc.step(port, cfg, can_preempt)
        # 语义层: 攒下的“值得说的话”变成头顶气泡。
        # 放在 step 之后 —— 感知(预期 vs 观察)就在 step 里发生,
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

    # 5.5 遗忘(0 点) + 夜间计划(LLM/规则模板生成次日计划)
    if world.clock_tick % cfg.ticks_per_day == 0:
        for npc in world.npcs.values():
            npc.on_day(cfg, world.clock_tick)
        planner = getattr(systems, "planner", None)
        if planner is not None:
            for npc in world.npcs.values():
                res = planner.plan_for_person(npc, world.clock_tick)
                npc.set_plan(res.entries)
