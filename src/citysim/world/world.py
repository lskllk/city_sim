"""World 容器 —— 地点/实体/NPC 注册表 + 事件总线。

世界是唯一事实源; Entity 为可变真实体。NPC Person 来自 npc/person(纯数据)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from citysim.npc.person import Person
from citysim.world.events import EventBus
from citysim.world.itemdefs import ItemDef, load_item_defs


@dataclass
class Entity:
    """世界侧真实体(可变)。"""
    entity_id: str
    name: str
    tags: set[str] = field(default_factory=set)
    affordances: dict[str, float] = field(default_factory=dict)  # 信号效果
    duration_ticks: int = 30
    location_id: str = ""
    claimed_by: str | None = None         # 占用者 npc_id
    stock: int = 1                        # 容器/消耗品库存; -1=无限
    attrs: dict[str, Any] = field(default_factory=dict)  # 如 bladder_load
    interruptible: bool = True            # M3 睡眠泛化: 床 False
    wake_condition: str | None = None     # "signal>=value"(用正则解析, 禁 eval)
    on_start: list[dict] = field(default_factory=list)       # M4 数据化效果
    on_complete: list[dict] = field(default_factory=list)    # M4 数据化效果
    provides: list[str] = field(default_factory=list)        # 容器可产物品类型

    @property
    def is_consumable(self) -> bool:
        return "consumable" in self.tags

    @property
    def is_sleepable(self) -> bool:
        return "sleepable" in self.tags

    def provides_edible(self) -> bool:
        """容器是否供食: 走 provides 列表(defs 判定); legacy 手工容器看假键。"""
        if self.provides:
            defs = load_item_defs()
            return any(p in defs and "edible" in defs[p].tags
                       for p in self.provides)
        return self.affordances.get("provides:edible", 0.0) > 0

    def claimable_by(self, npc_id: str | None) -> bool:
        return (self.claimed_by is None or self.claimed_by == npc_id) \
            and self.stock != 0


# ----------------------------------------------------------------------
# 物品定义 -> 真实体(M4: 从 config/items/*.json 生成, 零硬编码)
# ----------------------------------------------------------------------
def entity_from_def(d: ItemDef, location_id: str) -> Entity:
    """由 ItemDef 建一个可变 Entity(m5-rectify 12: 不再往 affordances 塞假键,
    供食语义由 provides(defs 判定)承载, 感知/决策读 EntityView.food_source)。"""
    return Entity(
        entity_id="", name=d.name, tags=set(d.tags),
        affordances=dict(d.affordances), duration_ticks=d.duration_ticks,
        location_id=location_id, stock=d.stock, attrs=dict(d.attrs),
        interruptible=d.interruptible, wake_condition=d.wake_condition,
        on_start=list(d.on_start), on_complete=list(d.on_complete),
        provides=list(d.provides),
    )


@dataclass
class World:
    clock_tick: int = 0
    entities: dict[str, Entity] = field(default_factory=dict)
    npcs: dict[str, Person] = field(default_factory=dict)
    bus: EventBus = field(default_factory=EventBus)
    _entity_seq: int = 0                  # 自动实体 id 计数(确定性)

    def hour_f(self) -> float:
        # tick 0 起 = 0:00; 一天 1440 tick
        return (self.clock_tick % 1440) / 60.0

    def entities_at(self, location_id: str) -> list[Entity]:
        return [e for e in self.entities.values()
                if e.location_id == location_id]

    def spawn_entity(self, e: Entity) -> Entity:
        if not e.entity_id:
            self._entity_seq += 1
            e.entity_id = f"auto{self._entity_seq}"
        self.entities[e.entity_id] = e
        return e

    def spawn_item_type(self, item_type: str,
                        location_id: str | None = None) -> Entity | None:
        """按 config/items 里的类型在世界生成一件实体(缺省 npc 的 home)。"""
        d = load_item_defs().get(item_type)
        if d is None:
            return None
        e = entity_from_def(d, location_id if location_id is not None else "home")
        return self.spawn_entity(e)
