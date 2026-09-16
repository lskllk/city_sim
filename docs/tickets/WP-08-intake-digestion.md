# WP-08 `Grant` + `Person._intake` 消化循环

- 状态：done
- 阶段：Step 2
- 依赖：WP-07
- 大小：M

## 目标

信号数学从 world 搬进 NPC：NPC 拿到 `Grant` 后**自己**逐 tick 消化。

## 改动

`npc/person.py`：

```python
self._intake: list[Grant] = []

def step(...) 或 heartbeat(...):
    # ① 消费 intake
    for g in list(self._intake):
        self.add_signal(g.signal, g.value / max(1, g.duration_ticks))
        g.remaining -= 1
        if g.remaining <= 0:
            self._finish_intake(g)    # 应用 on_done; 从 list 移除; 通知 world consume
    # ② 代谢 ③ hp ④ pending   (顺序与现在 engine 的 heartbeat 保持)
```

- `duration_ticks` 计数用 `Grant` 的副本（frozen 的话包一层可变态，或改用 `_ActiveGrant`）。
- 完成时调 `port.consume(self.person_id, g.handle)`（world 侧扣 stock / 回收）。

## 验收

- 单测：手搓 `Intake` 进 `_intake`，跑 N tick 后 `hunger` 增加 `value`（clamp 1.0）。
- 单测：`value=20` 的 Grant → 信号封顶在 1.0（信号层硬限位，与打分封顶呼应）。

## 风险

- **tick 顺序**：现在 engine 顺序是 heartbeat→interaction.step→decide。搬进来后
  消化必须在 `decide` 之前，否则一 tick 的观感变了。
- `Grant` 是 frozen，需要可变进度——用 `dataclasses.replace` 或单独的运行态结构。
