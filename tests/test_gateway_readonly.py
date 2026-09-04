"""display_m5_ui G0 确定性护栏: 网关只读观察不得扰动模拟。

跑 2000 tick, 逐 tick 建快照 + 周期 query(全部 npc_detail + 知识导出),
日志与纯 headless 逐行相同、事件序号未被额外消耗。
"""
from __future__ import annotations

from citysim.core.config import load_config
from citysim.gateway.scenarios import build_scenario
from citysim.gateway.snapshot import build_npc_detail, build_snapshot
from citysim.sim.loop import run_tick
from citysim.viz.kb_export import export_kb_json

CFG = load_config()


def _headless(seed=3, ticks=2000):
    world, systems, rng = build_scenario("demo", seed=seed, n_npc=5)
    for _ in range(ticks):
        run_tick(world, systems, CFG, rng)
    return world, systems


def test_gateway_does_not_perturb_sim() -> None:
    w_a, s_a = _headless()
    a_lines = list(s_a.log_lines)
    a_seq = w_a.bus.seq

    w, s, rng = build_scenario("demo", seed=3, n_npc=5)
    for t in range(2000):
        run_tick(w, s, CFG, rng)
        build_snapshot(w, s, CFG, "1x", [])          # 每 tick 建快照
        if t % 50 == 0:
            for pid in w.npcs:
                build_npc_detail(w, s, pid)          # 全部 query
                if w.npcs[pid].kb is not None:
                    export_kb_json(w.npcs[pid].kb)
    assert s.log_lines == a_lines                    # 日志逐行相同
    assert w.bus.seq == a_seq                        # 事件序号未被消耗
