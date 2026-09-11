# 计划表时间线 · 可视化设计（Plan Timeline Viz）

> 目标：一条横向时间线，等比例铺开当天 1440 分钟；在计划条目处画**原点(节点)**；
> 已走过的时间线**灰色**，还没走的**蓝色**；**悬浮节点**显示该条计划详情。

## 1. 数据来源（gateway snapshot）

每个 NPC 现在带 `plan`（`src/citysim/gateway/snapshot.py::_npc_base` → `Person.plan_snapshot()`）：

```json
{
  "id": "npc_wang",
  "tick": 1140, "day": 1, "hour_f": 19.0, "clock": "19:00",
  "plan": [
    {"id": "s0", "at_tick": 480,  "status": "done",    "intent": "interact", "target": "food_wang"},
    {"id": "s1", "at_tick": 720,  "status": "done",    "intent": "interact", "target": "veggie_1"},
    {"id": "s3", "at_tick": 840,  "status": "dropped", "intent": "interact", "target": "tv_wang"},
    {"id": "s4", "at_tick": 1080, "status": "done",    "intent": "interact", "target": "food_wang"},
    {"id": "s5", "at_tick": 1080, "status": "active",  "intent": "interact", "target": "tv_wang"},
    {"id": "s6", "at_tick": 1260, "status": "pending", "intent": "interact", "target": "bed_wang"}
  ],
  "active": {"entity": "tv_wang", "remaining": 120, "total": 240},
  "travel": null
}
```

字段说明：
- `at_tick`：绝对 tick（0=第 1 天 0:00）。
- `status`：`pending`（未到/未做）· `active`（正在执行）· `done`（自然完成）· `dropped`（被截止跳过/失败）。
- `intent`：`interact`（去物体）/ `move_to`（纯移动）。
- `target`：物体 id 或地点 id。

## 2. 坐标映射（等比例）

```
day_start = (tick // 1440) * 1440          # 当天 0:00 的绝对 tick
day_end   = day_start + 1440
x(t)      = x0 + (t - day_start) / 1440 * W     # W = 时间线像素宽
```

`t` 落在 `[day_start, day_end)`, 越界(跨天计划)时 clamp 到端点并画 `◀/▶` 小箭头。

时间刻度：每 3 小时（180 tick）一格，标注 `00 03 06 09 12 15 18 21`。

```
x0                                                               x0+W
│───────┬───────┬───────┬───────┬───────┬───────┬───────┬───────│
00      03      06      09      12      15      18      21      24
```

## 3. 三条线 + 节点

```
                 ┌ now(竖线)
                 ▼
灰(已走过) ━━━━━━━━━━━━━━━━━━●━━━━━━━━●━━━━━━━━━━━┿━━━━━━━━●━━━━━━━
蓝(还没走)                                    ╰──────────────┘
   ▲            ▲         ▲            ▲              ▲
 08:00吃      12:00买菜  14:00电视   18:00吃/电视   21:00睡
 (done 灰点)  (done 灰点) (dropped 灰叉) (active 高亮) (pending 蓝点)
```

- **底轨**：整条浅灰线（当天全长）。
- **已走过段** `[day_start, now]`：**灰色**实线（粗细 ≥2px）。
- **剩余段** `[now, day_end]`：**蓝色**实线。
- **now 标记**：一条竖线 + 游标点，随 tick 移动。
- **节点**：在每个 `at_tick` 画圆点，按 `status` 区分：

| status | 颜色 | 形状 | 说明 |
|---|---|---|---|
| `done` | 灰 `#9AA0A6` | 实心圆 | 已完成 |
| `active` | 橙/亮蓝 `#FFB300` | 实心圆 + 外圈脉冲 | 正在执行 |
| `pending` | 蓝 `#1E88E5` | 空心圆(描边) | 还没到 |
| `dropped` | 红灰 `#C0392B` | 叉 `✕` | 被截止/失败跳过 |

- 可选：`active` 节点到 `remaining` 结束处画一小段**半透明进度条**（`remaining/total`）。

## 4. 悬浮交互（hover）

鼠标进入节点半径（如 8px）→ 显示 tooltip：

```
┌──────────────────────────┐
│ 12:00  去 菜摊            │
│ 意图: interact            │
│ 目标: veggie_1            │
│ 状态: 已完成              │
└──────────────────────────┘
```

- 标题：`HH:MM` + 动词（interact→“去/做”，move_to→“前往”）。
- 正文：意图、目标 id、状态（中文映射）。
- 位置：节点上方，超出右边界则翻到左侧。
- 同一时刻多条（同刻串行）：节点纵向堆叠 1~2 层，或用小数字角标 `2`。

## 5. 多 NPC 布局

一天一条时间线；每个 NPC 一行，共享同一条时间轴（便于对比）：

```
王二  ━━━━━━━●━━━━●━━━✕━━━━━━━━━┿━━●━━━━━━●     (灰/蓝 + 节点)
李四  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━
     00    03    06    09    12    15    18  now ←轴
```

侧栏可复用现有 Inspector：选中 NPC → 高亮其行 + 展开该 NPC 的 `plan` 列表（文本）。

## 6. 边界情况

- **空计划**：只画底轨 + now 游标 + 文案“无计划”，不报错。
- **跨天条目**（`at_tick` 超出当天）：clamp 到端点并加箭头标记。
- **计划被整表替换**（0:00 夜间重规划）：`tick` 回绕到 0 时重置 `day_start`，整条重绘。
- **dropped 后同刻 successor**：两节点会重叠，需按 `id` 稳定排序后 >1 时错位 6px。
- **与当前活动的关系**：`active` 节点即 `active.entity`；若正在 `travel`，可在去往的 `dest` 上画一个“在途”游标。

## 7. Godot 落地建议

- 用 `Control` + `_draw()`（或 `Node2D`）自绘，避免每帧建节点：
  - `_draw`: 先画底轨/灰段/蓝段，再画 now 竖线，再遍历 `plan` 画节点。
  - `_process`: 从 `Store` 读最新 `npc.plan` 与 `tick`（只读镜像，遵守 Godot 只渲染铁律）。
- 命中测试自己做（节点圆心 + 半径），命中时用 `Tooltip`/`Panel` 显示。
- 配色常量集中一处：
  ```
  ELAPSED = Color("#9AA0A6")  # 灰
  REMAIN  = Color("#1E88E5")  # 蓝
  DONE    = Color("#9AA0A6")
  ACTIVE  = Color("#FFB300")
  PENDING = Color("#1E88E5")
  DROP    = Color("#C0392B")
  ```
- 数据已随 snapshot 每帧下发（`npc.plan`），前端**不计算** simulation，只做时间→像素映射。

## 8. 验收

- [ ] 一天 1440 分钟等比例；`now` 游标位置 = `tick` 映射。
- [ ] 灰/蓝分界严格在 `now`。
- [ ] 每个 `plan` 条目一个节点，位置 = `at_tick` 映射。
- [ ] 悬浮节点出 tooltip（时间/意图/目标/状态）。
- [ ] `dropped` 条目可见（叉），`active` 高亮。
- [ ] 夜间重规划后整条刷新。
