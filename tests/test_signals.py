"""M1 DoD: 信号单一真源。

0..1 float signals 唯一存储; 无 Body/state.body 双写; 纯函数代谢。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from citysim.core.config import SIGNALS, load_config
from citysim.npc.person import (
    Person,
    apply_metabolism,
    full_signals,
    signals_as_percent,
)

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config" / "sim.toml"
SRC = ROOT / "src" / "citysim"

METABOLISM = load_config(CFG_PATH).metabolism


# --- 纯函数代谢 -------------------------------------------------------
def test_metabolism_one_day() -> None:
    """初始全 1.0, 跑 1440 tick 纯代谢:
    hunger ≈ 0.0(24h 耗尽, ±0.01); thirst == 0.0(12h 见底后 clamp);
    energy ≈ 0.5(48h 慢降, ±0.01)。"""
    sig = full_signals(1.0)
    for _ in range(1440):
        apply_metabolism(sig, METABOLISM)
    assert sig["hunger"] == pytest.approx(0.0, abs=0.01)
    assert sig["thirst"] == 0.0
    assert sig["energy"] == pytest.approx(0.5, abs=0.01)


def test_clamp() -> None:
    """信号不越界 [0,1]——即使给超大 delta / 反方向恢复。"""
    sig = full_signals(1.0)
    huge = {s: -10.0 for s in SIGNALS}
    for _ in range(10):
        apply_metabolism(sig, huge)
    for v in sig.values():
        assert 0.0 <= v <= 1.0
    # set_state 也 clamp
    p = Person()
    p.set_state(energy=5.0, hunger=-2.0)
    assert p.signals["energy"] == 1.0
    assert p.signals["hunger"] == 0.0


def test_personality_multiplier() -> None:
    """personality_mul={"hunger":2.0} 时 hunger 下降速度 ×2。"""
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


# --- Person: 唯一真源 --------------------------------------------------
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


# --- 双写源 grep 检查(legacy 临时目录除外) ----------------------------
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
    """存储路径不许出现 round(v*100); 只允许视图函数所在模块。"""
    allowed = {SRC / "npc" / "person.py"}
    bad = [str(p) for p in _non_legacy_src_files()
           if "round(" in p.read_text(encoding="utf-8") and p not in allowed]
    assert bad == []
