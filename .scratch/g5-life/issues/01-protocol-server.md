# 01 — 协议/服务端基础修复（单一事件源 + act_class + 默认 full）

**What to build:** 让 M5 成果在 UI 上"显形"：事件对象化(保留 payload 结构)、每场景单次挂载、默认开知识库、快照给活动类别与 tps。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 事件单一源：attach 时同时把原始 Event 对象/结构化 dict 追加到 `systems.ui_events`；drain_log 改从它读(payload 保持 dict，audience 是数组)，log_lines 保留给回放
- [ ] attach 幂等(每场景只挂一次)，去掉场景构造内部重复 attach
- [ ] 默认 `kb_mode="full", tell_p=0.1`；demo 场景真正装上 KB
- [ ] snapshot npc 增服务端推导 `act_class`(按 active 实体 tags; travel→move, 否则 idle)；快照增 `tps`
- [ ] 场景注入事实 id 走 `a:`/`o:` 命名空间
- [ ] 全量 pytest 绿、回放/golden 不变
