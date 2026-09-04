# 13 — 调参常量入 config（utility + MOVE_TICKS）

**What to build:** `brain.UTILITY_POWER / UTILITY_THRESHOLD`、`loop.MOVE_TICKS=30` 是代码里的调参常量。入 sim.toml `[utility]` 与 `[motion]`，SimConfig 承载；代码引用 config。此为"调参规则化"纪律第一批。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] sim.toml 增 `[utility] power/threshold`、`[motion] move_ticks`；SimConfig 读入
- [ ] brain 用 config 值；loop MOVE_TICKS 用 config 值（删模块常量或留别名）
- [ ] 全量 pytest 绿（golden/soak 数值不变 → 默认值与原常量一致）
