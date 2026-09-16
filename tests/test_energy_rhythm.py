"""energy = 白天按基础速度消耗(24h 共 60%) + 入夜 2 小时再掉 40%。

设计: 基础速率稳定消耗(白天 1.0x), 20:00–22:00 阶跃到 9x 一口气把
剩下的 40% 掉完 → 困 → 去睡。不是"到点睡觉"的脚本。
合起来一天一条命: 0.6(基础) + 0.4(入夜多掉) = 1.0。
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
def test_day_is_baseline_and_dusk_spikes() -> None:
    assert abs(CFG.rhythm_at(12.0) - 1.0) < 1e-9         # 白天 = 基础 1.0x
    assert CFG.rhythm_at(21.0) == 9.0                     # 入夜 9x
    assert CFG.rhythm_at(21.0) > CFG.rhythm_at(12.0) * 5  # 入夜明显更快
    assert CFG.rhythm_at(20.0) > CFG.rhythm_at(19.98) * 5  # 是阶跃, 不是慢升


def test_dusk_spike_drains_the_rest() -> None:
    """20:00–22:00 (9x) 掉 ~0.45 —— 在基础之外多掉的那 0.4 就在这里。"""
    base = CFG.metabolism["energy"]
    dusk = -base * sum(CFG.rhythm_at(t / 60.0) for t in range(1200, 1320))
    assert 0.4 < dusk < 0.5, dusk


def test_energy_is_one_day() -> None:
    """基础 0.6 + 入夜 0.4 = 24h 一条命(不睡到底)。"""
    d = _daily_drain()
    assert 0.95 < d < 1.05, d


def test_base_is_60pct_over_24h() -> None:
    """白天那一整段(1.0x)24h 恰好 60%; 12h 白天 = 30%。"""
    base = CFG.metabolism["energy"]
    day24 = -base * 1440
    assert abs(day24 - 0.6) < 1e-9, day24
    day12 = -base * sum(CFG.rhythm_at(t / 60.0) for t in range(420, 1140))
    assert abs(day12 - 0.3) < 1e-6, day12


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


def test_dusk_drains_faster_than_day_for_the_same_person() -> None:
    w, s, _ = make_runtime(CFG)
    day_npc = add_npc(w, s, "d", energy=1.0)
    night_npc = add_npc(w, s, "n", energy=1.0)
    day_npc.heartbeat(600, CFG)                  # 10:00
    night_npc.heartbeat(1260, CFG)               # 21:00
    assert night_npc.signal("energy") < day_npc.signal("energy")
