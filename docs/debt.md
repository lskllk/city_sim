# M5 前置记账（2026-09-04，不阻止开工）

## 5a. 效果 op 集合需要版本化
- 现状 op 集合已锁定 6 个：`set_signal / add_signal / clear_pending /
  add_pending / spawn_item / consume_self`。
- 若 M5 及以后要加新 op（如知识库侧的持久化效应），改动面：`effects.py`
  注册+实现、`config/items/*.json` 效果表（dict，向后兼容）、既有 golden
  （向后兼容则仍绿）。
- TODO：op 集合版本化；将来添 op 时 `schema_version` bump（为存档兼容埋伏笔）。
- M5 暂不动。

## 5b. 物品配置 schema 未版本化
- `config/items/*.json` 的活 schema 在 `world/item_defs.py::ItemDef`。
- 未来若开放"玩家自定义物品"（M9+ 社区功能）：ItemDef 加
  `schema_version: int = 1`；加载校验版本号，不匹配拒绝 + 提示迁移脚本。
- 现在无需；开放用户编辑前必需。M5 暂不动。

## 附：交互完成时序契约（隐式，有 golden 兜底）
- "回收必须在 `interaction_done` 发布之后"：当前由 test_m4_equivalence 的
  golden 数据隐性保护（顺序弄反 golden diff 即红）。
- 已加显式单元锁：tests/test_interaction_completeness_contract.py
  （事件回调时 entity 尚存 → 本 tick 结束即消失）。
- M6/M7 动 interaction 完成/回收路径时以此为准。
