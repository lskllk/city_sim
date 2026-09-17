"""scenarios —— 场景加载器: scene JSON → (World + Systems + rng)。

把 config/scenes/elm_lane.json 建成 (world, systems, rng_pool):
  - 实体: 走 config/items defs(entity_from_def) + scene 覆盖 stock/open_hours, 零手搓;
  - NPC: scene 的 personality/init/memory/tell_bias(初始记忆, 单层靠 obs 学);
  - Systems: travel 距离矩阵(场景顶层 travel.default / travel.pairs)。

铁律: npc 不 import world; 加载器只组装, 不做决策。
"""
from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Plan, Work
from citysim.npc.person import Identity, Person
from citysim.npc.planner import ScriptedPlanner
from citysim.sim.loop import attach_replay, make_systems
from citysim.world.model.buildings import build_locations
from citysim.world.model.roads import RoadGraph
from citysim.world.model.itemdefs import load_item_defs
from citysim.world.world import Entity, World, entity_from_def

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]          # → d:\...\npc_cognition
SCENES_DIR = ROOT / "config" / "scenes"
# 默认场景【不再写死文件名】: elm_lane 只是首选, 没有就挑一个存在的。
# 以前写死一个路径 → 用户把那个文件删了, 后端在 import 时就 FileNotFoundError 闪退。
DEFAULT_SCENE = SCENES_DIR / "elm_lane.json"


def default_scene_path() -> Path | None:
    """挑一个可用的默认场景: elm_lane → scene.json → 目录里任意一个; 都没有 None。"""
    for name in ("elm_lane.json", "scene.json"):
        p = SCENES_DIR / name
        if p.is_file():
            return p
    if SCENES_DIR.is_dir():
        for f in sorted(SCENES_DIR.glob("*.json")):
            return f
    return None


# 测试自带的小场景副本: 【不依赖 config/scenes/】—— 用户随时会删/改那边,
# 测试不该跟着挂(实测: 删掉内置 demo 场景 → 一堆断言 KeyError)。
TESTS_DIR = ROOT / "tests" / "fixtures"
DEMO_SCENE = TESTS_DIR / "elm_lane.json"
NAV_SCENE = TESTS_DIR / "scenefornav.json"

CFG = load_config(ROOT / "config" / "sim.toml")
_ARGS_ORDER = ("energy", "hunger", "bladder", "hp")
# 初始记忆行允许的字段(与 Person.note 对齐; 其余忽略)
_MEM_FIELDS = frozenset({"located", "owner", "afford", "value", "price", "stock"})


