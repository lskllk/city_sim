"""InteractionSystem —— 执行 Intent + claim 仲裁 + 分 tick 效果推进。

世界侧唯一执行器: 校验 → claim → 登记 ActiveInteraction; 每 tick 分摊
affordances; 完成时处理 消耗品/如厕。事件经 EventBus 发布给 NPC 信箱。
"""
from __future__ import annotations

from dataclasses import dataclass

from citysim.core.types import Idle, InteractionDone, Interact, ItemGone
from citysim.npc.person import Person
from citysim.world.mechanism.effects import apply_effects, compile_effects
from citysim.world.world import Entity, World


@dataclass
class ActiveInteraction:
    entity_id: str
    handle: str = ""          # world 签发的唯一持有凭证(不撞车)
    # 进度(remaining/total)归 NPC 自己的 intake; 这里不存。


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class InteractionSystem:
    """一次持有多名 NPC 的进行中交互; 每 tick step 推进。"""

    def __init__(self) -> None:
        self.active: dict[str, ActiveInteraction] = {}   # key = npc_id
        # 最近一次 submit 失败的原因(供 NPC 侧 on_failure 用)。
        # (reason, retry_ticks); 成功时不计。
        self.last_fail: tuple[str, int] = ("", 0)
        # 唯一 handle 序号(确定性: 单线程递增)
        self._seq: int = 0

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
        # 容量 = stock: 只要还有人没用满, 就能同时用(3 张床 → 3 人睡)
        if not ent.claimable_by(pid):
            self._fail(world, pid, tid, "已被他人占用")
            return False
        # 现实约束: 目标必须同 region
        if ent.location_id != world.loc_of(pid):
            self._fail(world, pid, tid, "目标不在此地")
            return False

        old = self.active.get(pid)
        # 同 target 且已在交互 → 继续(不重置 remaining, 不重复 on_start)
        if old is not None and old.entity_id == tid:
            return True

        # rule 4: 旧 active 且 target 不同 → 先释放(新交互直接顶掉旧的)
        if old is not None and old.entity_id != tid:
            self._release(world, pid, cancel=True)

        # 登记(rule 3)
        self._seq += 1
        self.active[pid] = ActiveInteraction(
            entity_id=tid, handle=f"{tid}#{self._seq}",
        )
        ent.claimants.add(pid)
        # on_start 的 NPC 侧效果由 Person 应用(编译进 Grant.pending);
        # world 侧 on_start(如 spawn_item)很少见, 这里不再处理。
        _npc_start, _world_start = compile_effects(ent.on_start)
        if _world_start:
            apply_effects(world, npc, ent, _world_start)
        return True

    # --- 每 tick 推进 --------------------------------------------------
    def step(self, world: World, cfg) -> None:
        """不管信号/进度 —— NPC 自己消化(heartbeat); 这里只做收尾与清理。

        ① NPC 消化完的 intake → 扣货 / on_complete / 事件 / 回收(自然完成);
        ② 目标消失 / NPC 死亡 → 撤 claim。
        """
        for pid in list(world.npcs):
            npc = world.npcs[pid]
            for handle in npc.take_finished():
                self.finish(world, pid, handle, aborted=False)
        for pid in list(self.active.keys()):
            act = self.active[pid]
            if world.entities.get(act.entity_id) is None:
                self.active.pop(pid, None)
                continue
            npc = world.npcs.get(pid)
            if npc is None or not npc.is_alive():
                self._release(world, pid, cancel=True)

    def finish(self, world: World, pid: str, handle: str, *,
               aborted: bool = False) -> bool:
        """NPC 消化完毕(或 world 主动中止) → 收尾。校验“确实在持有”后才 _finalize。"""
        act = self.active.get(pid)
        if act is None or act.handle != handle:
            return False
        ent = world.entities.get(act.entity_id)
        if ent is None:
            self.active.pop(pid, None)
            return False
        self._finalize(world, pid, ent, act, aborted=aborted)
        return True

    # --- 完成 ---------------------------------------------------------
    def abort(self, world: World, pid: str) -> None:
        """硬中止(计划截止抢占): 同样触发 on_complete + 消耗 + 回收。"""
        act = self.active.get(pid)
        if act is None:
            return
        ent = world.entities.get(act.entity_id)
        if ent is None:
            self.active.pop(pid, None)
            return
        self._finalize(world, pid, ent, act, aborted=True)

    def _finalize(self, world: World, pid: str, ent: Entity,
                  act: ActiveInteraction, *, aborted: bool) -> None:
        """自然完成 / 硬中止共用收尾: 消耗 + on_complete + 事件 + 回收。

        区别: 自然完成额外通知 Person(on_interaction_done) 推进计划; 中止不发。
        两者都触发 on_complete(被打断也要触发)。
        """
        npc = world.npcs[pid]
        self._release(world, pid, cancel=False)

        def _self_consumes(ent) -> bool:
            return any((eff or {}).get("op") == "consume_self"
                       for eff in ent.on_complete)

        # 2.+3. 自然完成才扣货 / 跑 world 侧 on_complete;
        #   中止(aborted) = 没吃完 → 不扣货、不触发 on_complete
        #   不再“中止也扣一份饭”)。claim 已释放 → 东西回到世界。
        if not aborted:
            if (ent.is_consumable and ent.stock > 0 and not _self_consumes(ent)):
                ent.stock -= 1
            if ent.on_complete:
                _npc_done, world_o = compile_effects(ent.on_complete)
                apply_effects(world, npc, ent, world_o)

        # 5. 事件(先发布, 观察者可解析实体 tags) -> 6. 统一回收空消耗品
        kind = "interaction_aborted" if aborted else "interaction_done"
        world.bus.publish(world.bus.make(
            world.clock_tick, kind, pid, {"entity": ent.entity_id}))
        if (ent.stock == 0 and not ent.persist_empty
                and (ent.is_consumable or _self_consumes(ent))):
            world.entities.pop(ent.entity_id, None)
            npc.notify(ItemGone(ent.entity_id))
        if not aborted:
            npc.notify(InteractionDone(ent.entity_id, world.clock_tick))

    # --- 内部 ---------------------------------------------------------
    def release_active(self, world: World, pid: str) -> None:
        """主动清掉某 NPC 的残留 claim(move_to 出发前调用)。"""
        self._release(world, pid, cancel=True)

    def _release(self, world: World, pid: str, *, cancel: bool) -> None:
        act = self.active.pop(pid, None)
        npc = world.npcs.get(pid)
        if act is not None:
            ent = world.entities.get(act.entity_id)
            if ent is not None:
                ent.claimants.discard(pid)

    def _fail(self, world: World, pid: str, tid: str, why: str) -> None:
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid,
            {"target": tid, "why": why}))
        # 只把“为什么失败 + 冷却提示”记下; 写记忆/放弃 goal 归 NPC 自己。
        npc = world.npcs.get(pid)
        ent = world.entities.get(tid) if tid else None
        self.last_fail = (why, ent.duration_ticks if ent is not None else 0)
