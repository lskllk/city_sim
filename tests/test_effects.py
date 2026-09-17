"""物品效果的分流 + 世界侧 op 表。

物品的效果写在 `config/items/*.json` 的 `on_start`/`on_complete` 里, 但执行者不同:

  认知侧 add_signal / set_signal / add_pending
      → `model/itemdefs.compile_effects` 编译成【不带 op 名的结构数据】,
        塞进 `Grant.pending`, 由 NPC 自己应用(`Person.intake_add` → `_apply_neutral`)。
        **所以 npc/ 不认识 op 名, 而 world 也不该有第二套 signal 实现。**
  世界侧 spawn_item / consume_self
      → 留在 `mechanism/effects.OPS`, 由 `apply_effects` 执行。

这个文件从【真实链路】验两件事, 而不是直接喂 op 给 world —— 直接喂会测到一条
生产上永远走不到的代码路径。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.core.config import load_config
from citysim.core.ports import Grant
from citysim.npc.person import Identity, Person
from citysim.world.mechanism.effects import OPS, apply_effects
from citysim.world.model.itemdefs import COGNITIVE_OPS, compile_effects
from citysim.world.world import World

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _ctx():
    world = World()
    npc = Person(identity=Identity(person_id="p", name="p"))
    ent = world.spawn_item_type("meal_simple", "home")
    return world, npc, ent


_N = [0]


def _deliver_to_npc(npc, raw_effects):
    """真实链路: JSON 原样 → compile_effects → Grant.pending → NPC 自己应用。

    handle 必须每次不同 —— NPC 按 handle 去重(同一份不重复收)。
    """
    npc_side, world_side = compile_effects(raw_effects)
    assert world_side == [], "认知侧 op 不该留给世界"
    _N[0] += 1
    npc.intake_add(Grant(handle="h%d" % _N[0], entity_id="e",
                         signal="hunger", value=0.2, duration_ticks=10,
                         pending=npc_side))


# --- 分流规则 -------------------------------------------------------------

def test_world_ops_are_exactly_the_two_spawning_ones() -> None:
    """signal 类 op 不在这里 —— 它们在 COGNITIVE_OPS, 由 NPC 自己应用。

    留着它们 = 同一件事两套实现, 而且那套永远走不到。
    """
    assert set(OPS) == {"spawn_item", "consume_self"}
    assert set(COGNITIVE_OPS) == {"add_signal", "set_signal", "add_pending"}


def test_compile_splits_both_sides() -> None:
    npc_side, world_side = compile_effects([
        {"op": "add_signal", "signal": "hunger", "delta": 0.5},
        {"op": "spawn_item", "item_type": "food_apple", "count": 1},
    ])
    assert npc_side == ({"signal": "hunger", "add": 0.5},)
    assert world_side == [{"op": "spawn_item", "item_type": "food_apple",
                           "count": 1}]


# --- 认知侧: 走 Grant 进 NPC ----------------------------------------------

def test_add_signal_reaches_npc_through_grant() -> None:
    _w, npc, _e = _ctx()
    npc.set_signals(energy=0.1)
    _deliver_to_npc(npc, [{"op": "add_signal", "signal": "energy",
                           "delta": 0.5}])
    assert npc.signal("energy") == pytest.approx(0.6)


def test_add_signal_is_clamped_by_npc() -> None:
    _w, npc, _e = _ctx()
    npc.set_signals(energy=0.95)
    _deliver_to_npc(npc, [{"op": "add_signal", "signal": "energy",
                           "delta": 0.5}])
    assert npc.signal("energy") == 1.0
    _deliver_to_npc(npc, [{"op": "add_signal", "signal": "energy",
                           "delta": -3.0}])
    assert npc.signal("energy") == 0.0


def test_set_signal_reaches_npc_through_grant() -> None:
    _w, npc, _e = _ctx()
    _deliver_to_npc(npc, [{"op": "set_signal", "signal": "energy",
                           "value": 0.6}])
    assert npc.signal("energy") == pytest.approx(0.6)


def test_add_pending_reaches_npc_and_only_known_fields() -> None:
    """字段白名单现在归 NPC(它只认自己有的 pending 字段)。"""
    _w, npc, _e = _ctx()
    npc.add_bladder_pending(0.1)
    _deliver_to_npc(npc, [{"op": "add_pending", "field": "bladder_pending",
                           "amount": 0.3}])
    assert npc.bladder_pending == pytest.approx(0.4)
    _deliver_to_npc(npc, [{"op": "add_pending", "field": "不存在的字段",
                           "amount": 0.3}])
    assert npc.bladder_pending == pytest.approx(0.4)     # 未受影响


# --- 世界侧 op -------------------------------------------------------------

def test_spawn_item_creates_at_npc_loc() -> None:
    w, npc, ent = _ctx()
    w.place_npc(npc.person_id, "home")
    n0 = len(w.entities)
    apply_effects(w, npc, ent, [{"op": "spawn_item", "item_type": "meal_simple"}])
    assert len(w.entities) == n0 + 1
    new = [e for eid, e in w.entities.items()
           if eid != ent.entity_id and "edible" in e.tags]
    assert new and new[0].location_id == "home"


def test_spawn_item_count() -> None:
    w, npc, ent = _ctx()
    w.place_npc(npc.person_id, "home")
    n0 = len(w.entities)
    apply_effects(w, npc, ent,
                  [{"op": "spawn_item", "item_type": "meal_simple",
                    "count": 3}])
    assert len(w.entities) == n0 + 3


def test_consume_self_stock_only_no_pop() -> None:
    """consume_self 只扣库存, 不自行移除实体(回收统一在完成事件之后)。"""
    w, npc, ent = _ctx()
    meal = w.spawn_item_type("meal_simple", "home")
    apply_effects(w, npc, meal, [{"op": "consume_self"}])   # stock 1 -> 0
    assert meal.stock == 0
    assert meal.entity_id in w.entities        # 不在此处 pop
    # 无限(-1)不被消耗
    disp = w.spawn_item_type("station_workbench", "home")
    apply_effects(w, npc, disp, [{"op": "consume_self"}])
    assert disp.entity_id in w.entities and disp.stock == -1


def test_unknown_world_op_is_logged_not_crashed(caplog) -> None:
    w, npc, ent = _ctx()
    with caplog.at_level("WARNING"):
        apply_effects(w, npc, ent, [{"op": "并不存在的op"}])
    assert "未知 effect op" in caplog.text


# --- interaction.py 无领域硬编码字面 --------------------------------------
def test_interaction_has_no_domain_hardcode_literal() -> None:
    p = ROOT / "src" / "citysim" / "world" / "mechanism" / "interaction.py"
    text = p.read_text(encoding="utf-8")
    for tok in ("_TAKE_FOOD", "_PLAN_ZH", "厕所", "马桶", "bladder_pending"):
        assert tok not in text, f"interaction.py 残留 {tok!r}"
