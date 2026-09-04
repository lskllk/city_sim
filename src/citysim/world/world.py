"""World 容器 —— 地点/实体/NPC 注册表 + 事件总线。

世界是唯一事实源; Entity 为可变真实体。NPC Person 来自 npc/person(纯数据)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from citysim.npc.person import Person
from citysim.world.events import EventBus


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

    @property
    def is_consumable(self) -> bool:
        return "consumable" in self.tags

    @property
    def is_sleepable(self) -> bool:
        return "sleepable" in self.tags

    def provides_edible(self) -> bool:
        """M2~M4 过渡: container 经 affordances 声明 provides:edible。"""
        return self.affordances.get("provides:edible", 0.0) > 0

    def claimable_by(self, npc_id: str | None) -> bool:
        return (self.claimed_by is None or self.claimed_by == npc_id) \
            and self.stock != 0


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
