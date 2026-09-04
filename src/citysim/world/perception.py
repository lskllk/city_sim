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
        views.append(EntityView(
            entity_id=e.entity_id,
            name=e.name,
            tags=frozenset(e.tags),
            affordances=dict(e.affordances),
            duration_ticks=e.duration_ticks,
            distance=0.0,
            claimable=e.claimable_by(npc.person_id),
            stock_zero=e.stock == 0,
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


def consolidate_observations(npc, percept: Percept, kb) -> None:
    """感知 → 知识(M5 5.3 接线 1)。

    每个可见 container: 有货(claimable 且可食标记) → learn OBSERVED
    contains=edible; 空/不可用 → 与 KB 矛盾则 refute, 并 learn contains=none。
    """
    for v in percept.visible:
        if "container" not in v.tags:
            continue
        existing = kb.query(subject=v.entity_id, relation="contains")
        # 真空(stock==0): 证伪既有"有食"并学 none(design 5.3)
        if v.stock_zero:
            for f in existing:
                if f.obj == "edible":
                    kb.refute(f.fact_id)
            if not any(f.obj == "none" and f.source.kind == "OBSERVED"
                       for f in kb.query(subject=v.entity_id,
                                         relation="contains")):
                kb.learn(subject=v.entity_id, relation="contains",
                         obj="none", confidence=1.0,
                         source=Source(kind="OBSERVED"))
            continue
        # 被他人占用(非空但 claimable=False): 不是"空"的证据, 不更新(避免误证伪)
        if not v.claimable:
            continue
        # 可用且有食 → OBSERVED contains=edible + located_at(自住地)
        has = v.affordances.get("provides:edible", 0.0) > 0
        if not has:
            continue
        learned = any(f.source.kind == "OBSERVED" and f.obj == "edible"
                      for f in existing)
        if not learned:
            kb.learn(subject=v.entity_id, relation="contains",
                     obj="edible", confidence=1.0,
                     source=Source(kind="OBSERVED"))
        # 亲眼见到有食物的容器 -> 也记下它在哪(located_at), S1 收敛必需
        loc = kb.query(subject=v.entity_id, relation="located_at")
        known_loc = next((f.obj for f in loc
                          if f.source.kind == "OBSERVED"), None)
        if known_loc != npc.location_id:
            kb.learn(subject=v.entity_id, relation="located_at",
                     obj=npc.location_id, confidence=1.0,
                     source=Source(kind="OBSERVED"))
