"""soak_report —— 跑 3 NPC x 7 天, 打印日行为指标(供人肉校准/找 bug)。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from citysim.sim.loop import run_tick  # noqa: E402
from demo_scene import build_demo  # noqa: E402
from soak import SoakTracker, parse_decisions  # noqa: E402

DAYS = 7
TICKS = DAYS * 1440


def main(n_npc: int = 3, seed: int = 7) -> None:
    world, systems, rng_pool, cfg = build_demo(n_npc=n_npc, seed=seed, log=True)
    tr = SoakTracker(world, systems)
    for _ in range(TICKS):
        run_tick(world, systems, cfg, rng_pool)
        tr.observe()
    tr.decisions, tr.claims = parse_decisions(systems.log_lines)

    print(f"=== 3 NPC x {DAYS} 天 指标 ===")
    for pid in sorted(world.npcs):
        eats = [tr.eat.get(pid, {}).get(d, 0) for d in range(1, DAYS + 1)]
        drinks = [tr.drink.get(pid, {}).get(d, 0) for d in range(1, DAYS + 1)]
        toilets = [tr.toilet.get(pid, {}).get(d, 0) for d in range(1, DAYS + 1)]
        segs = tr.sleep_durations(pid)
        seg_len = [e - s for (s, e) in segs]
        stuck = tr.max_stuck.get(pid, {})
        idle = tr.max_idle_need.get(pid, (0, ""))
        print(f"\n{pid} {world.npcs[pid].name}")
        print(f"  吃/日: {eats}  喝/日: {drinks}  如厕/日: {toilets}")
        print(f"  睡眠段数: {len(segs)}  时长: {seg_len}")
        print(f"  卡0最长(t): {stuck}")
        print(f"  idle+need最长: {idle}")
    total = sum(len(tr.sleep_durations(p)) for p in world.npcs)
    n = n_npc
    print(f"\n总数: 睡眠段 {total} (人均{total / n:.1f}/7天 = "
          f"{total / n / DAYS:.2f}/天)")
    print(f"intent_failed {tr.failed} / decisions {tr.decisions} "
          f"= {tr.failed / max(1, tr.decisions):.1%}")
    vio = tr.repeat_claim_violations()
    print("抖动报警:", vio if vio else "无")
    print(f"运行后实体数: {len(world.entities)} (初始 ~{5 + n})")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--npc", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    main(a.npc, a.seed)
