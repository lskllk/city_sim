"""时间线的「实际行为段」（rich 快照 timeline 字段）。

后端每 tick 给每个 NPC 记一份当天行为段 {from,to,cls,text}，只在选中那个
（rich）的快照里下发，供前端画彩色行为带 + 悬浮。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.gateway.snapshot import _npc_rich
from citysim.world import engine as E

from helpers import add_entity, add_npc, make_runtime

CFG = load_config(Path("config/sim.toml"))


def test_activity_log_has_today_segments() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20, stock=5)
    npc = add_npc(w, s, "n", location="loc", hunger=0.2)
    for _ in range(60):
        E.tick(w, s, CFG)
    tl = _npc_rich(w, s, "n", npc)["timeline"]
    assert tl, "行为段为空"
    assert all(seg["from"] <= seg["to"] for seg in tl)
    assert {"from", "to", "cls", "text"} <= set(tl[0])
    assert {seg["cls"] for seg in tl} & {"eat", "idle"}


def test_activity_log_only_keeps_today() -> None:
    """跨天: 只留今天(剪掉昨天之前的段)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20, stock=5)
    add_entity(w, "bed", location="loc", tags=("sleepable",),
               affordances={}, duration_ticks=100)
    npc = add_npc(w, s, "n", location="loc")
    for _ in range(2 * 1440 + 100):
        E.tick(w, s, CFG)
    tl = _npc_rich(w, s, "n", npc)["timeline"]
    day_start = (w.clock_tick // 1440) * 1440
    # 剪到“今天”: 第一段可能跨过午夜(from<day_start), 但它的 to 必须落在今天
    assert tl[0]["to"] >= day_start
    assert len(tl) < 60                                   # 没无限累积
