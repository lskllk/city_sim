# 10 — move_to 前释放旧 active（claim 不悬挂）

**What to build:** loop 里 move_to 直接进 `systems.travel` 绕过 InteractionSystem；`_continue_plan` 改排程等边界下理论上存在 claim 悬挂。在 move_to 分支前做一次 idle 语义的 release，保证 `claimed_by` 不残留。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] move_to 提交前调 release（cancel 语义），实体 claimed_by 清空
- [ ] 新增/复用到点即走场景断言：无 NPC 残留 claimed_by
- [ ] 全量 pytest 绿
