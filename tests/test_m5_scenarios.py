"""M5 传播/纠错/遗忘/生存(testm5 S3-lite/S5/S6 可机器固化的部分)。

注: 全量 S1/S2/S4 需要人工校准阈值, 见 tools + docs 记录; 本文件固化了
可自动断言的机制层: 传闻机制与置信度衰减、遗忘后不被决策引用、知识=生存差。
"""
from __future__ import annotations

import random
from pathlib import Path

from citysim.core.config import load_config
from citysim.npc.knowledge import (ArchetypeKB, KnowledgeBase, Source,
                                   load_archetype)
from citysim.npc.person import Identity, Person
from citysim.sim.loop import attach_replay, make_systems, run_tick
from citysim.viz.trace_export import export_trace_chain
from citysim.world.world import World

from helpers import add_entity
from soak import SoakTracker

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _mk(kb, seq, subj, rel, obj, conf=1.0, kind="OBSERVED"):
    kb.learn(subject=subj, relation=rel, obj=obj, confidence=conf,
             source=Source(kind=kind))


def _npc(world, pid: str, loc: str):
    p = Person(identity=Identity(person_id=pid, name=pid), location_id=loc)
    world.npcs[pid] = p
    return p


def _run(world, systems, rng_pool, ticks, tracker=None):
    for _ in range(ticks):
        run_tick(world, systems, CFG, rng_pool)
        if tracker:
            tracker.observe()


# --- S3-lite: 传闻机制 + 置信度每跳 ×0.8 + 溯源回唯一 OBSERVED 根 ----------
def test_rumor_spreads_with_decaying_confidence() -> None:
    world = World()
    rng_pool = {}
    for i in range(4):
        p = _npc(world, f"n{i}", "home")
        p.kb = KnowledgeBase()
        p.set_state(hunger=0.9)          # 高饱腹, 久 idle, 便于闲聊
        rng_pool[f"n{i}"] = random.Random(100 + i)
    # 唯一目击者 n0 有 OBSERVED 事实: 咖啡馆#7 提供 fun
    seed_fact = world.npcs["n0"].kb.learn(
        subject="cafe_7", relation="affords", obj="fun", confidence=1.0,
        source=Source(kind="OBSERVED"))
    systems = make_systems(log=True, tell_p=0.2)
    attach_replay(world, systems)
    for pid in world.npcs:
        systems.scheduler.schedule(pid, 1, now=0)
    _run(world, systems, rng_pool, 1440 * 7)

    told = [l for l in systems.log_lines if "\ttold\t" in l]
    assert told, "p=0.2 一周内竟无一条传闻"
    # 至少一位接收者学到 TOLD, 置信度 ≤ 0.8(每跳 ×0.8)
    receivers = [f for f in world.npcs["n1"].kb.query(relation="affords")]
    assert receivers and receivers[0].source.kind == "TOLD"
    assert receivers[0].confidence <= 0.8
    # 溯源: 递归根 = 唯一 OBSERVED 起点
    chain = export_trace_chain(world.npcs["n1"].kb, [receivers[0].fact_id])
    kinds = {f["source_kind"] for f in chain["facts"]}
    assert "OBSERVED" in kinds or chain["facts"][0]["id"] == seed_fact.fact_id


def test_tell_off_means_no_rumor() -> None:
    world = World()
    rng_pool = {}
    for i in range(3):
        p = _npc(world, f"n{i}", "home")
        p.kb = KnowledgeBase()
        p.set_state(hunger=0.9)
        rng_pool[f"n{i}"] = random.Random(i)
    world.npcs["n0"].kb.learn(subject="cafe_7", relation="affords", obj="fun",
                              confidence=1.0,
                              source=Source(kind="OBSERVED"))
    systems = make_systems(log=True, tell_p=0.0)     # 关闭
    attach_replay(world, systems)
    for pid in world.npcs:
        systems.scheduler.schedule(pid, 1, now=0)
    _run(world, systems, rng_pool, 1440)
    assert not any("\ttold\t" in l for l in systems.log_lines)


# --- S5: 遗忘 —— 3 个半衰期后 conf≈0.125, 不再被决策引用; INJECTED 不衰减 ---
def test_forgetting_removes_source_from_decisions() -> None:
    from citysim.npc.brain import decide
    from citysim.core.types import Percept
    kb = KnowledgeBase()
    _mk(kb, None, "rest_b", "contains", "edible", 1.0, "OBSERVED")  # noqa: F841
    got = kb.query(subject="rest_b", relation="contains")
    fid = got[0].fact_id
    kb.decay(now_tick=3 * 10080, half_life_ticks=10080)   # 21 天 = 3 半衰期
    after = kb.query(subject="rest_b", relation="contains")
    assert abs(after[0].confidence - 0.125) <= 0.02
    # 低于 0.3 → 不再作为候选
    npc = _npc(World(), "p", "home")
    npc.set_state(hunger=0.1)
    intent = decide(Percept(tick=0, hour_f=8.0, location_id="home"),
                    npc.signals, {}, kb, CFG, random.Random(1))
    assert intent.kind != "move_to"


def test_injected_facts_do_not_decay() -> None:
    _, arch = load_archetype(ROOT / "config" / "archetypes" / "worker.json")
    kb = KnowledgeBase(arch)
    before = kb.query(relation="sells")[0].confidence
    kb.decay(now_tick=3 * 10080, half_life_ticks=10080)
    assert kb.query(relation="sells")[0].confidence == before


# --- S6: 稀缺 + 知识 = 生存差 -------------------------------------------
def test_knowledge_means_survival_in_scarcity() -> None:
    world = World()
    # home: 冰箱已空(stock=0); market: 有食物的超市容器
    add_entity(world, "fridge_1", location="home", tags=("container",),
               affordances={"provides:edible": 1.0}, duration_ticks=2, stock=0)
    add_entity(world, "market_1", location="market", tags=("container",),
               affordances={"provides:edible": 1.0}, duration_ticks=2, stock=100)
    rng_pool = {}
    for i in range(4):
        p = _npc(world, f"p{i}", "home")
        p.set_state(hunger=0.2)
        rng_pool[f"p{i}"] = random.Random(50 + i)
    # p0/p1 有知识: 知道超市在哪卖餐; p2/p3 没有
    for pid in ("p0", "p1"):
        kb = KnowledgeBase()
        kb.learn(subject="market_1", relation="sells", obj="meal_simple",
                 confidence=1.0, source=Source(kind="INJECTED", ref=("seed",)))
        kb.learn(subject="market_1", relation="located_at", obj="market",
                 confidence=1.0, source=Source(kind="INJECTED", ref=("seed",)))
        world.npcs[pid].kb = kb
    systems = make_systems(log=True)
    for pid in world.npcs:
        systems.scheduler.schedule(pid, 1, now=0)
    tr = SoakTracker(world, systems)
    _run(world, systems, rng_pool, 1440 * 3, tr)

    hk = {pid: tr.max_stuck.get(pid, {}).get("hunger", 0)
          for pid in world.npcs}
    assert max(hk["p0"], hk["p1"]) < 300, f"有知识却挨饿 {hk}"
    assert min(hk["p2"], hk["p3"]) > 1000, f"无知识理应挨饿 {hk}"
    # 有知识的吃到了(去了市场)
    assert all(world.npcs[p].signals["hunger"] > 0.4 for p in ("p0", "p1"))
