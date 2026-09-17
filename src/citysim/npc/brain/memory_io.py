"""npc/brain/memory_io —— 记忆的写入与遗忘。

  perceive_into  感知 → 记忆: 现场为准, 整行覆盖, believe=1(亲眼所见最硬)
                 返回【本次的新奇量】= Σ(1 − 旧 remember) —— 闲逛靠它结算 fun
  forget         按【调用节奏】做一步半衰衰减, 低于阈值删行
"""
from __future__ import annotations

from citysim.core.types import Percept
from citysim.npc.memory import MemBase, MemItem

FORGET_DEFAULT = 0.1  # remember 低于此 → 遗忘删除(默认阈值)


def perceive_into(mem: MemBase, percept: Percept, tick: int) -> float:
    """感知 → 记忆(写入): 把当前可见实体 upsert 进记忆库。非纯函数。

    同地 re-obs: 现场为准, 整行覆盖(located/owner/afford/price/…)并刷新
    believe/remember/last_seen。只 upsert 可见实体, 不做证伪删行(由上层策略定)。

    现场看到的 → source=""(亲眼) 且 believe=1.0: 不管之前听谁说过, 亲眼所见最硬。

    ★ 返回值 = 【本次的新奇量】= Σ(1 − 旧的 remember)。
      它是"这次看到的东西有多新"的度量:
        第一次见 = 1.0/件;  忘了又见 = 1 − remember;  天天见的 ≈ 0。
      闲逛靠它结算 fun(见 Person 的闲逛收工), 也靠它更新"这地方值不值得再去"。
    """
    gain = 0.0
    for v in percept.visible:
        afford, value = (next(iter(v.affordances.items()), ("", 0.0)))
        row = mem.get(v.entity_id)
        if row is None:
            gain += 1.0
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
            gain += max(0.0, 1.0 - float(row.remember))
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
    gain += _touch_place(mem, percept.location_id, tick)
    return gain


def place_id(loc: str) -> str:
    """地点记忆行的 id(和实体行共用一个库, 但 afford="" 不进决策候选)。"""
    return "loc:" + loc


def _touch_place(mem: MemBase, loc: str, tick: int) -> float:
    """写一行【地点记忆】("我逛过这里") —— 返回它这次的新奇量。

    为什么需要它:
      · 它是"我来过"的凭证 —— 闲逛选址靠它判断"**没去过**"(没去过才给乐观加成);
      · 它是"上次在这儿收获多少"的账(attrs["gain"]) —— 选址的第二项;
      · afford="" → **不进决策候选**(不会干扰吃饭睡觉);
      · 它自己也参与遗忘 → 忘了 = 重新变成"没去过" → 会再去看看。
    """
    pid = place_id(loc)
    row = mem.get(pid)
    if row is None:
        mem.set(MemItem(item_id=pid, located=loc, afford="",
                        tags=("place",), believe=1.0, remember=1.0,
                        last_seen=tick, attrs={"visits": 1, "gain": 0.0}))
        return 1.0
    gain = max(0.0, 1.0 - float(row.remember))
    mem.update(pid, remember=1.0, last_seen=tick)
    return gain


def forget(mem: MemBase, half_life_ticks: int, step_ticks: int = 1440,
           forget_threshold: float = FORGET_DEFAULT) -> int:
    """遗忘策略: 按【调用的间隔】做一步半衰衰减, 低于阈值删行。

    返回值 = 本次被遗忘删除的 item 数。何时调用/半衰/阈值由上层定(如每游戏日)。

    ★ 为什么是"一步"而不是"按距上次观察的 dt":
      本函数由上层【按固定节奏】调(现在 = 每个游戏日 0:00)。早先的实现用
      `remember × 0.5^(dt/half_life)`, 而 dt 是"距上次观察的全量时间"、remember
      是【已经衰减过的值】→ 同一段时间被算了两遍, 衰减比名义快:
      半衰 2 天 / 阈值 0.1 时, **4 天就删行**(本该 ~6.6 天)。
      现在按步长: `remember × 0.5^(step_ticks / half_life_ticks)`。
    """
    step = max(1, int(step_ticks))
    factor = 0.5 ** (step / max(1.0, float(half_life_ticks)))
    gone = 0
    for r in mem.items():
        rem = float(r.remember) * factor
        if rem < forget_threshold:
            mem.delete(r.item_id)
            gone += 1
        else:
            mem.update(r.item_id, remember=rem)
    return gone
