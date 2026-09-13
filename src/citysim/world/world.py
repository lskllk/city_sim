"""World 容器 —— 地点/实体/NPC 注册表 + 事件总线。

世界是唯一事实源; Entity 为可变真实体。NPC Person 来自 npc/person(纯数据)。
TASK001: 世界坐标 = scene 画布坐标(x/y/w/h 即 geometry, 无米制、无第二套地图);
World.locations 存 region 矩形, NPC.position/Entity.position 为连续 2D 坐标。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from citysim.npc.person import Person
from citysim.world.events import EventBus
from citysim.world.itemdefs import ItemDef, load_item_defs


def _region_center(rect: dict) -> tuple[float, float]:
    return (rect["x"] + rect["w"] / 2.0, rect["y"] + rect["h"] / 2.0)


def _stable_unit(s: str, salt: int) -> float:
    """确定性伪随机 0..1(同一实体永得同一相对位, 与数量/顺序无关)。"""
    h = 2166136261 ^ salt
    for ch in s:
        h = (h ^ ord(ch)) * 16777619 & 0xFFFFFFFF
    return ((h >> 8) % 10000) / 10000.0


def _default_anchor(rect: dict, entity_id: str) -> tuple[float, float]:
    """region 内稳定默认锚点: 用实体 id 的确定性哈希, 落在矩形边距内。"""
    margin_x = min(30.0, rect["w"] / 4.0)
    margin_y = min(30.0, rect["h"] / 4.0)
    ix = margin_x + _stable_unit(entity_id, 11) * max(0.0, rect["w"] - 2 * margin_x)
    iy = margin_y + _stable_unit(entity_id, 29) * max(0.0, rect["h"] - 2 * margin_y)
    return (round(rect["x"] + ix, 3), round(rect["y"] + iy, 3))


def lerp(a: tuple[float, float], b: tuple[float, float],
         t: float) -> tuple[float, float]:
    """线性插值(t 应已 clamp 0..1; travel 连续位置用)。"""
    t = max(0.0, min(1.0, float(t)))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)



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
    on_start: list[dict] = field(default_factory=list)       # M4 数据化效果
    on_complete: list[dict] = field(default_factory=list)    # M4 数据化效果
    price: float = 0.0                      # 价格(0=免费)
    owner: str = ""                         # 归属(""=无主/商店; npc_id=某人拥有)
    item_type: str = ""                     # 物品类型 id(合并同类容器/购买送货用)
    persist_empty: bool = False             # stock 归 0 不被回收(容器/货架)
    # elm_lane 开放时段: None=全天; []=永久关闭; [[start,end],...]分钟-of-day
    open_hours: list | None = None
    position: tuple[float, float] | None = None  # TASK001 空间锚点(scene 单位; None=未布置)

    def is_open_now(self, hour_f: float) -> bool:
        """当前是否营业。hour_f: 0..24 (含跨天则 mod 1440)。"""
        if self.open_hours is None:
            return True
        if not self.open_hours:
            return False
        minute = int(round(hour_f * 60)) % 1440
        return any(int(s) <= minute < int(e)
                   for s, e in self.open_hours)

    @staticmethod
    def parse_open_hours(spec) -> list | None:
        """'HH:MM-HH:MM,HH:MM-HH:MM' | 'closed' | None -> 分钟窗口 or None/[]。"""
        if spec is None or str(spec).strip() == "":
            return None
        if isinstance(spec, str) and spec.strip().lower() == "closed":
            return []
        if isinstance(spec, list):      # 已是 [[s,e],...]
            return spec
        out = []
        for part in str(spec).split(","):
            part = part.strip()
            if not part:
                continue
            a, _, b = part.partition("-")
            a = int(a.split(":")[0]) * 60 + int(a.split(":")[1])
            b = int(b.split(":")[0]) * 60 + int(b.split(":")[1])
            out.append([a, b])
        return out or []

    @property
    def is_consumable(self) -> bool:
        return "consumable" in self.tags

    @property
    def is_sleepable(self) -> bool:
        return "sleepable" in self.tags

    def claimable_by(self, npc_id: str | None) -> bool:
        return (self.claimed_by is None or self.claimed_by == npc_id) \
            and self.stock != 0


# ----------------------------------------------------------------------
# 物品定义 -> 真实体(M4: 从 config/items/*.json 生成, 零硬编码)
# ----------------------------------------------------------------------
def entity_from_def(d: ItemDef, location_id: str) -> Entity:
    """由 ItemDef 建一个可变 Entity。"""
    return Entity(
        entity_id="", name=d.name, tags=set(d.tags),
        affordances=dict(d.affordances), duration_ticks=d.duration_ticks,
        location_id=location_id, stock=d.stock, attrs=dict(d.attrs),
        interruptible=d.interruptible,
        on_start=list(d.on_start), on_complete=list(d.on_complete),
        price=d.price, item_type=d.item_type,
        persist_empty=d.persist_empty,
    )


@dataclass
class World:
    clock_tick: int = 0
    entities: dict[str, Entity] = field(default_factory=dict)
    npcs: dict[str, Person] = field(default_factory=dict)
    _npc_region: dict[str, str] = field(default_factory=dict)  # npc_id -> 逻辑 region(真实位置归 World)
    bus: EventBus = field(default_factory=EventBus)
    _entity_seq: int = 0                  # 自动实体 id 计数(确定性)
    locations: dict[str, dict] = field(default_factory=dict)
    # TASK001 region 几何: {loc: {"x":..,"y":..,"w":..,"h":..,"name":..,"kind":..}}
    # 来自 scene json 的 x/y/w/h, 直接作为世界坐标; 未注册 region = 无空间语义

    # --- NPC 逻辑位置(真实位置归 World; Person 不背坐标)------------
    def place_npc(self, npc_id: str, region: str) -> None:
        self._npc_region[npc_id] = region

    def loc_of(self, npc_id: str) -> str:
        return self._npc_region.get(npc_id, "")

    def hour_f(self) -> float:
        # tick 0 起 = 0:00; 一天 1440 tick
        return (self.clock_tick % 1440) / 60.0

    def entities_at(self, location_id: str) -> list[Entity]:
        return [e for e in self.entities.values()
                if e.location_id == location_id]

    # --- 建筑进入权限(owner/open_to/capacity) --------------------------
    def occupants(self, location_id: str) -> int:
        """当前在该 region 内的 NPC 数(旅行中尚未落地的不算)。"""
        return sum(1 for pid in self.npcs
                   if self._npc_region.get(pid) == location_id)

    def bind_home(self, npc_id: str, home: str) -> None:
        """把 NPC 的住所登记到建筑: 首个为户主, 其余进 open_to。"""
        r = self.locations.get(home)
        if r is None:
            return
        owner = str(r.get("owner", ""))
        if owner == "":
            r["owner"] = npc_id
        elif owner != npc_id:
            extra = list(r.get("open_to") or [])
            if npc_id not in extra:
                extra.append(npc_id)
            r["open_to"] = extra

    def resolve_access(self) -> None:
        """未显式指定 public 的地点: 有主/有名单=私人, 否则公共。"""
        for r in self.locations.values():
            if r.get("public") is None:
                r["public"] = not (r.get("owner") or r.get("open_to"))

    def is_public(self, r: dict) -> bool:
        """建筑是否公共(未 resolve 时按 owner/open_to 判定)。"""
        p = r.get("public")
        if p is not None:
            return bool(p)
        return not (r.get("owner") or r.get("open_to"))

    def allowed_in(self, r: dict, npc_id: str) -> bool:
        if self.is_public(r):
            return True
        if npc_id == r.get("owner", ""):
            return True
        return npc_id in (r.get("open_to") or [])

    def entry_check(self, location_id: str, npc_id: str) -> tuple[bool, str]:
        """可否进入某建筑 → (ok, 失败原因)。未注册 region 不设限。"""
        r = self.locations.get(location_id)
        if r is None:
            return True, ""
        if not self.allowed_in(r, npc_id):
            return False, "无权进入"
        cap = int(r.get("capacity", 0) or 0)
        if cap > 0 and self.occupants(location_id) >= cap:
            return False, "已满"
        return True, ""

    # --- TASK001 空间 helper ------------------------------------------
    def region_rect(self, location_id: str) -> dict | None:
        return self.locations.get(location_id)

    def region_center(self, location_id: str) -> tuple[float, float] | None:
        r = self.locations.get(location_id)
        return None if r is None else _region_center(r)

    def layout_location(self, location_id: str) -> None:
        """给某 region 内全部实体写入稳定默认锚点(显式 position 不覆盖)。

        幂等、确定性: 锚点由实体 id 哈希决定, 与数量/顺序无关。
        """
        r = self.locations.get(location_id)
        if r is None:
            return
        for e in self.entities_at(location_id):
            if e.position is None:
                e.position = _default_anchor(r, e.entity_id or e.name or "?")

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
