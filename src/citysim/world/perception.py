"""PerceptionSystem —— 为 NPC 构建 Percept(纯读取) + 感知落知识(M5)。"""
from __future__ import annotations

from citysim.core.types import EntityView, Percept
from citysim.npc.knowledge import Source


def build_percept(world, npc) -> Percept:
    """M3 版: 同 location 全可见。

    EntityView.claimable = (无人占用 或 自己占用) 且 stock!=0。
    events = 该 NPC 信箱里取走的全部事件。
    """
    views = []
    for e in world.entities_at(npc.location_id):
        closed = not e.is_open_now(world.hour_f())   # 停业=空(触发 refute)且不可claim
        views.append(EntityView(
            entity_id=e.entity_id,
            name=e.name,
            tags=frozenset(e.tags),
            affordances=dict(e.affordances),
            duration_ticks=e.duration_ticks,
            distance=0.0,
            claimable=e.claimable_by(npc.person_id) and not closed,
            stock_zero=(e.stock == 0) or closed,
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


def consolidate_observations(npc, percept: Percept, kb, tick: int = 0) -> None:
    """感知 → 知识(M5 5.3 接线 1; m5-rectify T2/T4/T5)。

    - 每可见静态可交互设施(非散落食物): 学 affords + located_at。
    - 纠错: 自学的 located_at 声称"X 在此地"、此地却看不到 X → refute(被搬走/移除)。
    - tick 显式传入(learn 真实时刻), upsert 由 KB 保证有界。
    """
    visible_ids = {v.entity_id for v in percept.visible}
    # T5②: OBSERVED located_at 指向当前地但实体不可见 → 证伪(陈旧位置知识)
    for f in kb.query(relation="located_at"):
        if (f.obj == npc.location_id and f.source.kind == "OBSERVED"
                and f.subject not in visible_ids):
            kb.refute(f.fact_id)

    for v in percept.visible:
        # 静态可交互设施(含散落食物): 学 affords(带数值) + located_at
        if v.affordances:
            for signal, delta in v.affordances.items():
                if delta > 0:
                    kb.learn(subject=v.entity_id, relation="affords",
                             obj=signal, confidence=1.0,
                             source=Source(kind="OBSERVED"), tick=tick,
                             value=delta)
            kb.learn(subject=v.entity_id, relation="located_at",
                     obj=npc.location_id, confidence=1.0,
                     source=Source(kind="OBSERVED"), tick=tick)
