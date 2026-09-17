"""「我此刻在干什么」= NPC 自己推导: `Person.activity()` -> (大类, 显示文字)。

第三批: 以前是 world 写进来的 —— 6 处 `set_activity("苹果"/"idle"/"闲逛"/"queue")`
把状态写到 NPC 身上, `act_class_of` 再去 world 的 travel/roaming/interaction 里
猜大类。现在大类从自己的 `_intake`(带 tags) + `_moving/_queued` 推。

钉: ① `set_activity` 必须消失; ② tags → 大类是数据驱动的; ③ 前端依赖的语义
(吃/睡时文字 = 那件东西的名字) 不变。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.ports import Grant
from citysim.npc.person import Person

from helpers import add_npc, make_runtime

CFG = load_config(Path("config/sim.toml"))


def _grant(name: str, tags: tuple[str, ...]) -> Grant:
    return Grant(handle="h:" + name, entity_id="e:" + name, name=name,
                 signal="hunger", value=0.5, duration_ticks=10, tags=tags)


def test_set_activity_is_gone() -> None:
    """world 不能再往 NPC 头上写字 —— 那个门必须关上。"""
    assert not hasattr(Person, "set_activity")


def test_idle_by_default() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    assert npc.activity() == ("idle", "idle")
    assert npc.activity_class == "idle"


def test_intake_decides_class_and_keeps_the_item_name() -> None:
    """吃/睡时显示文字 = 那件东西的名字(前端要显示"吃饭 · 苹果")。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    for name, tags, cls in [("苹果", ("edible", "consumable"), "eat"),
                            ("床", ("sleepable",), "sleep"),
                            ("马桶", ("toilet",), "toilet"),
                            ("销售前台", ("work", "station", "fixture"), "work")]:
        npc._intake.clear()
        npc.intake_add(_grant(name, tags))
        assert npc.activity() == (cls, name), name
    npc._intake.clear()
    npc.intake_add(_grant("", ("roam",)))            # 闲逛的 Grant 没有名字
    assert npc.activity() == ("wander", "闲逛")


def test_class_of_tags_is_data_driven() -> None:
    """新物件只要在 config/items 打 tag → 大类自动认得, 不用改代码。"""
    assert Person._class_of_tags(("edible",)) == "eat"
    assert Person._class_of_tags(("station",)) == "work"
    assert Person._class_of_tags(("roam",)) == "wander"
    assert Person._class_of_tags(("furniture", "pretty")) == "idle"


def test_move_and_queue_flags() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    npc._moving = True
    assert npc.activity() == ("move", "")
    npc._moving = False
    npc._queued = True                               # 异步买单已入队 → 在柜台等
    assert npc.activity() == ("idle", "queue")


def test_activity_class_equals_legacy_world_guess_when_idle() -> None:
    """world 侧 act_class_of 现在只是转发 —— 两者必须一致。"""
    from citysim.world.run.engine import act_class_of
    w, s, _ = make_runtime(CFG)
    add_npc(w, s, "npc", location="loc")
    assert act_class_of(w, s, "npc") == "idle"
    assert act_class_of(w, s, "nobody") == "idle"
