"""M2 DoD: 契约层 + decide() 纯函数(KB 打分)。

覆盖: 纯函数性 / 饿挑 edible / 满足即 idle / 同地点优先 / move_to 异地 /
平局确定性 / 不可 claim 忽略 / 在售商品 buy(多态意图)。
决策只来自 KB(affords + located_at) + 视野里的 price/owner。
"""
from __future__ import annotations

import copy
import random
from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import (
    Buy,
    EntityView,
    Idle,
    Interact,
    MoveTo,
    Percept,
)
from citysim.npc.brain import decide
from citysim.npc.knowledge import KnowledgeBase, Source
from citysim.npc.person import full_signals

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _ev(entity_id: str, tags=(), affordances=None, claimable=True,
        duration_ticks: int = 30, distance: float = 0.0,
        price: float = 0.0, owner: str = "") -> EntityView:
    return EntityView(
        entity_id=entity_id,
        name=entity_id,
        tags=frozenset(tags),
        affordances=dict(affordances or {}),
        duration_ticks=duration_ticks,
        distance=distance,
        claimable=claimable,
        location_id="loc",
        price=price,
        owner=owner,
    )


def _percept(*visible, location: str = "loc") -> Percept:
    return Percept(tick=0, hour_f=12.0, location_id=location,
                   visible=tuple(visible))


def _signals(**kw) -> dict[str, float]:
    s = full_signals(1.0)
    s.update(kw)
    return s


def _kb(facts: list[tuple]) -> KnowledgeBase:
    """facts: [(subject, relation, obj, value), ...] 全部 INJECTED conf=1.0。"""
    kb = KnowledgeBase()
    for subj, rel, obj, val in facts:
        kb.learn(subject=subj, relation=rel, obj=obj, value=val,
                 confidence=1.0, source=Source(kind="INJECTED"), tick=0)
    return kb


# --- 纯函数性 ---------------------------------------------------------
def test_pure_same_input_same_output_no_mutation() -> None:
    sig = _signals(hunger=0.2)
    kb = _kb([("rice_1", "affords", "hunger", 0.4),
              ("rice_1", "located_at", "loc", 0.0)])
    perc = _percept(_ev("rice_1", tags=("edible",),
                        affordances={"hunger": 0.4}))
    sig_before = copy.deepcopy(sig)
    i1 = decide(perc, sig, {}, kb, CFG, random.Random(3))
    i2 = decide(perc, sig, {}, kb, CFG, random.Random(3))
    assert i1 == i2
    assert sig == sig_before  # 入参未被修改


# --- 行为 -------------------------------------------------------------
def test_hungry_picks_edible() -> None:
    kb = _kb([("rice_1", "affords", "hunger", 0.4),
              ("rice_1", "located_at", "loc", 0.0)])
    edible = _ev("rice_1", tags=("edible", "consumable"),
                 affordances={"hunger": 0.4, "thirst": 0.1})
    intent = decide(_percept(edible), _signals(hunger=0.2), {},
                    kb, CFG, random.Random(0))
    assert isinstance(intent, Interact)
    assert intent.target_id == "rice_1"


def test_idle_when_satisfied() -> None:
    kb = _kb([("tv_1", "affords", "fun", 0.3),
              ("tv_1", "located_at", "loc", 0.0)])
    tv = _ev("tv_1", tags=("entertain",), affordances={"fun": 0.3})
    intent = decide(_percept(tv), _signals(), {}, kb, CFG, random.Random(0))
    assert isinstance(intent, Idle)


def test_move_to_remote_location() -> None:
    """视野无食物, KB 说 market 有食物 → move_to。"""
    kb = _kb([("market_1", "affords", "hunger", 0.5),
              ("market_1", "located_at", "market", 0.0)])
    intent = decide(_percept(), _signals(hunger=0.2), {},
                    kb, CFG, random.Random(0))
    assert isinstance(intent, MoveTo)
    assert intent.dest == "market"


def test_local_beats_remote() -> None:
    """同地点的候选优先于分数更高的异地候选。"""
    kb = _kb([
        ("market_1", "affords", "hunger", 0.5),
        ("market_1", "located_at", "market", 0.0),
        ("rice_1", "affords", "hunger", 0.4),
        ("rice_1", "located_at", "loc", 0.0),
    ])
    rice = _ev("rice_1", tags=("edible",), affordances={"hunger": 0.4})
    intent = decide(_percept(rice), _signals(hunger=0.2), {},
                    kb, CFG, random.Random(0))
    assert isinstance(intent, Interact)
    assert intent.target_id == "rice_1"


# --- 确定性 -----------------------------------------------------------
def test_tie_break_deterministic() -> None:
    kb = _kb([
        ("a_1", "affords", "hunger", 0.4), ("a_1", "located_at", "loc", 0.0),
        ("b_1", "affords", "hunger", 0.4), ("b_1", "located_at", "loc", 0.0),
    ])
    a = _ev("a_1", affordances={"hunger": 0.4})
    b = _ev("b_1", affordances={"hunger": 0.4})
    picks = []
    for _ in range(2):
        rng = random.Random(42)
        intent = decide(_percept(a, b), _signals(hunger=0.2), {},
                        kb, CFG, rng)
        assert isinstance(intent, Interact)
        picks.append(intent.target_id)
    assert picks[0] == picks[1]
    assert picks[0] in ("a_1", "b_1")


def test_not_claimable_is_ignored() -> None:
    kb = _kb([("bed_1", "affords", "energy", 0.7),
              ("bed_1", "located_at", "loc", 0.0)])
    occupied = _ev("bed_1", tags=("sleepable",), claimable=False,
                   affordances={"energy": 0.7})
    intent = decide(_percept(occupied), _signals(energy=0.1), {},
                    kb, CFG, random.Random(0))
    assert isinstance(intent, Idle)


# --- 购买(Buy 多态意图) -----------------------------------------------
def test_buy_when_for_sale_and_money_enough() -> None:
    """在售商品(price>0, owner="")且钱够 → Buy, 不是 Interact。"""
    kb = _kb([("tv_1", "affords", "fun", 0.4),
              ("tv_1", "located_at", "loc", 0.0)])
    tv = _ev("tv_1", tags=("entertain",), affordances={"fun": 0.4},
             price=60.0, owner="")
    intent = decide(_percept(tv), _signals(fun=0.2), {}, kb, CFG,
                    random.Random(0), money=100.0)
    assert isinstance(intent, Buy)
    assert intent.item_id == "tv_1"


def test_cant_buy_unaffordable_for_sale_item() -> None:
    """钱不够 → 不能就地用(跳过在售商品), 没有其它候选 → idle。"""
    kb = _kb([("tv_1", "affords", "fun", 0.4),
              ("tv_1", "located_at", "loc", 0.0)])
    tv = _ev("tv_1", tags=("entertain",), affordances={"fun": 0.4},
             price=60.0, owner="")
    intent = decide(_percept(tv), _signals(fun=0.2), {}, kb, CFG,
                    random.Random(0), money=10.0)
    assert isinstance(intent, Idle)


def test_owned_item_is_interact_not_buy() -> None:
    """已归自己的商品(owner!="") → 直接 Interact, 不再 Buy。"""
    kb = _kb([("tv_1", "affords", "fun", 0.4),
              ("tv_1", "located_at", "loc", 0.0)])
    tv = _ev("tv_1", tags=("entertain",), affordances={"fun": 0.4},
             price=60.0, owner="me")
    intent = decide(_percept(tv), _signals(fun=0.2), {}, kb, CFG,
                    random.Random(0), money=100.0)
    assert isinstance(intent, Interact)
    assert intent.target_id == "tv_1"
