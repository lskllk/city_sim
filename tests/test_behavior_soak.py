"""testM0~M3.md 第二步+疑点 —— 日行为断言(3 NPC x 7 天) + 实体泄漏 + 稀缺竞争。

这是 M4~M8 每次改动的行为安全网。断言口径照文档:
  - 每人每天吃 2~4 次; 睡 ~1 次/天且每段 300~600 tick
  - 无信号卡 0 超过 300 tick(饿死卡死 = 决策失灵)
  - 无连续 idle 超 2 小时(120 tick) 且同时有信号 <0.3
  - intent_failed 占比 < 15%
  - 无"同一目标 60t 内重复 claim >5 次"抖动循环
  - 实体数不泄漏: 运行后 <= 初始 + K(疑点 1)
  - 稀缺场景 4NPC x 1厕所 x 1餐盘(stock=2): claim 冲突被压到 5%~40%(疑点 2)
"""
from __future__ import annotations

import pytest

from citysim.sim.loop import run_tick

from demo_scene import build_demo, build_scarce
from soak import (THRESH_IDLE_NEED, THRESH_STUCK, SoakTracker,)

DAYS = 7
TICKS = DAYS * 1440
ENTITY_GROWTH_LIMIT = 2   # 疑点 1: 运行后实体增长上限(允许结束时残留 1 个进行中的餐)


def _run_ticks(world, systems, rng_pool, cfg, ticks: int) -> SoakTracker:
    tr = SoakTracker(world, systems)
    for _ in range(ticks):
        run_tick(world, systems, cfg, rng_pool)
        tr.observe()
    tr.load_decisions(systems.log_lines)
    return tr


@pytest.mark.parametrize("seed", [3, 7])
def test_daily_rhythm_soak(seed: int) -> None:
    world, systems, rng_pool, cfg = build_demo(n_npc=3, seed=seed, log=True)
    init_entities = len(world.entities)
    tr = _run_ticks(world, systems, rng_pool, cfg, TICKS)

    # 疑点 1: 实体数不泄漏
    assert len(world.entities) - init_entities <= ENTITY_GROWTH_LIMIT, \
        f"实体泄漏: {init_entities} -> {len(world.entities)}"

    for pid, npc in world.npcs.items():
        # 每人每天吃 2~4 次
        eats = [tr.eat.get(pid, {}).get(d, 0) for d in range(1, DAYS + 1)]
        assert all(2 <= e <= 4 for e in eats), f"{pid} 吃/日={eats}"

        # 睡 ~1 次/天(7 天共 5~8 段), 每段 300~600 tick
        segs = tr.sleep_segs.get(pid, [])
        lens = [e - s for s, e in segs]
        assert 5 <= len(segs) <= 8, f"{pid} 睡眠段数={len(segs)}"
        assert all(300 <= x <= 600 for x in lens), f"{pid} 睡眠时长={lens}"

        # 无信号卡 0 超阈值
        stuck = max(tr.max_stuck.get(pid, {}).values(), default=0)
        assert stuck <= THRESH_STUCK, f"{pid} 信号卡0 {stuck} tick"

        # 无 idle 且同时有信号<0.3 超过 2 小时
        idle_need = tr.max_idle_need.get(pid, (0, ""))[0]
        assert idle_need < THRESH_IDLE_NEED, f"{pid} idle+need {idle_need}t"

        assert npc.is_alive(), f"{pid} 死亡"

    # 资源竞争不失控 + 无抖动
    assert tr.failure_ratio() < 0.15, f"intent_failed {tr.failure_ratio():.1%}"
    assert tr.repeat_claim_violations() == []


@pytest.mark.parametrize("seed", [1, 3, 5])
def test_scarcity_conflict_pressure(seed: int) -> None:
    """疑点 2: 4 NPC 抢 1 厕所 + 1 餐盘(stock=2), 跑 2 天。

    claim 冲突/失败重选链路必须被真实压到: 失败占"交互尝试"的 5%~40%;
    且无人抖动/死亡。注: stock=2 只够 2 人吃, 另 2 人饥饿是设计内(scarcity),\n    本用例不跑"无信号卡 0"断言。
    """
    world, systems, rng_pool, cfg = build_scarce(n_npc=4, seed=seed, log=True)
    tr = _run_ticks(world, systems, rng_pool, cfg, 2 * 1440)

    interact = sum(len(v) for t in tr.claims.values() for v in t.values())
    assert interact > 0
    ratio = tr.failed / interact          # 失败 / 真正想抢的交互尝试
    assert 0.05 <= ratio <= 0.40, \
        f"冲突未被压到: failed={tr.failed} interact={interact} " \
        f"({ratio:.1%})"
    assert tr.failed > 0
    # 有限食物确实被消耗(不多于 stock=2)
    eats = sum(sum(d.values()) for d in tr.eat.values())
    assert 1 <= eats <= 2, f"eats={eats}"
    assert all(n.is_alive() for n in world.npcs.values())
    assert tr.repeat_claim_violations() == []   # 无抖动/卡死循环
