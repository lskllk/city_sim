"""energy = 白天基本不掉 + 入夜 2 小时掉光(昼夜倍率)。

设计: 白天几乎平(0.1x), 20:00–22:00 阶跃拉满(24x)一口气掉完 → 困 → 去睡。
不是"到点睡觉"的脚本, 只说"这时候困得快"。
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
def test_day_is_flat_and_dusk_spikes() -> None:
    assert CFG.rhythm_at(12.0) < 0.2                       # 白天几乎不掉
    assert CFG.rhythm_at(21.0) > CFG.rhythm_at(12.0) * 50  # 入夜 >> 白天
    assert CFG.rhythm_at(21.0) > CFG.rhythm_at(19.0) * 50  # 是阶跃, 不是慢升


def test_dusk_two_hours_empties_the_bar() -> None:
    """20:00–22:00 正好掉光 1.0。“快晚了两小时掉完”。"""
    base = CFG.metabolism["energy"]
    dusk = -base * sum(CFG.rhythm_at(t / 60.0) for t in range(1200, 1320))
    assert 0.9 < dusk < 1.1, dusk


def test_energy_is_one_day_not_four() -> None:
    """【两天的基准 + 入夜陡增】合成"一天一条命"。

    基准(-0.5/1440)光靠自己 2 天才耗光 1.0; 是 20:00–22:00 那段 24 倍把人放倒的,
    合起来 24h 不睡 ≈ 1.0(既不是 4 天, 也不是半天)。
    """
    d = _daily_drain()
    assert 0.9 < d < 1.1, d


def test_daytime_alone_does_not_empty_the_bar() -> None:
    """一整个白天(07:00–19:00)基本不动精力。"""
    base = CFG.metabolism["energy"]
    day = -base * sum(CFG.rhythm_at(t / 60.0) for t in range(420, 1140))
    assert day < 0.1, day


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
