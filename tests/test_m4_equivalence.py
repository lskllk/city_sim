"""testm4 B 组 —— 回放等价性(golden)。

golden: 以 M4 最终版为准收录(build_demo seed=3, 2000 tick, 逐行回放日志)。
M4 相对 M3 是纯行为保持重构(soak/scarcity 指标逐位一致), golden 为 M4 基线;
此后每次改动对照本基线, 防"行为漂移"。
"""
from __future__ import annotations

from pathlib import Path

from citysim.sim.loop import run_tick

from demo_scene import build_demo

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "m4_seed3_2000t.jsonl"


def _run_lines(seed: int) -> list[str]:
    world, systems, rng_pool, cfg = build_demo(n_npc=3, seed=seed, log=True)
    for _ in range(2000):
        run_tick(world, systems, cfg, rng_pool)
    return list(systems.log_lines)


def test_replay_matches_golden() -> None:
    assert GOLDEN.exists(), "缺少 golden; 用 tools/gen_golden.py 生成"
    expected = GOLDEN.read_text(encoding="utf-8").splitlines()
    lines = _run_lines(3)
    assert lines == expected


def test_golden_sensitive_to_seed() -> None:
    """golden 非空且确实对输入敏感(防假绿)。"""
    assert GOLDEN.read_text(encoding="utf-8").strip()
    assert _run_lines(3) != _run_lines(7)
