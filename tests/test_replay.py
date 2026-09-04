"""M3 DoD: 录制回放确定性 —— 固定 seed 跑 2000 tick 两次, 日志逐行相等。"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.sim.loop import run_tick

from helpers import add_entity, add_npc, make_runtime, seed_reviews

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _build(log: bool):
    world, systems, rng_pool = make_runtime(CFG, log=log)
    add_entity(world, "food_1", tags=("edible", "consumable"),
               affordances={"hunger": 0.6, "thirst": 0.1},
               duration_ticks=15, stock=3)
    add_entity(world, "bed_1", tags=("sleepable",),
               affordances={"energy": 0.7}, duration_ticks=480,
               wake_condition="energy>=0.99")
    add_entity(world, "tv_1", tags=("fun",), affordances={"fun": 0.4},
               duration_ticks=40)
    add_npc(world, systems, "a", rng_pool=rng_pool, seed=11, hunger=0.1)
    add_npc(world, systems, "b", rng_pool=rng_pool, seed=12, energy=0.1)
    add_npc(world, systems, "c", rng_pool=rng_pool, seed=13, fun=0.05)
    seed_reviews(world, systems)
    return world, systems, rng_pool


def _run_ticks(world, systems, rng_pool, n: int) -> None:
    for _ in range(n):
        run_tick(world, systems, CFG, rng_pool)


def test_replay_deterministic_2000_ticks() -> None:
    lines = []
    for _ in range(2):
        world, systems, rng_pool = _build(log=True)
        _run_ticks(world, systems, rng_pool, 2000)
        lines.append(list(systems.log_lines))

    assert len(lines[0]) == len(lines[1])
    assert lines[0] == lines[1]          # 逐行相等 → 确定性
    # 确保不是"什么都没发生"的假绿
    assert len(lines[0]) > 100
    assert any(l.startswith("E\t") for l in lines[0])
    assert any(l.startswith("D\t") for l in lines[0])


def test_replay_sensitive_to_input() -> None:
    """不同初始条件应产生不同轨迹(证明日志确实反映世界差异)。"""
    outs = []
    for hunger in (0.1, 0.9):
        world, systems, rng_pool = _build(log=True)
        world.npcs["a"].signals["hunger"] = hunger  # 改初始输入
        _run_ticks(world, systems, rng_pool, 400)
        outs.append(list(systems.log_lines))
    assert outs[0] != outs[1]
