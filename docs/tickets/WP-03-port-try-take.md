# WP-03 `try_take`（Interact：校验 + claim）

- 状态：done
- 阶段：Step 1
- 依赖：WP-01
- 大小：M

## 目标

把 `engine._apply` 的 `Interact` 分支搬成端口动词。本票**只搬校验与占位**，
信号仍由 `InteractionSystem.step` 应用（Step 2 才拆）。

## 改动

`WorldPortImpl.try_take(pid, entity_id) -> Grant | Deny`：

1. 实体存在 / `stock != 0` / `claimable_by(pid)` / 同 region（现在 `submit` 里那几
   条 rule）。
2. “在售商品·需购买”兜底：`price>0 and owner!=pid and not free_use` → `Deny`。
   （**例外**：住所授权 / 公共无主 / 本公司店员 → 放行。）
3. `interaction.submit(...)` 登记。
4. 返回 `Grant`（本票先填 `handle=entity_id`、signal/value/duration 从 affordances
   取；`pending/on_done` 留空，WP-10 再编译）。

`engine._apply` 的 `Interact` 分支改为调 `try_take`。

## 验收

- `tests/test_household.py`（授权人免费吃、引擎不拦）仍绿。
- `tests/test_multi_use.py`（容量=stock）仍绿。
- 新单测：非授权人 Interact 在售货 → `Deny("在售商品·需购买")`。

## 风险

- 失败路径现在会调 `npc.on_failure`（world 反写 NPC），本票**暂时保留**，
  WP-05 再改成 NPC 自处理。
- 同 target 已在交互 → 应返回 `Grant` 且不重置进度（沿用 `submit` 现语义）。
