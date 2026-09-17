"""world.edge —— 与 NPC 的边界: 两个层之间【唯一】的进出口。

  port          WorldPortImpl: NPC 主动拉的 5 个动词(权限/仲裁/原子都在这)
  perception    建 Percept: 世界 → NPC 的只读快照

铁律: 绝不给 NPC `World` / `Entity`(只给 Percept 与 Grant 这类纯数据);
反过来世界也只能通过 Person.notify()/assign() 对 NPC 说话。
"""
