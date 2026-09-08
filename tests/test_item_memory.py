"""item_memory —— item 中心记忆骨架单测(docs/kb_design.md)。

覆盖: 来源天花板 / 强来源主导不被 told 拉低 / told 升级弱来源 / 反证降 believe /
obs-told 提神 remember / 遗忘(remember<FORGET 删行) / 遗忘与 believe 分离。
"""
from __future__ import annotations

import pytest

from citysim.npc.item_memory import FORGET_THRESHOLD, ItemMemory, ItemRow


def test_observe_creates_row_full_content() -> None:
    m = ItemMemory()
    r = m.observe("tv_1", tick=10, located="market", owner="market",
                  afford="fun", value=0.4, price=60.0, stock=3)
    assert isinstance(r, ItemRow)
    assert m.get("tv_1") is r
    assert r.located == "market"
    assert r.owner == "market"
    assert r.afford == "fun" and r.value == 0.4
    assert r.price == 60.0 and r.stock == 3
    assert r.believe == 1.0          # OBSERVED 天花板
    assert r.remember == 1.0 and r.last_seen == 10


def test_told_creates_row_with_medium_believe() -> None:
    m = ItemMemory()
    m.hear("tv_1", tick=5, located="market", afford="fun")
    r = m.get("tv_1")
    assert r is not None
    assert r.believe == 0.6          # TOLD 天花板, 到不了 1.0
    assert r.source_kind == "TOLD"


def test_told_does_not_lower_observed_believe() -> None:
    m = ItemMemory()
    m.observe("tv_1", tick=1, located="market", owner="market", afford="fun")
    before = m.get("tv_1")
    m.hear("tv_1", tick=9, located="apt")      # told 说搬到 apt
    r = m.get("tv_1")
    assert r.believe == 1.0                     # 不被 told 拉低
    assert r.source_kind == "OBSERVED"
    assert r.located == "market"                # 不覆盖亲眼知道的内容
    assert r.remember == 1.0                    # 但仍被 told 提神


def test_told_upgrades_weaker_inferred_or_none() -> None:
    m = ItemMemory()
    # told 顶 INFERRED 弱先验 → 升到 told 天花板
    r = m.hear("tv_1", tick=1, located="apt", afford="fun")
    assert r.believe == 0.6


def test_contradict_lowers_believe_not_remember() -> None:
    m = ItemMemory()
    m.observe("tv_1", tick=1, located="market", afford="fun")
    r = m.get("tv_1")
    m.contradict("tv_1", tick=2, factor=0.5)   # 现场反证(预期在却不在)
    assert r.believe == pytest.approx(0.5)
    assert r.remember == 1.0                     # 反证不影响"记不记得"


def test_forget_drops_when_remember_decays() -> None:
    m = ItemMemory()
    m.observe("tv_1", tick=0, located="market", afford="fun")  # remember=1 at t0
    hl = 10                                       # 半衰期 10 tick
    # t=0..; 1 个半衰期 → 0.5; 过很久 → < FORGET → 删
    m.decay(now_tick=40, half_life_ticks=hl)      # 4 半衰期 → 0.5^4=0.0625 <0.1
    assert m.get("tv_1") is None
    assert len(m) == 0


def test_reobserve_refreshes_remember_before_forget() -> None:
    """重见会重置 remember —— 使原本会遗忘的行存活更久(对照组会丢)。"""
    fresh = ItemMemory()                    # 只 obs 一次
    kept = ItemMemory()                     # obs 一次 + 中途重见
    fresh.observe("tv_1", tick=0, located="market", afford="fun")
    kept.observe("tv_1", tick=0, located="market", afford="fun")
    kept.observe("tv_1", tick=30, located="market", afford="fun")  # 重见 → 重置
    # 44 tick(>4 半衰期): 只 obs 一次者该忘, 重见者仍记得
    fresh.decay(now_tick=44, half_life_ticks=10)
    kept.decay(now_tick=44, half_life_ticks=10)
    assert fresh.get("tv_1") is None       # 0.5^4.4 ≈ 0.047 < FORGET
    assert kept.get("tv_1") is not None    # 重置后仅 14 tick → 仍 ~0.38


def test_believe_and_remember_are_orthogonal() -> None:
    """同一行: 反复 told 可 keep remember 高, 但 believe 只到 told 天花板 0.6。"""
    m = ItemMemory()
    m.hear("tv_1", tick=1, located="market", afford="fun")   # 0.6
    for t in range(2, 50):
        m.hear("tv_1", tick=t)                                # 反复提起(空 told)
    r = m.get("tv_1")
    assert r.believe == 0.6       # 不会因 told 堆到 1.0
    assert r.remember == 1.0      # 但因常被提起一直记得


def test_items_only_returns_remembered_rows() -> None:
    m = ItemMemory()
    m.observe("a", tick=0, located="x", afford="fun")
    m.observe("b", tick=0, located="y", afford="fun")
    assert len(m.items()) == 2
    # 强制删一行
    m.forget_row("a")
    assert {r.item_id for r in m.items()} == {"b"}

