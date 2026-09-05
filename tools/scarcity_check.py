"""scarcity_check —— 稀缺场景 4NPC×1厕所×1餐盘(stock=2) 指标扫描(校准用)。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from citysim.sim.loop import run_tick  # noqa: E402
from demo_scene import build_scarce  # noqa: E402
from soak import SoakTracker  # noqa: E402


def run(seed: int, days: int):
    world, systems, rng_pool, cfg = build_scarce(n_npc=4, seed=seed, log=True)
    tr = SoakTracker(world, systems)
    ticks = days * 1440
    for _ in range(ticks):
        run_tick(world, systems, cfg, rng_pool)
        tr.observe()
    tr.load_decisions(systems.log_lines)
    alive = all(n.is_alive() for n in world.npcs.values())
    stuck = max((max(v.values(), default=0)
                 for v in tr.max_stuck.values()), default=0)
    interact = sum(len(v) for t in tr.claims.values() for v in t.values())
    eat_total = sum(sum(d.values()) for d in tr.eat.values())
    return (tr.failed, tr.decisions, tr.failure_ratio(), interact,
            tr.failed / max(1, interact), alive,
            len(tr.repeat_claim_violations()), stuck, eat_total)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="f", type=int, default=1)
    ap.add_argument("--to", dest="t", type=int, default=6)
    ap.add_argument("--days", type=int, default=2)
    a = ap.parse_args()
    print(f"4NPC x 1厕所 x 1餐盘(stock=2), {a.days} 天")
    print(f"{'seed':>4} {'fails':>5} {'dec':>5} {'fail/dec':>8} "
          f"{'interact':>8} {'fail/int':>9} alive jit stuck0 eats")
    for s in range(a.f, a.t + 1):
        (failed, dec, r1, interact, r2, alive, jit, stuck,
         eats) = run(s, a.days)
        print(f"{s:>4} {failed:>5} {dec:>5} {r1:>8.2%} {interact:>8} "
              f"{r2:>9.2%} {alive} {jit} {stuck:>5} {eats}")
