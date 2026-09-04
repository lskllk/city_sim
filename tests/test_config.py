"""M0 DoD: load_config() 读出的值与旧代码常量逐一对齐(不改变行为)。"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.core.config import SIGNALS, SimConfig, load_config
from citysim.npc.legacy.brain.review import MAX_INTERVAL_TICKS, MIN_INTERVAL_TICKS
from citysim.npc.legacy.person import BasalMetabolism, Person

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config" / "sim.toml"


@pytest.fixture(scope="module")
def cfg() -> SimConfig:
    return load_config(CFG_PATH)


def test_loads_as_frozen_dataclass(cfg: SimConfig) -> None:
    assert isinstance(cfg, SimConfig)


def test_time_parity(cfg: SimConfig) -> None:
    assert cfg.ticks_per_day == 1440


def test_sleep_parity(cfg: SimConfig) -> None:
    assert cfg.wake_energy == pytest.approx(Person.SLEEP_WAKE_E)  # 0.99
    assert cfg.asleep_review_ticks == Person.SLEEP_DECIDE_TICKS  # 480


def test_bladder_parity(cfg: SimConfig) -> None:
    assert cfg.bladder_convert == pytest.approx(Person.BLADDER_CONVERT)  # 0.02


def test_eat_parity(cfg: SimConfig) -> None:
    assert cfg.eat_hunger_threshold == pytest.approx(Person.EAT_HUNGER)  # 0.42


def test_default_duration_parity(cfg: SimConfig) -> None:
    # 旧 Person._duration_of 未声明时长物品的缺省
    assert cfg.default_duration_ticks == 30


def test_review_parity(cfg: SimConfig) -> None:
    # DEVIATION(M0): design 文本写 min=5/max=120, 但真实 ReviewClock 现值是
    # min=1/max=48。M0 不改行为、配置须与旧代码常量一致 → 采旧代码值。
    assert cfg.review_min_ticks == MIN_INTERVAL_TICKS
    assert cfg.review_max_ticks == MAX_INTERVAL_TICKS


def test_metabolism_parity(cfg: SimConfig) -> None:
    legacy = BasalMetabolism().deltas
    for s in SIGNALS:
        assert s in cfg.metabolism
        assert cfg.metabolism[s] == pytest.approx(legacy.get(s, 0.0))


def test_metabolism_missing_signals_default_zero(cfg: SimConfig) -> None:
    # toml 里未写出的信号应补 0.0
    for s in ("health", "social", "comfort", "temperature", "bladder", "hp"):
        assert cfg.metabolism[s] == 0.0


def test_signals_full_set() -> None:
    assert set(SIGNALS) == {
        "energy", "hunger", "thirst", "bladder", "temperature",
        "health", "fun", "social", "comfort", "hp",
    }
