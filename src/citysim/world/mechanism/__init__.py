"""world.mechanism —— 通用机制: 被上面多方共用的小零件。

  interaction  交互占用: claim / finish / abort(NPC 消化完 → 世界收尾扣货)
  effects      副作用 op 表 + apply_effects(数据驱动的"用了会怎样")
  events       事件总线: 世界发事件 → NPC 信箱
  pulses       场景脉冲: 世界侧定时脚本(改库存/永久停业)

它们不主动推进时间 —— 谁需要谁调。
"""
