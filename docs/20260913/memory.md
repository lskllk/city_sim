# Memory —— L0 物化视图 + L1 情景日志

> 状态：设计稿（未实现）。上位文档：`docs/20260913/mind.md`
>
> 决定：**保留 `MemItem`（L0），新增 `Episode` 环形日志（L1）；写入策略 = 变化 + 白名单。**

---

## 0. 一句话

> **`MemItem` 是给 `decide` 用的物化视图；`Episode` 是真相日志。`decide` 一行都不用改。**

---

## 1. 现在的 `MemItem` 做不到什么

用本项目的场景举例：

| 做不到 | 原因 |
|---|---|
| 「将信将疑」——两人告知两个价格 | 一行一个实体、后写覆盖，只能留最后一个 |
| 「上次来还没这个货架」 | 没有时间序列，只有 `last_seen` |
| 「王哥骗过我」 | 没有"经历"这一概念；`Mind` 里只有一个数字，解释不了 |
| 「李四说的我信，王哥说的我不信」 | `believe` 是单标量，不区分来源 |

---

## 2. 决定：L0 + L1

三条原则：

1. **不替换 `MemItem`。** 它继续存在、继续增量更新（就是现在的 `note()` / `perceive_into`）。
2. **`Episode` 只追加，不参与决策打分。** 它是证据与解释源。
3. **决策复杂度被控制住。** 不让 `decide` 变成历史折叠器；将来真要判"上次/变化"，
   加一个受限接口 `mem.history(subject, n=3)`，而不是把 fold 塞进评分函数。

白送的好处：**「关于人的记忆」不用单独开表了**——按 `subject` 过滤 `Episode` 就是。
关系数字（`Mind`）+ `Episode` 证据，正好对上 `mind.md` 里"数值算便宜、证据是真相"。

---

## 3. 数据模型

```python
Episode:
    tick: int
    kind: str          # 白名单，见 §4
    subject: str       # item_id / npc_id / org_id / location_id
    field: str         # 变了哪个字段（"" = 非字段类事件）
    old: Any
    new: Any
    source: str        # "" = 自己看到的；否则 npc_id（谁告诉我的）
    valence: float     # 0 = 无情绪；非 0 = 这件事当时让我起了反应
```

存储：`collections.deque(maxlen=N)`，N = 64~128。
（`core/ring.py::RingBuffer` 也可用，需补一个 `items()` 只读遍历。）

---

## 4. 写入策略：变化 + 白名单

**两个条件同时满足才写一条。**

### (a) 变化

字段值**真的变了**才写。`perceive_into` 每 tick 全量遍历可见实体，
"我又看了一眼苹果还在那儿"不产生任何信息量 → 不写。

### (d) 白名单 `kind`

```text
observed      感知到变化（价格 / 库存 / 归属 / 位置 变了）
told          别人告诉我的（source 必填）
bought        成交
taken/placed  进背包 / 放回世界
denied        被拒 / 失败（含原因）
contradicted  与记忆冲突（→ 触发 DOUBT 与 verify）
```

**明确不记**：无变化的重复感知、纯位移、每 tick 的数值微抖。

---

## 5. 为什么好实现

写入点是**集中的**：

| 位置 | 说明 |
|---|---|
| `npc/brain.py::perceive_into()` | 感知写入（`mem.set` / `mem.update`） |
| `npc/person.py::note()` | 所有其它写入的总入口（成交/事件/失败） |
| `npc/brain.py::forget()` | 遗忘（可选，见 §6） |

所以只要在这两处后面挂一个 `_append_episode(...)`，L1 就通了。要点：

- **`decide` 不改**，`MemItem` 结构不改，评分不变。
- **无 rng**，确定性不受影响（`test_replay.py` 不受影响）。
- `gateway/snapshot.py` 加一段只读导出（只导最近 k 条）。

**工作量评估：小。** 真正的成本不在实现，而在 §4 的判据调优。

---

## 6. 坑

1. **容量**：总分 = 每人 N × NPC 数。N 先定 64，别一上来给 512。
2. **变化检测必须廉价**：先比字段再决定写，不要在 `perceive_into` 里做深比较 / 字符串格式化。
3. **遗忘不删 Episode**（`brain.forget` 只衰减 `MemItem`）——让环形缓冲自然淘汰，
   否则会长出两套淘汰逻辑。
4. **快照别全量导**：只导最近 k 条，否则 WS 包体随 NPC 数线性膨胀。
5. **不要让 `decide` 依赖 Episode**（§2 原则 3）。

---

## 7. 暂缓

| 层 | 内容 | 何时做 |
|---|---|---|
| **L2 情景派生** | 从 Episode 派「经历」：「3 天前王哥说降价 → 没降」 | 做气泡 / DOUBT / 关系解释时 |
| **L3 文本语义** | 自然语言摘要，可被 LLM 查询 | 未定，优先级低于 L2 |
| `mem.history(subject, n)` | 受限查询接口 | 真的需要"上次/变化"类判断时 |

---

## 8. 验收

1. **同一物品被两个来源告知两个价格** → `Episode` 里两条都在（带各自 `source`）；
   `MemItem` 里仍只有一行，且**能解释这一行为什么**。
2. 「上次来还没这个货架」可由 `Episode` 推出（时间序列存在）。
3. `test_replay.py` 仍然通过（确定性未被破坏）。
4. 连续观察同一批不动实体，跑一整天，`Episode` 条数为 0。
