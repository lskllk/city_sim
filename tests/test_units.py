"""纯单元回归: 配置对齐 / 信号单一真源 / 时间轮调度。

合并自原 test_config.py + test_signals.py + test_scheduler.py。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.core.config import SIGNALS, SimConfig, load_config
from citysim.npc.person import (
    Person,
    apply_metabolism,
    full_signals,
    signals_as_percent,
)
from citysim.world.scheduler import TimingWheel

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config" / "sim.toml"
SRC = ROOT / "src" / "citysim"

METABOLISM = load_config(CFG_PATH).metabolism


# ===========================================================================
# 配置对齐(M0)
# ===========================================================================
@pytest.fixture(scope="module")
def cfg() -> SimConfig:
    return load_config(CFG_PATH)


def test_loads_as_frozen_dataclass(cfg: SimConfig) -> None:
    assert isinstance(cfg, SimConfig)


def test_time_parity(cfg: SimConfig) -> None:
    assert cfg.ticks_per_day == 1440


def test_sleep_parity(cfg: SimConfig) -> None:
    assert cfg.wake_energy == pytest.approx(0.99)
    assert cfg.asleep_review_ticks == 480


def test_bladder_parity(cfg: SimConfig) -> None:
    assert cfg.bladder_convert == pytest.approx(0.02)


def test_eat_parity(cfg: SimConfig) -> None:
    assert cfg.eat_hunger_threshold == pytest.approx(0.42)


def test_default_duration_parity(cfg: SimConfig) -> None:
    assert cfg.default_duration_ticks == 30


def test_review_parity(cfg: SimConfig) -> None:
    assert cfg.review_min_ticks == 1
    assert cfg.review_max_ticks == 48


def test_metabolism_parity(cfg: SimConfig) -> None:
    expected = {
        "hunger": -1.0 / 1440.0, "thirst": -1.0 / 720.0,
        "energy": -1.0 / 2880.0, "fun": -1.0 / 2880.0,
        "health": 0.0, "social": 0.0, "comfort": 0.0,
        "temperature": 0.0, "bladder": 0.0, "hp": 0.0,
    }
    for s in SIGNALS:
        assert s in cfg.metabolism
        assert cfg.metabolism[s] == pytest.approx(expected[s])


def test_metabolism_missing_signals_default_zero(cfg: SimConfig) -> None:
    for s in ("health", "social", "comfort", "temperature", "bladder", "hp"):
        assert cfg.metabolism[s] == 0.0


def test_signals_full_set() -> None:
    assert set(SIGNALS) == {
        "energy", "hunger", "thirst", "bladder", "temperature",
        "health", "fun", "social", "comfort", "hp",
    }


# ===========================================================================
# 信号单一真源(M1)
# ===========================================================================
def test_metabolism_one_day() -> None:
    sig = full_signals(1.0)
    for _ in range(1440):
        apply_metabolism(sig, METABOLISM)
    assert sig["hunger"] == pytest.approx(0.0, abs=0.01)
    assert sig["thirst"] == 0.0
    assert sig["energy"] == pytest.approx(0.5, abs=0.01)


def test_clamp() -> None:
    sig = full_signals(1.0)
    huge = {s: -10.0 for s in SIGNALS}
    for _ in range(10):
        apply_metabolism(sig, huge)
    for v in sig.values():
        assert 0.0 <= v <= 1.0
    p = Person()
    p.set_state(energy=5.0, hunger=-2.0)
    assert p.signals["energy"] == 1.0
    assert p.signals["hunger"] == 0.0


def test_personality_multiplier() -> None:
    def run(mul):
        sig = full_signals(1.0)
        for _ in range(100):
            apply_metabolism(sig, METABOLISM, personality_mul=mul)
        return sig["hunger"]

    base = run(None)
    doubled = run({"hunger": 2.0})
    drop_base = 1.0 - base
    drop_x2 = 1.0 - doubled
    assert drop_x2 == pytest.approx(drop_base * 2.0, rel=0.01)


def test_person_initialized_with_full_signal_set() -> None:
    p = Person()
    assert set(p.signals) == set(SIGNALS)


def test_is_alive_from_hp() -> None:
    p = Person()
    assert p.is_alive()
    p.signals["hp"] = 0.0
    assert not p.is_alive()


def test_signals_as_percent_view() -> None:
    p = Person()
    p.set_state(energy=0.52)
    out = signals_as_percent(p.signals)
    assert out["energy"] == 52
    assert all(0 <= v <= 100 for v in out.values())


def _non_legacy_src_files():
    for p in SRC.rglob("*.py"):
        if "legacy" in p.parts:
            continue
        yield p


def test_no_body_dual_write_anywhere() -> None:
    bad = []
    for p in _non_legacy_src_files():
        text = p.read_text(encoding="utf-8")
        if ("state.body" in text or ".body." in text
                or "class Body" in text or "body: Body" in text):
            bad.append(str(p))
    assert bad == []


def test_round_only_in_display_view() -> None:
    allowed = {SRC / "npc" / "person.py"}
    bad = []
    for p in _non_legacy_src_files():
        text = p.read_text(encoding="utf-8")
        if "round(" in text and "* 100" in text and p not in allowed:
            bad.append(str(p))
    assert bad == []


# ===========================================================================
# 时间轮调度(M3)
# ===========================================================================
def test_schedule_fires_after_delay() -> None:
    w = TimingWheel()
    w.schedule("a", 3, now=0)
    assert w.pop_due(1) == []
    assert w.pop_due(2) == []
    assert w.pop_due(3) == ["a"]
    assert w.pop_due(4) == []


def test_schedule_overwrites_previous() -> None:
    w = TimingWheel()
    w.schedule("a", 100, now=0)
    w.schedule("a", 5, now=0)   # 覆盖旧档
    assert w.pop_due(3) == []
    assert w.pop_due(5) == ["a"]
    assert w.pop_due(101) == []


def test_wheel_overflow() -> None:
    w = TimingWheel(horizon=64)
    w.schedule("a", 10000, now=0)
    assert w.pop_due(9999) == []
    assert w.pop_due(10000) == ["a"]


def test_due_order_sorted_deterministic() -> None:
    w = TimingWheel()
    w.schedule("npc_b", 1, now=0)
    w.schedule("npc_a", 1, now=0)
    assert w.pop_due(1) == ["npc_a", "npc_b"]
