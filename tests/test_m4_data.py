"""M4 DoD —— 物品/动作/副作用数据化。

覆盖:
  - config/items 加载(含 电视/饮水机 新 JSON)
  - entity_from_def / spawn_item_type(零硬编码建实体)
  - effects op 表(5 个 op) + 马桶 on_complete 数据化(清膀胱)
  - 集成: 电视(fun+0.4)、饮水机(thirst+0.6) 不改 Python 即被 NPC 使用
  - grep: 源码无 _TAKE_FOOD / 中文物品名作为 Python 字面量
"""
from __future__ import annotations

import random
from pathlib import Path

from citysim.core.config import load_config
from citysim.npc.person import Identity, Person
from citysim.sim.loop import attach_replay, make_systems, run_tick
from citysim.world.effects import OPS, apply_effects
from citysim.world.itemdefs import load_item_defs
from citysim.world.world import World, entity_from_def

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")
ITEMS_DIR = ROOT / "config" / "items"
SRC = ROOT / "src" / "citysim"

CHINESE_ITEM_NAMES = ["马桶", "简餐", "电视", "饮水机", "冰箱", "床"]


# --- 物品定义加载 -----------------------------------------------------
def test_loads_all_item_defs() -> None:
    defs = load_item_defs(ITEMS_DIR)
    assert {"tv", "water_dispenser", "bed_basic", "toilet",
            "fridge", "meal_simple"} <= set(defs)
    assert "edible" in defs["meal_simple"].tags
    assert defs["toilet"].on_complete[0]["op"] == "set_signal"
    assert defs["fridge"].provides == ("meal_simple",)
    assert defs["water_dispenser"].stock == -1     # 无限饮水机
    assert defs["tv"].affordances["fun"] == 0.4
    assert defs["water_dispenser"].affordances["thirst"] == 0.6


def test_entity_from_def_sets_on_complete_and_marker() -> None:
    defs = load_item_defs(ITEMS_DIR)
    toilet = entity_from_def(defs["toilet"], "home")
    assert toilet.on_complete and "toilet" in toilet.tags
    fridge = entity_from_def(defs["fridge"], "home")
    assert fridge.provides == ["meal_simple"]
    # m5-rectify 12: def 实体不再往 affordances 塞 provides:edible 假键
    assert "provides:edible" not in fridge.affordances


# --- effects op 表 ----------------------------------------------------
def _ctx():
    world = World()
    npc = Person(identity=Identity(person_id="p", name="p"))
    ent = world.spawn_item_type("tv", "home")
    return world, npc, ent


def test_ops_registry_has_first_five() -> None:
    assert {"set_signal", "add_signal", "clear_pending",
            "spawn_item", "consume_self"} <= set(OPS)


def test_apply_set_signal_and_clear_pending() -> None:
    world, npc, ent = _ctx()
    npc.bladder_pending = 0.7
    apply_effects(world, npc, ent, [
        {"op": "set_signal", "signal": "bladder", "value": 1.0},
        {"op": "clear_pending", "field": "bladder_pending"},
    ])
    assert npc.signals["bladder"] == 1.0
    assert npc.bladder_pending == 0.0


def test_apply_add_signal_clamped() -> None:
    world, npc, ent = _ctx()
    npc.set_state(fun=0.9)
    apply_effects(world, npc, ent,
                  [{"op": "add_signal", "signal": "fun", "value": 0.5}])
    assert npc.signals["fun"] == 1.0


def test_apply_spawn_item_and_consume_self() -> None:
    world, npc, ent = _ctx()
    n0 = len(world.entities)
    apply_effects(world, npc, ent,
                  [{"op": "spawn_item", "item_type": "meal_simple"}])
    assert len(world.entities) == n0 + 1          # 生成了一餐
    meal = world.spawn_item_type("meal_simple", "home")
    apply_effects(world, npc, meal, [{"op": "consume_self"}])
    assert meal.stock == 0
    assert meal.entity_id in world.entities      # m5-rectify 03: 回收统一在完成事件后


