# 06 — TOLD 起源引用 + 跨 NPC 溯源链

**What to build:** TOLD 来源 `ref=(speaker,)` 丢掉了 speaker 那条 fact 的 id，S3 溯源只能到"李四说的"。改为携带起源 fact 引用，让 `export_trace_chain` 能输出可跨 NPC 拼接直到最初 OBSERVED 的链。删除 `Fact.root_sources` 死代码。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] 传闻 learn 时 `ref=(speaker, "f:{origin_fact_id}")`
- [ ] `export_trace_chain` 对跨 NPC 引用输出占位/拼接信息（本地解析不到也不丢起源 id）
- [ ] 删除 `Fact.root_sources` 死代码
- [ ] S3 溯源测试：任取一个知道者，链能指向最初唯一 OBSERVED 根
- [ ] 全量 pytest 绿