def load_scene(path: str | Path | None = None,
               seed: int = 3) -> tuple[World, object, dict]:
    """读 scene json → (world, systems, rng_pool)。唯一场景入口。

    path=None(或不传) → 用 default_scene_path(): 存在的那个默认场景。
    """
    if path is None:
        path = default_scene_path()
    if path is None:
        raise FileNotFoundError(
            "config/scenes/ 里一个场景都没有 —— 请先在编辑器里导出一个场景")
    _p = Path(path)
    if not _p.is_file():
        raise FileNotFoundError("场景文件不存在: %s" % _p)
    data = json.loads(_p.read_text(encoding="utf-8"))
    world = World()
    # 建筑: 类型库(config/buildings) + 显式几何或 面积∝容量 自动布局
    world.locations = build_locations(data)
    _materialize_missing_units(world.locations, data)
    # 公司(场景里声明的 → 无头也能跑): 店铺归属 / 账 / 营业时间 / 招聘启事
    _load_companies(world, data)
    # 画布尺寸随场景下发(编辑器导出的地图可能不是 1280x800)
    world.canvas = dict(data.get("canvas", {}))
    # 编辑器导出的原始路网/建筑(含 rot/doors), 供观察器按编辑器思路渲染
    world.map = data.get("map") or {}

    systems = make_systems(log=True,
                           tell_p=float(data.get("tell_p", CFG.tell_p)),
                           listen_p=float(data.get("listen_p", CFG.listen_p)),
                           tell_same_home=float(data.get(
                               "tell_same_home", CFG.tell_same_home)),
                           tell_stranger=float(data.get(
                               "tell_stranger", CFG.tell_stranger)),
                           roads=RoadGraph(world.map, CFG.move_m_per_tick),
                           seed=int(seed))
    attach_replay(world, systems)      # 让 bus 事件(intent_failed/bought/…) 进 ui_events
    rng_pool: dict[str, random.Random] = {}

    # travel 距离矩阵(对称补齐)
    costs: dict[str, int] = {}
    for pair, n in data.get("travel", {}).get("pairs", {}).items():
        a, _, b = pair.partition("|")
        costs[f"{a}|{b}"] = int(n)
        costs[f"{b}|{a}"] = int(n)
    systems.travel_costs = costs
    systems.travel_default = int((data.get("travel") or {}).get("default", 0) or 0)
    # ★ 楼层单元 ↔ 父建筑: 编辑器导出的矩阵只有【建筑级】pair(bld_009|bld_010),
    #   但人和货常常住在【楼层单元】里(bld_009_f3) → 直接查表查不到 →
    #   brain 会退化用常量 DEFAULT_TRAVEL_TICKS(30) ✗✗ →
    #   "哪家店更近"在打分里完全没有区别(用户实测: 又近又便宜的梨不吸引人)。
    #   这里按父建筑把矩阵展开到【所有地点对】(12 个地点 → 132 对, 可忽略)。
    units = {uid: str((loc or {}).get("part_of") or uid)
             for uid, loc in world.locations.items()}
    resolved: dict[str, int] = {}
    for a in world.locations:
        for b in world.locations:
            if a == b:
                continue
            ba, bb = units.get(a, a), units.get(b, b)
            v = costs.get(f"{ba}|{bb}") or costs.get(f"{bb}|{ba}")
            if v is None:
                continue
            lo, hi = (a, b) if a <= b else (b, a)
            resolved[f"{lo}|{hi}"] = int(v)
    if resolved:
        costs = resolved
    # 注: 位移成本矩阵要等【NPC 建好之后】才能注入(见文件末尾) ——
    # 这里 world.npcs 还是空的, 以前那句循环等于什么都没做 ✗。
    # 后果: 打分里查到的 travel tick 全是常量 30,
    #       "哪家店更近"在决策里完全没有区别。

    # ---- 实体: itemdefs + scene 覆盖 -----------------------------------
    defs = load_item_defs()
    merged: dict[tuple, Entity] = {}      # 同一商品 → 合并, 不重复建实体
    for spec in data.get("entities", []):
        d = defs.get(spec["type"])
        if d is None:
            raise KeyError(f"scene 实体引用未知 item_type: {spec['type']}")
        e = entity_from_def(d, spec["at"])
        e.entity_id = spec["id"]
        if "stock" in spec:
            e.stock = int(spec["stock"])
        if "owner" in spec:            # 归属 id(person_id/company_id; 缺省=""公共)
            e.owner = str(spec["owner"])
        if "duration_ticks" in spec:   # scene 覆盖交互时长(如长时看电视)
            e.duration_ticks = int(spec["duration_ticks"])
        if "price" in spec:            # scene 覆盖售价(商店)
            e.price = float(spec["price"])
        if "persist_empty" in spec:    # 容器/货架: stock 归 0 不回收
            e.persist_empty = bool(spec["persist_empty"])
        e.open_hours = Entity.parse_open_hours(spec.get("open_hours"))
        if "position" in spec:          # 显式锚点优先(可选)
            e.position = (float(spec["position"][0]), float(spec["position"][1]))
        # 同一商品(同 类型/地点/归属/售价) → 库存合并, 不重复建实体
        key = (e.item_type, e.location_id, e.owner, round(e.price, 6))
        prev = merged.get(key)
        if prev is not None:
            prev.stock = -1 if (prev.stock == -1 or e.stock == -1) \
                else prev.stock + e.stock
            continue
        merged[key] = e
        world.spawn_entity(e)
    # 默认锚点: 每个 region 内按实体 id 稳定生成(显式 position 不覆盖)
    for loc_id in world.locations:
        world.layout_location(loc_id)

    # ---- NPC: 人设 + 初始记忆(memory 段, 出生空白, 单层靠 obs 学) ------
    for idx, spec in enumerate(data.get("npcs", [])):
        pid = spec["id"]
        home_region = _resolve_home(spec.get("home", ""), world.locations)
        extra_traits = spec.get("traits") or {}
        p = Person(identity=Identity(person_id=pid, name=spec["name"],
                                     gender=str(spec.get("gender", "")),
                                     birthday=str(spec.get("birthday", "")),
                                     traits={"role": str(spec.get("role", "")),
                                             **dict(extra_traits)}),
                   home=home_region,
                   money=float(spec.get("money", 100.0)),
                   personality=spec.get("personality", {}),
                   tell_bias=float(spec.get("tell_bias", 1.0)))
        world.place_npc(pid, home_region)
        init = spec.get("init", {})
        p.set_signals(**{k: float(v) for k, v in init.items() if k in _ARGS_ORDER})
        # 初始记忆: {item_id: {located/afford/value/price/stock/owner/believe}}
        for item_id, rec in (spec.get("memory") or {}).items():
            if not isinstance(rec, dict):
                continue
            fields = {k: v for k, v in rec.items() if k in _MEM_FIELDS}
            p.note(str(item_id), tick=0,
                   believe=float(rec.get("believe", 1.0)), **fields)
        world.npcs[pid] = p
        rng_pool[pid] = random.Random(seed * 100 + idx)

    # ---- 语义层: 注入“npc_id -> 名字”(渲染“王哥说…”用; npc 层不许 import world) ----
    _names = {pid: _p.name for pid, _p in world.npcs.items()}
    for _p in world.npcs.values():
        _p.set_name_lookup(lambda pid, _n=_names: _n.get(str(pid), ""))

    # ---- 初始认知(场景级): 让一批人“知道”某处的货(超市/广告/邻居说的) ----
    _seed_knowledge(world, data)

    # ---- 住所归属: NPC.home → 建筑 owner/open_to, 再封口 public ----
    # 场景未显式写 owner 时, 首个住进该房的人成为户主, 其余入 open_to。
    for pid, p in world.npcs.items():
        if p.home:
            world.bind_home(pid, p.home)
    world.resolve_access()

    # ---- 固定日计划(演示/观察): 场景写了 plans 段就装上 ScriptedPlanner ----
    plans = data.get("plans", {})
    if plans:
        systems.planner = ScriptedPlanner(plans)
        for pid, p in world.npcs.items():
            p.assign(Plan(  # 应用当天计划
                systems.planner.plan_for_person(p, 0)))
    # ---- 位移成本矩阵 + 【可闲逛的公共建筑】(建完所有 NPC 之后再注入) ----
    #   places = 所有【非住所】地点 id。闲逛时从里面随机选一个走过去。
    places = [lid for lid in sorted(world.locations)
              if not world.is_residence(lid)]
    for _p in world.npcs.values():
        _p.set_travel_costs(costs)
        _p.set_places(places)
    # 公司预置员工(作者直选): 要等【实体 + NPC】都建好才能绑工位/算岗位。
    _bind_company_staff(world, data)
    return world, systems, rng_pool


