# 05 — 传闻挂讲话者重评 tick + 置信/新近加权选样

**What to build:** `_rumor_pass` 现在每 tick 对每地点跑 O(N²)，p=0.1 是"每对每分钟 10%"→ 同地数人一小时内必传遍，S3 曲线是阶跃而非 S 形；且 `top_overlay_fact` 恒取 confidence 最高者，OBSERVED 1.0 永远压过 TOLD 0.8 → 假消息几乎无法二次传播（S4 传不出去）。改为：① 只在讲话者重评 tick 触发（成本 O(due)）；② 选择按 confidence 加权或优先近期（tick_learned 大）。

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] 传闻触发挂进 due 决策循环（讲话者本次重评 tick 才可能开口）
- [ ] 选样改为加权/近期优先；假消息（新近）能压过陈旧 OBSERVED 传播
- [ ] S3 扩散不再纯阶跃（可测的中间态）；S4 假消息可二次传播
- [ ] 全量 pytest 绿
