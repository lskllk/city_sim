"""PerceptionSystem —— 为 NPC 构建 Percept(纯读取)。"""
from __future__ import annotations

from citysim.core.types import EntityView, Percept


def build_percept(world, npc) -> Percept:
    """M3 版: 同 location 全可见。

    EntityView.claimable = (无人占用 或 自己占用) 且 stock!=0。
    events = 该 NPC 信箱里取走的全部事件。
    """
    views = []
    for e in world.entities_at(npc.location_id):
        views.append(EntityView(
            entity_id=e.entity_id,
            name=e.name,
            tags=frozenset(e.tags),
            affordances=dict(e.affordances),
            duration_ticks=e.duration_ticks,
            distance=0.0,
            claimable=e.claimable_by(npc.person_id),
            location_id=e.location_id,
        ))
    events = world.bus.drain_for(npc.person_id)
    return Percept(
        tick=world.clock_tick,
        hour_f=world.hour_f(),
        location_id=npc.location_id,
        visible=tuple(views),
        events=events,
    )
