# 12 — EntityView.provides 取代 provides:edible 假键

**What to build:** 容器可食标记 `affordances["provides:edible"]` 是 M2 临时标记，把非信号键混进 affordances。EntityView 加 `provides: frozenset[str]` 字段，itemdefs/perception/brain/_hungry_plan/consolidate 改读 provides，M6 前清掉假键。

**Blocked by:** 08

**Status:** ready-for-agent

- [ ] EntityView 增 `provides: frozenset[str]`；build_percept 从实体 provides 填
- [ ] consolidate 与 _hungry_plan 改读 provides（不再读 provides:edible 键）
- [ ] itemdefs 不再写 `provides:edible` 假键进 affordances
- [ ] 全量 pytest 绿
