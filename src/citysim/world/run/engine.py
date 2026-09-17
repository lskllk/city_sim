"""world/run/engine —— 世界执行器: 主循环 tick() + 观察/死亡

tick() 是【主循环】: 12 个步骤的编排(补货/招聘/工资/过期 → 心跳 → 交互 →
旅行/闲逛 → 柜台 → 决策 → 遗忘/计划 → 记时间线)。
其余四步(shop/economy/company/gossip)都是它按顺序调用的。

按 World↔Person 契约: 上帝(World 侧)执行'世界进程'并广播心跳,
只发事件、不写 Person。systems 为执行环境(duck: interaction/travel/
日志), 由上层构造传入; 本层不 import sim(避免 world→sim 反向依赖)。
"""
from __future__ import annotations

from citysim.npc import semantic as _sem
from citysim.core.config import SimConfig
from citysim.core.types import Idle, InteractionFailed, ItemGone, Plan, intent_kind, intent_target
from citysim.world.run.drive import due_npcs
from citysim.world.edge.port import WorldPortImpl

from citysim.world.econ.company import (_hire_due, _wage_due, hire_at, pay_wages)
from citysim.world.econ.economy import _restock_if_open
from citysim.world.run.gossip import SAY_COOLDOWN, _notify_due, _set_bubble
from citysim.world.econ.shop import _serve_shops

def tick(world, systems, cfg: SimConfig) -> None:
    """推进一个 tick 的世界演化(唯一执行入口)。世界进程在此, loop 只薄转发。"""
    world.clock_tick += 1

    # 0. 开门前补货: 公司用现钱向市场进货, 把货架补到目标(见 market.restock_all)
    _restock_if_open(world, systems, cfg)

    # 1. 招聘桥接(每天 hire_minute 一次): 空前台 ← 无角色的人(随机匹配)
    if _hire_due(world, cfg, systems.last_hire_tick):
        hire_at(world, systems, cfg)
        systems.last_hire_tick = world.clock_tick

    # 2. 发工资(每天 wage_minute 那一刻): 公司的账 → 员工个人。
    #     放在最前面: 与任何人的决策无关, 只是世界的收付节奏。
    if _wage_due(world, cfg, systems.last_wage_tick):
        pay_wages(world, cfg)
        systems.last_wage_tick = world.clock_tick

    # 3. 过期变质: 到点的食物 stock 归 0(壳留着 —— 货架/容器可能 persist_empty)。
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
                    other.notify(ItemGone(eid))     # 别人脑子里的那行也清掉


    # 4. 心跳(身体演化收进 Person; 世界只广播, 不改 signals): 代谢+hp+排泄
    died: list[str] = []
    for pid, npc in world.npcs.items():
        alive = npc.heartbeat(world.clock_tick, cfg,
                              busy=_busy(world, systems, pid))
        if not alive:
            died.append(pid)
    for pid in died:
        _kill(world, systems, pid)             # 死亡销毁 + 日志

    # 5. 交互推进(含睡眠唤醒提前完成)
    systems.interaction.step(world, cfg)

    # 6. 旅行到期: 落到目标 region(世界进程, 先于重评)
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
                    npc.notify(InteractionFailed(trv.to_loc, why, world.clock_tick))

    # 7. 闲逛到期 / 人已离开那个地方(world 侧会话; fun 由 NPC 自己消化)
    for pid in [p for p, r in systems.roaming.items()
                if r.until <= world.clock_tick or world.loc_of(p) != r.dest]:
        systems.roaming.pop(pid, None)

    # 8. 柜台服务: 每个店按前台数服务队首(每 tick 每个前台成交 1 份)
    _serve_shops(world, systems, cfg)

    # 9. 决策: NPC 主动拉(顺序执行; due 已排序 → 确定性仍在)。
    #     每人一轮: observe → decide → try_*(端口立即落账, 失败自己处理)。
    port = WorldPortImpl(world, systems, cfg)
    due = due_npcs(world, systems)
    for npc_id in due:
        npc = world.npcs.get(npc_id)
        if npc is None:
            continue
        decision = npc.step(port, cfg)
        # 语义层: 攒下的“值得说的话”变成头顶气泡。
        # 放在 step 之后 —— 感知(预期 vs 观察)就在 step 里发生,
        # 同一 tick 冒出来才跟得上画面。【谁都可能冒】, 不看闲不闲。
        said = npc.pending_speech(world.clock_tick, SAY_COOLDOWN)
        if said is not None:
            _set_bubble(systems, npc,
                        _sem.render(said, speaker_name=npc.name,
                                    ticks_per_day=cfg.ticks_per_day),
                        said.act,
                        world.clock_tick)
        intent = decision.intent
        kind = intent_kind(intent)
        target = intent_target(intent)
        if isinstance(intent, Idle):
            _notify_due(world, systems, npc, said,
                        cfg)   # 空闲才把这话说给别人听
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

    # 10. 遗忘(0 点) + 夜间计划(装了 planner 才生成次日计划; 否则纯 utility)
    if world.clock_tick % cfg.ticks_per_day == 0:
        for npc in world.npcs.values():
            npc.on_day(cfg, world.clock_tick)
        planner = getattr(systems, "planner", None)
        if planner is not None:
            for npc in world.npcs.values():
                npc.assign(Plan(planner.plan_for_person(
                    npc, world.clock_tick)))

    # 11. 行为段记录(时间线 viz; 纯观测)
    _record_activity(world, systems, cfg)


def _busy(world, systems, pid: str) -> bool:
    """忙碌 = 有进行中交互 或 正在跨地点移动 或 正在闲逛。"""
    return (systems.interaction.active.get(pid) is not None
            or pid in systems.travel
            or pid in systems.roaming)



def act_class_of(world, systems, pid: str) -> str:
    """这个 NPC 此刻在【做什么】(行为大类): move/eat/sleep/toilet/work/wander/idle。

    ★ 已经不需要"world 猜"了 —— 大类由 NPC 自己从它的 _intake/_moving/_queued
      推出来(`Person.activity()`)。这里只做一层转发, 让快照/时间线/工具少改。
    """
    npc = world.npcs.get(pid)
    return npc.activity_class if npc is not None else "idle"



def _record_activity(world, systems, cfg: SimConfig) -> None:
    """给每个 NPC 记一份【当天实际行为段】(时间线 viz 用; 只保留今天)。

    段 = {from, to, cls, text}; cls 变化就开新段。纯观测, 不改模拟。
    """
    tick = world.clock_tick
    day_start = (tick // max(1, cfg.ticks_per_day)) * cfg.ticks_per_day
    log = systems.activity_log
    for pid, npc in world.npcs.items():
        cls, text = npc.activity()
        segs = log.setdefault(pid, [])
        if segs and segs[-1]["cls"] == cls and segs[-1]["text"] == text:
            segs[-1]["to"] = tick                       # 同段延续
        else:
            if segs:
                segs[-1]["to"] = tick
            segs.append({"from": tick, "to": tick, "cls": cls, "text": text})
        while len(segs) > 1 and segs[0]["to"] < day_start:
            segs.pop(0)                                 # 剪掉今天之前的
    for pid in [p for p in log if p not in world.npcs]:
        log.pop(pid, None)



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
