# 气泡（Bubble）—— MVP 实现方案

> 状态：**实现方案（待实现）**。上位：`docs/20260914/mvp.md §3 显示`。
>
> **已拍板：** ① 气泡挂**听者**（内容 = 他刚学到的事实）；② MVP **不可点**（不做"谁说的"详情）。
> 后期语义丰富度再说，先跑通 MVP。
>
> 一句话：**后端决定"谁在什么时刻说什么"，前端只负责画和到点消失。**

---

## 1. 职责划分（沿用铁律）

> **Godot 只渲染，不计算。**

| 层 | 负责 |
|---|---|
| **后端（语义层）** | 决定：谁、哪个 tick、头顶冒什么字；维护生命周期（覆盖 / 冷却 / 过期） |
| **快照** | 纯读导出 `bubble` 字段 |
| **前端（Godot）** | 读快照 → 头顶画 → `now < until` 时淡出。**不写任何一行判断逻辑** |

---

## 2. 气泡是「瞬时事件」，不是「状态」

- 冒一下，存活约 40 ticks，最后 10 ticks 淡出。
- 与现有 `activity`（**当前在做什么**，持续状态）是两回事 → **不复用 `activity` 字段**，另开气泡槽位。
- 新消息覆盖旧气泡（每人同时最多 1 个）。

---

## 3. 数据契约

**`npc/person.py`**（沿用 `current_activity` 的先例：显示态放 `Person`，engine 写、snapshot 读）：

```python
def set_bubble(self, text: str, until_tick: int, kind: str) -> None: ...
@property
def bubble(self) -> tuple[str, int, str] | None: ...   # (text, until, kind)
```

**`gateway/snapshot.py`**（纯读）：

```json
"bubble": {"text": "听说苹果8块", "until": 1234, "kind": "told"}
```

无气泡时为 `null`。

---

## 4. 渲染

### 新建 `godot/scripts/render/bubble_layer.gd`（`Control`）

- 用 `draw_style_box(样式, rect)` + `draw_multiline_string(...)` 直接画 —— **零节点、零对象池**。
- **屏幕坐标 + 固定像素字号**（字号 10）：缩放地图时气泡大小不变、始终清晰。
  与 `entity_layer` 画圆点的策略一致（它也是屏幕坐标 + 最小像素尺寸）。
- **淡出**：`alpha = clamp((until - now) / FADE_TICKS, 0, 1)`，`FADE_TICKS ≈ 10`。
- **裁剪**：屏幕外不画（照抄 `entity_layer` 的 `-32 … size+32` 判定）。
- **位置**：圆点上方（`sp + Vector2(0, -r - gap)`），水平居中。
- **最大宽度 + 自动换行**：`draw_multiline_string` 定宽。

### 样式来源

复用 `npc_visual.tscn` 里那个已做好的 `StyleBoxFlat`（深底 / 圆角 6 / 描边 / 字号 10）。
它是该场景的**内联 sub_resource，跨场景引用不到** → **抽成一个 `.tres`**（如 `godot/resources/bubble.tres`），
让气泡层与 `npc_visual` 共用，样式保持单一真源。

### 为什么不用 `npc_visual.tscn`

- 该场景**根本没被实例化**（渲染层是 immediate-mode `_draw()`），两套范式混用更乱。
- 每个 NPC 一个 `PanelContainer` 节点，NPC 一多就要对象池。

### 为什么独立一层、不塞进 `entity_layer`

`entity_layer` **只管路上的 NPC**（"人在建筑里不画圆点"）。
气泡层独立 → 将来做**店内气泡**时不用改这一层，只要解决"人在店里可见"。

---

## 5. 文案（模板，不接 LLM）

后端一个极简模板表：

```text
told → "听说{名字}{价格}块"       例: "听说苹果8块"
```

- `{名字}` 取自 `config/items/*.json` 的 `name`（`food_apple` → `"苹果"`）—— 已有，不用新建。
- **只说事实，不说判断**：不做"降价了 / 好便宜"这种带评价的措辞（"便宜"需要参照，MVP 没有）。

---

## 6. 生命周期与节流

| 规则 | 值 |
|---|---|
| 每人同时最多 | 1 个（新的覆盖旧的） |
| 冒泡冷却 | 同一人 `BUBBLE_COOLDOWN` ticks 内不重复 |
| 存活 | ~40 ticks（末 10 淡出） |
| 屏幕外 | 不画 |

---

## 7. 时序示例

```text
t=100  玩家把苹果改成 8 块
t=140  顾客A 进店 → perceive → 记忆 price=8, believe=1.0, source=""
       → A 头顶冒  「苹果8块？」            (kind=surprise)
t=200  A 遇到同址的 D → 传递 believe = 8 × 0.95
       → D 头顶冒  「听说苹果8块」           (kind=told)
t=260  A 遇到路人 B → 传递 believe = 8 × 0.55
       → B 头顶冒  「听说苹果8块」           (kind=told)   ← 同一句话，但 B 信得低
```

玩家看到的画面：**一句话在街上走过三个人，并且越传越"虚"**
（"虚"可后续做成气泡更淡 / 字号更小；MVP 先不做）。

---

## 8. 落地清单

| 位置 | 改动 |
|---|---|
| `npc/person.py` | `set_bubble / bubble`（槽位 + 冷却） |
| 语义触发点（`world/engine.py::_notify_due` 等） | 传递成功时给**听者** `set_bubble(...)` |
| `gateway/snapshot.py` | 导出 `bubble`（纯读） |
| `godot/resources/bubble.tres` | 抽出的气泡样式 |
| `godot/scripts/render/bubble_layer.gd` | 新建：屏幕坐标画气泡 |
| `world_canvas.gd` / 场景挂载 | 把气泡层加进渲染顺序 |

---

## 9. 非目标（本期不做）

- 可点查看详情（"谁说的 / 我信几分"）—— 留作侦探线（`semantic_event.md §12`）。
- 语域（persona × mood）、LLM 润色、多行长文。
- 店内气泡（需先解决"顾客进店后可见"，见 `mvp.md §6`）。
- 气泡重要度分级 / 满屏降噪（先靠冷却 + 屏幕裁剪）。
- 气泡历史回看。
