"""PerceptionSystem —— 世界侧为 NPC 组装"感知包"(纯读取, 无副作用)。

职责: 由世界按 NPC 当前所在 location, 把该地可交互实体构造成只读 EntityView,
产出 Percept。不做任何"记忆写入" —— 那归 Person.perceive(brain 层)。

感知为 region 局部: 只含 npc 所在 location 的全部实体(不做跨 region 距离感知)。
"""
from __future__ import annotations

from citysim.core.types import EntityView, Percept


def _view_for(world, npc, e, closed: bool) -> EntityView:
    return EntityView(
        entity_id=e.entity_id,
        name=e.name,
        tags=frozenset(e.tags),
        affordances=dict(e.affordances),
        duration_ticks=e.duration_ticks,
        distance=0.0,
        claimable=e.claimable_by(npc.person_id) and not closed,
        stock_zero=(e.stock == 0) or closed,
        location_id=e.location_id,
        price=e.price,
        owner=e.owner,
    )


def build_percept(world, npc) -> Percept:
    """仅 npc 所在 location 的实体全可见(region 局部感知)。纯世界读, 不改任何状态。

    EntityView.claimable = (无人占用 或 自己占用) 且 stock!=0。
    events = 该 NPC 信箱里取走的全部事件。
    结果要不要记进记忆, 由 Person.perceive 决定(此处不管)。
    """
    loc = world.loc_of(npc.person_id)
    views = []
    for e in world.entities_at(loc):
        closed = not e.is_open_now(world.hour_f())   # 停业=空且不可claim
        views.append(_view_for(world, npc, e, closed))
    events = world.bus.drain_for(npc.person_id)
    return Percept(
        tick=world.clock_tick,
        hour_f=world.hour_f(),
        location_id=loc,
        visible=tuple(views),
        events=events,
    )
