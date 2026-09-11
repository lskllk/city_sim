"""效果操作解释器(M4 4.2) —— op 表 + apply_effects。

首批 5 个 op(定死): set_signal / add_signal / add_pending /
spawn_item(按物品类型在世界生成) / consume_self。
效果从 Entity.on_complete / on_start(数据化)驱动, 替换硬编码分支。
"""
from __future__ import annotations

import logging
from typing import Callable

from citysim.core.config import SIGNALS
from citysim.npc.person import Person
from citysim.world.itemdefs import load_item_defs
from citysim.world.world import Entity, World

log = logging.getLogger(__name__)

OPS: dict[str, Callable[[World, Person, Entity, dict], None]] = {}


def register(op_name: str):
    def deco(fn: Callable[[World, Person, Entity, dict], None]):
        OPS[op_name] = fn
        return fn
    return deco


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


@register("set_signal")
def _set_signal(world, npc, entity, eff) -> None:
    s, v = eff["signal"], eff.get("value", 0.0)
    if s in SIGNALS:
        npc.set_signal(s, v)


@register("add_signal")
def _add_signal(world, npc, entity, eff) -> None:
    s = eff["signal"]
    v = float(eff.get("delta", eff.get("value", 0.0)))
    if s in SIGNALS:
        npc.add_signal(s, v)


_PENDING_WHITELIST = frozenset({"bladder_pending"})


@register("add_pending")
def _add_pending(world, npc, entity, eff) -> None:
    """膀胱等 pending 字段累加(on_start 用)。"""
    f = eff.get("field", "")
    if f not in _PENDING_WHITELIST:
        log.warning("add_pending 拒绝字段 %r(白名单: %s)",
                    f, sorted(_PENDING_WHITELIST))
        return
    npc.add_bladder_pending(float(eff.get("amount", 0.0)))


@register("spawn_item")
def _spawn_item(world, npc, entity, eff) -> None:
    """在世界按 item_type 生成 count 件物品(默认 npc 所在 location)。"""
    it = eff.get("item_type")
    if not it:
        return
    defs = load_item_defs()
    if it not in defs:
        return
    count = int(eff.get("count", 1))
    for _ in range(max(1, count)):
        world.spawn_item_type(it, world.loc_of(npc.person_id))


@register("consume_self")
def _consume_self(world, npc, entity, eff) -> None:
    """消耗当前实体一份(stock-1)。回收不在此处 —— 统一由 _complete 第 5 步后
    处理, 保证 interaction_done 事件先于实体移除(m3 时序契约)。"""
    if entity.stock == -1:
        return
    if entity.stock > 0:
        entity.stock -= 1


def apply_effects(world: World, npc: Person, entity: Entity,
                  effect_list: list[dict]) -> None:
    """依序应用一列效果 op; 未知 op 记 warning 而非崩溃。"""
    for eff in effect_list:
        fn = OPS.get(eff.get("op", ""))
        if fn is not None:
            fn(world, npc, entity, eff)
        else:
            log.warning("未知 effect op=%s (entity=%s)",
                        eff.get("op"), entity.entity_id)

