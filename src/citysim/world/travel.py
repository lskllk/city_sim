"""world/travel —— 跨地点移动(世界进程, 归 World 层)。

Travel 记录一次移动(出发/到达地点与 tick), 供世界每 tick 线性推进连续位置。
"""
from __future__ import annotations

from dataclasses import dataclass

from citysim.world.world import lerp


@dataclass(frozen=True, slots=True)
class Travel:
    """跨地点移动: 记录出发/到达地点与 tick, 供世界插值(前端也消费)。"""
    from_loc: str
    to_loc: str
    depart_tick: int
    arrive_tick: int
    start_position: tuple[float, float] | None = None
    target_position: tuple[float, float] | None = None


def advance(world, travel: dict[str, Travel]) -> None:
    """每 tick 把旅行中 NPC 的连续 position 沿 start→target 线性推进。"""
    for pid, trv in list(travel.items()):
        npc = world.npcs.get(pid)
        if npc is None or trv.start_position is None \
                or trv.target_position is None:
            continue
        span = trv.arrive_tick - trv.depart_tick
        if span <= 0:
            continue
        t = (world.clock_tick - trv.depart_tick) / span
        npc.move_to(lerp(trv.start_position, trv.target_position, t))
