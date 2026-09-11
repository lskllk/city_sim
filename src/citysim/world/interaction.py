"""InteractionSystem —— 执行 Intent + claim 仲裁 + 分 tick 效果推进。

世界侧唯一执行器: 校验 → claim → 登记 ActiveInteraction; 每 tick 分摊
affordances; 完成时处理 消耗品/如厕。事件经 EventBus 发布给 NPC 信箱。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from citysim.core.config import SIGNALS
from citysim.core.types import Idle, Interact
from citysim.npc.person import Person
from citysim.world.effects import apply_effects
from citysim.world.world import Entity, World


@dataclass
class ActiveInteraction:
    npc_id: str
    entity_id: str
    remaining_ticks: int
    total_ticks: int


@dataclass
class Suspension:
    """软挂起的交互进度(被 reflex 抢占时暂存, 供 resume 恢复)。"""
    entity_id: str
    remaining_ticks: int
    total_ticks: int


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class InteractionSystem:
    """一次持有多名 NPC 的进行中交互; 每 tick step 推进。"""

    def __init__(self) -> None:
        self.active: dict[str, ActiveInteraction] = {}   # key = npc_id
        self.suspended: dict[str, Suspension] = {}        # key = npc_id(软挂起进度)

    # --- 提交 ---------------------------------------------------------
    def submit(self, world: World, npc: Person, intent) -> bool:
        """校验→claim→登记。失败发 intent_failed 事件。返回是否成功登记。"""
        pid = npc.person_id
        if isinstance(intent, Idle):
            if pid in self.active:
                self._release(world, pid, cancel=True)
            return True
        if not isinstance(intent, Interact):
            return False

        tid = intent.target_id
        ent = world.entities.get(tid) if tid else None

        # rule 2: 目标不存在 / 空 / 被他人占用 → 失败
        if ent is None:
            self._fail(world, pid, tid or "?", "目标不存在")
            return False
        if ent.stock == 0:
            self._fail(world, pid, tid, "已空(stock=0)")
            return False
        if ent.claimed_by not in (None, pid):
            self._fail(world, pid, tid, "已被他人占用")
            return False
        # 现实约束: 目标必须与 NPC 同 region(异地需先 MoveTo, 由执行器负责)
        if ent.location_id != world.loc_of(pid):
            self._fail(world, pid, tid, "目标不在此地")
            return False

        old = self.active.get(pid)
        # 同 target 且已在交互 → 继续(不重置 remaining, 不重复 on_start)
        if old is not None and old.entity_id == tid:
            return True

        # rule 4: 旧 active 且 target 不同 → 先释放(除非旧交互不可打断)
        if old is not None and old.entity_id != tid:
            old_ent = world.entities.get(old.entity_id)
            if old_ent is not None and not old_ent.interruptible:
                # m5-rectify 16: 床等不可打断交互 → 拒绝被新意图顶掉
                self._fail(world, pid, tid, "当前交互不可打断")
                return False
            self._release(world, pid, cancel=True)

        # 登记(rule 3)
        dur = max(1, ent.duration_ticks)
        self.active[pid] = ActiveInteraction(
            npc_id=pid, entity_id=tid,
            remaining_ticks=dur, total_ticks=dur,
        )
        ent.claimed_by = pid
        npc.set_activity(ent.name)
        # 数据化开始效果(M4): on_start(如 add_pending 膀胱负荷)在开始 tick 应用
        if ent.on_start:
            apply_effects(world, npc, ent, ent.on_start)
        return True

    # --- 每 tick 推进 --------------------------------------------------
    def step(self, world: World, cfg) -> None:
        for pid in list(self.active.keys()):
            act = self.active[pid]
            ent = world.entities.get(act.entity_id)
            if ent is None:
                self.active.pop(pid, None)
                continue
            npc = world.npcs.get(pid)
            if npc is None or not npc.is_alive():
                self._release(world, pid, cancel=True)
                continue
            # 1. 分摊 affordances(仅信号键)
            for s, delta in ent.affordances.items():
                if s not in SIGNALS or delta == 0.0:
                    continue
                step = delta / act.total_ticks
                if step:
                    npc.add_signal(s, step)
            # 3. remaining - 1
            act.remaining_ticks -= 1
            if act.remaining_ticks <= 0:
                self._complete(world, pid, ent, act)

    # --- 完成 ---------------------------------------------------------
    def _complete(self, world: World, pid: str, ent: Entity,
                  act: ActiveInteraction) -> None:
        self._finalize(world, pid, ent, act, aborted=False)

    def abort(self, world: World, pid: str) -> None:
        """硬中止(计划截止抢占): 同样触发 on_complete + 消耗 + 回收。"""
        act = self.active.get(pid)
        if act is None:
            return
        ent = world.entities.get(act.entity_id)
        if ent is None:
            self.active.pop(pid, None)
            return
        self.suspended.pop(pid, None)          # 硬中止 → 丢弃挂起进度
        self._finalize(world, pid, ent, act, aborted=True)

    def _finalize(self, world: World, pid: str, ent: Entity,
                  act: ActiveInteraction, *, aborted: bool) -> None:
        """自然完成 / 硬中止共用收尾: 消耗 + on_complete + 事件 + 回收。

        区别: 自然完成额外通知 Person(on_interaction_done) 推进计划; 中止不发。
        两者都触发 on_complete(被打断也要触发, 见 docs/task006.md)。
        """
        npc = world.npcs[pid]
        self._release(world, pid, cancel=False)

        def _self_consumes(ent) -> bool:
            return any((eff or {}).get("op") == "consume_self"
                       for eff in ent.on_complete)

        # 2. 消耗品扣库存; 若 on_complete 自带 consume_self 则交 op 扣(防双扣)
        #    回收统一在第 5 步之后(事件先于回收, 观察者可按 tags 分类)
        if (ent.is_consumable and ent.stock > 0 and not _self_consumes(ent)):
            ent.stock -= 1
        # 3. 数据化完成效果(M4 4.1): on_complete(consume_self 只扣库存, 不 pop)
        if ent.on_complete:
            apply_effects(world, npc, ent, ent.on_complete)

        # 4. 完成 → idle(下一 tick 由 drive 自然重评)
        npc.set_activity("idle")

        # 5. 事件(先发布, 观察者可解析实体 tags) -> 6. 统一回收空消耗品
        kind = "interaction_aborted" if aborted else "interaction_done"
        world.bus.publish(world.bus.make(
            world.clock_tick, kind, pid, {"entity": ent.entity_id}))
        if (ent.stock == 0 and not ent.persist_empty
                and (ent.is_consumable or _self_consumes(ent))):
            world.entities.pop(ent.entity_id, None)
        if not aborted:
            npc.on_interaction_done(ent.entity_id, world.clock_tick)

    # --- 软挂起 / 恢复(reflex 抢占) ------------------------------------
    def suspend(self, world: World, pid: str) -> Suspension | None:
        """软挂起当前交互: 释放 claim, 保留剩余进度。"""
        act = self.active.pop(pid, None)
        if act is None:
            return None
        ent = world.entities.get(act.entity_id)
        if ent is not None and ent.claimed_by == pid:
            ent.claimed_by = None
        npc = world.npcs.get(pid)
        if npc is not None:
            npc.set_activity("idle")
        susp = Suspension(act.entity_id, max(1, act.remaining_ticks),
                          max(1, act.total_ticks))
        self.suspended[pid] = susp
        return susp

    def resume(self, world: World, npc: Person, entity_id: str) -> bool:
        """恢复挂起进度(重新 claim + 还原 remaining); 无匹配挂起则 False。"""
        pid = npc.person_id
        susp = self.suspended.get(pid)
        if susp is None or susp.entity_id != entity_id:
            return False
        ent = world.entities.get(entity_id)
        if ent is None or ent.stock == 0 or ent.claimed_by not in (None, pid):
            return False
        self.suspended.pop(pid, None)
        ent.claimed_by = pid
        self.active[pid] = ActiveInteraction(
            npc_id=pid, entity_id=entity_id,
            remaining_ticks=max(1, susp.remaining_ticks),
            total_ticks=max(1, susp.total_ticks))
        npc.set_activity(ent.name)
        return True

    # --- 内部 ---------------------------------------------------------
    def release_active(self, world: World, pid: str) -> None:
        """m5-rectify 10: 主动清掉某 NPC 的残留 claim(move_to 出发前调用)。"""
        self._release(world, pid, cancel=True)

    def _release(self, world: World, pid: str, *, cancel: bool) -> None:
        act = self.active.pop(pid, None)
        npc = world.npcs.get(pid)
        if act is not None:
            ent = world.entities.get(act.entity_id)
            if ent is not None and ent.claimed_by == pid:
                ent.claimed_by = None
        if npc is not None:
            if cancel:
                npc.set_activity("idle")

    def _fail(self, world: World, pid: str, tid: str, why: str) -> None:
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid,
            {"target": tid, "why": why}))
        # 失败→记忆: 证伪只在失败后(目标不存在/已空→删; 被占/不可打断→冷却到实体时长)
        npc = world.npcs.get(pid)
        if npc is not None and tid:
            ent = world.entities.get(tid)
            npc.on_failure(tid, why, world.clock_tick,
                           retry_ticks=ent.duration_ticks if ent is not None
                           else None)
