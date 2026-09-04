# 03 — consume_self 时序修复（回收唯一化）

**What to build:** `effects.consume_self` 现在 stock−1 归零立即 `world.entities.pop`，发生在 `_complete` 发布 `interaction_done` 之前——违反"事件先于回收"时序契约；且若某物品既带 consumable tag 又写 consume_self 会双扣。让 op 只扣库存，回收只允许在 `_complete` 第 5 步统一发生。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] `consume_self` 只 `stock−1`，删除 pop
- [ ] 回收唯一路径 = `_complete` 第 5 步（事件发布后，空消耗品统一 pop）
- [ ] 显式时序测试：interaction_done 事件回调时实体仍可解析 tags；无 consumable+consume_self 双扣
- [ ] 全量 pytest 绿
