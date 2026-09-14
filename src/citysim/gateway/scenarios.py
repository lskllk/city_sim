"""scenarios —— 通用场景加载器(elm_lane 单一场景, M4 数据化规矩延伸)。

把 config/scenes/elm_lane.json 建成 (world, systems, rng_pool):
  - 实体: 走 config/items defs(entity_from_def) + scene 覆盖 stock/open_hours, 零手搓;
  - NPC: scene 的 personality/init/memory/tell_bias(初始记忆, 单层靠 obs 学);
  - Systems: travel 距离矩阵 + 归一化 pulses(世界侧定时脚本)。

铁律: npc 不 import world; 加载器只组装, 不做决策。
"""
from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path

from citysim.core.config import load_config
from citysim.npc.person import Identity, Person
from citysim.npc.planner import ScriptedPlanner
from citysim.sim.loop import attach_replay, make_systems
from citysim.world.buildings import build_locations
from citysim.world.pulses import normalize as _norm_pulses
from citysim.world.roads import RoadGraph
from citysim.world.itemdefs import load_item_defs
from citysim.world.world import Entity, World, entity_from_def

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]          # → d:\...\npc_cognition
DEFAULT_SCENE = ROOT / "config" / "scenes" / "elm_lane.json"
CFG = load_config(ROOT / "config" / "sim.toml")
_ARGS_ORDER = ("energy", "hunger", "bladder", "hp")
# 初始记忆行允许的字段(与 Person.note 对齐; 其余忽略)
_MEM_FIELDS = frozenset({"located", "owner", "afford", "value", "price", "stock"})


def load_scene(path: str | Path = DEFAULT_SCENE,
               seed: int = 3) -> tuple[World, object, dict]:
    """读 scene json → (world, systems, rng_pool)。唯一场景入口。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    world = World()
    # 建筑: 类型库(config/buildings) + 显式几何或 面积∝容量 自动布局
    world.locations = build_locations(data)
    _materialize_missing_units(world.locations, data)
    # 画布尺寸随场景下发(编辑器导出的地图可能不是 1280x800)
    world.canvas = dict(data.get("canvas", {}))
    # 编辑器导出的原始路网/建筑(含 rot/doors), 供观察器按编辑器思路渲染
    world.map = data.get("map") or {}

    systems = make_systems(log=True,
                           tell_p=float(data.get("tell_p", CFG.tell_p)),
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
    # 注入给每个人: 决策打分要靠它算“走这一趟的代价”
    for p in world.npcs.values():
        p.set_travel_costs(costs)
    # 场景脉冲(世界侧定时)
    systems.pulses = _norm_pulses(data.get("pulses", []), CFG.ticks_per_day)

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
        if "on_complete" in spec:      # scene 覆盖完成效果(如菜摊 spawn_item×3)
            e.on_complete = [dict(x) for x in spec["on_complete"]]
        e.open_hours = Entity.parse_open_hours(spec.get("open_hours"))
        if "position" in spec:          # 显式锚点优先(可选)
            e.position = (float(spec["position"][0]), float(spec["position"][1]))
        # 同一商品(同 类型/地点/归属/售价/效果) → 库存合并, 不重复建实体
        key = (e.item_type, e.location_id, e.owner, round(e.price, 6),
               repr(e.on_complete))
        prev = merged.get(key)
        if prev is not None:
            prev.stock = -1 if (prev.stock == -1 or e.stock == -1) \
                else prev.stock + e.stock
            continue
        merged[key] = e
        world.spawn_entity(e)
    # TASK001 默认锚点: 每个 region 内按实体 id 稳定生成(显式 position 不覆盖)
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

    # ---- 初始认知(场景级): 让一批人“知道”某处的货(超市/广告/邻居说的) ----
    _seed_knowledge(world, data)

    # ---- 住所归属: NPC.home → 建筑 owner/open_to, 再封口 public ----
    # 场景未显式写 owner 时, 首个住进该房的人成为户主, 其余入 open_to。
    for pid, p in world.npcs.items():
        if p.home:
            world.bind_home(pid, p.home)
    world.resolve_access()

    # ---- 固定日计划(演示/观察): 有 plans 段就用 ScriptedPlanner 替换模板 ----
    plans = data.get("plans", {})
    if plans:
        systems.planner = ScriptedPlanner(plans)
        for pid, p in world.npcs.items():
            res = systems.planner.plan_for_person(p, 0)       # 应用当天计划
            p.set_plan(res.entries)
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

    语义: 写的是【他们的知识】而不是世界真值(与 P8 一致) —— believe < 1 时
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
                       item_type=e.item_type, believe=believe, source=src,
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
                   tell_p: float | None = None):
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
    w, s, r = load_scene(path or DEFAULT_SCENE, seed=seed)
    if tell_p is not None:
        s.tell_p = float(tell_p)
    return w, s, r
