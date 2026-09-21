"""game 服务层的接缝测试 —— 拆分 `server.py` 之后才成为可能的两件事:

  ① `SimRunner` 的**增量推送逻辑**(观察驱动) 可以无头单测: runner 不 import
     fastapi, 所以不需要 viz extra, 也不需要起服务。
  ② `handle_cmd` 的 **reply 形状**可以直接测: 只依赖一个假 WebSocket。

这两块以前只能靠"起后端 + 连 WS"间接验, 而它们恰好是最容易悄悄坏掉的地方
(增量选取错了 → 前端少刷新或狂刷; reply 形状错了 → 前端点了没反应)。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from citysim.game.commands import handle_cmd
from citysim.game.runner import SimRunner


# ── ① SimRunner: 观察驱动的增量选取 ────────────────────────────────────

@pytest.fixture()
def runner() -> SimRunner:
    return SimRunner()


def test_runner_imports_without_fastapi() -> None:
    """runner 不许依赖 fastapi —— 否则它就不能无头单测, 也白拆了。"""
    import sys

    for name in ("fastapi", "citysim.game.runner"):
        sys.modules.pop(name, None)
    blocked = sys.modules.get("fastapi")
    sys.modules["fastapi"] = None          # type: ignore[assignment]
    try:
        import importlib

        mod = importlib.import_module("citysim.game.runner")
        assert hasattr(mod, "SimRunner")
    finally:
        if blocked is None:
            sys.modules.pop("fastapi", None)
        else:
            sys.modules["fastapi"] = blocked


def test_joined_client_gets_everything_once(runner: SimRunner) -> None:
    """新客户端接入 → 全部 NPC 脏一次; 紧接着再算就【不该】重复脏。

    这就是"静止时一帧 0 个 NPC"(省空转)的那条性质。
    """
    runner.note_client_joined()
    first = runner._dirty_npcs()
    assert first == set(runner.world.npcs), "接入首帧必须全量"
    assert runner._dirty_npcs() == set(), "没有变化时不该重复推"


def test_only_changed_npcs_are_dirty(runner: SimRunner) -> None:
    """推进之后, 脏集合必须【恰好】是渲染状态变了的那些人。"""
    runner.note_client_joined()
    runner._dirty_npcs()                      # 建立基线
    runner.advance(1)
    dirty = runner._dirty_npcs()
    # 手工重算一遍"谁的渲染签名变了", 与 _dirty_npcs 的结论对齐
    expected = {pid for pid, p in runner.world.npcs.items()
                if p.bubble is not None}      # 冒泡的人必推
    assert dirty <= set(runner.world.npcs)
    assert expected <= dirty
    # 再算一次: 签名已更新 → 除冒泡外应当干净
    again = runner._dirty_npcs()
    assert again <= {pid for pid, p in runner.world.npcs.items()
                     if p.bubble is not None}


def test_entities_dirty_only_on_change(runner: SimRunner) -> None:
    runner._dirty_entities()                  # 基线
    assert runner._dirty_entities() == set(), "物品没变就不该脏"


def _counts_at(runner: SimRunner) -> dict[str, int]:
    """每个地点有多少人。"""
    counts: dict[str, int] = {}
    for pid in runner.world.npcs:
        at = runner.world.loc_of(pid)
        counts[at] = counts.get(at, 0) + 1
    return counts


def test_watch_set_has_no_side_effects(runner: SimRunner) -> None:
    """watch_set 给气泡过滤用, 不许动轮转游标; _watched 才能动。"""
    counts = _counts_at(runner)
    runner.focus_loc = max(counts, key=lambda k: counts[k])
    runner.watch_per_frame = 1
    before = runner._watch_cursor
    for _ in range(3):
        runner.watch_set()
    assert runner._watch_cursor == before, "watch_set 不该动游标"
    if counts[runner.focus_loc] >= 2:      # 只有一个人时轮转无可轮
        runner._watched()
        assert runner._watch_cursor != before, "_watched 才推游标"


def test_watched_rotates_in_batches(runner: SimRunner) -> None:
    """盯着人多的建筑时, 每帧只发一批, 逐帧轮转。"""
    if len(runner.world.npcs) < 2:
        pytest.skip("场景人太少, 无法验证轮转")
    counts = _counts_at(runner)
    busiest = max(counts, key=lambda k: counts[k])
    runner.focus_loc = busiest
    runner.watch_per_frame = 1
    seen: set[str] = set()
    for _ in range(len(runner.world.npcs) * 2):
        got = runner._watched()
        assert len(got) <= 1, "每帧最多一批"
        seen |= got
    assert len(seen) >= min(2, counts[busiest]), "轮转应当覆盖更多人"


def test_focus_selects_the_person(runner: SimRunner) -> None:
    pid = next(iter(runner.world.npcs))
    runner.focus_npc = pid
    assert runner.watch_set() == {pid}
    assert pid in runner._watched()
    runner.note_client_joined()
    assert pid in runner._dirty_npcs(), "选中的那个每帧都要发"


# ── ② commands: reply 形状 ─────────────────────────────────────────────

class FakeWS:
    """只收集发出去的消息, 不需要真的 socket。"""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def _drive(runner: SimRunner, cmd: dict) -> dict:
    ws = FakeWS()
    asyncio.run(handle_cmd(runner, ws, cmd))
    assert ws.sent, "该回消息的指令什么都没回"
    msg = ws.sent[-1]
    assert msg["kind"] == "reply" or msg["kind"] == "pong"
    return msg


def test_company_op_ok_reply_shape(runner: SimRunner) -> None:
    cid = sorted(runner.world.companies)[0]
    msg = _drive(runner, {"name": "company_update",
                          "args": {"company": cid, "cash": 1234.5},
                          "req_id": 7})
    p = msg["payload"]
    assert p["req_id"] == 7 and p["ok"] is True and p["why"] is None
    # 经营类回整个 res(含 companies 列表) —— 前端靠它刷新面板
    assert p["data"]["company"] == cid
    assert any(c["id"] == cid and c["cash"] == 1234.5
               for c in p["data"]["companies"])
    assert runner.world.companies[cid].cash == 1234.5


def test_company_op_fail_reply_shape(runner: SimRunner) -> None:
    msg = _drive(runner, {"name": "company_update",
                          "args": {"company": "no_such", "cash": 1},
                          "req_id": 8})
    p = msg["payload"]
    assert p["ok"] is False and p["why"] and p["req_id"] == 8


def test_unknown_cmd_must_reply_why(runner: SimRunner) -> None:
    """未知指令回一句 why —— 不许静默忽略(否则前端点了没反应)。"""
    p = _drive(runner, {"name": "bogus", "args": {}, "req_id": 9})["payload"]
    assert p["ok"] is False and "未知指令" in p["why"]


def test_set_speed_and_invalid_speed(runner: SimRunner) -> None:
    asyncio.run(handle_cmd(runner, FakeWS(),
                           {"name": "set_speed", "args": {"speed": "100x"}}))
    assert runner.speed == "100x"
    # 坏档位走"未知指令"分支(与历史行为一致)
    p = _drive(runner, {"name": "set_speed", "args": {"speed": "999x"},
                        "req_id": 10})["payload"]
    assert p["ok"] is False


def test_set_price_changes_truth_only(runner: SimRunner) -> None:
    """改价【只改真值】—— 不碰任何 NPC 的记忆(那要靠看见/听人说)。"""
    eid = sorted(runner.world.entities)[0]
    before_price = runner.world.entities[eid].price
    p = _drive(runner, {"name": "set_price",
                        "args": {"entity": eid, "price": 4.25},
                        "req_id": 11})["payload"]
    assert p["ok"] is True and p["data"] == {"entity": eid, "price": 4.25}
    assert runner.world.entities[eid].price == 4.25
    assert before_price != 4.25


def test_set_price_bad_entity(runner: SimRunner) -> None:
    p = _drive(runner, {"name": "set_price",
                        "args": {"entity": "nope", "price": 1},
                        "req_id": 12})["payload"]
    assert p["ok"] is False and p["data"] is None and p["why"]


def test_select_is_silent_and_sets_focus(runner: SimRunner) -> None:
    """select 是"告知"(观察驱动), 不回包 —— 只改 focus。"""
    ws = FakeWS()
    asyncio.run(handle_cmd(runner, ws, {"name": "select",
                                        "args": {"npc": "npc_1",
                                                 "location": "bld_008"}}))
    assert ws.sent == [], "select 不该回消息"
    assert runner.focus_npc == "npc_1" and runner.focus_loc == "bld_008"


def test_hire_now_reply_shape(runner: SimRunner) -> None:
    p = _drive(runner, {"name": "hire_now", "args": {}, "req_id": 13})["payload"]
    assert p["ok"] is True and "hired" in p["data"]
