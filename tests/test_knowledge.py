"""M5 DoD —— 双层知识库 / 感知落知识 / KB 驱动移动 / 追溯导出。

覆盖: overlay 覆盖 / tombstone / 衰减半衰期 / 低置信度 / 追溯链回到根。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.core.config import load_config
from citysim.npc.knowledge import (ArchetypeKB, KnowledgeBase, Source,
                                   load_archetype)
from citysim.viz.kb_export import export_kb_json

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")
ARCH = ROOT / "config" / "archetypes" / "old_resident.json"


def _fact(kb: KnowledgeBase, subject: str, relation: str, obj,
          conf: float = 1.0, kind: str = "OBSERVED") -> None:
    kb.learn(subject=subject, relation=relation, obj=obj,
             confidence=conf, source=Source(kind=kind))


def _mk(seq, subj, rel, obj, conf, kind="INJECTED"):
    from citysim.npc.knowledge import Fact
    return Fact(fact_id=f"a:{subj}|{rel}|{seq}", subject=subj, relation=rel,
                obj=obj, confidence=conf, source=Source(kind=kind),
                tick_learned=0)


# --- 单元: 覆盖/证伪/衰减/置信度 ------------------------------------
def test_overlay_overrides_archetype() -> None:
    arch = ArchetypeKB([_mk(1, "bench_1", "affords", "hunger", 0.9)])
    kb = KnowledgeBase(arch)
    _fact(kb, "bench_1", "affords", "none", 1.0)
    got = kb.query(subject="bench_1", relation="affords")
    assert got[0].obj == "none"          # overlay 优先


def test_tombstone_blocks_archetype() -> None:
    arch = ArchetypeKB([_mk(1, "bench_1", "affords", "hunger", 0.9)])
    kb = KnowledgeBase(arch)
    kb.refute("a:bench_1|affords|1")
    assert kb.query(subject="bench_1", relation="affords") == ()


def test_decay_half_life() -> None:
    kb = KnowledgeBase()
    _fact(kb, "bench_1", "affords", "hunger", 1.0)
    kb.decay(now_tick=20160, half_life_ticks=20160)          # 1 个半衰期
    assert kb.query(subject="bench_1")[0].confidence == pytest.approx(0.5)
    kb.decay(now_tick=20160 * 2, half_life_ticks=20160)
    assert kb.query(subject="bench_1")[0].confidence == pytest.approx(0.25)


def test_low_confidence_treated_unknown() -> None:
    kb = KnowledgeBase()
    _fact(kb, "bench_1", "affords", "hunger", 0.01)
    assert kb.query(subject="bench_1", relation="affords") == ()


def test_load_archetype_injected() -> None:
    personality, kb = load_archetype(ARCH)
    assert personality.get("hunger") == 1.0
    facts = kb.query()
    assert facts and all(f.source.kind == "INJECTED" for f in facts)


def test_kb_json_export() -> None:
    kb = KnowledgeBase()
    _fact(kb, "bench_1", "affords", "hunger", 1.0)
    out = export_kb_json(kb)
    assert out["nodes"] and out["edges"]
    assert out["edges"][0]["source_kind"] == "OBSERVED"


# --- m5-rectify: T1 命名空间 / T2 逐键合并 / T4 tick / T7 upsert ----------
def test_fact_id_namespace_separates_layers() -> None:
    """原型 a: / overlay o: —— refute overlay 不误伤原型, fact() 不串。"""
    arch_f = _mk(1, "bench_1", "affords", "hunger", 0.9)
    kb = KnowledgeBase(ArchetypeKB([arch_f]))
    ov = kb.learn(subject="bench_1", relation="affords", obj="hunger",
                  confidence=1.0, source=Source(kind="OBSERVED"), tick=5)
    assert ov.fact_id.startswith("o:")
    assert kb.archetype.facts[0].fact_id.startswith("a:")
    assert kb.fact(ov.fact_id) is ov
    # 只有 overlay 被 refute → 原型不被 tombstone、仍可回退(conf 0.9)
    kb.refute(ov.fact_id)
    assert not kb.tombstones & {"a:bench_1|affords|1"}
    got = kb.query(subject="bench_1", relation="affords")
    assert got and got[0].fact_id.startswith("a:")


def test_query_perfact_keeps_other_archetype_facts() -> None:
    """目击一设施后 query(affords) 仍见原型里其它 affords(P0-1: 不再整层遮蔽)。"""
    arch = ArchetypeKB([
        _mk(1, "bench_1", "affords", "hunger", 0.9),
        _mk(2, "backup_bench", "affords", "hunger", 0.7)])
    kb = KnowledgeBase(arch)
    kb.learn(subject="bench_1", relation="affords", obj="hunger",
             confidence=1.0, source=Source(kind="OBSERVED"))
    subs = {f.subject for f in kb.query(relation="affords")}
    assert subs == {"bench_1", "backup_bench"}
    # overlay 同键覆盖同 subject 时原型同键隐藏, 但不同键(located_at)不受影响
    kb2 = KnowledgeBase(ArchetypeKB([
        _mk(1, "bench_1", "affords", "hunger", 0.9),
        _mk(2, "market_1", "located_at", "market", 1.0)]))
    kb2.learn(subject="bench_1", relation="affords", obj="hunger",
              confidence=1.0, source=Source(kind="OBSERVED"))
    assert kb2.query(relation="located_at")


def test_learn_records_explicit_tick() -> None:
    kb = KnowledgeBase()
    a = kb.learn(subject="f1", relation="located_at", obj="home",
                 confidence=1.0, source=Source(kind="OBSERVED"), tick=500)
    b = kb.learn(subject="f2", relation="located_at", obj="home",
                 confidence=1.0, source=Source(kind="OBSERVED"), tick=900)
    assert a.tick_learned == 500 and b.tick_learned == 900


def test_learn_upsert_bounded() -> None:
    kb = KnowledgeBase()
    a = kb.learn(subject="bench_1", relation="affords", obj="hunger",
                 confidence=1.0, source=Source(kind="OBSERVED"), tick=10)
    b = kb.learn(subject="bench_1", relation="affords", obj="hunger",
                 confidence=0.6, source=Source(kind="OBSERVED"), tick=50)
    assert len(kb.overlay) == 1          # 同键替换, 不新增
    assert a.fact_id == b.fact_id        # id 稳定
    assert b.confidence == 1.0           # 取更高 conf
    assert b.tick_learned == 10          # N2: 弱消息(0.6<1.0)不刷新 tick
    # 等强再观察(同 1.0)才刷新 tick
    c = kb.learn(subject="bench_1", relation="affords", obj="hunger",
                 confidence=1.0, source=Source(kind="OBSERVED"), tick=80)
    assert c.tick_learned == 80
    # 不同 obj → 新事实并存
    d = kb.learn(subject="bench_1", relation="affords", obj="none",
                 confidence=1.0, source=Source(kind="OBSERVED"), tick=90)
    assert d.fact_id != c.fact_id
    assert len(kb.overlay) == 2


def test_unknown_relation_raises_valueerror() -> None:
    kb = KnowledgeBase()
    with pytest.raises(ValueError):
        kb.learn(subject="x", relation="warp", obj="y", confidence=1.0,
                 source=Source(kind="OBSERVED"))


def test_all_facts_matches_query() -> None:
    arch = ArchetypeKB([
        _mk(1, "bench_1", "affords", "hunger", 0.9),
        _mk(2, "market_1", "located_at", "market", 1.0)])
    kb = KnowledgeBase(arch)
    kb.learn(subject="bench_1", relation="affords", obj="hunger",
             confidence=1.0, source=Source(kind="OBSERVED"))
    assert len(kb.all_facts()) == 2      # 同键去重(overlay 覆盖原型), 另一键并存


def test_upsert_keeps_higher_source_no_weak_refresh() -> None:
    """N2: OBSERVED 1.0 被 TOLD 0.8 重述 → conf/source 不降级、tick 不刷新。"""
    kb = KnowledgeBase()
    a = kb.learn(subject="cafe_7", relation="affords", obj="fun",
                 confidence=1.0, source=Source(kind="OBSERVED"), tick=100)
    b = kb.learn(subject="cafe_7", relation="affords", obj="fun",
                 confidence=0.8, source=Source(kind="TOLD", ref=("n1",)),
                 tick=5000)
    got = kb.query(subject="cafe_7", relation="affords")[0]
    assert got.fact_id == a.fact_id == b.fact_id   # upsert 保 id
    assert got.confidence == 1.0                   # 高置信不被拉低
    assert got.source.kind == "OBSERVED"           # 来源不降级(溯源根仍是亲眼)
    assert got.tick_learned == 100                 # 弱消息不刷新 tick(不延衰减)
    # 更强新证据才覆盖来源并刷新
    c = kb.learn(subject="cafe_7", relation="affords", obj="fun",
                 confidence=0.9, source=Source(kind="TOLD", ref=("n2",)),
                 tick=9000)                        # 仍 < 1.0 → 不改
    assert kb.query(subject="cafe_7")[0].source.kind == "OBSERVED"
