"""TASK006: 计划表 + 中断系统 端到端测试。

覆盖: 同刻串行(MoveTo→Interact) / 计划截止硬中止(on_complete 也触发) /
reflex 软挂起+高保真恢复 / 不可打断睡觉被致命 reflex 唤醒 / 失败 skip+日志。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Interact, MoveTo
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
               affordances={"fun": 0.5}, duration_ticks=5)
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng)
    npc.set_plan([PlanEntry("e0", 1, MoveTo(dest="work")),
                  PlanEntry("e1", 1, Interact("bench"))])
    _run(w, s, rng, 80)
    assert w.loc_of("npc") == "work"
    evs = _events(s)
    assert any(k == "interaction_done" and p.get("entity") == "bench"
               for k, _, p in evs)


def test_plan_deadline_aborts_and_fires_on_complete() -> None:
    """下一条到点 → 硬中止当前交互, 但仍触发 on_complete。"""
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "bench", location="work", tags=("work",),
               affordances={"fun": 0.5}, duration_ticks=100,
               on_complete=[{"op": "add_signal", "signal": "fun", "delta": 0.5}])
    npc = add_npc(w, s, "npc", location="work", rng_pool=rng)
    npc.set_signals(fun=0.4)
    npc.set_plan([PlanEntry("e0", 1, Interact("bench")),
                  PlanEntry("e1", 10, MoveTo(dest="home"))])
    _run(w, s, rng, 2)
    assert s.interaction.active["npc"].entity_id == "bench"
    _run(w, s, rng, 10)                       # 越过 tick 10 截止
    evs = _events(s)
    assert any(k == "interaction_aborted" and p.get("entity") == "bench"
               for k, _, p in evs), "未见 interaction_aborted"
    assert npc.signal("fun") >= 0.9, "硬中止未触发 on_complete(+0.5)"


def test_reflex_suspends_and_resumes_high_fidelity() -> None:
    """reflex 抢占计划交互 → 软挂起; reflex 完 → 恢复剩余进度, 非硬中止。"""
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "bench", location="work", tags=("work",),
               affordances={"fun": 0.5}, duration_ticks=20)
    add_entity(w, "wc", location="work", tags=("toilet",),
               affordances={"bladder": 0.6}, duration_ticks=3)
    npc = add_npc(w, s, "npc", location="work", rng_pool=rng, bladder=1.0)
    npc.set_plan([PlanEntry("e0", 1, Interact("bench"))])
    _run(w, s, rng, 5)
    assert s.interaction.active["npc"].entity_id == "bench"
    rem = s.interaction.active["npc"].remaining_ticks
    assert 0 < rem < 20

    npc.set_signal("bladder", 0.0)            # 触发致命 reflex
    run_tick(w, s, CFG, rng)
    assert s.interaction.active["npc"].entity_id == "wc"
    assert s.interaction.suspended["npc"].entity_id == "bench"
    # 高保真: 挂起的是"当时剩余"(本 tick step 已先扣 1), 而非重置为 20
    assert s.interaction.suspended["npc"].remaining_ticks == rem - 1

    _run(w, s, rng, 40)
    evs = _events(s)
    assert any(k == "interaction_done" and p.get("entity") == "bench"
               for k, _, p in evs), "恢复后 bench 未完成"
    assert not any(k == "interaction_aborted" for k, _, p in evs)
    assert "npc" not in s.interaction.suspended


def test_fatal_reflex_wakes_non_interruptible_sleep() -> None:
    """睡觉 interruptible=False, 快饿死仍被唤醒(致命 reflex 开后门)。"""
    w, s, rng = make_runtime(CFG, log=True)
    bed = add_entity(w, "bed", location="home", tags=("sleepable",),
                     affordances={"energy": 0.7}, duration_ticks=100)
    bed.interruptible = False
    add_entity(w, "food", location="home", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=3, stock=1)
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng,
                  energy=0.5, hunger=0.9)
    npc.set_plan([PlanEntry("e0", 1, Interact("bed"))])
    _run(w, s, rng, 5)
    assert s.interaction.active["npc"].entity_id == "bed"

    npc.set_signal("hunger", 0.0)             # 快饿死
    run_tick(w, s, CFG, rng)
    assert s.interaction.active["npc"].entity_id == "food", "未被唤醒吃饭"
    assert s.interaction.suspended["npc"].entity_id == "bed"


def test_interact_only_plan_auto_navigates() -> None:
    """计划只写交互物体(不写 MoveTo): 执行器自动先走到该物体的所在地。"""
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "bench", location="work", tags=("work",),
               affordances={"fun": 0.5}, duration_ticks=5)
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng)
    # 模拟“已知”: 记忆里知道 bench 在 work(如场景 kb_extra)
    npc.note("bench", located="work", believe=1.0)
    npc.set_plan([PlanEntry("e0", 1, Interact("bench"))])
    _run(w, s, rng, 80)
    assert w.loc_of("npc") == "work"           # 自动走位
    evs = _events(s)
    assert any(k == "interaction_done" and p.get("entity") == "bench"
               for k, _, p in evs)


def test_plan_entry_failure_skips_and_logs() -> None:
    """计划目标不存在 → 失败: 记日志 + 跳过该条, 不空转。"""
    w, s, rng = make_runtime(CFG, log=True)
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng)
    npc.set_plan([PlanEntry("e0", 1, Interact("ghost")),
                  PlanEntry("e1", 1, MoveTo(dest="home"))])
    _run(w, s, rng, 3)
    log = npc.failure_log()
    assert any(f["target"] == "ghost" for f in log), log
    evs = _events(s)
    assert any(k == "intent_failed" and p.get("target") == "ghost"
               for k, _, p in evs)
    # e0 已被 skip, 无残留 goal; e1 到家即完成 → idle
    assert npc.current_activity == "idle"
