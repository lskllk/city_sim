"""testm4 A 组 —— 效果解释器 op 表单测。

首批恰好 5 个 op; 每个 op 精确断言(含 clamp 边界 / 白名单)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.core.config import load_config
from citysim.npc.person import Identity, Person
from citysim.world.effects import OPS, apply_effects
from citysim.world.world import World

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")

ALLOWED_OPS = {"set_signal", "add_signal", "clear_pending",
               "add_pending", "spawn_item", "consume_self"}


def _ctx():
    world = World()
    npc = Person(identity=Identity(person_id="p", name="p"))
    ent = world.spawn_item_type("tv", "home")
    return world, npc, ent


def test_exactly_ops_registered() -> None:
    assert set(OPS) == ALLOWED_OPS


def test_set_signal() -> None:
    w, npc, ent = _ctx()
    npc.set_signals(energy=0.1)
    apply_effects(w, npc, ent,
                  [{"op": "set_signal", "signal": "energy", "value": 0.6}])
    assert npc.signal("energy") == pytest.approx(0.6)


def test_set_signal_clamped() -> None:
    w, npc, ent = _ctx()
    apply_effects(w, npc, ent,
                  [{"op": "set_signal", "signal": "energy", "value": 5.0}])
    assert npc.signal("energy") == 1.0


def test_add_signal_clamp_edges() -> None:
    w, npc, ent = _ctx()
    npc.set_signals(fun=0.95)
    apply_effects(w, npc, ent,
                  [{"op": "add_signal", "signal": "fun", "delta": 0.5}])
    assert npc.signal("fun") == 1.0
    apply_effects(w, npc, ent,
                  [{"op": "add_signal", "signal": "fun", "delta": -3.0}])
    assert npc.signal("fun") == 0.0


def test_clear_pending_whitelist_ok() -> None:
    w, npc, ent = _ctx()
    npc.set_bladder_pending(0.7)
    apply_effects(w, npc, ent,
                  [{"op": "clear_pending", "field": "bladder_pending"}])
    assert npc.bladder_pending == 0.0


def test_clear_pending_whitelist_rejects() -> None:
    w, npc, ent = _ctx()
    npc.set_signal("hunger", 0.4)
    apply_effects(w, npc, ent,
                  [{"op": "clear_pending", "field": "signals"}])  # 拒绝
    assert npc.signal("hunger") == pytest.approx(0.4)   # 未被清


def test_add_pending_ok_and_whitelist() -> None:
    w, npc, ent = _ctx()
    npc.set_bladder_pending(0.1)
    apply_effects(w, npc, ent, [{"op": "add_pending", "field": "bladder_pending",
                                 "amount": 0.3}])
    assert npc.bladder_pending == pytest.approx(0.4)
    apply_effects(w, npc, ent, [{"op": "add_pending", "field": "signals",
                                 "amount": 0.3}])       # 拒绝(白名单外)
    assert npc.bladder_pending == pytest.approx(0.4)   # 未受影响


def test_spawn_item_creates_at_npc_loc() -> None:
    w, npc, ent = _ctx()
    w.place_npc(npc.person_id, "home")
    n0 = len(w.entities)
    apply_effects(w, npc, ent, [{"op": "spawn_item", "item_type": "meal_simple"}])
    assert len(w.entities) == n0 + 1
    new = [e for eid, e in w.entities.items()
           if eid != ent.entity_id and "edible" in e.tags]
    assert new and new[0].location_id == "home"


def test_consume_self_stock_only_no_pop() -> None:
    """m5-rectify 03: consume_self 只扣库存, 不自行移除实体(回收统一在
    interaction 完成事件之后)。"""
    w, npc, ent = _ctx()
    meal = w.spawn_item_type("meal_simple", "home")
    apply_effects(w, npc, meal, [{"op": "consume_self"}])   # stock 1 -> 0
    assert meal.stock == 0
    assert meal.entity_id in w.entities        # 不在此处 pop
    # 无限(-1)不被消耗
    disp = w.spawn_item_type("water_dispenser", "home")
    apply_effects(w, npc, disp, [{"op": "consume_self"}])
    assert disp.entity_id in w.entities and disp.stock == -1


# --- testm4 E: interaction.py 无领域硬编码字面 -------------------------
def test_interaction_has_no_domain_hardcode_literal() -> None:
    p = ROOT / "src" / "citysim" / "world" / "interaction.py"
    text = p.read_text(encoding="utf-8")
    for tok in ("_TAKE_FOOD", "_PLAN_ZH", "厕所", "马桶", "bladder_pending"):
        assert tok not in text, f"interaction.py 残留 {tok!r}"
