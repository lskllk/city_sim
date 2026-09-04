"""M0 DoD: load_config() 读出的值与旧代码常量逐一对齐(不改变行为)。"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.core.config import SIGNALS, SimConfig, load_config

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
    # 迁移自旧 Person.SLEEP_WAKE_E=0.99 / SLEEP_DECIDE_TICKS=480
    assert cfg.wake_energy == pytest.approx(0.99)
    assert cfg.asleep_review_ticks == 480


def test_bladder_parity(cfg: SimConfig) -> None:
    # 迁移自旧 Person.BLADDER_CONVERT = 0.02
    assert cfg.bladder_convert == pytest.approx(0.02)


def test_eat_parity(cfg: SimConfig) -> None:
    # 迁移自旧 Person.EAT_HUNGER = 0.42
    assert cfg.eat_hunger_threshold == pytest.approx(0.42)


def test_default_duration_parity(cfg: SimConfig) -> None:
    # 旧 Person._duration_of 未声明时长物品的缺省
    assert cfg.default_duration_ticks == 30


def test_review_parity(cfg: SimConfig) -> None:
    # DEVIATION(M0): design 文本写 min=5/max=120, 真实旧 ReviewClock 现值是
    # min=1/max=48; 采旧代码值(1/48), 配置与旧代码常量一致。
    assert cfg.review_min_ticks == 1
    assert cfg.review_max_ticks == 48


def test_metabolism_parity(cfg: SimConfig) -> None:
    # 迁移自旧 BasalMetabolism.deltas
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
    # toml 里未写出的信号应补 0.0
    for s in ("health", "social", "comfort", "temperature", "bladder", "hp"):
        assert cfg.metabolism[s] == 0.0


def test_signals_full_set() -> None:
    assert set(SIGNALS) == {
        "energy", "hunger", "thirst", "bladder", "temperature",
        "health", "fun", "social", "comfort", "hp",
    }
