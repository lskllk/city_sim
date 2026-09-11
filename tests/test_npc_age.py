"""NPC 年龄(按天更新) + 角色(role) 契约。"""
from __future__ import annotations

from citysim.gateway.scenarios import load_scene, CFG

WANG = "npc_wang_er"
LI = "npc_li_si"


def test_age_role_from_scene() -> None:
    w, _s, _r = load_scene()
    wang = w.npcs[WANG]
    li = w.npcs[LI]
    # birthday 1985-06-15 / 1996-11-02, 游戏纪元 2026-01-01
    assert wang.age == 40 and wang.role == "worker"
    assert li.age == 29 and li.role == "student"


def test_age_updates_daily_on_birthday() -> None:
    w, _s, _r = load_scene()
    wang = w.npcs[WANG]                        # 生日 06-15
    wang.on_day(CFG, 100 * CFG.ticks_per_day)  # 2026-04-11 → 40
    assert wang.age == 40
    wang.on_day(CFG, 200 * CFG.ticks_per_day)  # 2026-07-20 → 41
    assert wang.age == 41


def test_snapshot_exposes_age_role_and_item_type() -> None:
    w, s, r = load_scene()
    from citysim.sim.loop import run_tick
    from citysim.gateway.snapshot import build_snapshot
    for _ in range(4):
        run_tick(w, s, CFG, r)
    snap = build_snapshot(w, s, CFG, "max", [])
    npc = next(n for n in snap["npcs"] if n["id"] == WANG)
    assert npc["age"] == 40 and npc["role"] == "worker"
    ent = next(e for e in snap["entities"]
               if e["id"] == "meal_simple_003")
    assert ent["item_type"] == "meal_simple"
