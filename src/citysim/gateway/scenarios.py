"""scenarios —— 通用场景加载器(elm_lane 单一场景, M4 数据化规矩延伸)。

把 config/scenes/elm_lane.json 建成 (world, systems, rng_pool):
  - 实体: 走 config/items defs(entity_from_def) + scene 覆盖 stock/open_hours, 零手搓;
  - NPC: scene 的 personality/init/kb_extra/tell_bias(出生空白知识, 单层靠 obs 学);
  - Systems: travel 距离矩阵 + 归一化 pulses(世界侧定时脚本)。

铁律: npc 不 import world; 加载器只组装, 不做决策。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from citysim.core.config import load_config
from citysim.npc.knowledge import KnowledgeBase, Source
from citysim.npc.person import Identity, Person
from citysim.sim.loop import make_systems
from citysim.sim.pulses import normalize as _norm_pulses
from citysim.world.itemdefs import load_item_defs
from citysim.world.world import Entity, World, entity_from_def

ROOT = Path(__file__).resolve().parents[3]          # → d:\...\npc_cognition
DEFAULT_SCENE = ROOT / "config" / "scenes" / "elm_lane.json"
CFG = load_config(ROOT / "config" / "sim.toml")
_ARGS_ORDER = ("energy", "hunger", "thirst", "bladder", "fun", "hp")


def load_scene(path: str | Path = DEFAULT_SCENE,
               seed: int = 3) -> tuple[World, object, dict]:
    """读 scene json → (world, systems, rng_pool)。唯一场景入口。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    world = World()
    # TASK001 region 几何: scene 的 x/y/w/h 即世界坐标(无第二套地图)
    world.locations = {loc_id: dict(geom) for loc_id, geom in
                       data.get("locations", {}).items()}

    systems = make_systems(log=True,
                           tell_p=float(data.get("tell_p", 0.0)))
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
    for spec in data.get("entities", []):
        d = defs.get(spec["type"])
        if d is None:
            raise KeyError(f"scene 实体引用未知 item_type: {spec['type']}")
        e = entity_from_def(d, spec["at"])
        e.entity_id = spec["id"]
        if "stock" in spec:
            e.stock = int(spec["stock"])
        e.open_hours = Entity.parse_open_hours(spec.get("open_hours"))
        if "position" in spec:          # 显式锚点优先(可选)
            e.position = (float(spec["position"][0]), float(spec["position"][1]))
        world.spawn_entity(e)
    # TASK001 默认锚点: 每个 region 内按实体 id 稳定生成(显式 position 不覆盖)
    for loc_id in world.locations:
        world.layout_location(loc_id)

    # ---- NPC: 人设 + 初始知识(kb_extra) -------------------------------
    for idx, spec in enumerate(data.get("npcs", [])):
        pid = spec["id"]
        p = Person(identity=Identity(person_id=pid, name=spec["name"]),
                   location_id=spec.get("home", ""))
        p.home = spec.get("home", "")
        p.money = float(spec.get("money", 100.0))
        if "spawn" in spec:                              # 显式出生点优先
            p.position = (float(spec["spawn"][0]), float(spec["spawn"][1]))
        else:
            home_center = world.region_center(p.home)
            if home_center is not None:                  # fallback: region 中心
                p.position = home_center
        init = spec.get("init", {})
        p.set_state(**{k: float(v) for k, v in init.items() if k in _ARGS_ORDER})
        p.personality = dict(spec.get("personality", {}))
        p.tell_bias = float(spec.get("tell_bias", 1.0))
        p.kb = KnowledgeBase()
        for f in spec.get("kb_extra", []):
            p.kb.learn(subject=f["subject"], relation=f["relation"],
                       obj=f["obj"], confidence=float(f.get("confidence", 1.0)),
                       source=Source(kind="OBSERVED", ref=("scn",)), tick=0,
                       value=float(f.get("value", 0.0)))
        world.npcs[pid] = p
        rng_pool[pid] = random.Random(seed * 100 + idx)
        systems.scheduler.schedule(pid, 1, now=0)
    return world, systems, rng_pool


# 兼容入口: 现在只有单一场景, scenario 名忽略(保留给旧测试/调用方)
def build_scenario(scenario: str | None = None, seed: int = 3,
                   n_npc: int | None = None,
                   tell_p: float | None = None):
    w, s, r = load_scene(DEFAULT_SCENE, seed=seed)
    if tell_p is not None:
        s.tell_p = float(tell_p)
    return w, s, r
