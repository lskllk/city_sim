"""drive —— 执行驱动: 本 tick 该推动谁决策。

接缝(stub): 计划表系统落地前的占位。当前规则: **所有非旅行 NPC** 每 tick 决策。
- 交互中的 NPC **也纳入**(否则无法被 reflex 抢占 / 被计划截止推进)。
- 旅行中的 NPC 不纳入(在途不打断, 到站再评估)。
- 忙/空闲由 Person.decide 内部仲裁(见 docs/task006.md): reflex > 计划 > idle。

TODO(schedule): 计划表系统成熟后, 由 plan 决定谁在何时被推动执行。
"""
from __future__ import annotations


def due_npcs(world, systems) -> list[str]:
    """本轮该决策的 npc_id(排序, 保证确定性)。

    排除旅行中; 交互中仍纳入(供抢占/截止推进)。
    """
    out: list[str] = []
    for pid in sorted(world.npcs):
        if pid in systems.travel:
            continue                      # 在途不打断
        out.append(pid)
    return out
