"""两 NPC 同场所争抢单厕所 —— 验证"失败才证伪"的占用冷却逻辑。

断言:
  1. 真的发生"已被他人占用"失败(冲突真实压到)
  2. 被占失败后该 NPC 对该目标进入冷却, 不会每 tick 反复扑同一目标(不抖动)
  3. 两人最终都能轮到用厕所(不会死锁)
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.sim.loop import run_tick

from helpers import add_entity, add_npc, make_runtime, seed_reviews

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")

TOILET_DONE = [{"op": "set_signal", "signal": "bladder", "value": 1.0}]


def _setup(log=True):
    w, s, rng = make_runtime(CFG, log=log)
    add_entity(w, "toilet_1", name="wc", location="home", tags=("toilet",),
               affordances={"bladder": 0.6}, duration_ticks=6,
               on_complete=list(TOILET_DONE))
    for pid in ("a", "b"):
        npc = add_npc(w, s, pid, location="home", rng_pool=rng, seed=1,
                      bladder=0.2)
        npc.note("toilet_1", located="home", afford="bladder", value=0.6,
                 believe=1.0)
    seed_reviews(w, s)
    return w, s, rng


def _run(w, s, rng, ticks):
    for _ in range(ticks):
        run_tick(w, s, CFG, rng)


def _events(s):
    """log_lines -> [('kind', subject, payload)]。"""
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


def test_two_npcs_share_single_toilet() -> None:
    w, s, rng = _setup()
    _run(w, s, rng, 600)

    evs = _events(s)
    occupied = [e for e in evs if e[0] == "intent_failed"
                and e[2].get("why") == "已被他人占用"]
    done_a = [e for e in evs if e[0] == "interaction_done"
              and e[1] == "a" and e[2].get("entity") == "toilet_1"]
    done_b = [e for e in evs if e[0] == "interaction_done"
              and e[1] == "b" and e[2].get("entity") == "toilet_1"]

    # 1) 冲突真实发生(抢同一个厕所)
    assert occupied, "两人同需求却没发生占用冲突(场景没建好?)"
    # 2) 两人最终都轮到用厕所(不死锁)
    assert done_a and done_b, f"有人没用上厕所: a={len(done_a)} b={len(done_b)}"
    # 3) 失败者的冷却应让其不会在紧邻 tick 反复扑同一目标(无抖动)
    ticks = {"a": [], "b": []}
    for pid in ("a", "b"):
        for t, ln in enumerate((s.log_lines or [])):
            parts = ln.split("\t")
            if parts[:1] == ["E"] and parts[2] == "intent_failed" \
                    and parts[3] == pid and "已被他人占用" in parts[4]:
                ticks[pid].append(t)
    for pid, ts in ticks.items():
        gaps = [b - a for a, b in zip(ts, ts[1:])]
        if gaps:
            # 被占冷却 retry=实体 duration(6); 再想也须等重评, 不应 1 tick 连续
            assert min(gaps) >= 2, f"{pid} 被占失败相邻太近(抖动): {gaps}"


def test_occupied_sets_cool_until_in_memory() -> None:
    """被占失败后, 失败者记忆里该目标 cool_until 应被设到未来(屏蔽它再选)。"""
    w, s, rng = _setup(log=True)
    _run(w, s, rng, 60)
    a = w.npcs.get("a")
    if a is None:
        return
    row = a.memory_dicts() and next(
        (r for r in a.memory_dicts() if r["item_id"] == "toilet_1"), None)
    # a 是否经历过被占失败
    failed_a = any(e[0] == "intent_failed" and e[1] == "a"
                   and e[2].get("why") == "已被他人占用"
                   for e in _events(s))
    if failed_a and row is not None:
        assert row["cool_until"] >= w.clock_tick, \
            f"a 被占失败后未设冷却: cool_until={row['cool_until']}"
