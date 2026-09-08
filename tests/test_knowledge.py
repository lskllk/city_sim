"""单层 KnowledgeBase 测试(去掉 INJECTED 原型层后)。

覆盖: learn/upsert(N2 来源不降级) / query 过滤 / refute+tombstone / decay 半衰 /
knows / subjects / all_facts / trace 溯源。全部事实来自 obs(OBSERVED)/told(TOLD)。
"""
from __future__ import annotations

import pytest

from citysim.npc.knowledge import CONF_UNKNOWN, KnowledgeBase, Source


def _ob(kb: KnowledgeBase, subject: str, relation: str, obj, conf=1.0,
         kind: str = "OBSERVED", tick: int = 0, value: float = 0.0):
    kb.learn(subject=subject, relation=relation, obj=obj, confidence=conf,
             source=Source(kind=kind), tick=tick, value=value)


def test_learn_creates_and_query_returns() -> None:
    kb = KnowledgeBase()
    _ob(kb, "bench_1", "affords", "fun", conf=1.0, value=0.3, tick=5)
    got = kb.query(subject="bench_1", relation="affords")
    assert len(got) == 1
    assert got[0].obj == "fun"
    assert got[0].value == 0.3
    assert got[0].source.kind == "OBSERVED"


def test_upsert_same_key_not_duplicated() -> None:
    kb = KnowledgeBase()
    a = kb.learn(subject="bench_1", relation="affords", obj="fun",
                 confidence=1.0, source=Source(kind="OBSERVED"), tick=10)
    b = kb.learn(subject="bench_1", relation="affords", obj="fun",
                 confidence=0.6, source=Source(kind="TOLD"), tick=50)
    assert len(kb.overlay) == 1
    assert a.fact_id == b.fact_id          # 同键 upsert, id 稳定
    # N2: 弱消息(0.6<1.0)不覆盖强证据、不刷新 tick
    got = kb.query()[0]
    assert got.confidence == 1.0
    assert got.source.kind == "OBSERVED"
    assert got.tick_learned == 10


def test_upsert_strong_new_upgrades() -> None:
    kb = KnowledgeBase()
    kb.learn(subject="cafe_7", relation="affords", obj="fun",
             confidence=0.6, source=Source(kind="TOLD"), tick=10)
    got = kb.learn(subject="cafe_7", relation="affords", obj="fun",
                   confidence=1.0, source=Source(kind="OBSERVED"), tick=80)
    assert got.confidence == 1.0
    assert got.source.kind == "OBSERVED"
    assert got.tick_learned == 80


def test_query_filters_by_subject_relation() -> None:
    kb = KnowledgeBase()
    _ob(kb, "a", "affords", "fun")
    _ob(kb, "a", "located_at", "market")
    _ob(kb, "b", "affords", "fun")
    assert len(kb.query(subject="a")) == 2
    assert len(kb.query(relation="affords")) == 2
    assert len(kb.query(subject="a", relation="located_at")) == 1


def test_refute_tombstones_and_hides() -> None:
    kb = KnowledgeBase()
    f = kb.learn(subject="bench_1", relation="affords", obj="fun",
                 confidence=1.0, source=Source(kind="OBSERVED"), tick=0)
    assert kb.query(relation="affords")
    kb.refute(f.fact_id)
    assert kb.query(relation="affords") == ()


def test_low_confidence_treated_unknown() -> None:
    kb = KnowledgeBase()
    _ob(kb, "bench_1", "affords", "fun", conf=0.01)
    assert kb.query(relation="affords") == ()   # < CONF_UNKNOWN 不出现在查询里


def test_decay_half_life() -> None:
    kb = KnowledgeBase()
    _ob(kb, "bench_1", "affords", "fun", conf=1.0, tick=0)
    kb.decay(now_tick=20160, half_life_ticks=20160)     # 1 个半衰期
    assert kb.query()[0].confidence == pytest.approx(0.5)
    kb.decay(now_tick=40320, half_life_ticks=20160)
    assert kb.query()[0].confidence == pytest.approx(0.25)


def test_decay_drops_below_unknown() -> None:
    kb = KnowledgeBase()
    _ob(kb, "bench_1", "affords", "fun", conf=1.0, tick=0)
    kb.decay(now_tick=20160 * 6, half_life_ticks=20160)  # 6 半衰 → ~0.0156
    assert kb.query() == ()
    assert len(kb.overlay) == 0


def test_knows() -> None:
    kb = KnowledgeBase()
    _ob(kb, "bench_1", "affords", "fun", conf=0.9)
    assert kb.knows("bench_1", "affords", "fun", min_conf=0.3)
    assert not kb.knows("bench_1", "affords", "hunger", min_conf=0.3)


def test_subjects_and_all_facts() -> None:
    kb = KnowledgeBase()
    _ob(kb, "a_1", "affords", "fun")
    _ob(kb, "b_1", "affords", "fun")
    assert kb.subjects("affords") == frozenset({"a_1", "b_1"})
    assert len(kb.all_facts()) == 2


def test_learn_unknown_relation_raises() -> None:
    kb = KnowledgeBase()
    with pytest.raises(ValueError):
        kb.learn(subject="x", relation="warp", obj="y", confidence=1.0,
                 source=Source(kind="OBSERVED"))


def test_trace_follows_source_ref() -> None:
    kb = KnowledgeBase()
    root = kb.learn(subject="cafe_7", relation="affords", obj="fun",
                    confidence=1.0, source=Source(kind="OBSERVED"), tick=100)
    spread = kb.learn(subject="cafe_7", relation="affords", obj="fun",
                      confidence=0.8, source=Source(kind="TOLD",
                                                    ref=("n1", f"f:{root.fact_id}")),
                      tick=200)
    # 弱消息不覆盖强来源: root 仍是唯一活事实, spread 未取代
    got = kb.query()[0]
    assert got.fact_id == root.fact_id
    tree = kb.trace(root.fact_id)
    assert tree and tree[0].fact_id == root.fact_id
