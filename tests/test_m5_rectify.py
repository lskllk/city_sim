"""m5-rectify 二轮(N1/N3)回归：注入动作库一致性 + interruptible 覆盖。"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Intent
from citysim.npc.goap import Action
from citysim.npc.person import Identity, Person
from citysim.world.interaction import (ActiveInteraction, InteractionSystem)
from citysim.world.scheduler import TimingWheel
from citysim.world.world import World

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def test_interaction_uses_injected_actions() -> None:
    """N1: exec 查本系统注入的动作库(与 decide 同源), 不落到磁盘默认库。"""
    inj = (Action(name="eat", exec="custom_exec"),)
    sys = InteractionSystem(scheduler=TimingWheel(), actions=inj)
    assert sys._find_action("eat").exec == "custom_exec"
    # 同名但不同 exec 的注入库覆盖默认
    assert sys._find_action("take") is None      # 注入库里没有的 → None
    # 未注入时才兜底默认库
    dflt = InteractionSystem(scheduler=TimingWheel())
    assert dflt._find_action("eat").exec == "spawn_from_container"


def test_interruptible_false_refuses_override() -> None:
    """N3: interruptible=False(床) 进行中 → 拒绝被新意图顶掉, claim 不悬挂。"""
    world = World()
    bed = world.spawn_item_type("bed_basic", "home")
    toilet = world.spawn_item_type("toilet", "home")
    npc = Person(identity=Identity(person_id="p", name="p"),
                 location_id="home")
    world.npcs["p"] = npc
    bed.claimed_by = "p"
    npc.active_interaction_id = bed.entity_id
    isys = InteractionSystem()
    isys.active["p"] = ActiveInteraction(npc_id="p", entity_id=bed.entity_id,
                                         remaining_ticks=480, total_ticks=480)
    failed: list[str] = []

    def _on(ev):
        if ev.kind == "intent_failed":
            failed.append(ev.kind)

    world.bus.subscribe_log(_on)
    ok = isys.submit(world, npc,
                     Intent(kind="interact", target_id=toilet.entity_id))
    assert ok is False                     # 不可打断 → 拒绝
    assert failed == ["intent_failed"]
    assert bed.claimed_by == "p"           # 未被顶替
    assert isys.active["p"].entity_id == bed.entity_id
