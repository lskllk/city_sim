# 11 — 食物 obj 归一化为类别（清 _EDIBLE_OBJS）

**What to build:** `brain._EDIBLE_OBJS = ("edible","meal","meal_simple")` 是领域硬编码回流；obj 若用别名/具体品名（如 sells obj="burger"）KB 移动就失效。让 inject/learn 时把食物 obj 归一化为类别（is_a 关系或直接存 "edible"），brain 只认类别。

**Blocked by:** 07

**Status:** ready-for-agent

- [ ] 定义归一规则：learn/inject 到食物类 obj 统一（含 is_a 支持），brain 去掉 `_EDIBLE_OBJS` 只认类别
- [ ] 既有 sells meal_simple / contains edible 语义不变（别名映射到类别）
- [ ] 新增单测：sells obj 为具体品名时 KB 移动仍触发
- [ ] 全量 pytest 绿
