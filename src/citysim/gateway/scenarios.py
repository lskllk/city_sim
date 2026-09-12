"""scenarios —— 通用场景加载器(elm_lane 单一场景, M4 数据化规矩延伸)。

把 config/scenes/elm_lane.json 建成 (world, systems, rng_pool):
  - 实体: 走 config/items defs(entity_from_def) + scene 覆盖 stock/open_hours, 零手搓;
  - NPC: scene 的 personality/init/memory/tell_bias(初始记忆, 单层靠 obs 学);
  - Systems: travel 距离矩阵 + 归一化 pulses(世界侧定时脚本)。

铁律: npc 不 import world; 加载器只组装, 不做决策。
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

from citysim.core.config import load_config
from citysim.npc.person import Identity, Person
from citysim.npc.planner import ScriptedPlanner
from citysim.sim.loop import attach_replay, make_systems
from citysim.world.buildings import build_locations
from citysim.world.pulses import normalize as _norm_pulses
from citysim.world.itemdefs import load_item_defs
from citysim.world.world import Entity, World, entity_from_def

ROOT = Path(__file__).resolve().parents[3]          # → d:\...\npc_cognition
DEFAULT_SCENE = ROOT / "config" / "scenes" / "elm_lane.json"
CFG = load_config(ROOT / "config" / "sim.toml")
_ARGS_ORDER = ("energy", "hunger", "thirst", "bladder", "fun", "hp")
# 初始记忆行允许的字段(与 Person.note 对齐; 其余忽略)
_MEM_FIELDS = frozenset({"located", "owner", "afford", "value", "price", "stock"})


def load_scene(path: str | Path = DEFAULT_SCENE,
               seed: int = 3) -> tuple[World, object, dict]:
    """读 scene json → (world, systems, rng_pool)。唯一场景入口。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    world = World()
    # 建筑: 类型库(config/buildings) + 显式几何或 面积∝容量 自动布局
    world.locations = build_locations(data)
    # 画布尺寸随场景下发(编辑器导出的地图可能不是 1280x800)
    world.canvas = dict(data.get("canvas", {}))
    # 编辑器导出的原始路网/建筑(含 rot/doors), 供观察器按编辑器思路渲染
    world.map = data.get("map") or {}

    systems = make_systems(log=True,
                           tell_p=float(data.get("tell_p", 0.0)))
    attach_replay(world, systems)      # 让 bus 事件(intent_failed/bought/…) 进 ui_events
    rng_pool: dict[str, random.Random] = {}

    # travel 距离矩阵(对称补齐)
    costs: dict[str, int] = {}
    for pair, n in data.get("travel", {}).get("pairs", {}).items():
        a, _, b = pair.partition("|")
        costs[f"{a}|{b}"] = int(n)
        costs[f"{b}|{a}"] = int(n)
    systems.travel_costs = costs
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
        home_region = spec.get("home", "")
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


def build_scenario(scenario: str | None = None, seed: int = 3,
                   n_npc: int | None = None,
                   tell_p: float | None = None):
    # 场景来源优先级: 显式文件路径 > 环境变量 CITYSIM_SCENE > 内置默认场景。
    # 路径既可为绝对路径, 也可相对仓库根(如 godot_editor/scene.json)。
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
