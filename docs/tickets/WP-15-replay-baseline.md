# WP-15 回放/确定性基线重钉

- 状态：todo
- 阶段：Step 3
- 依赖：WP-06（Step 1 已足够；Step 2 全做完后再钉一次）
- 大小：M

## 目标

把“同 seed → 同轨迹”重新钉住，并显式记录 WP-00 的顺序选择带来的变化。

## 改动

- `tests/test_replay.py`：若 WP-00 选 B（顺序执行），复核逐 tick 一致；
  若选 A，确认 commit 队列不引入不确定性。
- `tests/test_behavior_soak.py`：7 天安全网重跑，记录与 main 的差异（预期：仅
  少量因公平性/顺序产生的偏移）。
- `tools/soak*.py` / `tools/scarcity_check.py` 作为人工复核。
- 在 `docs/tickets/README.md` 记录最终基线的 commit。

## 验收

- `pytest -q` 全绿。
- `test_replay.py` 同 seed 两次运行逐 tick 一致。
- soak 无 NPC 异常死亡/卡死（阈值与 main 同量级）。

## 风险

- 这是**行为基线变更**，不是纯重构；要把差异归因写清楚（WP-00 选择 + intake 时序），
  否则以后调参时会把“重构引入的漂移”误当成 bug。