# 兼容入口: 现在只有单一场景, scenario 名忽略(保留给旧测试/调用方)
def _resolve_scene_path(raw: str) -> Path | None:
    """把场景路径解析为文件: 绝对/相对当前目录 → 相对仓库根。找不到返回 None。"""
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return p
    alt = ROOT / raw
    return alt if alt.is_file() else None


def _clock_minutes(v, default: int) -> int:
    """"HH:MM" → 当天分钟(0..1440, 24:00 = 1440); int 直接用; 非法回 default。"""
    if isinstance(v, int):
        return v
    s = str(v or "").strip()
    hh, sep, mm = s.partition(":")
    if sep and hh.isdigit() and mm.isdigit():
        h, m = int(hh), int(mm)
        if 0 <= h <= 24 and 0 <= m < 60:
            return h * 60 + m
    return int(default)


def _load_companies(world: World, data: dict) -> None:
    """场景里声明的公司(编辑器可编) —— 让场景【无头也能跑】(有店主/岗位/交易)。

    shape:
      "companies": [
        {"id":"org_x", "name":"甲店", "shops":["bld_004"], "cash":1000,
         "open":"08:00", "close":"19:00", "wage_per_hour":10,
         "hiring_slots":2, "slots":2, "restock_to":60}
      ]
    兼容旧的 int 写法 open_minute/close_minute。
    """
    from citysim.world.model.companies import Company
    for spec in (data.get("companies") or []):
        if not isinstance(spec, dict):
            continue
        shops = tuple(str(s) for s in (spec.get("shops") or []))
        cid = str(spec.get("id") or ("org_%s" % (shops[0] if shops else "x")))
        slots = int(spec.get("hiring_slots", 0))
        world.companies[cid] = Company(
            company_id=cid, name=str(spec.get("name", cid)),
            cash=float(spec.get("cash", 1000.0)),
            owner=str(spec.get("owner", "")),
            kind=str(spec.get("kind", "retail")),
            produces_item=str(spec.get("produces_item", "")),
            shops=shops,
            open_minute=_clock_minutes(spec.get("open"),
                                       int(spec.get("open_minute", 480))),
            close_minute=_clock_minutes(spec.get("close"),
                                        int(spec.get("close_minute", 1140))),
            wage_per_hour=float(spec.get("wage_per_hour", 10.0)),
            hiring_open=bool(spec.get("hiring_open", slots > 0)),
            hiring_slots=slots,
            slots=int(spec.get("slots", 2)),
            restock_to=int(spec.get("restock_to", 60)))
        for sid in shops:
            if sid in world.locations:
                world.locations[sid]["company"] = cid


