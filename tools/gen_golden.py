"""gen_golden —— 生成/刷新 M4 回放 golden 基线。

用法: python tools/gen_golden.py [--seed 3] [--ticks 2000]
输出: tests/golden/m4_seed3_2000t.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from citysim.sim.loop import run_tick  # noqa: E402
from demo_scene import build_demo  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--ticks", type=int, default=2000)
    a = ap.parse_args()
    world, systems, rng_pool, cfg = build_demo(n_npc=3, seed=a.seed, log=True)
    for _ in range(a.ticks):
        run_tick(world, systems, cfg, rng_pool)
    out = ROOT / "tests" / "golden" / f"m4_seed{a.seed}_{a.ticks}t.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(systems.log_lines), encoding="utf-8")
    print(f"written {out} ({len(systems.log_lines)} lines)")


if __name__ == "__main__":
    main()
