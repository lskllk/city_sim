# 07 — learn 改 upsert + overlay/tombstone 有界断言

**What to build:** learn 每次都生成新 fact，没有 upsert；refute→relearn 让 id 反复翻新、tombstones 无界累积（M5 版"实体泄漏"）。改为同 `(subject, relation, obj)` 已存在则替换（取更高 confidence、更新 tick、保留 id），并加有界断言。

**Blocked by:** 01, 02

**Status:** ready-for-agent

- [ ] `learn` upsert：同键已存在 → 替换（更高 conf / 刷新 tick），不新增 id；已 tombstone 的原型 id 不复活
- [ ] tombstone 仅在原型/overlay 被 refute 时累积，有界（随 upsert 键稳定）
- [ ] 宏观/soak 加 `len(overlay) <= 实体数 × 5` 断言（回归网）
- [ ] 新增单测：同键重复 learn 后 overlay 条数不涨
- [ ] 全量 pytest 绿