def _bind_company_staff(world: World, data: dict) -> None:
    """把公司预置的【员工】绑好(作者直选 = 上帝模式, 不等 hire_minute)。

    spec 里: "staff": ["npc_a", {"npc":"npc_b", "station":"station_counter_001",
                            "wage": 8}]   ← wage 不给 = 跟公司时薪(comp.wage_per_hour)
    · 给了 station 就用它; 没给就自动挑公司第一个【空着的销售台】;
    · 写 work 绑定 + 角色 + 员工名单(和运行期 hire_at 一样)。
    """
    from citysim.world.econ.company import vacant_counters
    for spec in (data.get("companies") or []):
        if not isinstance(spec, dict):
            continue
        comp = world.companies.get(str(spec.get("id") or ""))
        if comp is None:
            continue
        staff = list(comp.staff)
        for entry in (spec.get("staff") or []):
            nid = str(entry.get("npc") if isinstance(entry, dict) else entry)
            npc = world.npcs.get(nid)
            if npc is None:
                continue
            station = (str(entry.get("station", ""))
                       if isinstance(entry, dict) else "")
            # 逐人时薪: 场景里写了就用, 没写跟公司默认
            wage = float(comp.wage_per_hour)
            if isinstance(entry, dict) and entry.get("wage") is not None:
                wage = float(entry["wage"])
            if not station:
                vac = vacant_counters(world, comp)
                station = vac[0][1].entity_id if vac else ""
            shop_id = comp.shops[0] if comp.shops else ""
            if station:
                ent = world.entities.get(station)
                if ent is not None and ent.location_id in comp.shops:
                    shop_id = ent.location_id
            npc.assign(Work(comp.company_id, shop_id, station,
                            comp.open_minute, comp.close_minute, wage,
                            role="worker"))
            staff.append((nid, wage))
        comp.staff = tuple(staff)


def _materialize_missing_units(locations: dict, data: dict) -> int:
    """补出【场景引用了、但 locations 里没导出】的楼层单元。

    典型来源: 编辑器里先把楼层数调到 10 点了「填满住户」, 又把楼层数减回 6 再导出 ——
    楼上那几层的人还在 npc.home 里, 对应的地点却没了。
    直接让他们落在幽灵地点上会: 没床没饭 / 占用统计数不到人。
    这里按父建筑补出该单元(几何/容量/类型照搬, part_of 指向父建筑),
    比“硬塞进父建筑”更忠于数据意图(每层仍是一个独立的家)。
    """
    wanted: set[str] = set()
    for spec in data.get("npcs", []):
        if isinstance(spec, dict):
            wanted.add(str(spec.get("home", "")))
    for ent in data.get("entities", []):
        if isinstance(ent, dict):
            wanted.add(str(ent.get("at", "")))
    made = 0
    for ref in sorted(wanted):
        if not ref or ref in locations:
            continue
        head, sep, tail = ref.rpartition("_f")
        if not (sep and tail.isdigit() and head in locations):
            continue
        parent = locations[head]
        loc = dict(parent)
        loc["part_of"] = head
        loc["name"] = "%s · %s层" % (parent.get("name", head), tail)
        loc["owner"] = ""          # 每层独立成户: 不继承父建筑的归属
        loc["open_to"] = []
        loc["public"] = None       # 由 resolve_access 按“有无人”重新判定
        locations[ref] = loc
        made += 1
        log.warning("补出缺失的楼层地点: %s (父 %s)", ref, head)
    return made


