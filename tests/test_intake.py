"""WP-08: 吃东西 = NPC 自己消化(heartbeat 逐 tick 加信号)。

world 只签发 `Grant`(一份可用之物), 信号怎么涨由 NPC 自己的身体循环决定。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.world.port import WorldPortImpl

from helpers import add_entity, add_npc, make_runtime

CFG = load_config("config/sim.toml")


def _port(w, s) -> WorldPortImpl:
    return WorldPortImpl(w, s, CFG)


def test_eating_raises_hunger_via_heartbeat() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=10)
    npc = add_npc(w, s, "npc", location="loc", hunger=0.0)
    npc.step(_port(w, s), CFG)                    # 开始吃
    h0 = npc.signal("hunger")
    for _ in range(5):
        npc.heartbeat(0, CFG)                     # 消化 5 tick
    assert npc.signal("hunger") > h0 + 0.2        # 5×0.05=0.25(减一点代谢)


def test_no_double_intake_while_continuing() -> None:
    """同一目标每 tick 决策(continue) → 体内只有 1 份 intake。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "npc", location="loc", hunger=0.2)
    port = _port(w, s)
    for _ in range(5):
        npc.step(port, CFG)                       # 每 tick 都 Interact(meal)
    assert len(npc._intake) == 1
    assert npc.signal("hunger") < 0.6             # 没有爆涨(每 tick 塞一份的旧 bug)


def test_finished_intake_is_flushed_and_consumes_one() -> None:
    """消化完 → world.step 收尾时扣 1 份。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=1, stock=3)
    npc = add_npc(w, s, "npc", location="loc", hunger=0.0)
    npc.step(_port(w, s), CFG)                    # 开始吃(1 tick 的份)
    npc.heartbeat(0, CFG)                         # 消化完
    s.interaction.step(w, CFG)                    # world 收尾(内部 take_finished)
    assert w.entities["meal"].stock == 2


def test_take_finished_is_destructive() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=1)
    npc = add_npc(w, s, "npc", location="loc", hunger=0.0)
    npc.step(_port(w, s), CFG)
    npc.heartbeat(0, CFG)
    assert npc.take_finished() == ["meal"]
    assert npc.take_finished() == []              # 取走即清
