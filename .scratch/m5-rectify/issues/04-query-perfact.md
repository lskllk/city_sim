# 04 — query 逐事实覆盖 + KB.all_facts() 单一语义源

**What to build:** `KnowledgeBase.query` 现在"整层遮蔽"：overlay 有任意一条命中，原型整层消失。NPC 目击一次冰箱后，原型里所有 contains/sells 对它永久不可见 → S2（冰箱空改道超市）失败。改为 overlay 逐条覆盖同 `(subject, relation, obj)` 的原型事实，不同键并存。`viz/kb_export._all_facts` 自己拼的第二套语义删除，KB 提供 `all_facts()`，viz 只调它。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `query` 按 `(subject, relation, obj)` 键逐条合并：原型（未 tombstone）先入，overlay 同键覆盖、不同键并存；排序 `(-confidence, fact_id)` 稳定
- [ ] `KnowledgeBase.all_facts()` 提供单一语义源；`kb_export` 改调它
- [ ] 新增单测：目击冰箱后 query(contains/sells) 仍能看到原型超市事实
- [ ] S2 剧本（过时冰箱→改道超市）红转绿
- [ ] 全量 pytest 绿
