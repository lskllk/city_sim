# docs 文档约定

## 1. 两类文档

| 类型 | 位置 | 含义 | 可否移动 |
|---|---|---|---|
| **常青（evergreen）** | `docs/` 根目录 | 规则 / 契约 / 愿景。长期有效 | **不要动**——被代码与测试引用 |
| **按日归档（dated）** | `docs/<YYYYMMDD>/` | 某次讨论产出的设计稿 | 随意，日期即版本 |

## 2. 目录结构

```text
docs/
  README.md              本文件
  Vision.md              长期愿景（常青）
  naming.md              命名规则（常青；tests/test_naming.py 强制）
  plan_timeline_viz.md   计划表时间线可视化（常青；plan_timeline.gd 引用）
  20260910/
    requirements.md      需求拆解 + 设计草案
  20260913/
    semantic_event.md    NPC 语义层（气泡 / 传播载体）
    mind.md              情绪 / 关系 / 传播 MVP
    memory.md            记忆：L0 物化视图 + L1 情景日志
    plan.md              计划表：角色日程模板 + 自由块（MVP）
```

## 3. 命名规则

- 目录：`YYYYMMDD`，如 `20260913`。
- 文件：小写 `snake_case` ASCII，如 `semantic_event.md`、`mind.md`。
- **日期不进文件名**——日期已经在目录上。
- 中文标题写在文件内，不写进文件名。

## 4. 引用写法

- 常青：`docs/naming.md`
- 归档：`docs/20260913/mind.md`
- 跨文档引用带小节号：`docs/20260913/mind.md §7.2`

## 5. 已知悬空引用（待清理）

以下文件被代码引用但**已删除**（见 commit `8c9dd2b`），引用未同步更新：

| 引用方 | 悬空目标 |
|---|---|
| `godot/scripts/protocol/protocol.gd` | `docs/observation_contract.md` |
| `godot/scripts/shared/building_style.gd` | `docs/building_abstraction.md` |
| `src/citysim/world/buildings.py` | `docs/building_abstraction.md` |
| `docs/20260910/requirements.md` | `docs/task0XX.md` |
