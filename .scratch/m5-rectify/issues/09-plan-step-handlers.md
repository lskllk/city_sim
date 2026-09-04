# 09 — 取食链动作名硬编码清除（PLAN_STEP_HANDLERS + exec 绑定）

**What to build:** `interaction._continue_plan` 里 `if act.plan_queue[0] == "eat"` 是领域硬编码，JSON 改个动作名取食链就静默断。做 `PLAN_STEP_HANDLERS: dict[str, Callable]`，动作 JSON 加 `exec` 字段绑定实现。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] `config/actions/*.json` 增 `exec` 字段；`goap` 动作对象带 handler 名
- [ ] `interaction` 用 PLAN_STEP_HANDLERS 分派，去掉 `"eat"` 字面量分支
- [ ] 保留 take_from_container→spawn meal→eat 现有链语义；改动作名不断链
- [ ] 全量 pytest 绿
