"""world/mechanism/effects —— 【世界侧】的效果 op 表。

物品的效果写在 `config/items/*.json` 的 `on_start` / `on_complete` 里, 分两类:

  · 认知侧的(改自己的信号/膀胱) —— 由 `model/itemdefs.compile_effects` 剥走,
    编译成【不带 op 名的结构数据】交给 NPC 自己应用。所以 **npc/ 完全不认识
    这里面的 op 名**。
  · 世界侧的(生成东西 / 消耗自己) —— 留在本模块, 由 `apply_effects` 执行。
    它需要 World / Entity, 所以归世界。

因此本文件只认两个 op: `spawn_item` / `consume_self`。
新增世界侧效果的步骤: 写个 `@register("名字")` 的函数 + 在 config/items 里用它。
"""
from __future__ import annotations

import logging
from typing import Callable

from citysim.npc.person import Person
from citysim.world.model.itemdefs import load_item_defs
from citysim.world.world import Entity, World

log = logging.getLogger(__name__)

OPS: dict[str, Callable[[World, Person, Entity, dict], None]] = {}


def register(op_name: str):
    def deco(fn: Callable[[World, Person, Entity, dict], None]):
        OPS[op_name] = fn
        return fn
    return deco


@register("spawn_item")
def _spawn_item(world, npc, entity, eff) -> None:
    """在世界按 item_type 生成 count 件物品(默认 npc 所在 location)。"""
    it = eff.get("item_type")
    if not it:
        return
    if it not in load_item_defs():
        return
    count = int(eff.get("count", 1))
    for _ in range(max(1, count)):
        world.spawn_item_type(it, world.loc_of(npc.person_id))


@register("consume_self")
def _consume_self(world, npc, entity, eff) -> None:
    """消耗当前实体一份(stock-1)。

    它同时是个【标记】: 带 `consumable` tag 的东西本来就会被 interaction 自动
    扣一份; 不带这个 tag、却又该被用掉的(如一次性用品), 写这个 op 来声明
    "我用完就没了" —— interaction 看到它就不自动扣, 改由这里扣。
    回收不在此处: 统一在完成事件之后(保证 interaction_done 先于实体移除)。
    """
    if entity.stock == -1:
        return
    if entity.stock > 0:
        entity.stock -= 1


def apply_effects(world: World, npc: Person, entity: Entity,
                  effect_list: list[dict]) -> None:
    """依序应用一列【世界侧】效果; 未知 op 记 warning 而非崩溃。"""
    for eff in effect_list:
        fn = OPS.get(eff.get("op", ""))
        if fn is not None:
            fn(world, npc, entity, eff)
        else:
            log.warning("未知 effect op=%s (entity=%s)",
                        eff.get("op"), entity.entity_id)
