"""InteractionSystem —— 执行 Intent + claim 仲裁 + 分 tick 效果推进。

世界侧唯一执行器: 校验 → claim → 登记 ActiveInteraction; 每 tick 分摊
affordances; 完成时处理 消耗品/马桶/plan_queue 链; 睡眠用 wake_condition
数据驱动提前结束。事件经 EventBus 发布给 NPC 信箱。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from citysim.core.config import SIGNALS
from citysim.npc.person import Person
from citysim.world.world import Entity, World

_WAKE_RE = re.compile(r"^(\w+)\s*>=\s*([0-9.]+)$")


@dataclass
class ActiveInteraction:
    npc_id: str
    entity_id: str
    remaining_ticks: int
    total_ticks: int
    plan_queue: tuple[str, ...] = ()   # GOAP 后续步骤(如 ("eat",))


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class InteractionSystem:
    """一次持有多名 NPC 的进行中交互; 每 tick step 推进。"""

    def __init__(self, scheduler: Any = None) -> None:
        self.active: dict[str, ActiveInteraction] = {}   # key = npc_id
        self._scheduler = scheduler                       # TimingWheel | None
        self._meal_seq = 0

    # --- 提交 ---------------------------------------------------------
    def submit(self, world: World, npc: Person, intent) -> bool:
        """校验→claim→登记。失败发 intent_failed 事件。返回是否成功登记。"""
        pid = npc.person_id
        if intent.kind == "idle":
            if pid in self.active:
                self._release(world, pid, cancel=True)
                self._resched(world, pid, 1)
            return True

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

        # rule 4: 旧 active 且 target 不同 → 先释放
        old = self.active.get(pid)
        if old is not None and old.entity_id != tid:
            self._release(world, pid, cancel=True)

        # 登记(rule 3)
        dur = max(1, ent.duration_ticks)
        plan = tuple(intent.trace.plan or ())
        self.active[pid] = ActiveInteraction(
            npc_id=pid, entity_id=tid,
            remaining_ticks=dur, total_ticks=dur,
            plan_queue=plan[1:] if plan else (),
        )
        ent.claimed_by = pid
        npc.active_interaction_id = tid
        npc.current_activity = ent.name
        # 开始 tick 一次性挂排泄负荷(不分摊; 如进食)
        if not ent.is_sleepable and ent.attrs.get("bladder_load", 0) > 0:
            npc.bladder_pending += float(ent.attrs["bladder_load"])
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
            # 1. 分摊 affordances(仅信号键; provides:* 标记不参与)
            for s, delta in ent.affordances.items():
                if s not in SIGNALS or delta == 0.0:
                    continue
                step = delta / act.total_ticks
                if s in npc.signals:
                    npc.signals[s] = _clamp(npc.signals[s] + step)
            # 睡眠泛化: wake_condition 满足即提前完成
            if ent.wake_condition and _wake_satisfied(ent.wake_condition, npc.signals):
                self._complete(world, pid, ent, act, early=True)
                continue
            # 3. remaining - 1
            act.remaining_ticks -= 1
            if act.remaining_ticks <= 0:
                self._complete(world, pid, ent, act, early=False)

    # --- 完成 ---------------------------------------------------------
    def _complete(self, world: World, pid: str, ent: Entity,
                  act: ActiveInteraction, *, early: bool) -> None:
        npc = world.npcs[pid]
        self._release(world, pid, cancel=False)
        consumed_empty = False

        # 2. 消耗品 stock-1; 空则回收实体(防泄漏, 如吃完的餐/水不再滞留世界)
        #    回收须在 interaction_done 事件发布之后, 否则观察者无法按实体分类
        if ent.is_consumable and ent.stock > 0:
            ent.stock -= 1
            consumed_empty = ent.stock <= 0
        # 3. 马桶(清空膀胱) —— 硬编码, M4 搬进数据化 on_complete
        if "toilet" in ent.tags:
            npc.bladder_pending = 0.0
            npc.signals["bladder"] = 1.0
            npc.current_activity = "idle"

        # 4. plan_queue 非空 → 弹出下一步并直接续上(不等重评)
        if act.plan_queue:
            self._continue_plan(world, npc, act)
        elif early:
            self._resched(world, pid, 1)   # 提前结束(唤醒等)→ 尽快重评
        else:
            npc.current_activity = "idle"

        # 5. 事件(先发布, 观察者可解析实体 tags) -> 再回收空消耗品
        world.bus.publish(world.bus.make(
            world.clock_tick, "interaction_done", pid,
            {"entity": ent.entity_id}))
        if consumed_empty:
            world.entities.pop(ent.entity_id, None)

    def _continue_plan(self, world: World, npc: Person, act: ActiveInteraction) -> None:
        """取食链: take 完成后生成一份餐并立即开吃。

        有限库存容器(stock != -1)每次供餐扣 1; 扣到 0 后不再可占用。
        """
        container = world.entities.get(act.entity_id)
        if container is None:
            return
        if container.stock != -1:
            if container.stock <= 0:
                return                     # 没货, 不再产餐
            container.stock -= 1
        # 弹出本步(取食成功)
        if act.plan_queue[0] == "eat":
            self._meal_seq += 1
            meal = Entity(
                entity_id="", name="简餐",
                tags={"edible", "consumable"},
                affordances={"hunger": 0.5, "thirst": 0.1},
                duration_ticks=20, location_id=npc.location_id,
                stock=1, attrs={"bladder_load": 0.3},
            )
            world.spawn_entity(meal)
            # 直接开启新交互(吃)
            self.active[npc.person_id] = ActiveInteraction(
                npc_id=npc.person_id, entity_id=meal.entity_id,
                remaining_ticks=meal.duration_ticks,
                total_ticks=meal.duration_ticks, plan_queue=(),
            )
            meal.claimed_by = npc.person_id
            npc.active_interaction_id = meal.entity_id
            npc.current_activity = meal.name
            if meal.attrs.get("bladder_load", 0) > 0:
                npc.bladder_pending += float(meal.attrs["bladder_load"])
            # 重排下次重评到餐吃完(覆盖 take 的旧档)
            self._resched(world, npc.person_id, meal.duration_ticks)

    # --- 内部 ---------------------------------------------------------
    def _release(self, world: World, pid: str, *, cancel: bool) -> None:
        act = self.active.pop(pid, None)
        npc = world.npcs.get(pid)
        if act is not None:
            ent = world.entities.get(act.entity_id)
            if ent is not None and ent.claimed_by == pid:
                ent.claimed_by = None
        if npc is not None:
            npc.active_interaction_id = None
            if cancel:
                npc.current_activity = "idle"

    def _fail(self, world: World, pid: str, tid: str, why: str) -> None:
        world.bus.publish(world.bus.make(
            world.clock_tick, "intent_failed", pid,
            {"target": tid, "why": why}))

    def _resched(self, world: World, pid: str, delay: int) -> None:
        if self._scheduler is not None:
            self._scheduler.schedule(pid, delay, now=world.clock_tick)


def _wake_satisfied(cond: str, signals: dict[str, float]) -> bool:
    """解析 "signal>=value"(正则, 禁 eval)。"""
    m = _WAKE_RE.match(cond.strip())
    if not m:
        return False
    signal, val = m.group(1), float(m.group(2))
    return signals.get(signal, 0.0) >= val
