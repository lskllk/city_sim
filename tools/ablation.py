"""ablation —— testm5 第四节消融矩阵。

同场景(home + 两食源市场)同 seed 集(1-10, 带初始噪声), 跑三档 KB:
  off            无 KB(找食全靠眼前)
  archetype_only 原型: 认识两家店(sells+located_at) —— 人人相同
  full           原型 + 个人 overlay(一半人亲历过 market_a、一半 market_b)

指标: 平均首餐时刻(吃到的那些人) / 吃上人数 / stuck0(hunger≤0)总 tick /
      intent_failed/空跑率 / 两两 overlay Jaccard 距离均值。
预期 full≈archetype_only ≥ off(生存); full 是唯一有知识多样性的。若某项倒挂
(full 比 off 差) → 记为发现(过时知识害人且纠错慢), 不是失败。
输出 docs/ablation.json + 打印聚合表。
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from citysim.core.config import load_config  # noqa: E402
from citysim.npc.knowledge import (ArchetypeKB, Fact, KnowledgeBase,  # noqa: E402
                                   Source)
from citysim.npc.person import Identity, Person  # noqa: E402
from citysim.sim.loop import attach_replay, make_systems, run_tick  # noqa: E402
from citysim.world.world import World  # noqa: E402

from tests.helpers import add_entity  # noqa: E402
try:
    from helpers import add_entity  # noqa: F811
except ImportError:
    from tests.helpers import add_entity  # noqa: F811

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")
DOCS = ROOT / "docs"
N_NPC = 4
DAYS = 4
SEEDS = range(1, 11)


def _fact(seq, subj, rel, obj, conf=1.0):
    return Fact(fact_id=f"k{seq}", subject=subj, relation=rel, obj=obj,
                confidence=conf, source=Source(kind="INJECTED", ref=("a",)))


def _fac(world, loc, n):
    for i in range(n):
        add_entity(world, f"bed_{loc}_{i}", location=loc, tags=("sleepable",),
                   affordances={"energy": 0.7}, duration_ticks=480,
                   wake_condition="energy>=0.99")
        add_entity(world, f"water_{loc}_{i}", location=loc,
                   tags=("drink", "consumable"), affordances={"thirst": 0.6},
                   duration_ticks=10, stock=5000)
    add_entity(world, f"toilet_{loc}", location=loc, tags=("toilet",),
               affordances={"bladder": 0.6, "comfort": 0.05}, duration_ticks=5,
               on_complete=[{"op": "set_signal", "signal": "bladder",
                             "value": 1.0},
                            {"op": "clear_pending", "field": "bladder_pending"}])


def _food(world, eid, loc, stock):
    add_entity(world, eid, location=loc, tags=("container",),
               affordances={"provides:edible": 1.0}, duration_ticks=2,
               stock=stock)


def run_one(mode: str, seed: int) -> dict:
    world = World()
    systems = make_systems(log=True, tell_p=0.0)
    attach_replay(world, systems)
    rng_pool: dict[str, random.Random] = {}
    _fac(world, "home", N_NPC)
    for mk in ("market_a", "market_b"):
        _fac(world, mk, N_NPC)
        _food(world, mk, mk, 400)
    for i in range(N_NPC):
        pid = f"n{i}"
        p = Person(identity=Identity(person_id=pid, name=pid),
                   location_id="home")
        r = random.Random(seed * 100 + i)
        p.hour_f = r.uniform(0.0, 24.0)
        noise = 0.1
        p.set_state(
            energy=r.uniform(0.4, 0.9), hunger=r.uniform(0.2, 0.9),
            thirst=r.uniform(0.3, 0.9), bladder=1.0, health=1.0,
            temperature=1.0, fun=r.uniform(0.3, 1.0),
            social=r.uniform(0.3, 1.0), comfort=0.8, hp=1.0)
        world.npcs[pid] = p
        rng_pool[pid] = random.Random(seed * 10 + i)
        systems.scheduler.schedule(pid, 1, now=0)
    # KB 配置
    arch_facts = ArchetypeKB([
        _fact(1, "market_a", "sells", "meal_simple"),
        _fact(2, "market_a", "located_at", "market_a"),
        _fact(3, "market_b", "sells", "meal_simple"),
        _fact(4, "market_b", "located_at", "market_b"),
        _fact(5, "meal_simple", "is_a", "edible")])
    for i in range(N_NPC):
        if mode == "off":
            continue
        if mode == "archetype_only":
            world.npcs[f"n{i}"].kb = KnowledgeBase(arch_facts)
        else:  # full: 原型 + 个人 overlay(偶知 a、奇知 b 的 contains/located_at)
            kb = KnowledgeBase(arch_facts)
            mk = "market_a" if i % 2 == 0 else "market_b"
            kb.learn(subject=mk, relation="contains", obj="edible",
                     confidence=1.0, source=Source(kind="OBSERVED"))
            kb.learn(subject=mk, relation="located_at", obj=mk,
                     confidence=1.0, source=Source(kind="OBSERVED"))
            world.npcs[f"n{i}"].kb = kb

    eaten = {pid: False for pid in world.npcs}
    eat_ticks: dict[str, list[int]] = {pid: [] for pid in world.npcs}
    stuck_ticks = 0

    def _on(ev):
        nonlocal stuck_ticks
        if ev.kind != "interaction_done":
            return
        ent = world.entities.get(ev.payload.get("entity", ""))
        if ent is not None and "edible" in ent.tags:
            eaten[ev.subject_id] = True
            eat_ticks[ev.subject_id].append(ev.tick)
    world.bus.subscribe_log(_on)

    for t in range(DAYS * 1440):
        run_tick(world, systems, CFG, rng_pool)
        for npc in world.npcs.values():
            if npc.signals.get("hunger", 1.0) <= 0.0:
                stuck_ticks += 1
    # 指标
    firsts = [eat_ticks[pid][0] for pid in world.npcs if eat_ticks[pid]]
    ate = sum(eaten.values())
    d_lines = [l for l in (systems.log_lines or []) if l.startswith("D\t")]
    moves = sum(1 for l in d_lines if l.split("\t")[3] == "move_to")
    failed = sum(1 for l in (systems.log_lines or [])
                 if l.startswith("E\t") and l.split("\t")[2] == "intent_failed")
    empty_run = round(failed / moves, 4) if moves else None
    # 多样性(两两 overlay Jaccard 距离)
    sets = []
    for i in range(N_NPC):
        kb = world.npcs[f"n{i}"].kb
        sets.append(frozenset(f.subject for f in kb.overlay.values())
                    if kb is not None else frozenset())
    jacc = []
    for i in range(N_NPC):
        for j in range(i + 1, N_NPC):
            a, b = sets[i], sets[j]
            u = len(a | b)
            jacc.append(1.0 - len(a & b) / u if u else 0.0)
    div = sum(jacc) / len(jacc) if jacc else 0.0
    return dict(
        mode=mode, seed=seed, ate=ate,
        avg_first=round(sum(firsts) / len(firsts), 1) if firsts else None,
        stuck_ticks=stuck_ticks,
        empty_run=empty_run,
        diversity=round(div, 3),
    )


def run_all() -> dict:
    rows = []
    for mode in ("off", "archetype_only", "full"):
        for s in SEEDS:
            rows.append(run_one(mode, s))
    agg = {}
    for mode in ("off", "archetype_only", "full"):
        rs = [r for r in rows if r["mode"] == mode]
        firsts = [r["avg_first"] for r in rs if r["avg_first"] is not None]
        ers = [r["empty_run"] for r in rs if r["empty_run"] is not None]
        agg[mode] = dict(
            ate=sum(r["ate"] for r in rs),
            avg_first=round(sum(firsts) / len(firsts), 1) if firsts else None,
            stuck_ticks=sum(r["stuck_ticks"] for r in rs),
            empty_run=(round(sum(ers) / len(ers), 4) if ers else None),
            diversity=round(sum(r["diversity"] for r in rs) / len(rs), 3),
        )
    out = {"rows": rows, "agg": agg}
    (DOCS / "ablation.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return agg


if __name__ == "__main__":
    agg = run_all()
    print("\n消融矩阵聚合(10 seed 求和/均值):")
    hdr = ("mode", "吃上人数", "平均首餐tick", "stuck0总tick",
           "空跑率", "Jaccard距离")
    print(f"{hdr[0]:<14}{hdr[1]:>8}{hdr[2]:>12}{hdr[3]:>12}"
          f"{hdr[4]:>10}{hdr[5]:>12}")
    for mode in ("off", "archetype_only", "full"):
        a = agg[mode]
        er = "n/a" if a["empty_run"] is None else str(a["empty_run"])
        print(f"{mode:<14}{a['ate']:>8}{str(a['avg_first']):>12}"
              f"{a['stuck_ticks']:>12}{er:>10}"
              f"{a['diversity']:>12}")
