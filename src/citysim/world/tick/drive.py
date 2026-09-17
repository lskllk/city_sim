"""drive —— 执行驱动: 本 tick 该推动谁决策。

规则: **所有非旅行 NPC** 每 tick 都进候选。
- 频率由 Person.decide 决定: **手上有事就做完再决策**, 空闲才重算;
  唯一能打断当前动作的是 PLAN(上班)。
- 交互中的 NPC 仍纳入: 为了推进【计划条目到期】/ 上班打断。
- 旅行中的 NPC 不纳入(在途不打断, 到站再评估)。
"""
from __future__ import annotations


def due_npcs(world, systems) -> list[str]:
    """本轮该决策的 npc_id(排序, 保证确定性)。

    排除旅行中; 交互中仍纳入(供计划到期推进/上班打断)。
    """
    out: list[str] = []
    for pid in sorted(world.npcs):
        if pid in systems.travel:
            continue                      # 在途不打断
        if pid in getattr(systems, "queued", {}):
            continue                      # 在柜台排队 → 这轮不重决策(他在等)
        out.append(pid)
    return out
