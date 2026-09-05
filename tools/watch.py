"""第一步 · 终端观察器 —— 跑内核, 每 N tick 打一张表。

用法:
  python tools/watch.py --npc 6 --ticks 2400 --period 240 [--seed 7]
  --1x 以真实节拍跑(2 tick/s); 缺省 max 全速跑完再出表。

人肉观察找行为 bug: ①单日节律 ②资源竞争 ③长跑漂移 ④max 不崩。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from citysim.npc.person import signals_as_percent  # noqa: E402
from citysim.sim.loop import run_tick  # noqa: E402
from demo_scene import build_demo  # noqa: E402


def _hms(tick: int) -> tuple[int, int, int]:
    day = tick // 1440 + 1
    m = tick % 1440
    return day, m // 60, m % 60


def _row(world, systems, pid: str) -> str:
    npc = world.npcs[pid]
    pct = signals_as_percent(npc.signals)
    act = npc.current_activity or "idle"
    ai = systems.interaction.active.get(pid)
    if ai is not None:
        rem = ai.remaining_ticks
        ent = world.entities.get(ai.entity_id)
        act = f"{act}[{ent.name if ent else ai.entity_id}剩{rem}t]"
    it = npc.last_intent
    li = f"{it.kind}" if it else "?"
    if it and it.target_id:
        li += f"({it.target_id})"
    due = systems.scheduler.next_due(pid)
    next_t = due if due is None else due - world.clock_tick
    return (f"{npc.name:<4} E:{pct['energy']:>3} H:{pct['hunger']:>3} "
            f"T:{pct['thirst']:>3} B:{pct['bladder']:>3} | {li:<6} {act:<22} "
            f"重评@{next_t}")


def _events_since(lines, from_idx: int):
    evs = []
    for l in lines[from_idx:]:
        if l.startswith("E\t"):
            parts = l.split("\t")
            evs.append((int(parts[1]), parts[2], parts[3], parts[4]))
    return evs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npc", type=int, default=6)
    ap.add_argument("--ticks", type=int, default=2400)
    ap.add_argument("--period", type=int, default=240)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--1x", action="store_true", help="真实节拍 2 tick/s")
    a = ap.parse_args()

    world, systems, rng_pool, cfg = build_demo(n_npc=a.npc, seed=a.seed,
                                               log=True)
    marker = 0
    for t in range(1, a.ticks + 1):
        run_tick(world, systems, cfg, rng_pool)
        if getattr(a, "1x", False):
            time.sleep(0.5)
        if t % a.period == 0 or t == a.ticks:
            day, hh, mm = _hms(t)
            print(f"\n==== tick {t} | {hh:02d}:{mm:02d} day{day} ====")
            for pid in world.npcs:
                print(" ", _row(world, systems, pid))
            evs = _events_since(systems.log_lines, marker)
            marker = len(systems.log_lines)
            for (tk, kind, subj, payload) in evs[-6:]:
                print(f"   事件: [{tk}] {subj} {kind} {payload}")
    print("\nentities:", len(world.entities),
          "| events:", len(systems.log_lines))


if __name__ == "__main__":
    main()
