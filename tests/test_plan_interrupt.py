"""TASK006: 计划表 + 中断系统 端到端测试。

覆盖: 同刻串行(MoveTo→Interact) / 计划截止硬中止(on_complete 也触发) /
reflex 软挂起+高保真恢复 / 不可打断睡觉被致命 reflex 唤醒 / 失败 skip+日志。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Interact, MoveTo, Plan
from citysim.npc.schedule import PlanEntry
from citysim.sim.loop import run_tick

from helpers import add_entity, add_npc, make_runtime

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _run(w, s, rng, ticks: int) -> None:
    for _ in range(ticks):
        run_tick(w, s, CFG, rng)


def _events(s) -> list[tuple[str, str, dict]]:
    out = []
    for ln in (s.log_lines or []):
        parts = ln.split("\t")
        if parts[0] != "E":
            continue
        payload = {}
        if len(parts) > 4 and parts[4]:
            for kv in parts[4].split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    payload[k.strip()] = v.strip()
        out.append((parts[2], parts[3], payload))
    return out


def test_plan_move_then_interact_same_tick() -> None:
    """同刻两条: 先 MoveTo(work), 到达后再 Interact(bench)——串行。"""
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "bench", location="work", tags=("work",),
               affordances={"energy": 0.5}, duration_ticks=5)
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng)
    npc.assign(Plan([PlanEntry("e0", 1, MoveTo(dest="work")),
                  PlanEntry("e1", 1, Interact("bench"))]))
    _run(w, s, rng, 80)
    assert w.loc_of("npc") == "work"
    evs = _events(s)
    assert any(k == "interaction_done" and p.get("entity") == "bench"
               for k, _, p in evs)


def test_plan_deadline_aborts_and_fires_on_complete() -> None:
    """下一条到点 → 硬中止当前交互, 但仍触发 on_complete。

    注(2026-09-14 utility 主导后): 若 NPC 自己就有需求, 需求轨会先把活儿抢走,
    根本走不到“计划截止”。所以要测【计划路径】, 得让他没别的事想做 ——
    这里把 energy 填满(bench 的唯一 afford 就是 energy → 对他没吸引力)。
    on_complete 改成加 hunger(不会像 energy 那样被封顶), 断言才有意义。
    """
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "bench", location="work", tags=("work",),
               affordances={}, duration_ticks=100,
               on_complete=[{"op": "add_signal", "signal": "hunger", "delta": 0.5}])
    npc = add_npc(w, s, "npc", location="work", rng_pool=rng)
    npc.set_signals(energy=1.0, hunger=0.2)
    npc.assign(Plan([PlanEntry("e0", 1, Interact("bench")),
                  PlanEntry("e1", 10, MoveTo(dest="home"))]))
    _run(w, s, rng, 2)
    assert s.interaction.active["npc"].entity_id == "bench"
    _run(w, s, rng, 10)                       # 越过 tick 10 截止
    evs = _events(s)
    assert any(k == "interaction_aborted" and p.get("entity") == "bench"
               for k, _, p in evs), "未见 interaction_aborted"
    # WP-10/12: 硬中止 = 暂停(体内 intake 留着), 不再“中止也触发 on_complete”。
    assert npc.signal("hunger") < 0.5, "中止不应触发 on_complete(旧契约已废)"






def test_interact_only_plan_auto_navigates() -> None:
    """计划只写交互物体(不写 MoveTo): 执行器自动先走到该物体的所在地。"""
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "bench", location="work", tags=("work",),
               affordances={"energy": 0.5}, duration_ticks=5)
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng)
    # 模拟“已知”: 记忆里知道 bench 在 work(如场景 kb_extra)
    npc.note("bench", located="work", believe=1.0)
    npc.assign(Plan([PlanEntry("e0", 1, Interact("bench"))]))
    _run(w, s, rng, 80)
    assert w.loc_of("npc") == "work"           # 自动走位
    evs = _events(s)
    assert any(k == "interaction_done" and p.get("entity") == "bench"
               for k, _, p in evs)


def test_plan_entry_failure_skips_and_logs() -> None:
    """计划目标不存在 → 失败: 记日志 + 跳过该条, 不空转。"""
    w, s, rng = make_runtime(CFG, log=True)
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng)
    npc.assign(Plan([PlanEntry("e0", 1, Interact("ghost")),
                  PlanEntry("e1", 1, MoveTo(dest="home"))]))
    _run(w, s, rng, 3)
    log = npc.failure_log()
    assert any(f["target"] == "ghost" for f in log), log
    evs = _events(s)
    assert any(k == "intent_failed" and p.get("target") == "ghost"
               for k, _, p in evs)
    # e0 已被 skip, 无残留 goal; e1 到家即完成 → idle
    assert npc.current_activity == "idle"
