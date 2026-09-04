"""M5 DoD —— 双层知识库 / 感知落知识 / KB 驱动移动 / 追溯导出。

覆盖: overlay 覆盖 / tombstone / 衰减半衰期 / 低置信度;
核心验收 stale_knowledge: KB 说冰箱有食但真值空 → move_to 冰箱 → 到达感知
refute → 改道超市(知道 sells) → 吃到;
追溯链回到 INJECTED/OBSERVED 根。
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from citysim.core.config import load_config
from citysim.npc.knowledge import (ArchetypeKB, KnowledgeBase, Source,
                                   load_archetype)
from citysim.npc.person import Identity, Person
from citysim.sim.loop import make_systems, run_tick
from citysim.viz.kb_export import export_kb_json
from citysim.viz.trace_export import export_trace_chain
from citysim.world.world import World

from helpers import add_entity

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")
ARCH = ROOT / "config" / "archetypes" / "worker.json"


def _fact(kb: KnowledgeBase, subject: str, relation: str, obj,
          conf: float = 1.0, kind: str = "OBSERVED") -> None:
    kb.learn(subject=subject, relation=relation, obj=obj,
             confidence=conf, source=Source(kind=kind))


# --- 单元: 覆盖/证伪/衰减/置信度 ------------------------------------
def test_overlay_overrides_archetype() -> None:
    arch = ArchetypeKB([_mk(1, "fridge_1", "contains", "edible", 0.9)])
    kb = KnowledgeBase(arch)
    _fact(kb, "fridge_1", "contains", "none", 1.0)
    got = kb.query(subject="fridge_1", relation="contains")
    assert got[0].obj == "none"          # overlay 优先


def _mk(seq, subj, rel, obj, conf, kind="INJECTED"):
    from citysim.npc.knowledge import Fact
    return Fact(fact_id=f"f{seq}", subject=subj, relation=rel,
                obj=obj, confidence=conf, source=Source(kind=kind),
                tick_learned=0)


def test_tombstone_blocks_archetype() -> None:
    arch = ArchetypeKB([_mk(1, "fridge_1", "contains", "edible", 0.9)])
    kb = KnowledgeBase(arch)
    kb.refute("f1")
    assert kb.query(subject="fridge_1", relation="contains") == ()


def test_decay_half_life() -> None:
    kb = KnowledgeBase()
    _fact(kb, "fridge_1", "contains", "edible", 1.0)
    kb.decay(now_tick=20160)                    # 1 个半衰期
    assert kb.query(subject="fridge_1")[0].confidence == pytest.approx(0.5)
    kb.decay(now_tick=20160 * 2)
    assert kb.query(subject="fridge_1")[0].confidence == pytest.approx(0.25)


def test_low_confidence_treated_unknown() -> None:
    kb = KnowledgeBase()
    _fact(kb, "fridge_1", "contains", "edible", 0.01)
    assert kb.query(subject="fridge_1", relation="contains") == ()


def test_load_archetype_injected() -> None:
    personality, kb = load_archetype(ARCH)
    assert personality.get("fun") == 1.2
    facts = kb.query()
    assert facts and all(f.source.kind == "INJECTED" for f in facts)


# --- 核心验收: 过期知识 → 感知修正 → 改道 ---------------------------------
def test_stale_knowledge_move_and_redirect() -> None:
    """KB(原型) 说冰箱有食; 真值已空。NPC 在别处饿 → move_to 厨房 → 到达感知
    发现空 → refute 原型 → 改道超市(sells 事实) → 吃到。"""
    world = World()
    # kitchen: 空冰箱(不再提供食物)
    add_entity(world, "fridge_1", location="kitchen", tags=("container",),
               affordances={"provides:edible": 1.0}, duration_ticks=2,
               stock=0)
    # market: 超市(提供可食)
    add_entity(world, "market_1", location="market", tags=("container",),
               affordances={"provides:edible": 1.0}, duration_ticks=2,
               stock=10)

    npc = Person(identity=Identity(person_id="p", name="p"),
                 location_id="home")
    npc.set_state(hunger=0.2)
    arch = ArchetypeKB([
        _mk(1, "fridge_1", "contains", "edible", 0.9),
        _mk(2, "market_1", "sells", "meal_simple", 1.0),
        _mk(3, "fridge_1", "located_at", "kitchen", 1.0),
        _mk(4, "market_1", "located_at", "market", 1.0),
        _mk(5, "home_1", "located_at", "home", 1.0),
    ])
    npc.kb = KnowledgeBase(arch, now_tick=0)
    world.npcs["p"] = npc
    systems = make_systems(log=True)
    systems.scheduler.schedule("p", 1, now=0)
    rng = {"p": random.Random(2)}
    for _ in range(700):
        run_tick(world, systems, CFG, rng)

    # 途经并改道: 曾去 kitchen, 最终在市场吃到
    d_lines = systems.log_lines
    assert any("move_to\tkitchen" in l for l in d_lines)
    assert any("move_to\tmarket" in l for l in d_lines)
    assert npc.signals["hunger"] > 0.5          # 吃到了(改道成功)
    # 感知修正: 冰箱 contains 不再是可食
    got = npc.kb.query(subject="fridge_1", relation="contains")
    assert not any(f.obj == "edible" for f in got)
    # 追溯链: 用过的事实(改道超市依据的 sells)能回到 INJECTED/OBSERVED 根
    sells = [f for f in npc.kb.query(relation="sells") if f.obj == "meal_simple"]
    assert sells
    chain = export_trace_chain(npc.kb, [sells[0].fact_id])["facts"]
    assert chain and chain[0]["source_kind"] in ("INJECTED", "OBSERVED")


def test_kb_json_export() -> None:
    kb = KnowledgeBase()
    _fact(kb, "fridge_1", "contains", "edible", 1.0)
    out = export_kb_json(kb)
    assert out["nodes"] and out["edges"]
    assert out["edges"][0]["source_kind"] == "OBSERVED"
