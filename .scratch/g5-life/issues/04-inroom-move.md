# 04 — 房间内走位与落座

**What to build:** "谁在用什么"变成空间事实——NPC 朝目标物件移动并贴住, 交互带进度环, 失败折返。最大"活起来"收益。

**Blocked by:** 01, 03

**Status:** ready-for-agent

- [ ] snapshot 实体增 `slot_index`(房间内按 id 定序)
- [ ] active 非空 → 600ms 缓动到该物件槽下方并贴住, 头顶进度环(remaining/total)
- [ ] 提交失败(intent_failed) → 走一半停 + 红 ! 后回待机槽
- [ ] 完成后缓动回待机槽
