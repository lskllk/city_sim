"""WP-08: 吃东西 = NPC 自己消化(heartbeat 逐 tick 加信号)。

world 只签发 `Grant`(一份可用之物), 信号怎么涨由 NPC 自己的身体循环决定。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Decision, Interact, MoveTo
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


# --- WP-11: sleep/busy 自持 -------------------------------------------------
def test_sleep_freezes_energy_self_derived() -> None:
    """体内 intake 带 sleepable → 自己判“在睡”, 冻结 energy(不再由 world 注入)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "bed", location="loc", tags=("sleepable",), affordances={},
               duration_ticks=100,
               on_complete=[{"op": "add_signal", "signal": "energy",
                             "delta": 1.0}])
    npc = add_npc(w, s, "npc", location="loc", energy=0.3)
    npc.intake_add(_port(w, s).try_take("npc", "bed"))
    npc.heartbeat(1260, CFG)                     # 21:00 入夜, 本会掉很快
    assert npc.signal("energy") == 0.3           # 睡着 → 冻结


# --- WP-12: 中止 = 暂停(弃掉体内那份, 不浪费、不重复) ----------------------
def test_moving_away_drops_intake_without_wasting() -> None:
    """吃着吃着起身走 → 体内那份弃掉; 库存没被扣(不浪费)。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20, stock=2)
    npc = add_npc(w, s, "npc", location="loc", hunger=0.2)
    port = _port(w, s)
    npc.step(port, CFG)                          # 开始吃
    assert len(npc._intake) == 1
    npc.heartbeat(0, CFG)
    npc._execute(port, Decision(MoveTo(dest="other")), 0)
    assert npc._intake == []                     # 起身 → 弃掉
    assert w.entities["meal"].stock == 2         # 没被吃掉


def test_switching_target_drops_old_intake() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "a", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    add_entity(w, "b", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "npc", location="loc", hunger=0.2)
    port = _port(w, s)
    npc._execute(port, Decision(Interact(target_id="a")), 0)
    npc._execute(port, Decision(Interact(target_id="b")), 0)   # 换目标
    assert [ag.grant.entity_id for ag in npc._intake] == ["b"]
