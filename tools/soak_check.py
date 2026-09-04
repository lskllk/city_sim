"""soak_check —— 多 seed 快速校验日行为阈值(校准用, 非测试)。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from citysim.sim.loop import run_tick  # noqa: E402
from demo_scene import build_demo  # noqa: E402
from soak import SoakTracker  # noqa: E402

DAYS = 7
TICKS = DAYS * 1440


def check(seed: int) -> dict:
    world, systems, rng_pool, cfg = build_demo(n_npc=3, seed=seed, log=True)
    tr = SoakTracker(world, systems)
    for _ in range(TICKS):
        run_tick(world, systems, cfg, rng_pool)
        tr.observe()
    tr.load_decisions(systems.log_lines)
    res = {"eat_ok": True, "sleep_ok": True, "stuck": 0,
           "idle_need": 0, "ratio": tr.failure_ratio(),
           "jitter": len(tr.repeat_claim_violations()), "dead": False}
    for pid, npc in world.npcs.items():
        eats = [tr.eat.get(pid, {}).get(d, 0) for d in range(1, DAYS + 1)]
        if not all(2 <= e <= 4 for e in eats):
            res["eat_ok"] = False
            res.setdefault("eat_detail", {})[pid] = eats
        segs = tr.sleep_segs.get(pid, [])
        lens = [e - s for s, e in segs]
        if not (5 <= len(segs) <= 8) or not all(300 <= x <= 600 for x in lens):
            res["sleep_ok"] = False
            res.setdefault("sleep_detail", {})[pid] = (len(segs), lens)
        vals = tr.max_stuck.get(pid, {}).values()
        res["stuck"] = max(res["stuck"], max(vals, default=0))
        res["idle_need"] = max(res["idle_need"],
                               tr.max_idle_need.get(pid, (0, ""))[0])
        if not npc.is_alive():
            res["dead"] = True
    return res


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="f", type=int, default=1)
    ap.add_argument("--to", dest="t", type=int, default=10)
    a = ap.parse_args()
    for s in range(a.f, a.t + 1):
        r = check(s)
        ok = (r["eat_ok"] and r["sleep_ok"] and r["stuck"] == 0
              and r["idle_need"] < 120 and r["ratio"] < 0.15
              and r["jitter"] == 0 and not r["dead"])
        print(f"seed {s:>2}: {'PASS' if ok else 'FAIL'} "
              f"eat={r.get('eat_detail', 'ok')} sleep={r.get('sleep_detail', 'ok')} "
              f"stuck={r['stuck']} idle_need={r['idle_need']} "
              f"ratio={r['ratio']:.2%} jitter={r['jitter']}")
