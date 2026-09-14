"""energy = 【1 天】的存量 + 昼夜倍率(plan.md §3.6)。

设计(用户 2026-09-14 定):
  白天也掉, 只是掉得慢; 在做事(交互/赶路)掉得更快; 到了晚上掉得很快。
  —— 夜里掉得快 → 困 → 去睡。这不写"到点睡觉", 只写"夜里困得快"。

energy 不再是 4 天的储备, 而是 1 天:
  不睡满 24 小时刚好耗光 1.0(其中白天占 ~0.38, 夜里 ~0.62)。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config

from helpers import add_npc, make_runtime

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _daily_drain() -> float:
    """整整 24 小时不睡会掉多少 energy(正数)。"""
    base = CFG.metabolism["energy"]
    return -base * sum(CFG.rhythm_at(t / 60.0) for t in range(1440))


# ---------------------------------------------------------------------------
# 曲线
# ---------------------------------------------------------------------------
def test_night_drains_faster_than_day() -> None:
    assert CFG.rhythm_at(23.0) > CFG.rhythm_at(12.0)     # 深夜 >> 正午
    assert CFG.rhythm_at(2.0) > CFG.rhythm_at(14.0)
    assert CFG.rhythm_at(9.0) < 1.0 < CFG.rhythm_at(23.0)


def test_energy_is_one_day_not_four() -> None:
    """1 天的量: 24h 不睡 ≈ 耗光 1.0(既不是 4 天也不是半天)。"""
    d = _daily_drain()
    assert 0.9 < d < 1.1, d


def test_daytime_alone_does_not_empty_the_bar() -> None:
    """只白天醒着(15h)掉不到一半 —— 白天不该把人逼去睡。"""
    base = CFG.metabolism["energy"]
    day = -base * sum(CFG.rhythm_at(t / 60.0) for t in range(420, 1320))
    assert 0.25 < day < 0.5, day


# ---------------------------------------------------------------------------
# 活动系数
# ---------------------------------------------------------------------------
def test_sleep_freezes_energy() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", energy=0.5)
    npc.heartbeat(600, CFG, sleep=True)          # 600 = 10:00
    assert npc.signal("energy") == 0.5


def test_busy_drains_faster_than_idle() -> None:
    w, s, _ = make_runtime(CFG)
    a = add_npc(w, s, "a", energy=1.0)
    b = add_npc(w, s, "b", energy=1.0)
    a.heartbeat(600, CFG, busy=False)            # 闲着
    b.heartbeat(600, CFG, busy=True)             # 在做事
    assert b.signal("energy") < a.signal("energy")


def test_night_drains_faster_than_day_for_the_same_person() -> None:
    w, s, _ = make_runtime(CFG)
    day_npc = add_npc(w, s, "d", energy=1.0)
    night_npc = add_npc(w, s, "n", energy=1.0)
    day_npc.heartbeat(600, CFG)                  # 10:00
    night_npc.heartbeat(1380, CFG)               # 23:00
    assert night_npc.signal("energy") < day_npc.signal("energy")
