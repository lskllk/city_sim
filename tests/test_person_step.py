"""WP-05: `Person.step` 主动拉(observe→decide→try_*) + 失败自己处理。

钉两件事:
  1. NPC 自己 observe 并直接动 world(WP-00 选 B: 立即落账);
  2. 被 world 否决(Deny)时, NPC 自己写记忆/冷却 —— world 不再反写 NPC。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Decision, Interact
from citysim.world.port import WorldPortImpl

from helpers import add_entity, add_npc, make_runtime

CFG = load_config(Path("config/sim.toml"))


def _port(w, s) -> WorldPortImpl:
    return WorldPortImpl(w, s, CFG)


def test_step_observes_and_takes_free_food() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "npc", location="loc")
    npc.set_signals(hunger=0.2)
    d = npc.step(_port(w, s), CFG)
    assert isinstance(d.intent, Interact) and d.intent.target_id == "meal"
    assert s.interaction.active["npc"].entity_id == "meal"    # 立即落账


def test_execute_handles_deny_by_updating_memory() -> None:
    """在售货白拿被拒 → NPC 自己写冷却(不再要 world 回调 on_failure)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="shop", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    w.entities["meal"].price = 5.0
    w.entities["meal"].owner = "org_test"
    npc = add_npc(w, s, "npc", location="shop")
    npc.note("meal", located="shop", afford="hunger", value=0.5, price=5.0,
             owner="org_test", stock=1, believe=1.0)
    # 直接走执行: Interact 一件在售有主货 → 世界 Deny
    npc._execute(_port(w, s), Decision(Interact(target_id="meal")), 10)
    assert any(f["target"] == "meal" for f in npc.failure_log())
    row = next(r for r in npc.memory_dicts() if r["item_id"] == "meal")
    assert row["cool_until"] > 10                  # 冷却由 NPC 自己写
    assert "npc" not in s.interaction.active       # 没真的交互