def test_toilet_on_complete_is_data_driven() -> None:
    """用 JSON 马桶跑真: 低膀胱 NPC 如厕后膀胱回满、pending 清空(效果路径)。"""
    world = World()
    world.spawn_item_type("toilet", "home")
    npc = Person(identity=Identity(person_id="p", name="p"), location_id="home")
    npc.set_state(bladder=0.05)
    npc.bladder_pending = 0.4
    world.npcs["p"] = npc
    systems = make_systems()
    systems.scheduler.schedule("p", 1, now=0)
    for _ in range(20):
        run_tick(world, systems, CFG, {"p": random.Random(1)})
    assert npc.signals["bladder"] == 1.0
    assert npc.bladder_pending == 0.0


# --- 集成: 电视 / 饮水机(不改 Python 即用) ---------------------------
def _npc_scene(item_type: str, **start):
    world = World()
    world.spawn_item_type(item_type, "home")
    npc = Person(identity=Identity(person_id="p", name="p"), location_id="home")
    if start:
        npc.set_state(**start)
    world.npcs["p"] = npc
    systems = make_systems(log=True)
    attach_replay(world, systems)
    systems.scheduler.schedule("p", 1, now=0)
    return world, systems, {"p": random.Random(1)}, npc


def test_npc_uses_tv_from_json() -> None:
    world, systems, rng_pool, npc = _npc_scene("tv", fun=0.2)
    for _ in range(90):
        run_tick(world, systems, CFG, rng_pool)
    assert npc.signals["fun"] > 0.5               # 看电视 fun 回升


def test_npc_drinks_water_from_json() -> None:
    world, systems, rng_pool, npc = _npc_scene("water_dispenser", thirst=0.2)
    for _ in range(60):
        run_tick(world, systems, CFG, rng_pool)
    assert npc.signals["thirst"] > 0.6            # 喝饱


def test_fridge_chain_produces_meal_from_json() -> None:
    """JSON 冰箱(provides: meal_simple): 取→吃链产出的餐来自物品定义而非代码。"""
    world, systems, rng_pool, npc = _npc_scene("fridge", hunger=0.2)
    for _ in range(90):
        run_tick(world, systems, CFG, rng_pool)
    assert npc.signals["hunger"] > 0.5            # 吃到 JSON 简餐 → 饱了
    assert not any("edible" in e.tags and e.stock == 0
                   for e in world.entities.values())  # 无吃完残留(无泄漏)


# --- grep 硬编码检查 --------------------------------------------------
def _code_only(p: Path) -> str:
    """去掉注释(# 之后)与三引号 docstring 段, 只留代码/字符串面。"""
    lines = p.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    in_doc = False
    for raw in lines:
        stripped = raw.strip()
        # 三引号 docstring 开关
        if stripped.startswith(('"""', "'''")):
            if stripped.count('"""') + stripped.count("'''") >= 2 \
                    and not in_doc:
                continue                      # 单行 docstring
            in_doc = not in_doc
            continue
        if in_doc:
            continue
        code = raw.split("#", 1)[0]           # 去掉行注释
        if code.strip():
            out.append(code)
    return "\n".join(out)


def test_no_take_food_or_chinese_item_literal_in_src() -> None:
    bad = []
    for p in SRC.rglob("*.py"):
        # gateway = 展示/观察外围(同 tools 定位), 场景家具中文名是展示数据,
        # 非内核物品字面; 内核目录仍全查。
        if "gateway" in p.parts:
            continue
        text = _code_only(p)
        if "_TAKE_FOOD" in text:
            bad.append(f"{p}: _TAKE_FOOD")
        for name in CHINESE_ITEM_NAMES:
            if name in text:
                bad.append(f"{p}: 中文物品名 {name}")
    assert bad == []
