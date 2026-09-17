"""citysim.world —— 世界侧(账本 + 权限 + 几何)。

  world.py      世界容器 + Entity       ← 门面
  model/        世界长什么样(静态定义)
  edge/         与 NPC 的边界(唯一进出口)
  run/          世界的时钟(主循环在 run/engine.py)
  econ/         钱与货
  mechanism/    通用机制

平行层 citysim.npc 是认知侧(NPC 自己), 两层只通过 core/ 的契约对话 ——
npc 严禁 import world(CI 会挂)。
"""
