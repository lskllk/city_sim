# 14 — goap 动作库装配期注入（decide 不读盘）

**What to build:** `goap.hunger_plan()/load_actions()` 在 decide 纯函数内部经 lru_cache 读磁盘、路径 parents[3] 写死。改为动作库在装配期加载，作为参数传进 decide（design M2 原意），测试可注入临时目录。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 动作库装配期加载；decide/hunger_plan 收 actions 参数，不再内部读盘
- [ ] loop/测试装配点注入默认动作库；测试可注入临时 JSON
- [ ] 全量 pytest 绿
