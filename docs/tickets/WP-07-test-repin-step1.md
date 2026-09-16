# WP-07 Step 1 调用签名重钉（测试）

- 状态：todo
- 阶段：Step 1
- 依赖：WP-06
- 大小：M

## 目标

把因接口变化而红的测试改到新签名，**不改断言语义**（行为应等价，除 WP-00 的公平性）。

## 受影响的测试

| 文件 | 原因 |
|---|---|
| `tests/test_multi_use.py` | 直调 `interaction.submit` |
| `tests/test_access.py` | 调 `engine._apply` |
| `tests/test_household.py` | 调 `engine._apply`、`npc.decide` |
| `tests/test_decide_single_track.py` | `npc.decide`（应仍可用） |
| `tests/test_hp_three_states.py` | `npc.decide`（应仍可用） |
| `tests/test_contention_failure.py` | `on_failure` 语义（调用方变了） |

## 验收

- `pytest -q` 全绿。
- 不新增 `xfail`/`skip` 来掩盖行为差异（WP-00 选 A 导致公平性变化时，改断言并注释原因）。

## 风险

- `interaction.submit` 在 Step 2（WP-09）还会再变一次；本票先按 Step 1 的最小改动重钉。
