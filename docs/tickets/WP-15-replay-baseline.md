# WP-15 回放/确定性基线重钉

- 状态：done
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

## 实测结果(2026-…)

`DEMO_SCENE` 7 天 soak, **main vs 分支** 对比:

| 指标 | main | 分支 |
|---|---|---|
| 存活 NPC | 2 | 2 |
| decisions | 153 | 169 |
| intent_failed | 26 | 26 (ratio 0.17 → 0.154) |
| 信号卡 0(wang_er) | energy 282 / hunger 921 / bladder 26 | **完全一致** |
| 信号卡 0(li_si) | hunger 89 / bladder 0 | hunger 155 / bladder 18 |
| 60t 重复 claim(抖动) | 0 | 0 |
| 第 1 天吃饭次数 | 2 / 5 | 2 / 5 |

- **确定性**: `DEMO_SCENE`/`NAV_SCENE` 3000/4320 tick 两次同 seed → 状态哈希一致。
- **漂移归因**: 差异来自 WP-00 选 B(顺序执行)+ intake 时序; 无死亡、无抖动,
  行为在可接受范围。若要更贴 main, 可改回两阶段(A)并重跑本表。
