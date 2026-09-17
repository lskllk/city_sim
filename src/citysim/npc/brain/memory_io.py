"""npc/brain/memory_io —— 记忆的写入与遗忘。

  perceive_into  感知 → 记忆: 现场为准, 整行覆盖, believe=1(亲眼所见最硬)
  forget         按 last_seen 做半衰衰减, 低于阈值删行(何时调/半衰由上层定)
"""
from __future__ import annotations

from citysim.core.types import Percept
from citysim.npc.memory import MemBase, MemItem

FORGET_DEFAULT = 0.1  # remember 低于此 → 遗忘删除(默认阈值)


def perceive_into(mem: MemBase, percept: Percept, tick: int) -> None:
    """感知 → 记忆(写入): 把当前可见实体 upsert 进记忆库。非纯函数。

    同地 re-obs: 现场为准, 整行覆盖(located/owner/afford/price/…)并刷新
    believe/remember/last_seen。只 upsert 可见实体, 不做证伪删行(由上层策略定)。

    现场看到的 → source=""(亲眼) 且 believe=1.0: 不管之前听谁说过, 亲眼所见最硬。
    """
    for v in percept.visible:
        # TODO: affordances 多键 dict → 决定单值 or dict(MemItem.afford 现单值)
        afford, value = (next(iter(v.affordances.items()), ("", 0.0)))
        # owner 直接存世界真值 id(person_id/company_id/""=无主)：判定"自己的"靠
        # decide 的 self_id 比对, 不再用 "me" 哨兵。
        row = mem.get(v.entity_id)
        if row is None:
            mem.set(MemItem(
                item_id=v.entity_id, located=v.location_id,
                owner=v.owner, afford=afford, value=float(value),
                item_type=v.item_type, tags=tuple(sorted(v.tags)), source="",
                price=v.price, household=bool(v.household),
                free_use=bool(v.free_use), stock=int(v.stock),
                shelf_life_ticks=int(v.shelf_life_ticks),
                expires_tick=int(v.expires_tick),
                believe=1.0, remember=1.0, last_seen=tick))
        else:
            mem.update(
                v.entity_id, located=v.location_id, owner=v.owner,
                afford=afford or row.afford,
                value=float(value) if value else row.value,
                item_type=v.item_type, tags=tuple(sorted(v.tags)), source="",
                price=v.price, household=bool(v.household),
                free_use=bool(v.free_use), stock=int(v.stock),
                shelf_life_ticks=int(v.shelf_life_ticks),
                expires_tick=int(v.expires_tick),
                believe=1.0, remember=1.0, last_seen=tick)


FORGET_DEFAULT = 0.1  # remember 低于此 → 遗忘删除(默认阈值)

# 默认的位移成本(无路网/无成本矩阵时的降级): 固定 tick。
DEFAULT_TRAVEL_TICKS = 30
MAX_BUY_QTY = 30      # 单次购买上限(只是防手滑; 真正的量由目标存量决定)


def forget(mem: MemBase, now_tick: int, half_life_ticks: int,
           forget_threshold: float = FORGET_DEFAULT) -> int:
    """遗忘策略: 按 last_seen 把 remember 半衰衰减, 低于阈值删行。

    返回值 = 本次被遗忘删除的 item 数。何时调用/半衰/阈值由上层定(如每游戏日)。
    """
    gone = 0
    for r in mem.items():
        dt = max(0, now_tick - r.last_seen)
        if dt <= 0:
            continue
        rem = r.remember * (0.5 ** (dt / max(1, half_life_ticks)))
        if rem < forget_threshold:
            mem.delete(r.item_id)
            gone += 1
        else:
            mem.update(r.item_id, remember=rem)
    return gone
