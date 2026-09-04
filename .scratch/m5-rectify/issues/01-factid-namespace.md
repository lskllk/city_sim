# 01 — fact_id 命名空间分离（原型 a: / overlay o:）

**What to build:** 消除原型与 overlay 之间的 fact_id 碰撞。现在原型第一条 `fridge|contains|1` 与 NPC 首次目击 learn 生成的 `fridge|contains|1` 同 id，`refute` 会同时 tombstone 原型 + 删掉刚学的事实，`fact()` 串库。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] `_gen_fact_id` 区分命名空间：原型 `a:{subject}|{relation}|{n}`，overlay `o:{subject}|{relation}|{seq}`
- [ ] `refute` 只 tombstone 被指的那一条（原型/overlay 不互串）；`fact()` 查询不串
- [ ] `trace()` 的 `f:` 前缀约定随命名空间统一
- [ ] 既有 overlay 覆盖 / tombstone / refute / decay / stale_knowledge 单测保持绿
- [ ] 全量 pytest 绿；行为网（soak/稀缺/golden）零回归
