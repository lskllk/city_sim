# 16 — world/交互卫生批次

**What to build:** world / 交互一批小硬伤：
- `effects.py` 函数内 `import logging`×3 → 模块级 logger
- `events.publish` mailbox maxlen=64 静默丢事件 → 满时 warning 一次
- `_continue_plan` 先扣容器 stock 再检查 meal def → 顺序反过来（先验 def 再扣）
- `_continue_plan` 新 ActiveInteraction plan_queue=() → 传 plan_queue[1:]（或 docstring 明示"仅支持 2 步"）
- `Entity.interruptible` 加载了但无人读 → submit rule 4 尊重它（interruptible=False 拒绝被打断）或删除

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 上述五项落地（interruptible 择一：落地语义或删除）
- [ ] 全量 pytest 绿
