"""World 容器 —— 地点/实体/NPC 注册表 + 事件总线。

世界是唯一事实源; Entity 为可变真实体。NPC Person 来自 npc/person(纯数据)。
世界坐标 = 场景画布坐标(x/y/w/h 即几何, 没有米制、没有第二套地图);
World.locations 存 region 矩形, NPC.position/Entity.position 为连续 2D 坐标。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from citysim.npc.person import Person
from citysim.world.mechanism.events import EventBus
from citysim.world.model.itemdefs import ItemDef, load_item_defs


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





@dataclass
class Entity:
    """世界侧真实体(可变)。"""
    entity_id: str
    name: str
    tags: set[str] = field(default_factory=set)
    affordances: dict[str, float] = field(default_factory=dict)  # 信号效果
    duration_ticks: int = 30
    location_id: str = ""
    claimants: set[str] = field(default_factory=set)  # 占用者集合(可并发)
    stock: int = 1                        # 数量/剩余。★ 没有"无限"(-1)这回事:
                                          #   家具恒为 1, 货物可以多; 合并只发生在货物上。
    attrs: dict[str, Any] = field(default_factory=dict)  # 如 bladder_load
    price: float = 0.0                      # 价格(0=免费)
    owner: str = ""                         # 归属(""=无主/商店; npc_id=某人拥有)
    item_type: str = ""                     # 物品类型 id(合并同类容器/购买送货用)
    persist_empty: bool = False             # stock 归 0 不被回收(容器/货架)
    shelf_life_ticks: int = 0               # 保质期(0=不坏); 由 itemdef 带入
    expires_tick: int = 0                   # 到点变质(0=不过期); 送货/生成时打戳
    # elm_lane 开放时段: None=全天; []=永久关闭; [[start,end],...]分钟-of-day
    open_hours: list | None = None
    position: tuple[float, float] | None = None  # 空间锚点(场景单位; None=未布置)

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
    def is_furniture(self) -> bool:
        """家具: 摆下去就一直在的东西(工位/销售台/马桶…)。

        数量恒为 1、不合并、用了也不消耗 —— 所以它能被反复使用、
        并且"同时只能一个人用"(容量=stock=1: 一个马桶不会被两个人一起占)。
        """
        return "fixture" in self.tags

    @property
    def is_consumable(self) -> bool:
        """货物才会被消耗。家具永远不算 —— 哪怕定义里误打了 consumable。"""
        return "consumable" in self.tags and not self.is_furniture

    @property
    def claimed_by(self) -> str | None:
        """“谁在用”的展示用主占用者(多人并发时取 id 最小者)。

        仅是【展示兼容】字段: 真相在 `claimants` 集合里, 不要用它做仲裁。
        """
        return min(self.claimants) if self.claimants else None

    @claimed_by.setter
    def claimed_by(self, value: str | None) -> None:
        """兼容旧写法(entity.claimed_by = pid): 等价于把占用者设为仅此人。"""
        self.claimants = set() if value is None else {str(value)}

    def claimable_by(self, npc_id: str | None) -> bool:
        """还能不能被 npc_id 占用。

        ★ 定死: 容量 = stock —— 一件实体代表 stock 个可用单位,
          因此最多 stock 人可【同时】占用它。家具 stock=1 → 一次只一个人用;
          货物合并后 stock=N → 一"堆"货可被 N 人同时取(取走即减)。
        """
        if self.stock == 0:
            return False
        if npc_id is not None and npc_id in self.claimants:
            return True                       # 已经是我在用 → 继续
        return len(self.claimants) < self.stock


# ----------------------------------------------------------------------
# 物品定义 -> 真实体(从 config/items/*.json 生成, 零硬编码)
# ----------------------------------------------------------------------
def entity_from_def(d: ItemDef, location_id: str) -> Entity:
    """由 ItemDef 建一个可变 Entity。"""
    return Entity(
        entity_id="", name=d.name, tags=set(d.tags),
        affordances=dict(d.affordances), duration_ticks=d.duration_ticks,
        location_id=location_id, stock=d.stock, attrs=dict(d.attrs),
        price=d.price, item_type=d.item_type,
        persist_empty=d.persist_empty,
        shelf_life_ticks=d.shelf_life_ticks,
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
    # 公司(经营单位): id -> Company。店铺的归属写在 location["company"] 上,
    # 成交时据此把款记进它的账(见 engine._execute_buy)。
    companies: dict = field(default_factory=dict)
    # region 几何: {loc: {"x":..,"y":..,"w":..,"h":..,"name":..,"kind":..}}
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

    def is_residence(self, location_id: str) -> bool:
        """是不是"住所"(建筑类型 kind=home)。编辑器放进去的东西 = 家用物品。"""
        return str((self.locations.get(location_id) or {}).get("kind", "")) == "home"

    def is_household(self, entity, npc_id: str) -> bool:
        """★ 定死的原则: **放在某住所的东西, 该住所的所有授权人都能免费使用**。

        授权口径与门禁同源(`allowed_in`: owner / open_to / 公共) —— 能进这所
        房子的人, 就能用屋里的东西, 不看 price/owner。
        非住所(商铺/市场/公共) → False, 照旧按买卖/免费公共规则走。
        """
        loc = getattr(entity, "location_id", "") or ""
        r = self.locations.get(loc)
        if r is None or not self.is_residence(loc):
            return False
        return self.allowed_in(r, npc_id)

    def company_owner_of(self, entity) -> str:
        """这件东西归哪家公司。判据(按优先级):

        1. `entity.owner` 本身是公司 id → 归该公司(公司买货后就这么写);
        2. **家具(fixture)不继承地点公司** —— 家具归属由放置时显式决定,
           `owner=""` 就是公共(如公司门口的马桶, 谁都能用);
        3. 其余(可零售的【商品】)没有显式归属时, 默认归【所在地点的公司】。

        没有 → ""。
        """
        o = str(getattr(entity, "owner", "") or "")
        if o and o in self.companies:
            return o
        if "fixture" in tuple(getattr(entity, "tags", ()) or ()):
            return ""                      # 家具: 显式 owner(""=公共)算数
        c = str((self.locations.get(getattr(entity, "location_id", "") or "")
                 or {}).get("company", "") or "")
        return c

    def is_employee(self, company_id: str, npc_id: str) -> bool:
        """是不是这家公司的店员(拿工资的人)。"""
        comp = self.companies.get(company_id)
        if comp is None:
            return False
        return any(n == npc_id for n, _w in comp.staff)

    def free_use(self, entity, npc_id: str) -> bool:
        """★ 定死的三条归属/使用规则 —— 这个 NPC 能不能【免费直接用】它。

        1. 在【住所】里 → 归该屋; 有该屋权限的人(owner/open_to/公共)随便用。
        2. 归属为【公共】(owner=="" 且不属于任何公司) → 不管价格多少,
           任何人都能免费直接用。
        3. 归属【公司】 → 只有该公司【店员】能免费直接用;
           外人要买(price>0 走 Buy, price<=0 用不了)。
        (自己的东西当然也免费 —— 含在“住所/公共/员工”之外的单列分支里。)
        """
        # 规则 1: 家宅物品
        if self.is_household(entity, npc_id):
            return True
        # 自己的东西
        if str(getattr(entity, "owner", "") or "") == npc_id:
            return True
        # 规则 3: 公司物品 → 仅本公司店员
        cid = self.company_owner_of(entity)
        if cid:
            return self.is_employee(cid, npc_id)
        # 规则 2: 公共(无主) → 任何人、不论价格
        return str(getattr(entity, "owner", "") or "") == ""

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

    # --- 空间 helper ----------------------------------------------------

    def region_center(self, location_id: str) -> tuple[float, float] | None:
        r = self.locations.get(location_id)
        return None if r is None else _region_center(r)

    def door_point(self, location_id: str) -> tuple[float, float] | None:
        """建筑门点(寻路起点/终点)。编辑器 map 的门 > 建筑中心 > region 中心。"""
        b = ((self.map or {}).get("buildings") or {}).get(location_id)
        if isinstance(b, dict):
            doors = b.get("doors") or []
            d = doors[0] if doors else None
            if isinstance(d, (list, tuple)) and len(d) >= 2:
                return (float(d[0]), float(d[1]))
            c = b.get("center")
            if isinstance(c, (list, tuple)) and len(c) >= 2:
                return (float(c[0]), float(c[1]))
        return self.region_center(location_id)

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
        """加入世界; 没 id 的自动编号。

        id 规则: ``<itemtype>_<NNN>``(同一类型全局递增)。
        以前是 ``auto<N>`` —— 玩家在 Inspector 里看到的就是 “auto1”,
        而且和场景里的 id 不在一个命名空间, 没法对账。
        递增时要跳过已被占用的 id(场景导入的实体不参与计数)。
        """
        if not e.entity_id:
            while True:
                self._entity_seq += 1
                cand = (f"{e.item_type}_{self._entity_seq:03d}"
                        if e.item_type else f"auto{self._entity_seq}")
                if cand not in self.entities:
                    e.entity_id = cand
                    break
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
