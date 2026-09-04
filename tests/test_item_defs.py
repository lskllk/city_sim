"""testm4 A 组 —— 物品定义加载校验(先写红后写绿)。

fail-fast: 任何一条校验不过 -> ConfigError 且指明文件名; 禁止静默跳过。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from citysim.world.itemdefs import ConfigError, load_item_defs

ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = ROOT / "config" / "items"
EXPECTED = {"bed_basic", "toilet", "fridge", "meal_simple",
            "water_dispenser", "tv"}


def _write(tmp: Path, name: str, data: dict) -> None:
    (tmp / name).write_text(json.dumps(data, ensure_ascii=False),
                            encoding="utf-8")


def test_load_all_configs() -> None:
    defs = load_item_defs(ITEMS_DIR)
    assert EXPECTED <= set(defs)


def test_bad_signal_key_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "bad.json",
           {"item_type": "bad", "duration_ticks": 5,
            "affordances": {"mana": 0.5}})
    with pytest.raises(ConfigError, match="bad.json"):
        load_item_defs(tmp_path)


def test_bad_op_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "bad.json",
           {"item_type": "bad", "duration_ticks": 5,
            "on_complete": [{"op": "nope", "signal": "hunger"}]})
    with pytest.raises(ConfigError, match="bad.json"):
        load_item_defs(tmp_path)


def test_bad_wake_condition_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "bad.json",
           {"item_type": "bad", "duration_ticks": 5,
            "wake_condition": "energy>0.99"})   # 缺 =
    with pytest.raises(ConfigError, match="bad.json"):
        load_item_defs(tmp_path)


def test_bad_duration_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "bad.json", {"item_type": "bad", "duration_ticks": 0})
    with pytest.raises(ConfigError, match="bad.json"):
        load_item_defs(tmp_path)


def test_provides_dangling_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "bad.json",
           {"item_type": "bad", "duration_ticks": 5,
            "provides": ["ghost_item"]})
    with pytest.raises(ConfigError, match="bad.json"):
        load_item_defs(tmp_path)
