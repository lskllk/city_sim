"""PerceptionSystem —— 为 NPC 构建 Percept(纯读取) + 感知落知识(M5)。

TASK001 空间感知: 同 semantic region 全可见(既有行为不变); 跨 region 仅当
distance <= perception_radius。半径来自 config [spatial]; 无 region 几何时
退回纯同-region(旧行为), 保证 helpers/无几何世界不改变语义。
"""
from __future__ import annotations

from citysim.core.types import EntityView, PerceptionRecord, Percept
from citysim.npc.knowledge import Source


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


def build_percept(world, npc, radius: float | None = None) -> Percept:
    """同 region 全可见; 跨 region 距离内可见(radius=None 或无从几何时跳过)。

    EntityView.claimable = (无人占用 或 自己占用) 且 stock!=0。
    events = 该 NPC 信箱里取走的全部事件。
    """
    views = []
    anchor_here = npc.position
    for e in world.entities_at(npc.location_id):
        closed = not e.is_open_now(world.hour_f())   # 停业=空且不可claim
        views.append(_view_for(world, npc, e, closed))
    # 跨 region: 需要距离语义(region 几何 + 双方 position)才参与
    if radius is not None and radius > 0 and world.has_spatial(npc.location_id):
        for e in world.entities.values():
            if e.location_id == npc.location_id:
                continue
            if not world.has_spatial(e.location_id):
                continue
            ep = world.anchor_of(e)
            if ep is None:
                continue
            d = ((anchor_here[0] - ep[0]) ** 2
                 + (anchor_here[1] - ep[1]) ** 2) ** 0.5
            if d > radius:
                continue
            closed = not e.is_open_now(world.hour_f())
            v = _view_for(world, npc, e, closed)
            v = EntityView(entity_id=v.entity_id, name=v.name, tags=v.tags,
                           affordances=v.affordances,
                           duration_ticks=v.duration_ticks, distance=d,
                           claimable=v.claimable, stock_zero=v.stock_zero,
                           location_id=v.location_id, price=v.price,
                           owner=v.owner)
            views.append(v)
    events = world.bus.drain_for(npc.person_id)
    npc.last_percept = PerceptionRecord(
        tick=world.clock_tick, npc_id=npc.person_id,
        location_id=npc.location_id, position=npc.position,
        observed_entity_ids=tuple(sorted(v.entity_id for v in views)))
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
        # 静态可交互设施(含散落食物): 学 affords(带数值) + located_at + price_of
        # TASK001: located_at 学实体真实 region(v.location_id)。同 region 可见时
        # 与旧语义(当前 region)一致; 跨 region 可见则不再写错"在此地"。
        if v.affordances:
            for signal, delta in v.affordances.items():
                if delta > 0:
                    kb.learn(subject=v.entity_id, relation="affords",
                             obj=signal, confidence=1.0,
                             source=Source(kind="OBSERVED"), tick=tick,
                             value=delta)
            kb.learn(subject=v.entity_id, relation="located_at",
                     obj=v.location_id, confidence=1.0,
                     source=Source(kind="OBSERVED"), tick=tick)
        if v.price > 0:
            kb.learn(subject=v.entity_id, relation="price_of",
                     obj=v.price, confidence=1.0,
                     source=Source(kind="OBSERVED"), tick=tick,
                     value=v.price)