def _seed_knowledge(world, data: dict) -> int:
    """场景级【初始认知】: 一次让一批 NPC 知道某个地点里的货。

    没有这个的话, 只能逐个 NPC 手写 memory —— 百人场景不现实。

    scene JSON:
      "knowledge": [
        {"who": "all" | "unit" | ["npc_a", ...],
         "unit": "bld_008_f1",            // who="unit" 时: 住在这个地址的人
         "from": "bld_004",               // 关于哪个地点的货(必须是已存在的 location)
         "items": [],                     // 空 = 该地点全部实体; 否则按 item_type / entity_id 过滤
         "believe": 0.8}                  // 这是“听说”而不是亲眼所见 → 打折
      ]

    who 三种写法:
      "all"    —— 所有人(商铺打广告)
      "unit"   —— **住在 unit 这个地址的人**(编辑器里“让这一家人知道”):
                  按 home 展开 → 住户改了也不用改数据
      [id,...] —— 显式名单

    语义: 写的是【他们的知识】而不是世界真值 —— believe < 1 时
    他们会拿这条记忆当参考, 但不如亲眼所见那么笃定。
    """
    rules = data.get("knowledge") or []
    if not isinstance(rules, list):
        return 0
    seeded = 0
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        who = rule.get("who", "all")
        if who == "unit":
            unit = str(rule.get("unit", rule.get("from", "")))
            ids = sorted(pid for pid, p in world.npcs.items()
                         if p.home == unit)
        elif who in ("all", None, ""):
            ids = sorted(world.npcs)
        else:
            ids = [str(x) for x in who]
        loc = str(rule.get("from", ""))
        want = {str(x) for x in (rule.get("items") or [])}
        believe = float(rule.get("believe", 0.8))
        ents = [e for e in sorted(world.entities.values(), key=lambda x: x.entity_id)
                if e.location_id == loc
                and (not want or e.item_type in want or e.entity_id in want)]
        if not ents:
            log.warning("knowledge: 地点 %r 没有可告知的物件, 跳过", loc)
            continue
        for pid in ids:
            p = world.npcs.get(pid)
            if p is None:
                continue
            src = "ad:%s" % loc       # 来源可追溯: 将来“到店发现不对”能追到是哪块招牌说的
            for e in ents:
                afford, value = next(iter(e.affordances.items()), ("", 0.0))
                p.note(e.entity_id, tick=0, located=e.location_id,
                       owner=e.owner, afford=afford, value=float(value),
                       price=e.price, stock=e.stock,
                       item_type=e.item_type, tags=e.tags,
                       believe=believe, source=src,
                       shelf_life_ticks=int(e.shelf_life_ticks))
                seeded += 1
    if seeded:
        log.info("knowledge: 注入 %d 条初始记忆", seeded)
    return seeded


def _resolve_home(home: str, locations: dict) -> str:
    """把 npc.home 解析成一个【真实存在】的地点(补不出单元时的兜底)。

    父建筑存在 → 回退到父建筑; 都没有 → ""(无住所, 但至少是诚实的)。
    """
    if not home or home in locations:
        return home
    head, sep, tail = home.rpartition("_f")
    if sep and tail.isdigit() and head in locations:
        log.warning("住所楼层不存在: %s → 回退到父建筑 %s", home, head)
        return head
    log.warning("住所不存在: %s → 置为空住所", home)
    return ""


def build_scenario(scenario: str | None = None, seed: int = 3,
                   n_npc: int | None = None,
                   tell_p: float | None = None,
                   listen_p: float | None = None,
                   tell_same_home: float | None = None,
                   tell_stranger: float | None = None):
    # 场景来源优先级: 显式文件路径 > 环境变量 CITYSIM_SCENE > 内置默认场景。
    # 路径既可为绝对路径, 也可相对仓库根(如 godot/scene.json)。
    path = _resolve_scene_path(str(scenario)) if scenario else None
    if path is None:
        env = os.environ.get("CITYSIM_SCENE", "").strip()
        if env:
            path = _resolve_scene_path(env)
            if path is None:
                import sys
                print(f"[scenarios] CITYSIM_SCENE 指向的文件不存在: {env}"
                      f" (相对仓库根: {ROOT}); 回退默认场景", file=sys.stderr)
    if path is None:
        path = default_scene_path()
    if path is None:
        raise FileNotFoundError(
            "config/scenes/ 里一个场景文件都没有 —— 请先在编辑器里导出一个场景")
    w, s, r = load_scene(path, seed=seed)
    if tell_p is not None:
        s.tell_p = float(tell_p)
    if listen_p is not None:
        s.listen_p = float(listen_p)
    if tell_same_home is not None:
        s.tell_same_home = float(tell_same_home)
    if tell_stranger is not None:
        s.tell_stranger = float(tell_stranger)
    return w, s, r
