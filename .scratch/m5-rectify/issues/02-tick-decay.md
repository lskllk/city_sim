# 02 — tick 语义理顺 + 半衰期默认值统一

**What to build:** learn 记的 tick 现在是"上次 decay 的 tick"（decay 兼任时钟），所有当天学到的事实 tick 都等于当天 0 点。让 learn 显式收 tick，decay 不再兼任时钟；半衰期删方法默认值强制传参，消除 10080/20160 不一致误导。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] `learn(..., tick=...)` 显式参数，`tick_learned` 记真实学习 tick；`decay` 不再更新 `_now` 作为学习时钟
- [ ] 所有调用方（consolidate / 传闻 / 测试注入）显式传 tick
- [ ] `decay(half_life_ticks)` 删默认值强制传；运行时统一 10080（config）
- [ ] 新增单测：同一天不同时刻 learn 的两条事实 tick_learned 不同
- [ ] 全量 pytest 绿
