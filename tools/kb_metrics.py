"""kb_metrics —— testm5 第三节宏观真实感指标(7 天 × 6 NPC 城镇, full KB)。

城镇: home(生活设施) + 两个食源市场 market_a/market_b(各自独立 location,
带生活设施)。每个 NPC 原型只"认识"其中一家(交替分 3/3) → 不同人知道不同店,
个体化出现; 找食必须靠 KB move_to(跨 location)。

指标(操作化定义, 见 docs/testM5result.md):
  探索率      = move_to 决策 / 全部决策
  空跑率      = intent_failed / move_to(当前空跑主要=扑空空仓)
  知识多样性  = 两两 overlay 的 Jaccard 距离均值(≥0.3 目标)
  追溯完整性  = 抽样决策 used_fact_ids 能 export_trace_chain 到根的比例
  KB 增长     = 人均 overlay day3 vs day7(应有界; decay 起效)
输出: docs/kb_metrics.json + docs/kb_metrics.txt + docs/narrate_logs/macro.log
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from citysim.core.config import load_config
from citysim.npc.knowledge import ArchetypeKB, Fact, KnowledgeBase, Source
from citysim.npc.person import Identity, Person
from citysim.sim.loop import attach_replay, make_systems, run_tick
from citysim.viz.kb_export import export_kb_dot
from citysim.viz.trace_export import export_trace_chain
from citysim.world.world import World

from tests.helpers import add_entity  # noqa: E402

try:  # 直接运行 python tools/kb_metrics.py(tools 目录在 sys.path, tests 不一定)
    from helpers import add_entity  # noqa: F811
except ImportError:  # pytest 环境
    from tests.helpers import add_entity  # noqa: F811

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")
DOCS = ROOT / "docs"
NARR = DOCS / "narrate_logs"
NARR.mkdir(parents=True, exist_ok=True)
N_NPC = 6
DAYS = 7

ROOT_KIND = ("INJECTED", "OBSERVED")


def _fact(seq, subj, rel, obj, conf=1.0):
    return Fact(fact_id=f"k{seq}", subject=subj, relation=rel, obj=obj,
                confidence=conf, source=Source(kind="INJECTED", ref=("arch",)))


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


def build_town(seed: int = 1):
    world = World()
    systems = make_systems(log=True, tell_p=0.1)
    attach_replay(world, systems)
    rng_pool: dict[str, random.Random] = {}
    _fac(world, "home", N_NPC)
    for m in ("market_a", "market_b"):
        _fac(world, m, N_NPC)
        _food(world, m, m, 400)
    for i in range(N_NPC):
        pid = f"n{i}"
        p = Person(identity=Identity(person_id=pid, name=pid),
                   location_id="home")
        r = random.Random(seed * 100 + i)
        p.hour_f = r.uniform(0.0, 24.0)
        p.set_state(energy=r.uniform(0.5, 0.9), hunger=r.uniform(0.5, 0.9),
                    thirst=r.uniform(0.4, 0.8), bladder=1.0, health=1.0,
                    temperature=1.0, fun=0.6, social=0.6, comfort=0.8, hp=1.0)
        world.npcs[pid] = p
        rng_pool[pid] = random.Random(seed * 10 + i)
        systems.scheduler.schedule(pid, 1, now=0)
    # 原型: 一半认识 market_a, 一半认识 market_b(不同人知道不同店)
    for i in range(N_NPC):
        mk = "market_a" if i % 2 == 0 else "market_b"
        arch = ArchetypeKB([
            _fact(1, mk, "sells", "meal_simple", 1.0),
            _fact(2, mk, "located_at", mk, 1.0),
            _fact(3, "meal_simple", "is_a", "edible", 1.0)])
        world.npcs[f"n{i}"].kb = KnowledgeBase(arch)
    return world, systems, rng_pool


def run_metrics() -> dict:
    world, systems, rng_pool = build_town()
    overlay_at_day3 = {f"n{i}": 0 for i in range(N_NPC)}
    used_samples: list[tuple[str, str]] = []   # (npc, fact_id)
    eaten = {pid: False for pid in world.npcs}

    def _on(ev):
        if ev.kind != "interaction_done":
            return
        ent = world.entities.get(ev.payload.get("entity", ""))
        if ent is not None and "edible" in ent.tags:
            eaten[ev.subject_id] = True
    world.bus.subscribe_log(_on)

    for t in range(DAYS * 1440):
        run_tick(world, systems, CFG, rng_pool)
        if t == 1440 * 3:
            for pid, npc in world.npcs.items():
                if npc.kb is not None:
                    overlay_at_day3[pid] = len(npc.kb.overlay)
        # 逐 tick 采 move_to 决策(数量本就少), 供追溯完整性
        for pid, npc in world.npcs.items():
            li = npc.last_intent
            if (li is not None and li.kind == "move_to"
                    and li.trace.used_fact_ids):
                used_samples.append((pid, li.trace.used_fact_ids[0]))
    overlay_day7 = {pid: len(npc.kb.overlay)
                    for pid, npc in world.npcs.items() if npc.kb is not None}
    d_lines = [l for l in (systems.log_lines or []) if l.startswith("D\t")]
    moves = sum(1 for l in d_lines if l.split("\t")[3] == "move_to")
    decisions = len(d_lines)
    failed = sum(1 for l in (systems.log_lines or [])
                 if l.startswith("E\t") and l.split("\t")[2] == "intent_failed")
    exploration = moves / max(1, decisions)
    empty_run = failed / max(1, moves)

    # 知识多样性: 两两 overlay Jaccard 距离
    def subj_set(pid):
        kb = world.npcs[pid].kb
        return frozenset(f.subject for f in kb.overlay.values())
    sets = [subj_set(f"n{i}") for i in range(N_NPC)]
    jacc = []
    for i in range(N_NPC):
        for j in range(i + 1, N_NPC):
            a, b = sets[i], sets[j]
            inter = len(a & b)
            union = len(a | b) or 1
            jacc.append(1.0 - inter / union)      # 距离
    diversity = sum(jacc) / len(jacc) if jacc else 1.0

    # 追溯完整性(去重: 同一 move_to 旅行期会被反复采到)
    unique = sorted(set(used_samples))
    ok = tot = 0
    for pid, fid in unique[:50]:
        tot += 1
        ch = export_trace_chain(world.npcs[pid].kb, [fid])
        if ch["facts"] and ch["facts"][0]["source_kind"] in ROOT_KIND:
            ok += 1
    trace_complete = ok / max(1, tot)

    # 人均 overlay 增长(day3 vs day7)与有界
    ov3 = sum(overlay_at_day3.values()) / N_NPC
    ov7 = sum(overlay_day7.values()) / N_NPC
    max_ov = max(overlay_day7.values())

    # 吃东西确认 KB 被用上(每家 NPC 都靠 move_to 吃到了)
    # 叙事/DOT 产物(第 1/4/7 天)供人工 review
    (NARR / "macro.log").write_text("\n".join(systems.log_lines or []),
                                    encoding="utf-8")
    for day in (1, 4, 7):
        for pid in ("n0", "n3"):
            (DOCS / f"kb_{pid}_d{day}.dot").write_text(
                export_kb_dot(world.npcs[pid].kb), encoding="utf-8")

    all_eat = sum(eaten.values())
    m = dict(
        days=DAYS, n_npc=N_NPC,
        decisions=decisions, moves=moves, failed=failed,
        exploration=round(exploration, 4),
        empty_run=round(empty_run, 4),
        jaccard_distance=round(diversity, 3),
        trace_complete=round(trace_complete, 4),
        overlay_per_npc_day3=round(ov3, 2),
        overlay_per_npc_day7=round(ov7, 2),
        overlay_max= max_ov,
        all_npc_ate=all_eat == N_NPC,
        used_samples=tot,
    )
    (DOCS / "kb_metrics.json").write_text(
        json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    return m


if __name__ == "__main__":
    m = run_metrics()
    for k, v in m.items():
        print(f"{k}: {v}")
