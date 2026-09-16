# WP-05 `Person.step(port)` + Deny 自处理

- 状态：done
- 阶段：Step 1
- 依赖：WP-01、WP-00
- 大小：M

## 目标

把“world 推 Percept + 返回 Decision 给 engine 执行”翻转为“NPC 主动观察 + 主动请求”。

## 改动

`npc/person.py`：

```python
def step(self, port, cfg, can_preempt=True):
    self.perceive(port.observe(self.person_id), self._tick)   # 主动拉
    d = self.decide(...)
    intent = d.intent
    if isinstance(intent, MoveTo):   a = port.try_move(self.person_id, intent.dest)
    elif isinstance(intent, Interact):  r = port.try_take(self.person_id, intent.target_id)
    elif isinstance(intent, Buy):    a = port.try_buy(self.person_id, intent.item_id, intent.qty)
    else: return d
    if 失败: self._on_denied(...)     # ← on_failure 逻辑搬来, 调用方变成自己
    return d
```

- `process(percept, cfg, can_preempt)` 保留为兼容壳（或删；见 WP-07 重钉），
  内部改为 `port` 版。
- `on_failure` 逻辑（删记忆/冷却/写失败日志/放弃 goal/`denied` 气泡）**原样保留**，
  只是调用点从 `engine` / `interaction._fail` 变成 `Person`。

## 验收

- 单测：NPC 站在在售货前决定 `Interact` → `try_take` 返回 `Deny` → NPC 自己
  写冷却、放弃 goal、记失败日志。
- `tests/test_decide_single_track.py` 里 `npc.decide` 直调路径不受影响。

## 风险

- `_on_denied` 与原 `on_failure` 参数对齐（`why`、`retry_ticks`）。
- WP-00 若选 A（两阶段），这里拿到的是“请求已记”，失败回传是异步的 → 需要
  回调；选 B 则同步。
