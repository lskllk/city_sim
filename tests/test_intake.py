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
    done = npc.take_finished()
    assert len(done) == 1 and done[0].startswith("meal")   # handle 唯一(meal#N)
    assert npc.take_finished() == []              # 取走即清


# --- WP-10: 效果边界(编译进 Grant, NPC 自己应用) --------------------------
def test_on_done_effect_applied_by_npc() -> None:
    """on_complete 的 NPC 侧效果(add_signal)由 Person 消化完成时应用。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "bed", location="loc", tags=("sleepable",),
               affordances={}, duration_ticks=2,
               on_complete=[{"op": "add_signal", "signal": "energy",
                             "delta": 1.0}])
    npc = add_npc(w, s, "npc", location="loc", energy=0.2)
    npc.intake_add(_port(w, s).try_take("npc", "bed"))   # 直接开始(床无 afford)
    npc.heartbeat(0, CFG)
    assert npc.signal("energy") < 1.0            # 还没完成
    npc.heartbeat(0, CFG)                        # 第 2 tick → 完成
    assert npc.signal("energy") == 1.0           # on_done 由 NPC 自己应用


def test_on_start_pending_applied_by_npc_once() -> None:
    """on_start 的 add_pending 编译成 Grant.pending, 开始时应用一次。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    w.entities["meal"].on_start = [{"op": "add_pending",
                                    "field": "bladder_pending", "amount": 0.3}]
    npc = add_npc(w, s, "npc", location="loc", hunger=0.2)
    npc.step(_port(w, s), CFG)
    assert npc.bladder_pending == 0.3            # 只应用一次
    npc.heartbeat(0, CFG)
    assert npc.bladder_pending < 0.3             # 开始转为膀胱
